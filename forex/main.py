import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path to allow shared imports if needed
sys.path.append(str(Path(__file__).parent.parent))

import structlog
from forex.config import settings
from forex.data.storage.repository import ForexCandleRepository
from forex.data.ingestion.oanda_stream import OandaStreamer
from forex.execution.shadow.trader import ForexShadowTrader

# Setup Logging
logging.basicConfig(
    format="%(message)s",
    stream=sys.stdout,
    level=logging.INFO,
)
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
    logger_factory=structlog.stdlib.LoggerFactory(),
)
logger = structlog.get_logger()


async def main():
    logger.info("Forex System Starting", env=settings.oanda_env, pairs=settings.pairs)
    
    # Initialize Storage
    repo = ForexCandleRepository(settings.sqlite_path)
    logger.info(f"Database initialized at {settings.sqlite_path}")
    
    # Initialize Ingestion
    streamer = OandaStreamer(repo)
    
    # Initialize Shadow Trader
    trader = ForexShadowTrader(repo)
    
    # Run
    ingestion_task = asyncio.create_task(streamer.start())
    trader_task = asyncio.create_task(trader.start())
    
    try:
        # Keep main alive and monitor tasks
        while True:
            await asyncio.sleep(1)
            if float(settings.oanda_access_token or 0) == 0 and not streamer.is_mock:
                 logger.warning("No token found, but streamer not in mock mode? Check logic.")
                 
    except asyncio.CancelledError:
        logger.info("Shutdown requested")
        streamer.stop()
        trader.stop()
        await asyncio.gather(ingestion_task, trader_task)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
