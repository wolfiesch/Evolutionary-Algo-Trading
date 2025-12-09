"""Shadow (paper) trading module."""
from .position import Position
from .trader import ShadowTrader, TradeLog
from .pool_manager import ShadowPoolManager, StrategyPerformance, ShadowPoolState
from .hot_reload import StrategyWatcher, check_reload_signal

__all__ = [
    "Position",
    "ShadowTrader",
    "TradeLog",
    "ShadowPoolManager",
    "StrategyPerformance",
    "ShadowPoolState",
    "StrategyWatcher",
    "check_reload_signal",
]
