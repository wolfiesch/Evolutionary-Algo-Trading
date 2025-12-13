"""
Multi-strategy shadow pool manager.

Manages multiple strategies from the shadow pool simultaneously,
tracking performance per strategy and handling position limits.
"""
import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, TYPE_CHECKING
import pandas as pd

from .trader import ShadowTrader, TradeLog
from .position import Position
from engine.strategy_logic.parser import Strategy, Signal, GeneExpressionParser
from engine.gene_pool import market_filter
from shared.engine.gene_pool import volatility
from config import settings

if TYPE_CHECKING:
    from notifications.discord import DiscordNotifier

logger = logging.getLogger("trades")
error_logger = logging.getLogger("errors")


@dataclass
class StrategyPerformance:
    """Track performance for a single strategy."""
    strategy_id: str
    strategy_name: str
    trade_count: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl: float = 0.0
    max_drawdown: float = 0.0
    peak_pnl: float = 0.0
    last_trade_time: Optional[int] = None

    @property
    def win_rate(self) -> float:
        if self.trade_count == 0:
            return 0.0
        return self.winning_trades / self.trade_count

    def update_drawdown(self):
        """Update max drawdown tracking."""
        if self.total_pnl > self.peak_pnl:
            self.peak_pnl = self.total_pnl

        current_dd = (self.peak_pnl - self.total_pnl) if self.peak_pnl > 0 else 0
        if current_dd > self.max_drawdown:
            self.max_drawdown = current_dd


@dataclass
class ShadowPoolState:
    """Overall shadow pool state."""
    paper_equity: float
    initial_equity: float
    positions: dict[str, Position] = field(default_factory=dict)  # key: "strategy_id:symbol"
    strategy_performance: dict[str, StrategyPerformance] = field(default_factory=dict)

    @property
    def total_pnl(self) -> float:
        return self.paper_equity - self.initial_equity

    @property
    def total_pnl_pct(self) -> float:
        if self.initial_equity == 0:
            return 0.0
        return (self.paper_equity / self.initial_equity - 1) * 100

    @property
    def current_exposure(self) -> float:
        if self.paper_equity == 0:
            return 0.0
        return sum(p.size_usdt for p in self.positions.values()) / self.paper_equity

    @property
    def open_position_count(self) -> int:
        return len(self.positions)


