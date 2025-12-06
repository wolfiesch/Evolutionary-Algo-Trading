"""Shadow (paper) trading implementation."""
import json
import logging
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import Optional
from pathlib import Path
import pandas as pd

from .position import Position
from engine.strategy_logic.parser import Strategy, Signal, GeneExpressionParser
from engine.gene_pool import market_filter, volatility
from config import settings


logger = logging.getLogger("trades")
error_logger = logging.getLogger("errors")


@dataclass
class TradeLog:
    """Full trade state vector for logging."""
    timestamp: int
    strategy_id: str
    coin: str
    signal: str
    gene_expression: str
    price_at_signal: float
    simulated_fill: float
    position_size_usdt: float
    btc_trend: float
    atr_regime: float
    market_regime: str = "unknown"
    pnl: Optional[float] = None
    pnl_pct: Optional[float] = None

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(asdict(self), indent=None)


class ShadowTrader:
    """
    Paper trading engine that simulates execution on real order books.

    Applies realistic friction:
    - 0.10% exchange fee
    - 0.15% estimated slippage
    - Total: 0.25% per side
    """

    def __init__(
        self,
        strategy: Strategy,
        equity: float | None = None,
        log_path: Path | None = None,
    ):
        self.strategy = strategy
        self.equity = equity or settings.initial_equity
        self.initial_equity = self.equity
        self.positions: dict[str, Position] = {}  # symbol -> position
        self.parser = GeneExpressionParser()
        self.log_path = log_path or settings.logs_dir / "shadow_trades.jsonl"
        self.trade_count = 0
        self.winning_trades = 0
        self.losing_trades = 0

        # Risk limits from config
        self.max_position_pct = settings.max_position_pct
        self.max_open_positions = settings.max_open_positions
        self.max_exposure = settings.max_exposure
        self.risk_per_trade = settings.risk_per_trade
        self.friction_per_side = settings.friction_per_side

        # Ensure log directory exists
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def process_candle(
        self,
        symbol: str,
        candles: pd.DataFrame,
        btc_candles: pd.DataFrame,
    ) -> Optional[Signal]:
        """
        Process a new candle and execute any signals.

        Args:
            symbol: Trading symbol
            candles: OHLCV data for symbol (oldest first)
            btc_candles: BTC candle data for market filter

        Returns:
            Signal that was acted upon, or None
        """
        has_position = symbol in self.positions

        # Get signal from strategy
        signal = self.parser.get_signal(
            self.strategy, candles, btc_candles, has_position
        )

        if signal == Signal.HOLD:
            return None

        current_price = candles["close"].iloc[-1]
        btc_trend_val = market_filter.btc_trend(btc_candles, 60)
        atr_regime_val = volatility.atr_regime(candles, 14)

        # Determine market regime
        market_regime = self._classify_regime(btc_candles, atr_regime_val)

        if signal == Signal.ENTRY_LONG:
            return self._execute_entry(
                symbol, current_price, btc_trend_val, atr_regime_val, market_regime
            )
        elif signal == Signal.EXIT_LONG:
            return self._execute_exit(
                symbol, current_price, btc_trend_val, atr_regime_val, market_regime
            )

        return None

    def _classify_regime(self, btc_candles: pd.DataFrame, atr_regime: float) -> str:
        """Classify current market regime.

        Uses 24-hour lookback for 1-minute candles (1440 bars).
        A week would be 10080 bars but that's excessive for our 200-bar buffer.
        24h is sufficient to detect regime shifts and fits within typical data windows.
        """
        # 24 hours of 1-minute candles = 24 * 60 = 1440 bars
        # But since we typically only have 200 bars, use a shorter 4-hour window (240 bars)
        # with proportionally scaled thresholds
        lookback = min(240, len(btc_candles) - 1)  # 4 hours of 1-min candles
        if lookback < 60:  # Need at least 1 hour of data
            return "unknown"

        btc_trend = btc_candles["close"].iloc[-1] / btc_candles["close"].iloc[-lookback] - 1

        # Scale thresholds: 5% weekly ≈ 0.7% daily ≈ 0.12% per 4 hours
        # Use 1% threshold for 4-hour window to detect meaningful moves
        threshold = 0.01

        if btc_trend > threshold:
            if atr_regime > 0:
                return "bull_volatile"
            else:
                return "bull_calm"
        elif btc_trend < -threshold:
            if atr_regime > 0:
                return "bear_volatile"
            else:
                return "bear_calm"
        else:
            return "sideways"

    def _execute_entry(
        self,
        symbol: str,
        price: float,
        btc_trend: float,
        atr_regime: float,
        market_regime: str,
    ) -> Optional[Signal]:
        """Execute a simulated long entry."""
        # Check risk limits
        if len(self.positions) >= self.max_open_positions:
            logger.info(f"Max positions ({self.max_open_positions}) reached, skipping entry for {symbol}")
            return None

        current_exposure = sum(p.size_usdt for p in self.positions.values())

        # Calculate position size (1% risk, max 10% position)
        position_size = min(
            self.equity * self.risk_per_trade,
            self.equity * self.max_position_pct,
        )

        # Check if adding this position would breach max exposure
        pending_exposure = (current_exposure + position_size) / self.equity
        if pending_exposure > self.max_exposure:
            logger.info(
                f"Entry would breach max exposure ({self.max_exposure:.0%}): "
                f"current={current_exposure/self.equity:.1%} + pending={position_size/self.equity:.1%} "
                f"= {pending_exposure:.1%}, skipping {symbol}"
            )
            return None

        # Apply friction (buy at higher price)
        fill_price = price * (1 + self.friction_per_side)

        # Create position
        position = Position(
            symbol=symbol,
            strategy_id=self.strategy.name,
            entry_time=int(datetime.now().timestamp() * 1000),
            entry_price=fill_price,
            size_usdt=position_size,
        )
        self.positions[symbol] = position

        # Log trade
        trade_log = TradeLog(
            timestamp=position.entry_time,
            strategy_id=self.strategy.name,
            coin=symbol,
            signal="ENTRY_LONG",
            gene_expression=self.strategy.entry_long or "",
            price_at_signal=price,
            simulated_fill=fill_price,
            position_size_usdt=position_size,
            btc_trend=btc_trend,
            atr_regime=atr_regime,
            market_regime=market_regime,
        )
        self._log_trade(trade_log)

        return Signal.ENTRY_LONG

    def _execute_exit(
        self,
        symbol: str,
        price: float,
        btc_trend: float,
        atr_regime: float,
        market_regime: str,
    ) -> Optional[Signal]:
        """Execute a simulated long exit."""
        position = self.positions.get(symbol)
        if not position:
            return None

        # Apply friction (sell at lower price)
        fill_price = price * (1 - self.friction_per_side)

        # Calculate P&L
        pnl_pct = (fill_price - position.entry_price) / position.entry_price
        pnl_usdt = position.size_usdt * pnl_pct

        # Update equity
        self.equity += pnl_usdt
        self.trade_count += 1

        if pnl_usdt >= 0:
            self.winning_trades += 1
        else:
            self.losing_trades += 1

        # Log trade
        trade_log = TradeLog(
            timestamp=int(datetime.now().timestamp() * 1000),
            strategy_id=self.strategy.name,
            coin=symbol,
            signal="EXIT_LONG",
            gene_expression=self.strategy.exit_long or "",
            price_at_signal=price,
            simulated_fill=fill_price,
            position_size_usdt=position.size_usdt,
            btc_trend=btc_trend,
            atr_regime=atr_regime,
            market_regime=market_regime,
            pnl=pnl_usdt,
            pnl_pct=pnl_pct * 100,
        )
        self._log_trade(trade_log)

        # Remove position
        del self.positions[symbol]

        return Signal.EXIT_LONG

    def _log_trade(self, trade: TradeLog) -> None:
        """Append trade to log file."""
        with open(self.log_path, "a") as f:
            f.write(trade.to_json() + "\n")

        if trade.pnl is not None:
            logger.info(
                f"{trade.signal} {trade.coin} @ {trade.simulated_fill:.4f} "
                f"(size: ${trade.position_size_usdt:.2f}, pnl: ${trade.pnl:.2f} / {trade.pnl_pct:.2f}%)"
            )
        else:
            logger.info(
                f"{trade.signal} {trade.coin} @ {trade.simulated_fill:.4f} "
                f"(size: ${trade.position_size_usdt:.2f})"
            )

    @property
    def total_pnl(self) -> float:
        """Total realized P&L since start."""
        return self.equity - self.initial_equity

    @property
    def total_pnl_pct(self) -> float:
        """Total realized P&L percentage."""
        return (self.equity / self.initial_equity - 1) * 100

    @property
    def current_exposure(self) -> float:
        """Current exposure as fraction of equity."""
        if self.equity == 0:
            return 0.0
        return sum(p.size_usdt for p in self.positions.values()) / self.equity

    @property
    def win_rate(self) -> float:
        """Win rate (0-1)."""
        if self.trade_count == 0:
            return 0.0
        return self.winning_trades / self.trade_count

    def get_stats(self) -> dict:
        """Get current trading statistics."""
        return {
            "equity": self.equity,
            "initial_equity": self.initial_equity,
            "total_pnl": self.total_pnl,
            "total_pnl_pct": self.total_pnl_pct,
            "trade_count": self.trade_count,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": self.win_rate,
            "open_positions": len(self.positions),
            "current_exposure": self.current_exposure,
        }
