"""Shadow (paper) trading module."""
from .position import Position
from .trader import ShadowTrader, TradeLog
from .pool_manager import ShadowPoolManager, StrategyPerformance, ShadowPoolState

__all__ = [
    "Position",
    "ShadowTrader",
    "TradeLog",
    "ShadowPoolManager",
    "StrategyPerformance",
    "ShadowPoolState",
]
