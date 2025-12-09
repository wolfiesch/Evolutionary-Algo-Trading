"""Fitness data models - asset-agnostic."""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class FitnessResult:
    """
    Complete fitness evaluation result.

    Phase 2A: Sharpe-only score.
    Phase 2B: Full regime testing with multipliers.
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

    # Phase 2B: Regime testing
    regime_scores: dict[str, float] = field(default_factory=dict)
    regime_trade_counts: dict[str, int] = field(default_factory=dict)
    regime_pass_count: int = 0
    regime_multiplier: float = 1.0
    drawdown_multiplier: float = 1.0

    # Regime testing mode
    regime_testing_enabled: bool = False
    negative_regime: Optional[str] = None  # Which regime had negative Sharpe

    def summary(self) -> dict:
        """Return summary dict for logging."""
        base = {
            "final_score": f"{self.final_score:.3f}",
            "sharpe_ratio": f"{self.sharpe_ratio:.2f}",
            "max_drawdown": f"{self.max_drawdown:.1%}",
            "trade_count": self.trade_count,
            "win_rate": f"{self.win_rate:.1%}",
            "disqualified": self.disqualified,
            "reason": self.disqualification_reason or "N/A",
        }

        # Add regime info if enabled
        if self.regime_testing_enabled:
            base["regime_pass_count"] = f"{self.regime_pass_count}/5"
            base["regime_multiplier"] = f"{self.regime_multiplier:.2f}"

        return base

    def regime_summary(self) -> str:
        """Return formatted regime scores summary."""
        if not self.regime_scores:
            return "No regime scores"

        lines = []
        for regime, sharpe in sorted(self.regime_scores.items()):
            trade_count = self.regime_trade_counts.get(regime, 0)
            passed = "PASS" if sharpe >= 0.5 else "FAIL" if sharpe >= 0 else "NEG!"
            lines.append(f"  {regime}: Sharpe={sharpe:.2f} ({trade_count} trades) [{passed}]")

        return "\n".join(lines)