class ShadowPoolManager:
    """
    Manages multiple strategies from the shadow pool.

    Features:
    - Loads strategies from shadow pool directory
    - Tracks performance per strategy
    - Enforces position limits across all strategies
    - Implements stop-loss and kill switches
    - Hot-reload of strategies (add/remove without restart)
    """

    def __init__(
        self,
        shadow_pool_dir: Optional[Path] = None,
        initial_equity: float = 10_000.0,
        log_path: Optional[Path] = None,
        notifier: Optional["DiscordNotifier"] = None,
    ):
        self.shadow_pool_dir = shadow_pool_dir or (settings.logs_dir / "shadow_pool")
        self.log_path = log_path or (settings.logs_dir / "shadow_trades.jsonl")
        self.parser = GeneExpressionParser()
        self.notifier = notifier

        # State
        self.state = ShadowPoolState(
            paper_equity=initial_equity,
            initial_equity=initial_equity,
        )

        # Loaded strategies
        self.strategies: dict[str, Strategy] = {}  # strategy_id -> Strategy
        self.strategy_metadata: dict[str, dict] = {}  # strategy_id -> metadata

        # Risk limits
        self.max_position_pct = settings.max_position_pct
        self.max_open_positions = settings.max_open_positions
        self.max_exposure = settings.max_exposure
        self.risk_per_trade = settings.risk_per_trade
        self.friction_per_side = settings.friction_per_side
        self.stop_loss_pct = 0.03  # 3% stop loss

        # Kill switch state
        self.trading_paused = False
        self.pause_until: Optional[datetime] = None
        self.hourly_pnl_start: float = initial_equity
        self.hourly_pnl_start_time: datetime = datetime.utcnow()

        # Ensure directories exist
        self.shadow_pool_dir.mkdir(parents=True, exist_ok=True)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

        # Load strategies on init
        self.reload_strategies()

    def remove_strategy(self, strategy_id: str) -> bool:
        """
        Remove a strategy from memory.

        Args:
            strategy_id: ID of strategy to remove

        Returns:
            True if removed, False if not found
        """
        if strategy_id in self.strategies:
            del self.strategies[strategy_id]
            if strategy_id in self.strategy_metadata:
                del self.strategy_metadata[strategy_id]
            logger.info(f"Removed strategy {strategy_id} from memory")
            return True
        return False

    def reload_strategies(self) -> int:
        """
        Reload strategies from shadow pool directory.

        Returns:
            Number of strategies loaded
        """
        self.strategies.clear()
        self.strategy_metadata.clear()

        for filepath in self.shadow_pool_dir.glob("*.json"):
            try:
                with open(filepath, "r") as f:
                    data = json.load(f)

                strategy_id = data.get("strategy_id", filepath.stem)

                # Parse strategy
                strategy = self.parser.parse({
                    "strategy_name": data.get("strategy_name", strategy_id),
                    "entry_long": data.get("entry_long"),
                    "exit_long": data.get("exit_long"),
                    "entry_short": data.get("entry_short"),
                    "exit_short": data.get("exit_short"),
                })

                self.strategies[strategy_id] = strategy
                self.strategy_metadata[strategy_id] = data

                # Initialize performance tracking if new
                if strategy_id not in self.state.strategy_performance:
                    self.state.strategy_performance[strategy_id] = StrategyPerformance(
                        strategy_id=strategy_id,
                        strategy_name=strategy.name,
                    )

                logger.info(f"Loaded strategy: {strategy.name} ({strategy_id})")

            except Exception as e:
                error_logger.error(f"Failed to load strategy from {filepath}: {e}")

        logger.info(f"Loaded {len(self.strategies)} strategies from shadow pool")
        return len(self.strategies)

    def check_kill_switches(self) -> bool:
        """
        Check kill switch conditions.

        Returns:
            True if trading should continue, False if paused
        """
        now = datetime.utcnow()

        # Check if pause has expired
        if self.pause_until and now >= self.pause_until:
            self.trading_paused = False
            self.pause_until = None
            logger.info("Kill switch pause expired, resuming trading")

        if self.trading_paused:
            return False

        # Check hourly drawdown (reset every hour)
        if (now - self.hourly_pnl_start_time).total_seconds() >= 3600:
            self.hourly_pnl_start = self.state.paper_equity
            self.hourly_pnl_start_time = now

        hourly_dd = (self.hourly_pnl_start - self.state.paper_equity) / self.state.initial_equity

        # >5% drawdown in 1 hour -> pause 1 hour
        if hourly_dd > 0.05:
            logger.warning(f"KILL SWITCH: >5% drawdown in 1 hour ({hourly_dd:.1%}), pausing for 1 hour")
            self.trading_paused = True
            self.pause_until = now.replace(hour=now.hour + 1, minute=0, second=0)
            # Send Discord notification
            if self.notifier:
                asyncio.create_task(self.notifier.send_kill_switch(
                    trigger=f">5% drawdown in 1 hour ({hourly_dd:.1%})",
                    current_equity=self.state.paper_equity,
                    initial_equity=self.state.initial_equity,
                    drawdown_pct=hourly_dd * 100,
                    pause_duration="1 hour",
                ))
            return False

        # Check total drawdown
        total_dd = (self.state.initial_equity - self.state.paper_equity) / self.state.initial_equity

        # >15% total drawdown -> full stop
        if total_dd > 0.15:
            logger.critical(f"KILL SWITCH: >15% total drawdown ({total_dd:.1%}), FULL STOP")
            self.trading_paused = True
            self.pause_until = None  # Manual resume required
            # Send Discord notification
            if self.notifier:
                asyncio.create_task(self.notifier.send_kill_switch(
                    trigger=f">15% total drawdown ({total_dd:.1%}) - FULL STOP",
                    current_equity=self.state.paper_equity,
                    initial_equity=self.state.initial_equity,
                    drawdown_pct=total_dd * 100,
                    pause_duration=None,  # Manual restart required
                ))
            return False

        # >10% in 24 hours would need tracking (simplified here)

        return True

    def check_stop_losses(self, prices: dict[str, float]) -> list[str]:
        """
        Check stop-losses for all open positions.

        Args:
            prices: Current prices per symbol

        Returns:
            List of position keys that hit stop loss
        """
        triggered = []

        for key, position in self.state.positions.items():
            if position.symbol not in prices:
                continue

            current_price = prices[position.symbol]

            # Check stop-loss (3% below entry for longs)
            if position.side == "LONG":
                stop_price = position.entry_price * (1 - self.stop_loss_pct)
                if current_price <= stop_price:
                    triggered.append(key)
                    logger.warning(
                        f"STOP LOSS triggered for {position.symbol} "
                        f"(entry: {position.entry_price:.4f}, stop: {stop_price:.4f}, "
                        f"current: {current_price:.4f})"
                    )

        return triggered

    def process_candle(
        self,
        symbol: str,
        candles: pd.DataFrame,
        btc_candles: pd.DataFrame,
        current_prices: dict[str, float],
    ) -> list[tuple[str, Signal]]:
        """
        Process a candle for all strategies.

        Args:
            symbol: Trading symbol
            candles: OHLCV data for symbol
            btc_candles: BTC candle data for market filter
            current_prices: Current prices for all symbols (for stop-loss)

        Returns:
            List of (strategy_id, signal) tuples for signals acted upon
        """
        signals_acted = []

        # Check kill switches first
        if not self.check_kill_switches():
            return signals_acted

        # Check stop-losses
        stop_losses = self.check_stop_losses(current_prices)
        for key in stop_losses:
            strategy_id, sym = key.split(":", 1)
            if sym == symbol:
                self._execute_exit(
                    strategy_id=strategy_id,
                    symbol=symbol,
                    price=current_prices[symbol],
                    btc_candles=btc_candles,
                    reason="STOP_LOSS",
                )
                signals_acted.append((strategy_id, Signal.EXIT_LONG))

        current_price = candles["close"].iloc[-1]
        btc_trend_val = market_filter.btc_trend(btc_candles, 60)
        atr_regime_val = volatility.atr_regime(candles, 14)
        market_regime = self._classify_regime(btc_candles, atr_regime_val)

        # Extract current candle OHLC for slippage calibration
        candle_ohlc = (
            float(candles["open"].iloc[-1]),
            float(candles["high"].iloc[-1]),
            float(candles["low"].iloc[-1]),
            float(candles["close"].iloc[-1]),
        )

        # Process each strategy
        for strategy_id, strategy in self.strategies.items():
            position_key = f"{strategy_id}:{symbol}"
            has_position = position_key in self.state.positions

            try:
                signal = self.parser.get_signal(strategy, candles, btc_candles, has_position)

                if signal == Signal.ENTRY_LONG:
                    if self._execute_entry(
                        strategy_id=strategy_id,
                        symbol=symbol,
                        price=current_price,
                        btc_trend=btc_trend_val,
                        atr_regime=atr_regime_val,
                        market_regime=market_regime,
                        candle_ohlc=candle_ohlc,
                    ):
                        signals_acted.append((strategy_id, signal))

                elif signal == Signal.EXIT_LONG:
                    if self._execute_exit(
                        strategy_id=strategy_id,
                        symbol=symbol,
                        price=current_price,
                        btc_candles=btc_candles,
                        reason="SIGNAL",
                        candle_ohlc=candle_ohlc,
                    ):
                        signals_acted.append((strategy_id, signal))

            except Exception as e:
                error_logger.error(f"Error processing {symbol} for {strategy_id}: {e}")

        return signals_acted

    def _classify_regime(self, btc_candles: pd.DataFrame, atr_regime: float) -> str:
        """Classify current market regime."""
        lookback = min(240, len(btc_candles) - 1)
        if lookback < 60:
            return "unknown"

        btc_trend = btc_candles["close"].iloc[-1] / btc_candles["close"].iloc[-lookback] - 1
        threshold = 0.01

        if btc_trend > threshold:
            return "bull_volatile" if atr_regime > 0 else "bull_calm"
        elif btc_trend < -threshold:
            return "bear_volatile" if atr_regime > 0 else "bear_calm"
        else:
            return "sideways"

    def _execute_entry(
        self,
        strategy_id: str,
        symbol: str,
        price: float,
        btc_trend: float,
        atr_regime: float,
        market_regime: str,
        candle_ohlc: Optional[tuple[float, float, float, float]] = None,
    ) -> bool:
        """
        Execute a simulated long entry.

        Args:
            strategy_id: Strategy identifier
            symbol: Trading symbol
            price: Signal price (candle close)
            btc_trend: BTC trend value
            atr_regime: ATR regime value
            market_regime: Market regime classification
            candle_ohlc: Tuple of (open, high, low, close) for slippage tracking
        """
        position_key = f"{strategy_id}:{symbol}"

        # Check position limits
        if self.state.open_position_count >= self.max_open_positions:
            logger.debug(f"Max positions reached, skipping entry for {strategy_id}:{symbol}")
            return False

        # Calculate position size
        position_size = min(
            self.state.paper_equity * self.risk_per_trade,
            self.state.paper_equity * self.max_position_pct,
        )

        # Check exposure limit
        pending_exposure = (
            sum(p.size_usdt for p in self.state.positions.values()) + position_size
        ) / self.state.paper_equity

        if pending_exposure > self.max_exposure:
            logger.debug(f"Max exposure would be breached, skipping {strategy_id}:{symbol}")
            return False

        # Apply friction
        fill_price = price * (1 + self.friction_per_side)

        # Create position
        position = Position(
            symbol=symbol,
            strategy_id=strategy_id,
            entry_time=int(datetime.utcnow().timestamp() * 1000),
            entry_price=fill_price,
            size_usdt=position_size,
            stop_loss_price=fill_price * (1 - self.stop_loss_pct),
        )
        self.state.positions[position_key] = position

        # Calculate implied slippage for calibration
        implied_slippage = (fill_price - price) / price if price > 0 else 0

        # Log trade with slippage data
        strategy = self.strategies.get(strategy_id)
        trade_log = TradeLog(
            timestamp=position.entry_time,
            strategy_id=strategy_id,
            coin=symbol,
            signal="ENTRY_LONG",
            gene_expression=strategy.entry_long if strategy else "",
            price_at_signal=price,
            simulated_fill=fill_price,
            position_size_usdt=position_size,
            btc_trend=btc_trend,
            atr_regime=atr_regime,
            market_regime=market_regime,
            candle_open=candle_ohlc[0] if candle_ohlc else None,
            candle_high=candle_ohlc[1] if candle_ohlc else None,
            candle_low=candle_ohlc[2] if candle_ohlc else None,
            candle_close=candle_ohlc[3] if candle_ohlc else None,
            implied_slippage_pct=implied_slippage * 100,  # As percentage
        )
        self._log_trade(trade_log)

        return True

    def _execute_exit(
        self,
        strategy_id: str,
        symbol: str,
        price: float,
        btc_candles: pd.DataFrame,
        reason: str = "SIGNAL",
        candle_ohlc: Optional[tuple[float, float, float, float]] = None,
    ) -> bool:
        """
        Execute a simulated long exit.

        Args:
            strategy_id: Strategy identifier
            symbol: Trading symbol
            price: Signal price (candle close)
            btc_candles: BTC candle data for market context
            reason: Exit reason (SIGNAL, STOP_LOSS, EMERGENCY_CLOSE)
            candle_ohlc: Tuple of (open, high, low, close) for slippage tracking
        """
        position_key = f"{strategy_id}:{symbol}"
        position = self.state.positions.get(position_key)

        if not position:
            return False

        # Apply friction
        fill_price = price * (1 - self.friction_per_side)

        # Calculate P&L
        pnl_pct = (fill_price - position.entry_price) / position.entry_price
        pnl_usdt = position.size_usdt * pnl_pct

        # Update state
        self.state.paper_equity += pnl_usdt

        # Update strategy performance
        perf = self.state.strategy_performance.get(strategy_id)
        if perf:
            perf.trade_count += 1
            perf.total_pnl += pnl_usdt
            perf.last_trade_time = int(datetime.utcnow().timestamp() * 1000)

            if pnl_usdt >= 0:
                perf.winning_trades += 1
            else:
                perf.losing_trades += 1

            perf.update_drawdown()

        # Get market context
        btc_trend_val = market_filter.btc_trend(btc_candles, 60)
        atr_regime_val = volatility.atr_regime(btc_candles, 14)  # Use BTC for regime
        market_regime = self._classify_regime(btc_candles, atr_regime_val)

        # Calculate implied slippage for calibration (negative for exits)
        implied_slippage = (price - fill_price) / price if price > 0 else 0

        # Log trade with slippage data
        strategy = self.strategies.get(strategy_id)
        # Capture entry time before removing position
        entry_time_ms = position.entry_time

        trade_log = TradeLog(
            timestamp=int(datetime.utcnow().timestamp() * 1000),
            strategy_id=strategy_id,
            coin=symbol,
            signal=f"EXIT_LONG_{reason}",
            gene_expression=strategy.exit_long if strategy else "",
            price_at_signal=price,
            simulated_fill=fill_price,
            position_size_usdt=position.size_usdt,
            btc_trend=btc_trend_val,
            atr_regime=atr_regime_val,
            market_regime=market_regime,
            pnl=pnl_usdt,
            pnl_pct=pnl_pct * 100,
            candle_open=candle_ohlc[0] if candle_ohlc else None,
            candle_high=candle_ohlc[1] if candle_ohlc else None,
            candle_low=candle_ohlc[2] if candle_ohlc else None,
            candle_close=candle_ohlc[3] if candle_ohlc else None,
            implied_slippage_pct=implied_slippage * 100,  # As percentage
        )
        self._log_trade(trade_log, entry_time_ms=entry_time_ms)

        # Remove position
        del self.state.positions[position_key]

        return True

    def _log_trade(self, trade: TradeLog, entry_time_ms: Optional[int] = None) -> None:
        """Append trade to log file and send Discord notification."""
        with open(self.log_path, "a") as f:
            f.write(trade.to_json() + "\n")

        if trade.pnl is not None:
            logger.info(
                f"[{trade.strategy_id}] {trade.signal} {trade.coin} @ {trade.simulated_fill:.4f} "
                f"(size: ${trade.position_size_usdt:.2f}, pnl: ${trade.pnl:.2f} / {trade.pnl_pct:.2f}%)"
            )
        else:
            logger.info(
                f"[{trade.strategy_id}] {trade.signal} {trade.coin} @ {trade.simulated_fill:.4f} "
                f"(size: ${trade.position_size_usdt:.2f})"
            )

        # Send Discord notification
        if self.notifier:
            if "ENTRY" in trade.signal:
                asyncio.create_task(self.notifier.send_trade_entry(trade))
            elif "EXIT" in trade.signal:
                asyncio.create_task(self.notifier.send_trade_exit(trade, entry_time_ms))

    def get_stats(self) -> dict:
        """Get overall and per-strategy statistics."""
        return {
            "paper_equity": self.state.paper_equity,
            "initial_equity": self.state.initial_equity,
            "total_pnl": self.state.total_pnl,
            "total_pnl_pct": self.state.total_pnl_pct,
            "open_positions": self.state.open_position_count,
            "current_exposure": self.state.current_exposure,
            "strategies_loaded": len(self.strategies),
            "trading_paused": self.trading_paused,
            "strategy_performance": {
                sid: {
                    "name": perf.strategy_name,
                    "trade_count": perf.trade_count,
                    "win_rate": perf.win_rate,
                    "total_pnl": perf.total_pnl,
                    "max_drawdown": perf.max_drawdown,
                }
                for sid, perf in self.state.strategy_performance.items()
            },
        }

    def close_all_positions(self, prices: dict[str, float], btc_candles: pd.DataFrame) -> int:
        """
        Emergency close all positions.

        Args:
            prices: Current prices per symbol
            btc_candles: BTC candles for logging

        Returns:
            Number of positions closed
        """
        closed = 0

        for key in list(self.state.positions.keys()):
            strategy_id, symbol = key.split(":", 1)
            if symbol in prices:
                self._execute_exit(
                    strategy_id=strategy_id,
                    symbol=symbol,
                    price=prices[symbol],
                    btc_candles=btc_candles,
                    reason="EMERGENCY_CLOSE",
                )
                closed += 1

        logger.warning(f"Emergency closed {closed} positions")
        return closed
