"""
OANDA Data Streamer
Handles connection to OANDA V20 API and streaming/polling of data.
Includes 'Mock' mode for testing without credentials.
"""
import asyncio
import logging
import random
import time
from datetime import datetime

# Try importing oandapy, fail gracefully if not installed
try:
    import oandapyV20
    import oandapyV20.endpoints.instruments as instruments
    # import oandapyV20.endpoints.pricing as pricing # Unused for now
    HAS_OANDA = True
except ImportError:
    HAS_OANDA = False

from forex.config import settings
from crypto.data.storage.models import Candle # Reuse universal model
from forex.data.storage.repository import ForexCandleRepository

logger = logging.getLogger("forex.ingestion")

class OandaStreamer:
    def __init__(self, repository: ForexCandleRepository):
        self.repo = repository
        self.running = False
        self.client = None
        self.account_id = settings.oanda_account_id
        self.access_token = settings.oanda_access_token
        self.pairs = settings.pairs
        
        # Mode detection
        self.is_mock = False
        if not HAS_OANDA:
            logger.warning("oandapyV20 not installed. Forcing MOCK mode.")
            self.is_mock = True
        elif not self.access_token or not self.account_id:
            logger.warning("OANDA Credentials missing. Forcing MOCK mode.")
            self.is_mock = True
        else:
            self.client = oandapyV20.API(access_token=self.access_token, environment=settings.oanda_env)
            
    async def start(self):
        """Start the data stream loop."""
        self.running = True
        logger.info(f"Starting OandaStreamer (Mock Mode: {self.is_mock})")
        
        while self.running:
            try:
                if self.is_mock:
                    await self._run_mock_loop()
                else:
                    await self._run_live_loop()
            except Exception as e:
                logger.error(f"Streamer error: {e}")
                await asyncio.sleep(settings.reconnect_delay_seconds)

    async def _run_mock_loop(self):
        """Generate synthetic candles for testing."""
        logger.info("Generating mock candles...")
        while self.running:
            # Generate 1 candle per pair
            candles = []
            now_ts = int(time.time() * 1000)
            
            for pair in self.pairs:
                # Random walk logic
                prev_price = 1.1000 if "EUR" in pair else 100.00
                
                # Try fetch last candle to chain price
                last_candles = self.repo.get_latest(pair, limit=1)
                if last_candles:
                    prev_price = last_candles[0].close
                
                change = (random.random() - 0.5) * 0.0010 # +/- 10 pips
                close = prev_price + change
                
                c = Candle(
                    symbol=pair,
                    timestamp=now_ts,
                    open=prev_price,
                    high=max(prev_price, close) + 0.0002,
                    low=min(prev_price, close) - 0.0002,
                    close=close,
                    volume=random.randint(100, 1000),
                    turnover=0.0
                )
                candles.append(c)
            
            # Save
            if candles:
                self.repo.insert_batch(candles)
                logger.info(f"Mock: Inserted {len(candles)} candles. {candles[0].symbol}: {candles[0].close:.5f}")
            
            # Wait for next "candle" (speed up compared to real 1m)
            await asyncio.sleep(5) 

    async def _run_live_loop(self):
        """Poll OANDA for latest candles."""
        # Polling strategy for Phase 1 (Simpler than Stream parsing)
        logger.info("Polling OANDA API...")
        while self.running:
            for pair in self.pairs:
                await self._fetch_latest_candle(pair)
                await asyncio.sleep(0.5) # Rate limit protection
            
            # Wait for remainder of minute? or polling cycle?
            # 5s polling for 'live' feel
            await asyncio.sleep(5)

    async def _fetch_latest_candle(self, pair):
        """Fetch M1 candle from OANDA."""
        # Note: OANDA strings use underscores, e.g. EUR_USD
        params = {
            "count": 5,
            "granularity": settings.candle_interval # M1
        }
        r = instruments.InstrumentsCandles(instrument=pair, params=params)
        try:
            self.client.request(r)
            data = r.response
            candles_obj = data.get("candles", [])
            
            parsed = []
            for c in candles_obj:
                if c["complete"]:
                    # OANDA time is ISO8601. Convert to ms timestamp
                    # "2023-10-05T10:00:00.000000000Z"
                    dt = datetime.strptime(c["time"].split(".")[0], "%Y-%m-%dT%H:%M:%S")
                    ts = int(dt.replace(tzinfo=None).timestamp() * 1000)
                    
                    parsed.append(Candle(
                        symbol=pair,
                        timestamp=ts,
                        open=float(c["mid"]["o"]),
                        high=float(c["mid"]["h"]),
                        low=float(c["mid"]["l"]),
                        close=float(c["mid"]["c"]),
                        volume=float(c["volume"]),
                        turnover=0.0
                    ))
            
            if parsed:
                self.repo.insert_batch(parsed)
                logger.debug(f"Inserted {len(parsed)} candles for {pair}")
                
        except Exception as e:
            logger.error(f"OANDA API Error for {pair}: {e}")

    def stop(self):
        self.running = False
