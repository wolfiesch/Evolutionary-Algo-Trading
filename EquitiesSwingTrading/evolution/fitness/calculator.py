"""
Fitness Calculator for Equities Swing Trading.

Calculates strategy fitness with regime-aware scoring:
- Base Sharpe ratio
- Drawdown penalty
- Trade frequency penalty
- Regime consistency bonus

Fitness requirements:
- Sharpe > 0.5 in 4/5 regimes
- Max drawdown < 25%
- Minimum 20 trades
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd
import numpy as np

from evolution.fitness.regime_classifier import MarketRegime

logger = logging.getLogger(__name__)


@dataclass
class FitnessConfig:
    """Configuration for fitness calculation."""
    # Sharpe bounds
    min_sharpe: float = -5.0
    max_sharpe: float = 5.0

    # Penalties
    drawdown_penalty_factor: float = 2.0
    trade_penalty_threshold: int = 20      # Min trades for full score
    trade_penalty_factor: float = 0.5

    # Disqualification thresholds
    min_trades: int = 5
    max_drawdown_threshold: float = 0.50   # 50% = disqualified

    # Regime requirements
    min_regimes_positive: int = 4          # 4/5 regimes with Sharpe > 0.5
    regime_sharpe_threshold: float = 0.5
    regime_penalty_factor: float = 1.0

    # Annualization (for daily bars)
    trading_days_per_year: int = 252

    # Sentinel value for disqualification
    disqualified_score: float = -999.0


@dataclass
class BacktestResults:
    """Results from a backtest run."""
    # Equity curve
    equity_curve: pd.Series = field(default_factory=pd.Series)
    final_equity: float = 0.0

    # Trade statistics
    trade_count: int = 0
    win_count: int = 0
    loss_count: int = 0

    # Performance metrics
    total_return: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0

    # Regime-specific
    regime: Optional[str] = None


@dataclass
class FitnessResult:
    """Result of fitness calculation."""
    score: float
    base_sharpe: float
    drawdown_penalty: float
    trade_penalty: float
    regime_penalty: float
    regime_bonus: float
    is_disqualified: bool
    disqualification_reason: Optional[str]

    # Component scores
    regime_scores: dict = field(default_factory=dict)


class EquitiesFitnessCalculator:
    """
    Calculate fitness score for equities strategies.

    Scoring formula:
        score = (base_sharpe + regime_bonus) * regime_multiplier
                - drawdown_penalty
                - trade_penalty
                - regime_penalty

    Disqualification:
        - Less than 5 trades
        - Max drawdown > 50%
    """

    def __init__(self, config: Optional[FitnessConfig] = None):
        """
        Initialize calculator.

        Args:
            config: Fitness calculation configuration
        """
        self.config = config or FitnessConfig()

    def calculate(
        self,
        results: BacktestResults,
        regime_results: Optional[dict[str, BacktestResults]] = None,
    ) -> FitnessResult:
        """
        Calculate fitness score.

        Args:
            results: Overall backtest results
            regime_results: Optional dict of regime -> BacktestResults

        Returns:
            FitnessResult with score and breakdown
        """
        # Check for disqualification
        disqualified, reason = self._check_disqualification(results)

        if disqualified:
            return FitnessResult(
                score=self.config.disqualified_score,
                base_sharpe=results.sharpe_ratio,
                drawdown_penalty=0.0,
                trade_penalty=0.0,
                regime_penalty=0.0,
                regime_bonus=0.0,
                is_disqualified=True,
                disqualification_reason=reason,
            )

        # Calculate components
        base_sharpe = self._calculate_base_sharpe(results)
        drawdown_penalty = self._calculate_drawdown_penalty(results)
        trade_penalty = self._calculate_trade_penalty(results)

        # Regime analysis
        regime_bonus = 0.0
        regime_penalty = 0.0
        regime_scores = {}

        if regime_results:
            regime_bonus, regime_penalty, regime_scores = self._calculate_regime_scores(
                regime_results
            )

        # Final score
        score = (
            base_sharpe
            + regime_bonus
            - drawdown_penalty
            - trade_penalty
            - regime_penalty
        )

        return FitnessResult(
            score=score,
            base_sharpe=base_sharpe,
            drawdown_penalty=drawdown_penalty,
            trade_penalty=trade_penalty,
            regime_penalty=regime_penalty,
            regime_bonus=regime_bonus,
            is_disqualified=False,
            disqualification_reason=None,
            regime_scores=regime_scores,
        )

    def _check_disqualification(
        self,
        results: BacktestResults,
    ) -> tuple[bool, Optional[str]]:
        """Check if results should be disqualified."""
        if results.trade_count < self.config.min_trades:
            return True, f"Too few trades: {results.trade_count} < {self.config.min_trades}"

        if results.max_drawdown > self.config.max_drawdown_threshold:
            return True, f"Max drawdown too high: {results.max_drawdown:.1%} > {self.config.max_drawdown_threshold:.1%}"

        return False, None

    def _calculate_base_sharpe(self, results: BacktestResults) -> float:
        """Calculate clamped base Sharpe ratio."""
        sharpe = results.sharpe_ratio

        # Clamp to bounds
        sharpe = max(self.config.min_sharpe, min(self.config.max_sharpe, sharpe))

        return sharpe

    def _calculate_drawdown_penalty(self, results: BacktestResults) -> float:
        """Calculate penalty for drawdown."""
        return self.config.drawdown_penalty_factor * results.max_drawdown

    def _calculate_trade_penalty(self, results: BacktestResults) -> float:
        """Calculate penalty for insufficient trades."""
        if results.trade_count >= self.config.trade_penalty_threshold:
            return 0.0

        # Linear penalty from 0 to trade_penalty_factor
        ratio = results.trade_count / self.config.trade_penalty_threshold
        return self.config.trade_penalty_factor * (1.0 - ratio)

    def _calculate_regime_scores(
        self,
        regime_results: dict[str, BacktestResults],
    ) -> tuple[float, float, dict]:
        """
        Calculate regime-based bonus and penalty.

        Returns:
            (bonus, penalty, regime_scores_dict)
        """
        regime_scores = {}
        positive_regimes = 0
        negative_regimes = 0

        for regime_name, results in regime_results.items():
            sharpe = results.sharpe_ratio
            regime_scores[regime_name] = sharpe

            if sharpe >= self.config.regime_sharpe_threshold:
                positive_regimes += 1
            elif sharpe < 0:
                negative_regimes += 1

        # Bonus for passing threshold in 4/5 regimes
        bonus = 0.0
        if positive_regimes >= self.config.min_regimes_positive:
            bonus = 0.5  # Reward for regime consistency

        # Penalty for negative Sharpe in any regime
        penalty = self.config.regime_penalty_factor * negative_regimes * 0.2

        return bonus, penalty, regime_scores


def calculate_sharpe(
    equity_curve: pd.Series,
    trading_days_per_year: int = 252,
) -> float:
    """
    Calculate annualized Sharpe ratio from equity curve.

    Args:
        equity_curve: Series of equity values
        trading_days_per_year: Days for annualization (252 for daily)

    Returns:
        Annualized Sharpe ratio
    """
    if len(equity_curve) < 2:
        return 0.0

    # Calculate returns
    returns = equity_curve.pct_change().dropna()

    if len(returns) == 0 or returns.std() == 0:
        return 0.0

    # Annualized Sharpe
    sharpe = (returns.mean() / returns.std()) * np.sqrt(trading_days_per_year)

    # Clamp to reasonable bounds
    return float(max(-10.0, min(10.0, sharpe)))


def calculate_max_drawdown(equity_curve: pd.Series) -> float:
    """
    Calculate maximum drawdown from equity curve.

    Args:
        equity_curve: Series of equity values

    Returns:
        Max drawdown as positive decimal (0.20 = 20% drawdown)
    """
    if len(equity_curve) < 2:
        return 0.0

    # Running maximum
    running_max = equity_curve.expanding().max()

    # Drawdown series
    drawdowns = (equity_curve - running_max) / running_max

    # Return max drawdown (most negative) as positive
    return float(abs(drawdowns.min()))


def calculate_fitness(
    results: BacktestResults,
    regime_results: Optional[dict[str, BacktestResults]] = None,
    config: Optional[FitnessConfig] = None,
) -> float:
    """
    Calculate fitness score for strategy.

    Convenience function that returns just the score.

    Args:
        results: Backtest results
        regime_results: Optional regime-specific results
        config: Fitness configuration

    Returns:
        Fitness score (float)
    """
    calculator = EquitiesFitnessCalculator(config)
    result = calculator.calculate(results, regime_results)
    return result.score


# =============================================================================
# QUICK TEST
# =============================================================================

def quick_test():
    """Test fitness calculator."""
    print("Testing fitness calculator...")

    # Create sample results
    equity = pd.Series([100000, 101000, 102500, 101500, 103000, 104000, 103500, 105000])

    results = BacktestResults(
        equity_curve=equity,
        final_equity=105000,
        trade_count=25,
        win_count=15,
        loss_count=10,
        total_return=0.05,
        sharpe_ratio=calculate_sharpe(equity),
        max_drawdown=calculate_max_drawdown(equity),
        win_rate=0.60,
    )

    print(f"Sharpe: {results.sharpe_ratio:.2f}")
    print(f"Max DD: {results.max_drawdown:.2%}")

    # Calculate fitness
    calculator = EquitiesFitnessCalculator()
    fitness = calculator.calculate(results)

    print(f"\nFitness score: {fitness.score:.2f}")
    print(f"  Base Sharpe: {fitness.base_sharpe:.2f}")
    print(f"  DD penalty: -{fitness.drawdown_penalty:.2f}")
    print(f"  Trade penalty: -{fitness.trade_penalty:.2f}")
    print(f"  Disqualified: {fitness.is_disqualified}")

    # Test disqualification
    print("\nTesting disqualification...")
    bad_results = BacktestResults(trade_count=3)
    bad_fitness = calculator.calculate(bad_results)
    print(f"Few trades: score={bad_fitness.score}, reason={bad_fitness.disqualification_reason}")


if __name__ == "__main__":
    quick_test()
