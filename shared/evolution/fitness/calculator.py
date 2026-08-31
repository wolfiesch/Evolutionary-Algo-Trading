"""
Fitness calculator - asset-agnostic.

Phase 2A: Sharpe-only scoring with basic disqualification.
Phase 2B: Full regime testing with multipliers.

IMPORTANT: Fitness scoring must preserve ranking signal even for negative-Sharpe
strategies. This allows evolution to learn "which direction to improve" rather
than collapsing all losers to identical scores.
"""
from typing import Optional
from shared.evolution.backtester.models import BacktestResults
from shared.evolution.fitness.models import FitnessResult
from shared.evolution.fitness.regime_classifier import (
    REGIME_NAMES,
    calculate_regime_pass_count,
    calculate_regime_multiplier,
    has_negative_regime,
)


# Disqualification thresholds (hard fails only - use sparingly)
MIN_TRADES = 5               # Absolute minimum for any statistical validity
MIN_TRADES_PER_REGIME = 2    # Phase 2B: Minimum trades per regime
MAX_DRAWDOWN_HARD = 0.50     # 50% max drawdown - hard fail (was 25%, too strict)
MIN_WIN_RATE = 0.0           # Removed - win rate is in the score, not a gate
MIN_REGIME_PASSES = 4        # Need Sharpe >= 0.5 in 4/5 regimes
MAX_SHARPE_CAP = 5.0         # Sanity cap - Sharpe > 5.0 is suspicious
MIN_SHARPE_FLOOR = -5.0      # Floor for extremely negative Sharpe (prevents -inf)

# NOTE on Sharpe values:
# - Backtester clamps Sharpe to [-10, +10] - these are FLOOR/CEILING, not sentinels
# - Fitness calculator further clamps to [-5, +5] for scoring purposes
# - DISQUALIFIED strategies get score = -999 (the actual sentinel value)
# - A Sharpe of -10 means "genuinely terrible strategy", not "something broke"

# Continuous penalty weights (soft penalties, not hard gates)
DRAWDOWN_PENALTY_WEIGHT = 2.0    # How much to penalize drawdown
TRADE_COUNT_TARGET = 30          # Ideal number of trades for statistical validity
TRADE_PENALTY_WEIGHT = 0.5       # Penalty for being far from target trade count


