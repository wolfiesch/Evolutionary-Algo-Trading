"""Fitness data models - asset-agnostic."""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class FitnessResult:
    """
    Complete fitness evaluation result.

    Phase 2A: Sharpe-only score.
    Phase 2B+: Will add regime_scores, regime_pass_count, etc.
    """
    # Core metrics (from backtest)
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    trade_count: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    total_return: float = 0.0

    # Fitness score
    final_score: float = 0.0

    # Disqualification
    disqualified: bool = False
    disqualification_reason: Optional[str] = None

    # Phase 2B+: Regime testing (placeholder for now)
    regime_scores: dict[str, float] = field(default_factory=dict)
    regime_pass_count: int = 0
    regime_multiplier: float = 1.0
    drawdown_multiplier: float = 1.0

    def summary(self) -> dict:
        """Return summary dict for logging."""
        return {
            "final_score": f"{self.final_score:.3f}",
            "sharpe_ratio": f"{self.sharpe_ratio:.2f}",
            "max_drawdown": f"{self.max_drawdown:.1%}",
            "trade_count": self.trade_count,
            "win_rate": f"{self.win_rate:.1%}",
            "disqualified": self.disqualified,
            "reason": self.disqualification_reason or "N/A",
        }
