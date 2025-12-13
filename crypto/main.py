"""Entry point for crypto-alpha system."""
import argparse
import asyncio
import signal as sig
import sys
import pandas as pd
from pathlib import Path
from typing import Optional

from config import settings
from logs import setup_logging
from data.ingestion.bybit_ws import BybitWebSocketClient, ConnectionState
from data.storage.repository import CandleRepository
from data.storage.models import Candle
from data.quality_filters import CandleValidator
from execution.shadow.trader import ShadowTrader
from execution.shadow.pool_manager import ShadowPoolManager
from execution.shadow.hot_reload import check_reload_signal
from engine.strategy_logic.parser import GeneExpressionParser
from notifications import DiscordNotifier, NotificationScheduler


# Hardcoded test strategy (Phase 1 / fallback)
TEST_STRATEGY = {
    "strategy_name": "Phase1_Test_RSI_Mean_Reversion",
    "entry_long": "btc_trend(60) >= 0 AND norm_rsi(14) < -0.6",
    "exit_long": "norm_rsi(14) > 0.4",
    "entry_short": None,
    "exit_short": None,
}

# Top 29 Bybit Futures by volume (Phase 1 static universe)
# [*TO-DO*] - Fetch dynamically from Bybit API in Phase 2
SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT",
    "ADAUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT", "MATICUSDT",
    "LTCUSDT", "ATOMUSDT", "UNIUSDT", "ETCUSDT",
    "XLMUSDT", "NEARUSDT", "APTUSDT", "FILUSDT", "ARBUSDT",
    "OPUSDT", "INJUSDT", "SUIUSDT", "STXUSDT", "IMXUSDT",
    "LDOUSDT", "RNDRUSDT", "SEIUSDT", "TIAUSDT", "JUPUSDT",
]

# Phase 3: Reduced symbol set for initial shadow trading validation
PHASE3_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]


