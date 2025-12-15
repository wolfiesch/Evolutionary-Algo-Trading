"""
Fitness calculator - asset-agnostic.

Phase 2A: Sharpe-only scoring with basic disqualification.
Phase 2B: Full regime testing with multipliers.
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


# Disqualification thresholds
MIN_TRADES = 10              # Further lowered to escape stuck evolutions (was 15, 30, originally 50)
MIN_TRADES_PER_REGIME = 2    # Phase 2B: Minimum trades per regime
MAX_DRAWDOWN_HARD = 0.25     # 25% max drawdown
MIN_WIN_RATE = 0.05          # 5% minimum win rate (very relaxed for Phase 2A testing)
MIN_REGIME_PASSES = 4        # Need Sharpe >= 0.5 in 4/5 regimes
MAX_SHARPE_CAP = 3.0         # Sanity cap - Sharpe > 3.0 is rare in production


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
    # Cap Sharpe at MAX_SHARPE_CAP to prevent inflated scores from low-trade strategies
    base_sharpe = max(0.0, backtest_results.sharpe_ratio)  # Floor at 0
    capped_sharpe = min(base_sharpe, MAX_SHARPE_CAP)  # Cap at 3.0
    result.final_score = capped_sharpe * result.drawdown_multiplier

    # Add soft-fail reason for debugging (not technically disqualified, but score=0)
    if backtest_results.sharpe_ratio <= 0 and result.final_score == 0.0:
        result.disqualification_reason = f"Negative Sharpe ratio: {backtest_results.sharpe_ratio:.2f}"

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

    Formula:
        final_score = sharpe_ratio * regime_multiplier * drawdown_multiplier

    Where:
        - regime_multiplier = 0 if <4 regimes pass (Sharpe >= 0.5), else (passed/5)
        - drawdown_multiplier = drawdown_penalty(max_dd)

    Regime Rules:
        1. HARD FAIL: Any regime with negative Sharpe -> disqualified
        2. PASS REQUIREMENT: Sharpe >= 0.5 in at least 4/5 regimes

    Disqualification (score = 0):
        - Less than MIN_TRADES total trades
        - Any regime with negative Sharpe
        - Max drawdown > 25%
        - Win rate < 15%
        - Less than 4 regimes pass (Sharpe >= 0.5)

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

    # Check basic disqualification (same as Phase 2A)
    if overall_results.trade_count < MIN_TRADES:
        result.disqualified = True
        result.disqualification_reason = f"Insufficient trades: {overall_results.trade_count} < {MIN_TRADES}"
        result.final_score = 0.0
        return result

    if overall_results.max_drawdown > MAX_DRAWDOWN_HARD:
        result.disqualified = True
        result.disqualification_reason = f"Max drawdown too high: {overall_results.max_drawdown:.1%} > {MAX_DRAWDOWN_HARD:.0%}"
        result.final_score = 0.0
        return result

    if overall_results.win_rate < MIN_WIN_RATE:
        result.disqualified = True
        result.disqualification_reason = f"Win rate too low: {overall_results.win_rate:.1%} < {MIN_WIN_RATE:.0%}"
        result.final_score = 0.0
        return result

    # Phase 2B: Check regime-specific disqualification
    # HARD FAIL: Any regime with negative Sharpe
    has_neg, neg_regime = has_negative_regime(regime_sharpes)
    if has_neg:
        result.disqualified = True
        result.negative_regime = neg_regime
        result.disqualification_reason = f"Negative Sharpe in {neg_regime}: {regime_sharpes[neg_regime]:.2f}"
        result.final_score = 0.0
        return result

    # Calculate regime pass count and multiplier
    result.regime_pass_count = calculate_regime_pass_count(regime_sharpes)
    result.regime_multiplier = calculate_regime_multiplier(regime_sharpes, MIN_REGIME_PASSES)

    # Disqualify if not enough regimes pass
    if result.regime_pass_count < MIN_REGIME_PASSES:
        result.disqualified = True
        result.disqualification_reason = f"Only {result.regime_pass_count}/5 regimes pass (need {MIN_REGIME_PASSES})"
        result.final_score = 0.0
        return result

    # Calculate drawdown multiplier
    result.drawdown_multiplier = drawdown_penalty(overall_results.max_drawdown)

    # Final score: Sharpe * regime_multiplier * drawdown_multiplier
    base_sharpe = max(0.0, overall_results.sharpe_ratio)
    result.final_score = base_sharpe * result.regime_multiplier * result.drawdown_multiplier

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
