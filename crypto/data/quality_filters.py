"""Data quality filters for candle validation."""
import logging
from dataclasses import dataclass
from typing import Optional

from data.storage.models import Candle


logger = logging.getLogger("trades")
error_logger = logging.getLogger("errors")


@dataclass
class ValidationResult:
    """Result of candle validation."""
    valid: bool
    reason: Optional[str] = None
    requires_warmup: bool = False


class CandleValidator:
    """
    Validates incoming candle data for quality issues.

    Detects:
    - Flash crashes (>50% move in one candle)
    - Zero volume candles
    - Data gaps (>5 minutes between candles)
    """

    FLASH_CRASH_THRESHOLD = 0.50  # 50% move
    MAX_GAP_MS = 5 * 60 * 1000    # 5 minutes in milliseconds

    def __init__(self):
        self._last_candles: dict[str, Candle] = {}

    def validate(self, candle: Candle) -> ValidationResult:
        """
        Validate a candle against quality rules.

        Args:
            candle: The candle to validate

        Returns:
            ValidationResult with validity and reason
        """
        # 1. Check zero volume -> invalid
        if candle.volume == 0:
            logger.warning(
                f"Zero volume candle filtered for {candle.symbol} at {candle.timestamp}"
            )
            return ValidationResult(
                valid=False,
                reason="Zero volume candle"
            )

        # 2. If prev candle exists for this symbol
        prev_candle = self._last_candles.get(candle.symbol)
        if prev_candle:
            # a. Check flash crash (>50% price change) -> invalid, log error
            price_change = abs(candle.close - prev_candle.close) / prev_candle.close
            if price_change > self.FLASH_CRASH_THRESHOLD:
                error_logger.error(
                    f"Flash crash detected for {candle.symbol}: "
                    f"{price_change:.2%} move from {prev_candle.close} to {candle.close}"
                )
                return ValidationResult(
                    valid=False,
                    reason=f"Flash crash detected: {price_change:.2%} move"
                )

            # b. Check data gap (>5 min) -> valid but requires_warmup=True
            time_gap = candle.timestamp - prev_candle.timestamp
            if time_gap > self.MAX_GAP_MS:
                logger.warning(
                    f"Data gap detected for {candle.symbol}: "
                    f"{time_gap / 1000:.0f}s between candles"
                )
                # Update last candle before returning
                self._last_candles[candle.symbol] = candle
                return ValidationResult(
                    valid=True,
                    reason=f"Data gap: {time_gap / 1000:.0f}s",
                    requires_warmup=True
                )

        # 3. Update _last_candles[symbol]
        self._last_candles[candle.symbol] = candle

        # 4. Return ValidationResult
        return ValidationResult(valid=True)

    def reset(self, symbol: Optional[str] = None) -> None:
        """Reset validator state (e.g., after warmup)."""
        if symbol:
            self._last_candles.pop(symbol, None)
        else:
            self._last_candles.clear()
