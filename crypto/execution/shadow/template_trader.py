"""
Template-based Shadow Trader for evolved strategies.

This module runs template strategies (from evolve_template.py) in shadow mode,
processing live data and logging paper trades for validation.

Unlike the gene expression pool manager, this handles:
- Parameter-based strategies (CryptoStrategyTemplate)
- Timeframe aggregation (e.g., 1m -> H1)
- Vectorized signal generation
"""
import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional
import pandas as pd

from shared.evolution.parameters import CryptoParameters
from shared.evolution.templates import CryptoStrategyTemplate
from config import settings

logger = logging.getLogger("trades")
error_logger = logging.getLogger("errors")


@dataclass
class TemplatePosition:
    """Track an open template position."""
    symbol: str
    strategy_id: str
    entry_time: int  # ms timestamp
    entry_price: float
    size_usdt: float
    stop_loss_price: Optional[float] = None

    def unrealized_pnl_pct(self, current_price: float) -> float:
        """Calculate unrealized P&L percentage."""
        return (current_price - self.entry_price) / self.entry_price * 100


@dataclass
class TemplateTradeLog:
    """Log entry for a template strategy trade."""
    timestamp: int
    strategy_id: str
    symbol: str
    signal: str
    composite_score: float
    entry_threshold: float
    price_at_signal: float
    simulated_fill: float
    position_size_usdt: float
    market_regime: str
    pnl: Optional[float] = None
    pnl_pct: Optional[float] = None

    def to_json(self) -> str:
        return json.dumps({
            "timestamp": self.timestamp,
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "signal": self.signal,
            "composite_score": self.composite_score,
            "entry_threshold": self.entry_threshold,
            "price_at_signal": self.price_at_signal,
            "simulated_fill": self.simulated_fill,
            "position_size_usdt": self.position_size_usdt,
            "market_regime": self.market_regime,
            "pnl": self.pnl,
            "pnl_pct": self.pnl_pct,
            "strategy_type": "template",
        })


