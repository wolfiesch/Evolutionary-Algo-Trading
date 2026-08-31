#!/usr/bin/env python3
"""
Run template strategies in shadow trading mode.

Usage:
    python3 run_template_shadow.py --strategy=winning_strategies/eth_h1_evolved_v1.json

This script connects to live market data and runs evolved template strategies
in paper trading mode for validation before real deployment.
"""
import argparse
import asyncio
import signal as sig
import sys
from pathlib import Path
from typing import Optional

# Add parent directory to path for proper imports
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd

from config import settings
from logs import setup_logging
from data.ingestion.bybit_ws import BybitWebSocketClient, ConnectionState
from data.storage.repository import CandleRepository
from data.storage.models import Candle
from data.quality_filters import CandleValidator
from execution.shadow.template_trader import TemplateShadowTrader, load_template_strategy
from notifications import DiscordNotifier


class TemplateShadowRunner:
    """Run template strategies in shadow mode."""

    def __init__(self, strategy_path: Path, symbols: list[str] = None):
        """
        Initialize template shadow runner.

        Args:
            strategy_path: Path to the evolved strategy JSON
            symbols: List of symbols to track (for BTC data)
        """
        # Setup logging
        self.trade_logger, self.error_logger = setup_logging(settings.logs_dir)
        self.trade_logger.info(f"Initializing template shadow runner: {strategy_path}")

        # Initialize notifications
        self.notifier: Optional[DiscordNotifier] = None
        if settings.discord_enabled:
            self.notifier = DiscordNotifier(settings.discord_webhook_url)
            self.trade_logger.info("Discord notifications enabled")

        # Initialize components
        self.repository = CandleRepository(settings.sqlite_path)
        self.validator = CandleValidator()

        # Load template strategy
        self.trader = load_template_strategy(strategy_path, self.notifier)
        self.strategy_symbol = self.trader.symbol

        # Symbols to track (strategy symbol + BTC for market filter)
        self._symbols = symbols or [self.strategy_symbol, "BTCUSDT"]
        if "BTCUSDT" not in self._symbols:
            self._symbols.append("BTCUSDT")

        # State
        self._running = False
        self._candle_count = 0
        self._connection_state = ConnectionState.DISCONNECTED
        self._trading_paused = True

        self.trade_logger.info(
            f"Template shadow runner initialized:\n"
            f"  Strategy: {self.trader.strategy_id}\n"
            f"  Symbol: {self.strategy_symbol}\n"
            f"  Timeframe: {self.trader.timeframe_minutes}m\n"
            f"  Backtest Sharpe: {self.trader.backtest_sharpe:.2f}\n"
            f"  Backtest Win Rate: {self.trader.backtest_win_rate:.1%}"
        )

    async def on_connection_state_change(self, new_state: ConnectionState) -> None:
        """Handle connection state changes."""
        old_state = self._connection_state
        self._connection_state = new_state

        if new_state == ConnectionState.READY:
            self._trading_paused = False
            self.trade_logger.info("Trading RESUMED - system ready")
        else:
            self._trading_paused = True
            self.trade_logger.info(f"Trading PAUSED - connection state: {new_state.value}")

    async def on_candle(self, candle: Candle) -> None:
        """Process incoming candle."""
        try:
            # Validate
            result = self.validator.validate(candle)
            if not result.valid:
                self.error_logger.warning(
                    f"Invalid candle for {candle.symbol}: {result.reason}"
                )
                return

            # Store
            self.repository.insert(candle)
            self._candle_count += 1

            if self._candle_count % 100 == 0:
                self.trade_logger.info(
                    f"Processed {self._candle_count} candles | "
                    f"Equity: ${self.trader.paper_equity:.2f} | "
                    f"Trades: {self.trader.trade_count}"
                )

            # Skip if paused
            if self._trading_paused:
                return

            # Build BTC candles for market filter
            btc_candles_df = self._get_btc_candles()

            # Process candle through template trader
            candle_dict = {
                "open": candle.open,
                "high": candle.high,
                "low": candle.low,
                "close": candle.close,
                "volume": candle.volume,
                "timestamp": candle.timestamp,
            }

            signal = self.trader.process_candle(
                symbol=candle.symbol,
                candle=candle_dict,
                btc_candles_df=btc_candles_df,
            )

            if signal:
                self.trade_logger.info(f"Signal executed: {signal}")

        except Exception as e:
            self.error_logger.error(f"Error processing candle: {e}", exc_info=True)

    def _get_btc_candles(self) -> pd.DataFrame:
        """Get BTC candles for market filter."""
        from datetime import datetime

        now = int(datetime.utcnow().timestamp() * 1000)
        start = now - (200 * 60 * 1000)  # 200 1m bars

        candles = self.repository.get_range(
            symbol="BTCUSDT",
            start_ts=start,
            end_ts=now,
        )

        if not candles:
            return pd.DataFrame()

        return pd.DataFrame([{
            "open": c.open,
            "high": c.high,
            "low": c.low,
            "close": c.close,
            "volume": c.volume,
            "timestamp": c.timestamp,
        } for c in candles])

    async def run(self):
        """Run the shadow trading loop."""
        self._running = True

        # Setup signal handlers
        loop = asyncio.get_event_loop()
        for s in (sig.SIGTERM, sig.SIGINT):
            loop.add_signal_handler(s, lambda: asyncio.create_task(self.shutdown()))

        self.trade_logger.info(f"Starting shadow trading for symbols: {self._symbols}")

        # Create WebSocket client
        ws_client = BybitWebSocketClient(
            symbols=self._symbols,
            on_candle=self.on_candle,
            on_state_change=self.on_connection_state_change,
        )

        try:
            # Log startup
            self.trade_logger.info(
                f"Template Shadow Trading STARTED:\n"
                f"  Strategy: {self.trader.strategy_id}\n"
                f"  Symbol: {self.strategy_symbol}\n"
                f"  Timeframe: {self.trader.timeframe_minutes}m"
            )

            # Run WebSocket client (blocking)
            await ws_client.run()

        except Exception as e:
            self.error_logger.error(f"Error in shadow trading loop: {e}", exc_info=True)

    async def shutdown(self):
        """Graceful shutdown."""
        self.trade_logger.info("Shutting down template shadow trader...")
        self._running = False

        # Log final stats
        stats = self.trader.get_stats()
        self.trade_logger.info(
            f"Final stats:\n"
            f"  Equity: ${stats['paper_equity']:.2f}\n"
            f"  P&L: ${stats['total_pnl']:.2f} ({stats['total_pnl_pct']:.2f}%)\n"
            f"  Trades: {stats['trade_count']}\n"
            f"  Win Rate: {stats['win_rate']:.1%}"
        )



def main():
    parser = argparse.ArgumentParser(description="Run template strategy in shadow mode")
    parser.add_argument(
        "--strategy",
        type=str,
        required=True,
        help="Path to strategy JSON (relative to crypto/ dir)",
    )
    args = parser.parse_args()

    # Resolve strategy path
    crypto_dir = Path(__file__).parent
    strategy_path = crypto_dir / args.strategy

    if not strategy_path.exists():
        print(f"Error: Strategy file not found: {strategy_path}")
        sys.exit(1)

    # Run
    runner = TemplateShadowRunner(strategy_path)
    asyncio.run(runner.run())


if __name__ == "__main__":
    main()