def calculate_fitness(backtest_results: BacktestResults) -> FitnessResult:
    """
    Calculate fitness score from backtest results.

    CONTINUOUS SCORING FORMULA (preserves ranking for all strategies):
        final_score = base_sharpe - drawdown_penalty - trade_penalty

    Where:
        - base_sharpe = sharpe clamped to [MIN_SHARPE_FLOOR, MAX_SHARPE_CAP]
        - drawdown_penalty = DRAWDOWN_PENALTY_WEIGHT * max_dd
        - trade_penalty = penalty for being far from target trade count

    HARD DISQUALIFICATION (score = -999, only for truly invalid):
        - Less than MIN_TRADES trades (no statistical validity)
        - Max drawdown > 50% (catastrophic failure)

    This formula ensures:
        - Sharpe=-2 ranks higher than Sharpe=-5 (learning signal preserved)
        - Drawdown is penalized smoothly, not as a hard gate
        - Low trade counts are penalized but not disqualifying

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

    # HARD DISQUALIFICATION - only for truly invalid strategies
    if backtest_results.trade_count < MIN_TRADES:
        result.disqualified = True
        result.disqualification_reason = f"Insufficient trades: {backtest_results.trade_count} < {MIN_TRADES}"
        result.final_score = -999.0  # Sentinel for "invalid", not 0
        return result

    if backtest_results.max_drawdown > MAX_DRAWDOWN_HARD:
        result.disqualified = True
        result.disqualification_reason = f"Catastrophic drawdown: {backtest_results.max_drawdown:.1%} > {MAX_DRAWDOWN_HARD:.0%}"
        result.final_score = -999.0
        return result

    # CONTINUOUS SCORING - all non-disqualified strategies get rankable scores

    # 1. Base Sharpe (clamped to prevent extreme outliers)
    base_sharpe = max(MIN_SHARPE_FLOOR, min(MAX_SHARPE_CAP, backtest_results.sharpe_ratio))

    # 2. Drawdown penalty (linear, always reduces score)
    dd_penalty = DRAWDOWN_PENALTY_WEIGHT * backtest_results.max_drawdown
    result.drawdown_multiplier = 1.0 - backtest_results.max_drawdown  # For logging

    # 3. Trade count penalty (penalize both too few and too many trades)
    # Fewer trades = less confidence in results
    # Too many trades = likely noise trading / high friction
    trade_ratio = backtest_results.trade_count / TRADE_COUNT_TARGET
    if trade_ratio < 1.0:
        # Penalize for too few trades (more severe)
        trade_penalty = TRADE_PENALTY_WEIGHT * (1.0 - trade_ratio)
    else:
        # Small penalty for excessive trading
        trade_penalty = TRADE_PENALTY_WEIGHT * 0.1 * min(trade_ratio - 1.0, 2.0)

    # Final score: higher is better, can be negative
    result.final_score = base_sharpe - dd_penalty - trade_penalty

    # Add note about score composition for debugging
    if backtest_results.sharpe_ratio < 0:
        result.disqualification_reason = (
            f"Negative Sharpe={backtest_results.sharpe_ratio:.2f} "
            f"(dd_pen={dd_penalty:.2f}, trade_pen={trade_penalty:.2f})"
        )

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


def calculate_fitness_with_regimes(
    overall_results: BacktestResults,
    regime_results: dict[str, BacktestResults],
) -> FitnessResult:
    """
    Calculate fitness score with regime testing (Phase 2B).

    CONTINUOUS SCORING FORMULA:
        final_score = base_sharpe * regime_multiplier - drawdown_penalty - regime_penalty

    Where:
        - base_sharpe = sharpe clamped to [MIN_SHARPE_FLOOR, MAX_SHARPE_CAP]
        - regime_multiplier = passed_regimes / 5 (continuous, not a gate)
        - drawdown_penalty = DRAWDOWN_PENALTY_WEIGHT * max_dd
        - regime_penalty = penalty for negative Sharpe in any regime (soft, not hard fail)

    Regime Rules (soft penalties, not hard gates):
        1. Negative Sharpe in a regime: heavy penalty but not disqualification
        2. Fewer than 4/5 regimes passing: reduced multiplier

    HARD DISQUALIFICATION (score = -999):
        - Less than MIN_TRADES total trades
        - Max drawdown > 50%

    Args:
        overall_results: Aggregated backtest results across all regimes
        regime_results: Dict mapping regime name to BacktestResults

    Returns:
        FitnessResult with regime-aware score
    """
    result = FitnessResult(
        sharpe_ratio=overall_results.sharpe_ratio,
        max_drawdown=overall_results.max_drawdown,
        trade_count=overall_results.trade_count,
        win_rate=overall_results.win_rate,
        profit_factor=overall_results.profit_factor,
        total_return=overall_results.total_return,
        regime_testing_enabled=True,
    )

    # Extract regime Sharpe ratios and trade counts
    regime_sharpes: dict[str, float] = {}
    regime_trade_counts: dict[str, int] = {}

    for regime in REGIME_NAMES:
        if regime in regime_results:
            regime_sharpes[regime] = regime_results[regime].sharpe_ratio
            regime_trade_counts[regime] = regime_results[regime].trade_count
        else:
            # Missing regime - treat as 0 Sharpe, 0 trades
            regime_sharpes[regime] = 0.0
            regime_trade_counts[regime] = 0

    result.regime_scores = regime_sharpes
    result.regime_trade_counts = regime_trade_counts

    # HARD DISQUALIFICATION - only for truly invalid strategies
    if overall_results.trade_count < MIN_TRADES:
        result.disqualified = True
        result.disqualification_reason = f"Insufficient trades: {overall_results.trade_count} < {MIN_TRADES}"
        result.final_score = -999.0
        return result

    if overall_results.max_drawdown > MAX_DRAWDOWN_HARD:
        result.disqualified = True
        result.disqualification_reason = f"Catastrophic drawdown: {overall_results.max_drawdown:.1%} > {MAX_DRAWDOWN_HARD:.0%}"
        result.final_score = -999.0
        return result

    # CONTINUOUS SCORING - regime-aware

    # 1. Base Sharpe (clamped)
    base_sharpe = max(MIN_SHARPE_FLOOR, min(MAX_SHARPE_CAP, overall_results.sharpe_ratio))

    # 2. Regime pass count and multiplier (continuous)
    result.regime_pass_count = calculate_regime_pass_count(regime_sharpes)
    # Use continuous multiplier: passes/5, minimum 0.2 to preserve some signal
    result.regime_multiplier = max(0.2, result.regime_pass_count / 5.0)

    # 3. Negative regime penalty (soft penalty, not hard fail)
    has_neg, neg_regime = has_negative_regime(regime_sharpes)
    regime_penalty = 0.0
    if has_neg:
        result.negative_regime = neg_regime
        # Penalty proportional to how negative the worst regime is
        worst_sharpe = min(regime_sharpes.values())
        regime_penalty = abs(worst_sharpe) * 0.5  # 50% of the negative magnitude

    # 4. Drawdown penalty
    dd_penalty = DRAWDOWN_PENALTY_WEIGHT * overall_results.max_drawdown
    result.drawdown_multiplier = 1.0 - overall_results.max_drawdown

    # Final score: higher is better
    result.final_score = (base_sharpe * result.regime_multiplier) - dd_penalty - regime_penalty

    # Add debugging info
    if result.regime_pass_count < MIN_REGIME_PASSES or has_neg:
        result.disqualification_reason = (
            f"Regimes: {result.regime_pass_count}/5 pass, "
            f"neg_regime={neg_regime}, "
            f"regime_pen={regime_penalty:.2f}"
        )

    return result


def aggregate_regime_results(regime_results: dict[str, BacktestResults]) -> BacktestResults:
    """
    Aggregate backtest results from multiple regimes into overall results.

    Args:
        regime_results: Dict mapping regime name to BacktestResults

    Returns:
        Aggregated BacktestResults
    """
    from shared.evolution.backtester.models import BacktestResults, Trade
    import pandas as pd

    all_trades: list[Trade] = []
    all_equity_points: list[float] = []
    total_candles = 0

    for regime, results in regime_results.items():
        all_trades.extend(results.trades)
        if results.equity_curve is not None and len(results.equity_curve) > 0:
            all_equity_points.extend(results.equity_curve.tolist())
        total_candles += results.candle_count

    # Calculate aggregated metrics
    trade_count = len(all_trades)
    wins = [t for t in all_trades if t.is_winner]
    losses = [t for t in all_trades if not t.is_winner]

    win_rate = len(wins) / trade_count if trade_count > 0 else 0.0
    gross_profit = sum(t.pnl for t in wins)
    gross_loss = abs(sum(t.pnl for t in losses))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

    # Create equity curve from all points
    if all_equity_points:
        equity_curve = pd.Series(all_equity_points)
        final_equity = equity_curve.iloc[-1]
        total_return = (final_equity - 10000) / 10000  # Assuming 10k initial

        # Calculate max drawdown
        peak = equity_curve.expanding().max()
        drawdown = (equity_curve - peak) / peak
        max_drawdown = abs(drawdown.min())

        # Calculate Sharpe (simplified - use per-period returns)
        # NOTE: Cap at -10/+10 consistent with backtester engines (floor, not sentinel)
        returns = equity_curve.pct_change().dropna()
        if len(returns) > 1 and returns.std() > 0:
            sharpe = (returns.mean() / returns.std()) * (525600 ** 0.5)  # Annualized
            sharpe = max(-10.0, min(10.0, sharpe))
        else:
            sharpe = 0.0
    else:
        equity_curve = pd.Series([10000.0])
        final_equity = 10000.0
        total_return = 0.0
        max_drawdown = 0.0
        sharpe = 0.0

    return BacktestResults(
        symbol="AGGREGATED",
        candle_count=total_candles,
        trades=all_trades,
        trade_count=trade_count,
        win_count=len(wins),
        loss_count=len(losses),
        win_rate=win_rate,
        profit_factor=profit_factor,
        equity_curve=equity_curve,
        final_equity=final_equity,
        total_return=total_return,
        max_drawdown=max_drawdown,
        sharpe_ratio=sharpe,
    )
