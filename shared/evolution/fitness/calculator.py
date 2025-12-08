"""
Fitness calculator - asset-agnostic.

Phase 2A: Sharpe-only scoring with basic disqualification.
Phase 2B+: Will add regime testing and full formula.
"""
from shared.evolution.backtester.models import BacktestResults
from shared.evolution.fitness.models import FitnessResult


# Disqualification thresholds
# [*TO-DO*] - Increase MIN_TRADES to 30 when more data available
MIN_TRADES = 3               # Phase 2A: Very low for testing with limited data
MAX_DRAWDOWN_HARD = 0.25     # 25% max drawdown
MIN_WIN_RATE = 0.15          # 15% minimum win rate (relaxed for testing)


def calculate_fitness(backtest_results: BacktestResults) -> FitnessResult:
    """
    Calculate fitness score from backtest results.

    Phase 2A Formula (simple):
        final_score = sharpe_ratio * drawdown_multiplier

    Where:
        - drawdown_multiplier = drawdown_penalty(max_dd)

    Disqualification (score = 0):
        - Less than MIN_TRADES trades (insufficient sample)
        - Max drawdown > 25%
        - Win rate < 20%

    Args:
        backtest_results: Results from backtester

    Returns:
        FitnessResult with score and metrics
    """
    result = FitnessResult(
        sharpe_ratio=backtest_results.sharpe_ratio,
        max_drawdown=backtest_results.max_drawdown,
        trade_count=backtest_results.trade_count,
        win_rate=backtest_results.win_rate,
        profit_factor=backtest_results.profit_factor,
        total_return=backtest_results.total_return,
    )

    # Check disqualification conditions
    if backtest_results.trade_count < MIN_TRADES:
        result.disqualified = True
        result.disqualification_reason = f"Insufficient trades: {backtest_results.trade_count} < {MIN_TRADES}"
        result.final_score = 0.0
        return result

    if backtest_results.max_drawdown > MAX_DRAWDOWN_HARD:
        result.disqualified = True
        result.disqualification_reason = f"Max drawdown too high: {backtest_results.max_drawdown:.1%} > {MAX_DRAWDOWN_HARD:.0%}"
        result.final_score = 0.0
        return result

    if backtest_results.win_rate < MIN_WIN_RATE:
        result.disqualified = True
        result.disqualification_reason = f"Win rate too low: {backtest_results.win_rate:.1%} < {MIN_WIN_RATE:.0%}"
        result.final_score = 0.0
        return result

    # Calculate drawdown multiplier
    result.drawdown_multiplier = drawdown_penalty(backtest_results.max_drawdown)

    # Phase 2A: Simple fitness formula
    # Sharpe ratio (can be negative) * drawdown penalty
    base_sharpe = max(0.0, backtest_results.sharpe_ratio)  # Floor at 0
    result.final_score = base_sharpe * result.drawdown_multiplier

    return result


def drawdown_penalty(max_dd: float) -> float:
    """
    Calculate drawdown penalty multiplier.

    From Phase 2 plan:
    - DD < 10%: No penalty (multiplier = 1.0)
    - DD 10-20%: Linear penalty (1.0 -> 0.5)
    - DD 20-25%: Severe penalty (0.5 -> 0.0)
    - DD > 25%: Disqualified (multiplier = 0)

    Args:
        max_dd: Maximum drawdown as positive decimal (0.15 = 15%)

    Returns:
        Multiplier from 0.0 to 1.0
    """
    if max_dd < 0.10:
        return 1.0
    elif max_dd < 0.20:
        # Linear from 1.0 to 0.5
        return 1.0 - 0.5 * ((max_dd - 0.10) / 0.10)
    elif max_dd < 0.25:
        # Linear from 0.5 to 0.0
        return 0.5 - 0.5 * ((max_dd - 0.20) / 0.05)
    else:
        return 0.0


def rank_strategies(fitness_results: list[tuple[str, FitnessResult]]) -> list[tuple[str, FitnessResult]]:
    """
    Rank strategies by fitness score (descending).

    Args:
        fitness_results: List of (strategy_name, FitnessResult) tuples

    Returns:
        Sorted list with highest scores first
    """
    return sorted(
        fitness_results,
        key=lambda x: x[1].final_score,
        reverse=True
    )
