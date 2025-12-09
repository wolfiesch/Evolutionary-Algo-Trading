"""Data quality filters for candle validation."""
import logging
import time
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
    - Clock sync issues (future timestamps, excessive clock drift, non-monotonic timestamps)
    - Zero volume candles
    - Volume spike anomalies (>10x average volume)
    - Wick anomalies (>5x typical high-low range)
    - Flash crashes (>50% price move between candles)
    - Data gaps (>5 minutes between candles)
    """

    FLASH_CRASH_THRESHOLD = 0.50  # 50% move
    MIN_GAP_MS = 5 * 60 * 1000    # 5 minutes - trigger warmup
    MAX_GAP_MS = 60 * 60 * 1000   # 1 hour - force full reset
    MAX_FUTURE_DRIFT_MS = 60 * 1000  # 60 seconds - allow some clock skew
    MAX_PAST_DRIFT_MS = 365 * 24 * 60 * 60 * 1000  # 1 year - reject very old data
    VOLUME_SPIKE_THRESHOLD = 10.0  # 10x average volume
    VOLUME_HISTORY_SIZE = 20  # Track last 20 candles for volume baseline
    WICK_ANOMALY_THRESHOLD = 5.0  # 5x typical high-low range
    RANGE_HISTORY_SIZE = 20  # Track last 20 candles for range baseline

    def __init__(self):
        self._last_candles: dict[str, Candle] = {}
        self._volume_history: dict[str, list[float]] = {}  # symbol -> recent volumes
        self._range_history: dict[str, list[float]] = {}  # symbol -> recent high-low ranges

    def validate(self, candle: Candle) -> ValidationResult:
        """
        Validate a candle against quality rules.

        Args:
            candle: The candle to validate

        Returns:
            ValidationResult with validity and reason
        """
        # 0. Clock sync validation - ensure timestamps are UTC and reasonable
        current_time_ms = int(time.time() * 1000)
        time_diff = candle.timestamp - current_time_ms

        # Reject candles from the future (allowing small clock skew)
        if time_diff > self.MAX_FUTURE_DRIFT_MS:
            error_logger.error(
                f"Clock sync error for {candle.symbol}: "
                f"Candle timestamp {time_diff / 1000:.0f}s in the future"
            )
            return ValidationResult(
                valid=False,
                reason=f"Future timestamp: {time_diff / 1000:.0f}s ahead"
            )

        # Reject very old candles (>1 year old)
        if time_diff < -self.MAX_PAST_DRIFT_MS:
            error_logger.error(
                f"Clock sync error for {candle.symbol}: "
                f"Candle timestamp {abs(time_diff) / (1000 * 60 * 60 * 24):.0f} days old"
            )
            return ValidationResult(
                valid=False,
                reason=f"Timestamp too old: {abs(time_diff) / (1000 * 60 * 60 * 24):.0f} days"
            )

        # Check timestamp monotonicity (if we have a previous candle)
        prev_candle = self._last_candles.get(candle.symbol)
        if prev_candle and candle.timestamp <= prev_candle.timestamp:
            logger.warning(
                f"Non-monotonic timestamp for {candle.symbol}: "
                f"current={candle.timestamp}, prev={prev_candle.timestamp}"
            )
            return ValidationResult(
                valid=False,
                reason="Non-monotonic timestamp (not increasing)"
            )

        # 1. Check zero volume -> invalid
        if candle.volume == 0:
            logger.warning(
                f"Zero volume candle filtered for {candle.symbol} at {candle.timestamp}"
            )
            return ValidationResult(
                valid=False,
                reason="Zero volume candle"
            )

        # 1b. Check volume spike anomalies
        if candle.symbol in self._volume_history:
            volume_hist = self._volume_history[candle.symbol]
            if len(volume_hist) >= 5:  # Need at least 5 candles for baseline
                avg_volume = sum(volume_hist) / len(volume_hist)
                if avg_volume > 0 and candle.volume > avg_volume * self.VOLUME_SPIKE_THRESHOLD:
                    error_logger.error(
                        f"Volume spike detected for {candle.symbol}: "
                        f"{candle.volume:.2f} vs avg {avg_volume:.2f} "
                        f"({candle.volume / avg_volume:.1f}x)"
                    )
                    return ValidationResult(
                        valid=False,
                        reason=f"Volume spike: {candle.volume / avg_volume:.1f}x average"
                    )

        # Track volume history for this symbol
        if candle.symbol not in self._volume_history:
            self._volume_history[candle.symbol] = []
        self._volume_history[candle.symbol].append(candle.volume)
        # Keep only last N candles
        if len(self._volume_history[candle.symbol]) > self.VOLUME_HISTORY_SIZE:
            self._volume_history[candle.symbol].pop(0)

        # 1c. Check wick anomalies (abnormally large high-low range)
        candle_range = candle.high - candle.low
        if candle.symbol in self._range_history:
            range_hist = self._range_history[candle.symbol]
            if len(range_hist) >= 5:  # Need at least 5 candles for baseline
                avg_range = sum(range_hist) / len(range_hist)
                if avg_range > 0 and candle_range > avg_range * self.WICK_ANOMALY_THRESHOLD:
                    error_logger.error(
                        f"Wick anomaly detected for {candle.symbol}: "
                        f"range {candle_range:.2f} vs avg {avg_range:.2f} "
                        f"({candle_range / avg_range:.1f}x)"
                    )
                    return ValidationResult(
                        valid=False,
                        reason=f"Wick anomaly: {candle_range / avg_range:.1f}x typical range"
                    )

        # Track range history for this symbol
        if candle.symbol not in self._range_history:
            self._range_history[candle.symbol] = []
        self._range_history[candle.symbol].append(candle_range)
        # Keep only last N candles
        if len(self._range_history[candle.symbol]) > self.RANGE_HISTORY_SIZE:
            self._range_history[candle.symbol].pop(0)

        # 2. If prev candle exists for this symbol, check price and gap
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
            if time_gap > self.MIN_GAP_MS:
                gap_minutes = time_gap / (1000 * 60)

                # Extreme gap (>1 hour) - force full reset
                if time_gap > self.MAX_GAP_MS:
                    error_logger.error(
                        f"Extreme data gap for {candle.symbol}: "
                        f"{gap_minutes:.1f} minutes - forcing full reset"
                    )
                    # Clear all state for this symbol to force fresh start
                    self.reset(candle.symbol)
                    return ValidationResult(
                        valid=True,
                        reason=f"Extreme gap: {gap_minutes:.1f} min",
                        requires_warmup=True
                    )

                # Regular gap (5 min - 1 hour) - warmup needed
                logger.warning(
                    f"Data gap detected for {candle.symbol}: "
                    f"{gap_minutes:.1f} minutes ({int(time_gap / 60000)} missing candles)"
                )
                # Update last candle before returning
                self._last_candles[candle.symbol] = candle
                return ValidationResult(
                    valid=True,
                    reason=f"Data gap: {gap_minutes:.1f} min",
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
            self._volume_history.pop(symbol, None)
            self._range_history.pop(symbol, None)
        else:
            self._last_candles.clear()
            self._volume_history.clear()
            self._range_history.clear()