class TemplateShadowTrader:
    """
    Shadow trader for template-based strategies.

    Features:
    - Timeframe aggregation (1m candles -> H1 candles)
    - Template signal generation
    - Paper trading with friction
    - Trade logging compatible with existing infrastructure
    """

    def __init__(
        self,
        strategy_path: Path,
        timeframe_minutes: int = 60,
        initial_equity: float = 10_000.0,
        log_path: Optional[Path] = None,
        notifier=None,
    ):
        """
        Initialize template shadow trader.

        Args:
            strategy_path: Path to the strategy JSON file
            timeframe_minutes: Target timeframe in minutes (e.g., 60 for H1)
            initial_equity: Starting paper equity
            log_path: Path to trade log file
            notifier: Optional Discord notifier
        """
        self.strategy_path = strategy_path
        self.timeframe_minutes = timeframe_minutes
        self.log_path = log_path or (settings.logs_dir / "shadow_trades.jsonl")
        self.notifier = notifier

        # Load strategy
        with open(strategy_path, "r") as f:
            data = json.load(f)

        self.strategy_id = strategy_path.stem
        self.symbol = data.get("symbol", "ETHUSDT")
        self.params = CryptoParameters.from_dict(data.get("parameters", {}))
        self.template = CryptoStrategyTemplate(self.params)

        # Backtest metrics from strategy file
        self.backtest_sharpe = data.get("fitness", {}).get("sharpe_ratio", 0)
        self.backtest_win_rate = data.get("fitness", {}).get("win_rate", 0)

        # State
        self.paper_equity = initial_equity
        self.initial_equity = initial_equity
        self.position: Optional[TemplatePosition] = None

        # Candle aggregation buffers (symbol -> list of 1m candles)
        self._candle_buffer: dict[str, list] = {}
        self._last_aggregate_time: dict[str, int] = {}

        # Risk parameters
        self.risk_per_trade = settings.risk_per_trade
        self.friction_per_side = settings.friction_per_side
        self.stop_loss_pct = 0.03

        # Trade counting
        self.trade_count = 0
        self.winning_trades = 0
        self.total_pnl = 0.0

        # Ensure log directory exists
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info(
            f"Loaded template strategy: {self.strategy_id} "
            f"(symbol={self.symbol}, timeframe={timeframe_minutes}m, "
            f"backtest_sharpe={self.backtest_sharpe:.2f})"
        )

    def process_candle(
        self,
        symbol: str,
        candle: dict,  # {open, high, low, close, volume, timestamp}
        btc_candles_df: pd.DataFrame,
    ) -> Optional[str]:
        """
        Process a 1-minute candle.

        Aggregates candles and generates signals when timeframe completes.

        Args:
            symbol: Trading symbol
            candle: 1-minute candle dict
            btc_candles_df: BTC candle DataFrame for market filter

        Returns:
            Signal string if trade executed, None otherwise
        """
        if symbol != self.symbol:
            return None

        # Add to buffer
        if symbol not in self._candle_buffer:
            self._candle_buffer[symbol] = []

        self._candle_buffer[symbol].append(candle)

        # Check if we have enough candles for aggregation
        if len(self._candle_buffer[symbol]) < self.timeframe_minutes:
            return None

        # Check if timeframe boundary reached (align to hour)
        candle_ts = candle.get("timestamp", 0)
        current_minute = datetime.utcfromtimestamp(candle_ts / 1000).minute

        # For H1, aggregate when minute == 59 (end of hour)
        if self.timeframe_minutes == 60 and current_minute != 59:
            # Keep buffer at most 2x timeframe to limit memory
            if len(self._candle_buffer[symbol]) > self.timeframe_minutes * 2:
                self._candle_buffer[symbol] = self._candle_buffer[symbol][-self.timeframe_minutes:]
            return None

        # Aggregate candles
        buffer = self._candle_buffer[symbol][-self.timeframe_minutes:]
        agg_candle = self._aggregate_candles(buffer)

        # Build candle history for template (need at least 100 bars)
        # For now, use the aggregated candle as latest
        candles_df = self._build_candle_history(symbol, agg_candle)

        if len(candles_df) < 60:
            logger.debug(f"Not enough candle history ({len(candles_df)} bars), waiting...")
            return None

        # Generate signals using template
        signal = self._evaluate_and_trade(candles_df, btc_candles_df)

        # Clear buffer after processing
        self._candle_buffer[symbol] = []

        return signal

    def _aggregate_candles(self, candles: list) -> dict:
        """Aggregate 1m candles into higher timeframe candle."""
        if not candles:
            return {}

        return {
            "open": candles[0]["open"],
            "high": max(c["high"] for c in candles),
            "low": min(c["low"] for c in candles),
            "close": candles[-1]["close"],
            "volume": sum(c["volume"] for c in candles),
            "timestamp": candles[-1]["timestamp"],
        }

    def _build_candle_history(self, symbol: str, latest_candle: dict) -> pd.DataFrame:
        """
        Build candle history DataFrame for template.

        Uses stored H1 candles from repository, plus latest aggregated candle.
        """
        from data.storage.repository import CandleRepository

        repo = CandleRepository(settings.sqlite_path)

        # Fetch recent H1 candles (we need ~100 for indicators)
        # For now, aggregate from 1m data in DB
        end_time = latest_candle.get("timestamp", int(datetime.utcnow().timestamp() * 1000))
        start_time = end_time - (200 * self.timeframe_minutes * 60 * 1000)  # 200 bars back

        raw_candles = repo.get_candles(
            symbol=symbol,
            start_time=start_time,
            end_time=end_time,
        )

        if not raw_candles:
            return pd.DataFrame()

        # Convert to DataFrame
        df = pd.DataFrame([{
            "open": c.open,
            "high": c.high,
            "low": c.low,
            "close": c.close,
            "volume": c.volume,
            "timestamp": c.timestamp,
        } for c in raw_candles])

        # Resample to target timeframe
        df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")
        df = df.set_index("datetime")

        rule = f"{self.timeframe_minutes}min"
        ohlcv = df.resample(rule).agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
            "timestamp": "last",
        }).dropna()

        return ohlcv.reset_index(drop=True)

    def _evaluate_and_trade(
        self,
        candles_df: pd.DataFrame,
        btc_candles_df: pd.DataFrame,
    ) -> Optional[str]:
        """
        Evaluate template signals and execute paper trades.

        Returns:
            Signal name if trade executed
        """
        try:
            # Generate signals
            signals_df = self.template.generate_signals(candles_df)

            # Get latest signals
            latest = signals_df.iloc[-1]
            current_price = candles_df["close"].iloc[-1]
            composite = latest["composite"]

            # Determine regime
            is_regime_b = latest.get("is_regime_b", False)
            regime = "trending" if is_regime_b else "ranging"

            has_position = self.position is not None

            # Check for exit first
            if has_position and latest["exit_long"]:
                return self._execute_exit(current_price, composite, regime, "SIGNAL")

            # Check for entry
            if not has_position and latest["entry_long"]:
                return self._execute_entry(current_price, composite, regime)

            # Check stop loss
            if has_position:
                unrealized_pnl_pct = self.position.unrealized_pnl_pct(current_price)
                if unrealized_pnl_pct <= -self.stop_loss_pct * 100:
                    return self._execute_exit(current_price, composite, regime, "STOP_LOSS")

            return None

        except Exception as e:
            error_logger.error(f"Error evaluating template signals: {e}")
            return None

    def _execute_entry(
        self,
        price: float,
        composite: float,
        regime: str,
    ) -> str:
        """Execute paper entry."""
        fill_price = price * (1 + self.friction_per_side)
        position_size = self.paper_equity * self.risk_per_trade

        self.position = TemplatePosition(
            symbol=self.symbol,
            strategy_id=self.strategy_id,
            entry_time=int(datetime.utcnow().timestamp() * 1000),
            entry_price=fill_price,
            size_usdt=position_size,
            stop_loss_price=fill_price * (1 - self.stop_loss_pct),
        )

        trade_log = TemplateTradeLog(
            timestamp=self.position.entry_time,
            strategy_id=self.strategy_id,
            symbol=self.symbol,
            signal="ENTRY_LONG",
            composite_score=composite,
            entry_threshold=self.params.entry_threshold_long,
            price_at_signal=price,
            simulated_fill=fill_price,
            position_size_usdt=position_size,
            market_regime=regime,
        )
        self._log_trade(trade_log)

        logger.info(
            f"[{self.strategy_id}] ENTRY_LONG {self.symbol} @ {fill_price:.4f} "
            f"(composite={composite:.3f}, threshold={self.params.entry_threshold_long:.2f})"
        )

        return "ENTRY_LONG"

    def _execute_exit(
        self,
        price: float,
        composite: float,
        regime: str,
        reason: str,
    ) -> str:
        """Execute paper exit."""
        if not self.position:
            return None

        fill_price = price * (1 - self.friction_per_side)
        pnl_pct = (fill_price - self.position.entry_price) / self.position.entry_price
        pnl_usdt = self.position.size_usdt * pnl_pct

        # Update state
        self.paper_equity += pnl_usdt
        self.total_pnl += pnl_usdt
        self.trade_count += 1
        if pnl_usdt >= 0:
            self.winning_trades += 1

        trade_log = TemplateTradeLog(
            timestamp=int(datetime.utcnow().timestamp() * 1000),
            strategy_id=self.strategy_id,
            symbol=self.symbol,
            signal=f"EXIT_LONG_{reason}",
            composite_score=composite,
            entry_threshold=self.params.exit_threshold_long,
            price_at_signal=price,
            simulated_fill=fill_price,
            position_size_usdt=self.position.size_usdt,
            market_regime=regime,
            pnl=pnl_usdt,
            pnl_pct=pnl_pct * 100,
        )
        self._log_trade(trade_log)

        logger.info(
            f"[{self.strategy_id}] EXIT_LONG_{reason} {self.symbol} @ {fill_price:.4f} "
            f"(pnl=${pnl_usdt:.2f} / {pnl_pct*100:.2f}%)"
        )

        self.position = None
        return f"EXIT_LONG_{reason}"

    def _log_trade(self, trade: TemplateTradeLog) -> None:
        """Append trade to log file."""
        with open(self.log_path, "a") as f:
            f.write(trade.to_json() + "\n")

    def get_stats(self) -> dict:
        """Get trader statistics."""
        win_rate = self.winning_trades / self.trade_count if self.trade_count > 0 else 0
        return {
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "timeframe_minutes": self.timeframe_minutes,
            "paper_equity": self.paper_equity,
            "initial_equity": self.initial_equity,
            "total_pnl": self.total_pnl,
            "total_pnl_pct": (self.paper_equity / self.initial_equity - 1) * 100,
            "trade_count": self.trade_count,
            "win_rate": win_rate,
            "has_position": self.position is not None,
            "backtest_sharpe": self.backtest_sharpe,
            "backtest_win_rate": self.backtest_win_rate,
        }


def load_template_strategy(strategy_path: Path, notifier=None) -> TemplateShadowTrader:
    """
    Load a template strategy for shadow trading.

    Args:
        strategy_path: Path to strategy JSON file
        notifier: Optional Discord notifier

    Returns:
        Configured TemplateShadowTrader instance
    """
    # Determine timeframe from strategy file
    with open(strategy_path, "r") as f:
        data = json.load(f)

    timeframe = data.get("timeframe", 60)  # Default to H1

    return TemplateShadowTrader(
        strategy_path=strategy_path,
        timeframe_minutes=timeframe,
        notifier=notifier,
    )
