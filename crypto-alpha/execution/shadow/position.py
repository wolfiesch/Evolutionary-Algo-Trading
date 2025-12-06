"""Position tracking for shadow trading."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Position:
    """Open position state."""
    symbol: str
    strategy_id: str
    entry_time: int  # Unix timestamp milliseconds
    entry_price: float
    size_usdt: float
    side: str = "LONG"  # Only LONG for Phase 1
    stop_loss_price: Optional[float] = None

    @property
    def entry_datetime(self) -> datetime:
        """Convert entry timestamp to datetime."""
        return datetime.fromtimestamp(self.entry_time / 1000)

    def unrealized_pnl(self, current_price: float) -> float:
        """Calculate unrealized P&L at current price."""
        if self.side == "LONG":
            return self.size_usdt * (current_price / self.entry_price - 1)
        else:
            return self.size_usdt * (1 - current_price / self.entry_price)

    def unrealized_pnl_pct(self, current_price: float) -> float:
        """Calculate unrealized P&L percentage."""
        if self.side == "LONG":
            return (current_price / self.entry_price - 1) * 100
        else:
            return (1 - current_price / self.entry_price) * 100