class CryptoAlphaSystem:
    """Main system orchestrator."""

    def __init__(self, use_shadow_pool: bool = False, symbols: list[str] = None):
        """
        Initialize the crypto alpha system.

        Args:
            use_shadow_pool: If True, use multi-strategy shadow pool manager.
                            If False, use single hardcoded strategy (Phase 1 mode).
            symbols: List of symbols to trade. Defaults to PHASE3_SYMBOLS if shadow pool,
                    otherwise full SYMBOLS list.
        """
        # Setup logging first
        self.trade_logger, self.error_logger = setup_logging(settings.logs_dir)
        self.trade_logger.info("Initializing crypto-alpha system")

        # Mode selection
        self.use_shadow_pool = use_shadow_pool

        # Initialize Discord notifications
        self.notifier: Optional[DiscordNotifier] = None
        self.scheduler: Optional[NotificationScheduler] = None
        if settings.discord_enabled:
            self.notifier = DiscordNotifier(settings.discord_webhook_url)
            self.trade_logger.info("Discord notifications enabled")

        # Initialize components
        self.repository = CandleRepository(settings.sqlite_path)
        self.validator = CandleValidator()
        self.parser = GeneExpressionParser()

        if use_shadow_pool:
            # Phase 3: Multi-strategy shadow pool (pass notifier)
            self.pool_manager = ShadowPoolManager(notifier=self.notifier)
            self.trader = None
            self.strategy = None
            self._symbols = symbols or PHASE3_SYMBOLS
            self.trade_logger.info(
                f"Shadow pool mode: {self.pool_manager.get_stats()['strategies_loaded']} strategies loaded"
            )
        else:
            # Phase 1: Single hardcoded strategy
            self.strategy = self.parser.parse(TEST_STRATEGY)
            self.trader = ShadowTrader(self.strategy)
            self.pool_manager = None
            self._symbols = symbols or SYMBOLS

        # State
        self._running = False
        self._candle_count = 0
        self._connection_state = ConnectionState.DISCONNECTED
        self._trading_paused = True  # Start paused until READY
        self._current_prices: dict[str, float] = {}  # Track latest prices
        self._reload_check_counter = 0  # Check for hot-reload every N candles

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

        # Send Discord alert on critical state changes
        if self.notifier and new_state == ConnectionState.DISCONNECTED and old_state != ConnectionState.DISCONNECTED:
            await self.notifier.send_connection_alert(
                state="DISCONNECTED",
                details="WebSocket connection lost. Attempting to reconnect...",
            )

    async def on_candle(self, candle: Candle) -> None:
        """Callback for each new candle from WebSocket."""
        try:
            # Validate candle quality
            result = self.validator.validate(candle)
            if not result.valid:
                self.error_logger.warning(
                    f"Invalid candle for {candle.symbol}: {result.reason}"
                )
                return

            if result.requires_warmup:
                self.trade_logger.info(
                    f"Data gap detected for {candle.symbol}, warmup required"
                )
                # Reset validator state for this symbol
                self.validator.reset(candle.symbol)

            # Store candle
            self.repository.insert(candle)
            self._candle_count += 1

            # Track current prices for stop-loss checks
            self._current_prices[candle.symbol] = candle.close

            # Log progress every 100 candles
            if self._candle_count % 100 == 0:
                self.trade_logger.info(
                    f"Processed {self._candle_count} candles, "
                    f"DB has {self.repository.count()} total"
                )

            # Check for hot-reload signal (every 50 candles, ~50 seconds)
            self._reload_check_counter += 1
            if self.use_shadow_pool and self._reload_check_counter >= 50:
                self._reload_check_counter = 0
                if check_reload_signal():
                    old_count = len(self.pool_manager.strategies)
                    new_count = self.pool_manager.reload_strategies()
                    self.trade_logger.info(
                        f"Hot-reload: {old_count} -> {new_count} strategies"
                    )

            # Get enough history for indicators (need at least 100 candles)
            candles = self.repository.get_latest(candle.symbol, limit=200)
            if len(candles) < 100:
                return  # Not enough data yet

            # Get BTC candles for market filter
            btc_candles = self.repository.get_latest("BTCUSDT", limit=200)
            if len(btc_candles) < 100:
                return  # Not enough BTC data yet

            # Convert to DataFrames
            df = self._candles_to_df(candles)
            btc_df = self._candles_to_df(btc_candles)

            # Process through shadow trader (skip BTC itself)
            # Only trade when connection is READY
            if candle.symbol != "BTCUSDT" and not self._trading_paused:
                if self.use_shadow_pool:
                    # Phase 3: Multi-strategy mode
                    signals = self.pool_manager.process_candle(
                        symbol=candle.symbol,
                        candles=df,
                        btc_candles=btc_df,
                        current_prices=self._current_prices,
                    )
                    for strategy_id, signal in signals:
                        self.trade_logger.info(
                            f"Signal: {signal.value} for {candle.symbol} [{strategy_id}]"
                        )
                else:
                    # Phase 1: Single strategy mode
                    signal = self.trader.process_candle(candle.symbol, df, btc_df)
                    if signal:
                        self.trade_logger.info(
                            f"Signal: {signal.value} for {candle.symbol}"
                        )

        except Exception as e:
            self.error_logger.exception(f"Error processing candle: {e}")

    def _candles_to_df(self, candles: list[Candle]) -> pd.DataFrame:
        """Convert Candle objects to DataFrame."""
        return pd.DataFrame([{
            'open': c.open,
            'high': c.high,
            'low': c.low,
            'close': c.close,
            'volume': c.volume,
        } for c in candles])

    async def run(self) -> None:
        """Main run loop."""
        self._running = True
        self.trade_logger.info(f"Starting with {len(self._symbols)} symbols: {self._symbols}")

        if self.use_shadow_pool:
            stats = self.pool_manager.get_stats()
            self.trade_logger.info(f"Mode: Shadow Pool ({stats['strategies_loaded']} strategies)")
            self.trade_logger.info(f"Initial equity: ${stats['initial_equity']:.2f}")
        else:
            self.trade_logger.info(f"Mode: Single Strategy")
            self.trade_logger.info(f"Strategy: {self.strategy.name}")
            self.trade_logger.info(f"Entry: {self.strategy.entry_long}")
            self.trade_logger.info(f"Exit: {self.strategy.exit_long}")

        # Start notification scheduler if enabled
        if self.notifier and self.use_shadow_pool:
            self.scheduler = NotificationScheduler(
                notifier=self.notifier,
                get_stats=self.pool_manager.get_stats,
            )
            await self.scheduler.start()

            # Send startup notification
            startup_stats = self.pool_manager.get_stats()
            await self.notifier.send_startup(startup_stats)

        # Create WebSocket client
        client = BybitWebSocketClient(
            symbols=self._symbols,
            on_candle=self.on_candle,
            interval="1",
            on_state_change=self.on_connection_state_change,
        )

        # Handle graceful shutdown
        def shutdown(signum, frame):
            self.trade_logger.info("Shutdown signal received")
            self._running = False
            client.stop()

            # Print final stats
            self.trade_logger.info("=== Final Stats ===")
            self.trade_logger.info(f"Total candles: {self._candle_count}")

            if self.use_shadow_pool:
                stats = self.pool_manager.get_stats()
                self.trade_logger.info(f"Paper Equity: ${stats['paper_equity']:.2f}")
                self.trade_logger.info(f"Total P&L: ${stats['total_pnl']:.2f} ({stats['total_pnl_pct']:.2f}%)")
                self.trade_logger.info(f"Open positions: {stats['open_positions']}")
                self.trade_logger.info("Strategy Performance:")
                for sid, perf in stats['strategy_performance'].items():
                    self.trade_logger.info(
                        f"  {perf['name']}: {perf['trade_count']} trades, "
                        f"{perf['win_rate']:.1%} win rate, ${perf['total_pnl']:.2f} P&L"
                    )
            else:
                stats = self.trader.get_stats()
                self.trade_logger.info(f"Equity: ${stats['equity']:.2f}")
                self.trade_logger.info(f"Total P&L: ${stats['total_pnl']:.2f} ({stats['total_pnl_pct']:.2f}%)")
                self.trade_logger.info(f"Trades: {stats['trade_count']}")
                self.trade_logger.info(f"Win rate: {stats['win_rate']:.1%}")

        sig.signal(sig.SIGINT, shutdown)
        sig.signal(sig.SIGTERM, shutdown)

        # Run WebSocket client
        self.trade_logger.info(f"Connecting to Bybit WebSocket...")
        await client.run()

        # Cleanup after WebSocket stops (on shutdown)
        await self._cleanup()

    async def _cleanup(self) -> None:
        """Clean up resources on shutdown."""
        # Stop notification scheduler
        if self.scheduler:
            await self.scheduler.stop()

        # Send shutdown notification with final stats
        if self.notifier:
            final_stats = None
            if self.use_shadow_pool and self.pool_manager:
                final_stats = self.pool_manager.get_stats()
            elif self.trader:
                final_stats = self.trader.get_stats()

            await self.notifier.send_shutdown(final_stats)
            await self.notifier.close()


