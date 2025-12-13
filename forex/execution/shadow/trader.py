"""
Forex Shadow Trader (Phase 1 Sanity Check)
Executes random trades to verify plumbing.
"""
import logging
import random
import time
import asyncio
from dataclasses import dataclass
from typing import Dict

from forex.config import settings
from forex.data.storage.repository import ForexCandleRepository

logger = logging.getLogger("forex.shadow")

@dataclass
class ForexPosition:
    symbol: str
    entry_price: float
    entry_time: int
    units: int # OANDA uses units, not "size_usdt" directly, but we can simplify
    side: str = "LONG"

class ForexShadowTrader:
    def __init__(self, repository: ForexCandleRepository):
        self.repo = repository
        self.equity = settings.initial_equity
        self.positions: Dict[str, ForexPosition] = {}
        self.running = False
        
        # Stats
        self.trades_count = 0
        self.total_pnl = 0.0

    async def start(self):
        self.running = True
        logger.info(f"Starting Forex Shadow Trader (Equity: ${self.equity:.2f})")
        while self.running:
            await self._tick()
            await asyncio.sleep(5) # 5s tick

    async def _tick(self):
        """Check all pairs for random signals."""
        for pair in settings.pairs:
            # Get latest price
            candles = self.repo.get_latest(pair, limit=1)
            if not candles:
                continue
            
            latest = candles[0]
            price = latest.close
            
            # Trading Logic
            if pair in self.positions:
                # 10% chance to close
                if random.random() < 0.10:
                    self._close_position(pair, price)
            else:
                # 5% chance to open
                if random.random() < 0.05:
                    self._open_position(pair, price)

    def _get_pip_size(self, pair: str) -> float:
        if "JPY" in pair:
            return 0.01
        return 0.0001

    def _apply_friction(self, price: float, pair: str, side: str) -> float:
        pip = self._get_pip_size(pair)
        cost = settings.friction_pips * pip
        if side == "BUY":
            return price + cost
        else:
            return price - cost

    def _open_position(self, pair: str, price: float):
        # Position Sizing: 10% of equity
        size_allocation = self.equity * 0.10
        # Units = Allocation / Price (Simplified, assuming non-leverage for sanity)
        units = int(size_allocation / price) 
        
        # Friction
        fill_price = self._apply_friction(price, pair, "BUY")
        
        pos = ForexPosition(
            symbol=pair,
            entry_price=fill_price,
            entry_time=int(time.time() * 1000),
            units=units
        )
        self.positions[pair] = pos
        logger.info(f"OPEN LONG {pair} @ {fill_price:.5f} ({units} units)")

    def _close_position(self, pair: str, price: float):
        pos = self.positions[pair]
        fill_price = self._apply_friction(price, pair, "SELL")
        
        # PnL = (Exit - Entry) * Units
        # Note: If Quote currency is USD (EUR_USD), this is PnL in USD.
        # If Quote is JPY (USD_JPY), this is PnL in JPY. Need conversion.
        # Phase 1 Limitation: Assume Account is USD, and ignore currency conversion for non-USD quote pairs (sanity check only)
        # OR just handle USD quote pairs correctly.
        
        raw_pnl = (fill_price - pos.entry_price) * pos.units
        
        # Quick conversion hack for Phase 1 MVP
        if pair.endswith("_JPY"):
            raw_pnl /= price # Divide by USDJPY to get USD? approx
        elif pair.endswith("_CHF"):
            raw_pnl /= price 
            
        self.equity += raw_pnl
        self.total_pnl += raw_pnl
        self.trades_count += 1
        
        del self.positions[pair]
        logger.info(f"CLOSE LONG {pair} @ {fill_price:.5f} | PnL: ${raw_pnl:.2f} | Eq: ${self.equity:.2f}")

    def stop(self):
        self.running = False
