"""Entry point for crypto-alpha system."""
import asyncio
import signal as sig
import sys
import pandas as pd
from pathlib import Path

from config import settings
from logs import setup_logging
from data.ingestion.bybit_ws import BybitWebSocketClient
from data.storage.repository import CandleRepository
from data.storage.models import Candle
from data.quality_filters import CandleValidator
from execution.shadow.trader import ShadowTrader
from engine.strategy_logic.parser import GeneExpressionParser


# Hardcoded test strategy (Phase 1)
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


class CryptoAlphaSystem:
    """Main system orchestrator."""

    def __init__(self):
        # Setup logging first
        self.trade_logger, self.error_logger = setup_logging(settings.logs_dir)
        self.trade_logger.info("Initializing crypto-alpha system")

        # Initialize components
        self.repository = CandleRepository(settings.sqlite_path)
        self.validator = CandleValidator()
        self.parser = GeneExpressionParser()
        self.strategy = self.parser.parse(TEST_STRATEGY)
        self.trader = ShadowTrader(self.strategy)

        # State
        self._running = False
        self._candle_count = 0
        self._symbols = SYMBOLS

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

            # Log progress every 100 candles
            if self._candle_count % 100 == 0:
                self.trade_logger.info(
                    f"Processed {self._candle_count} candles, "
                    f"DB has {self.repository.count()} total"
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
            if candle.symbol != "BTCUSDT":
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
        self.trade_logger.info(f"Starting with {len(self._symbols)} symbols")
        self.trade_logger.info(f"Strategy: {self.strategy.name}")
        self.trade_logger.info(f"Entry: {self.strategy.entry_long}")
        self.trade_logger.info(f"Exit: {self.strategy.exit_long}")

        # Create WebSocket client
        client = BybitWebSocketClient(
            symbols=self._symbols,
            on_candle=self.on_candle,
            interval="1",
        )

        # Handle graceful shutdown
        def shutdown(signum, frame):
            self.trade_logger.info("Shutdown signal received")
            self._running = False
            client.stop()

            # Print final stats
            stats = self.trader.get_stats()
            self.trade_logger.info("=== Final Stats ===")
            self.trade_logger.info(f"Total candles: {self._candle_count}")
            self.trade_logger.info(f"Equity: ${stats['equity']:.2f}")
            self.trade_logger.info(f"Total P&L: ${stats['total_pnl']:.2f} ({stats['total_pnl_pct']:.2f}%)")
            self.trade_logger.info(f"Trades: {stats['trade_count']}")
            self.trade_logger.info(f"Win rate: {stats['win_rate']:.1%}")

        sig.signal(sig.SIGINT, shutdown)
        sig.signal(sig.SIGTERM, shutdown)

        # Run WebSocket client
        self.trade_logger.info(f"Connecting to Bybit WebSocket...")
        await client.run()


async def main():
    """Entry point."""
    system = CryptoAlphaSystem()
    await system.run()


if __name__ == "__main__":
    asyncio.run(main())