async def main():
    """Entry point."""
    parser = argparse.ArgumentParser(
        description="Crypto Alpha Trading System"
    )
    parser.add_argument(
        "--shadow-pool",
        action="store_true",
        help="Use multi-strategy shadow pool (Phase 3 mode)",
    )
    parser.add_argument(
        "--symbols",
        type=str,
        default=None,
        help="Comma-separated list of symbols to trade (e.g., BTCUSDT,ETHUSDT,SOLUSDT)",
    )
    parser.add_argument(
        "--all-symbols",
        action="store_true",
        help="Use all 29 symbols instead of Phase 3 default",
    )
    parser.add_argument(
        "--run-lifecycle",
        action="store_true",
        help="Run strategy lifecycle review (retire/promote)",
    )

    args = parser.parse_args()

    if args.run_lifecycle:
        from execution.shadow.pool_manager import ShadowPoolManager
        from execution.shadow.lifecycle import StrategyLifecycleManager
        
        # Setup logging
        setup_logging(settings.logs_dir)
        
        print("Running strategy lifecycle review...")
        pool_manager = ShadowPoolManager()  # Loads current state
        lifecycle_manager = StrategyLifecycleManager(pool_manager)
        report = lifecycle_manager.run_review_cycle()
        print(f"Lifecycle Review Complete.")
        print(f"  Retired: {len(report.retired)}")
        print(f"  Promoted Candidates: {len(report.promoted_candidates)}")
        return


    # Determine symbols
    symbols = None
    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",")]
    elif args.all_symbols:
        symbols = SYMBOLS

    system = CryptoAlphaSystem(
        use_shadow_pool=args.shadow_pool,
        symbols=symbols,
    )
    await system.run()


if __name__ == "__main__":
    asyncio.run(main())
