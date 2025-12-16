"""Shadow (paper) trading infrastructure for equities."""
from .models import (
    SignalType,
    ExitReason,
    Position,
    TradeLog,
    Signal,
    PortfolioSnapshot,
    DailySummary,
)
from .position_tracker import PositionTracker, PositionTrackerConfig
from .trader import EquitiesShadowTrader, ShadowTraderConfig
from .reporter import ReportGenerator

__all__ = [
    # Models
    "SignalType",
    "ExitReason",
    "Position",
    "TradeLog",
    "Signal",
    "PortfolioSnapshot",
    "DailySummary",
    # Position tracking
    "PositionTracker",
    "PositionTrackerConfig",
    # Trader
    "EquitiesShadowTrader",
    "ShadowTraderConfig",
    # Reporting
    "ReportGenerator",
]
