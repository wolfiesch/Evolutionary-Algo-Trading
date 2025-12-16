"""Position tracking for equities shadow trading."""
import json
import logging
from dataclasses import dataclass, asdict
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from .models import Position, ExitReason


logger = logging.getLogger(__name__)


@dataclass
class PositionTrackerConfig:
    """Configuration for position tracking."""
    max_positions: int = 20
    max_position_pct: float = 0.05  # 5% max per position
    max_exposure_pct: float = 0.80  # 80% max total exposure
    default_stop_loss_pct: float = 0.05  # 5% stop loss
    max_holding_days: int = 20  # Max days to hold a position


class PositionTracker:
    """
    Manages open positions for shadow trading.

    Responsibilities:
    - Track all open positions
    - Enforce position limits
    - Calculate exposure and risk metrics
    - Persist state to disk
    """

    def __init__(
        self,
        config: Optional[PositionTrackerConfig] = None,
        state_path: Optional[Path] = None,
    ):
        self.config = config or PositionTrackerConfig()
        self.positions: dict[str, Position] = {}  # symbol -> Position
        self.state_path = state_path

        # Load persisted state if available
        if self.state_path and self.state_path.exists():
            self._load_state()

    def can_open_position(self, equity: float, position_value: float) -> tuple[bool, str]:
        """
        Check if a new position can be opened.

        Returns:
            (can_open, reason) - True if allowed, False with explanation if not
        """
        # Check max positions
        if len(self.positions) >= self.config.max_positions:
            return False, f"Max positions ({self.config.max_positions}) reached"

        # Check max position size
        max_position = equity * self.config.max_position_pct
        if position_value > max_position:
            return False, f"Position size ${position_value:.2f} exceeds max ${max_position:.2f}"

        # Check total exposure
        current_exposure = self.get_exposure(equity)
        pending_exposure = current_exposure + (position_value / equity)
        if pending_exposure > self.config.max_exposure_pct:
            return (
                False,
                f"Would breach max exposure: current {current_exposure:.1%} + "
                f"pending {position_value/equity:.1%} = {pending_exposure:.1%} > "
                f"{self.config.max_exposure_pct:.0%}"
            )

        return True, "OK"

    def add_position(self, position: Position) -> None:
        """Add a new position."""
        if position.symbol in self.positions:
            logger.warning(f"Overwriting existing position for {position.symbol}")

        self.positions[position.symbol] = position
        self._save_state()
        logger.info(
            f"Opened position: {position.symbol} @ ${position.entry_price:.2f} "
            f"({position.shares:.2f} shares, ${position.notional_value:.2f})"
        )

    def remove_position(self, symbol: str) -> Optional[Position]:
        """Remove and return a position."""
        position = self.positions.pop(symbol, None)
        if position:
            self._save_state()
            logger.info(f"Closed position: {symbol}")
        return position

    def get_position(self, symbol: str) -> Optional[Position]:
        """Get a position by symbol."""
        return self.positions.get(symbol)

    def has_position(self, symbol: str) -> bool:
        """Check if we have a position in a symbol."""
        return symbol in self.positions

    def get_all_positions(self) -> list[Position]:
        """Get all open positions."""
        return list(self.positions.values())

    def get_exposure(self, equity: float) -> float:
        """Calculate total exposure as fraction of equity."""
        if equity <= 0:
            return 0.0
        total_notional = sum(p.notional_value for p in self.positions.values())
        return total_notional / equity

    def get_exposure_value(self) -> float:
        """Get total exposure value in dollars."""
        return sum(p.notional_value for p in self.positions.values())

    def get_unrealized_pnl(self, prices: dict[str, float]) -> float:
        """Calculate total unrealized P&L given current prices."""
        total = 0.0
        for symbol, position in self.positions.items():
            if symbol in prices:
                total += position.unrealized_pnl(prices[symbol])
        return total

    def get_positions_needing_stop(
        self,
        prices: dict[str, float]
    ) -> list[tuple[Position, float]]:
        """Get positions that should be stopped out."""
        stops = []
        for symbol, position in self.positions.items():
            if symbol in prices:
                current_price = prices[symbol]
                if position.should_stop_out(current_price):
                    stops.append((position, current_price))
        return stops

    def get_positions_exceeding_hold_time(
        self,
        current_date: date
    ) -> list[Position]:
        """Get positions that exceed max holding period."""
        expired = []
        for position in self.positions.values():
            days = position.days_held(current_date)
            if days >= self.config.max_holding_days:
                expired.append(position)
        return expired

    def get_position_summary(
        self,
        prices: dict[str, float],
        current_date: date
    ) -> list[dict]:
        """Get summary of all positions with current prices."""
        summaries = []
        for symbol, position in self.positions.items():
            current_price = prices.get(symbol, position.entry_price)
            summaries.append({
                "symbol": symbol,
                "strategy_id": position.strategy_id,
                "entry_date": position.entry_date.isoformat(),
                "entry_price": position.entry_price,
                "current_price": current_price,
                "shares": position.shares,
                "notional_value": position.notional_value,
                "unrealized_pnl": position.unrealized_pnl(current_price),
                "unrealized_pnl_pct": position.unrealized_pnl_pct(current_price),
                "days_held": position.days_held(current_date),
                "stop_loss_price": position.stop_loss_price,
            })
        return sorted(summaries, key=lambda x: x["unrealized_pnl_pct"], reverse=True)

    def _save_state(self) -> None:
        """Persist position state to disk."""
        if not self.state_path:
            return

        self.state_path.parent.mkdir(parents=True, exist_ok=True)

        state = {
            "timestamp": datetime.utcnow().isoformat(),
            "positions": {}
        }

        for symbol, position in self.positions.items():
            state["positions"][symbol] = {
                "symbol": position.symbol,
                "strategy_id": position.strategy_id,
                "entry_date": position.entry_date.isoformat(),
                "entry_price": position.entry_price,
                "shares": position.shares,
                "notional_value": position.notional_value,
                "side": position.side,
                "stop_loss_price": position.stop_loss_price,
                "stop_loss_pct": position.stop_loss_pct,
                "insider_intensity": position.insider_intensity,
                "revenue_cagr": position.revenue_cagr,
            }

        with open(self.state_path, "w") as f:
            json.dump(state, f, indent=2)

    def _load_state(self) -> None:
        """Load position state from disk."""
        if not self.state_path or not self.state_path.exists():
            return

        try:
            with open(self.state_path, "r") as f:
                state = json.load(f)

            for symbol, pos_data in state.get("positions", {}).items():
                position = Position(
                    symbol=pos_data["symbol"],
                    strategy_id=pos_data["strategy_id"],
                    entry_date=date.fromisoformat(pos_data["entry_date"]),
                    entry_price=pos_data["entry_price"],
                    shares=pos_data["shares"],
                    notional_value=pos_data["notional_value"],
                    side=pos_data.get("side", "LONG"),
                    stop_loss_price=pos_data.get("stop_loss_price"),
                    stop_loss_pct=pos_data.get("stop_loss_pct", 0.05),
                    insider_intensity=pos_data.get("insider_intensity"),
                    revenue_cagr=pos_data.get("revenue_cagr"),
                )
                self.positions[symbol] = position

            logger.info(f"Loaded {len(self.positions)} positions from state file")
        except Exception as e:
            logger.error(f"Failed to load position state: {e}")

    def clear_all(self) -> list[Position]:
        """Clear all positions (for kill switch). Returns cleared positions."""
        cleared = list(self.positions.values())
        self.positions.clear()
        self._save_state()
        logger.warning(f"Cleared all {len(cleared)} positions")
        return cleared
