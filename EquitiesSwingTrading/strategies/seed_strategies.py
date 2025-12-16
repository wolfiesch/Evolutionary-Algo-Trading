"""
Seed Strategies for Equities Swing Trading System

A curated set of starter strategies that combine:
- Market regime filters (SPY trend, VIX levels)
- Fundamental signals (insider activity, earnings quality)
- Technical signals (trend, momentum, mean reversion)

Each strategy follows the design principles:
1. ALWAYS include a market filter (spy_trend or vix_regime)
2. Combine fundamental + technical for alpha
3. Maximum 5 primitives per strategy
4. Use integer parameters only
5. Clear entry/exit logic

Usage:
    from strategies.seed_strategies import get_seed_strategies
    strategies = get_seed_strategies()
"""

from evolution.backtester.evaluator import Strategy


# =============================================================================
# MOMENTUM STRATEGIES
# =============================================================================

INSIDER_MOMENTUM = Strategy(
    name="Insider_Momentum",
    entry_long=(
        "spy_trend(20) >= 0 "
        "AND insider_buy_intensity(90) > 0.3 "
        "AND ema_trend(9, 21) == 1.0"
    ),
    exit_long=(
        "norm_rsi(14) > 0.6 "
        "OR ema_trend(9, 21) == -1.0"
    ),
)
"""
Insider Momentum: Follow the smart money.

Logic: When insiders are buying heavily (Form 4 signals) AND the stock
is in a technical uptrend, we ride the momentum.

- Entry: Market uptrend + strong insider buying + short-term uptrend
- Exit: Overbought RSI or trend reversal

Expected: Lower frequency (insider signals are rare), higher conviction.
"""


TREND_FOLLOWING = Strategy(
    name="Trend_Following",
    entry_long=(
        "spy_trend(50) >= 0 "
        "AND vix_regime(14) >= 0 "
        "AND ema_trend(20, 50) == 1.0 "
        "AND price_position(20) > 0.5"
    ),
    exit_long=(
        "ema_trend(20, 50) == -1.0 "
        "OR price_position(20) < -1.0"
    ),
)
"""
Trend Following: Classic momentum with regime filter.

Logic: Only trade strong trends in low-volatility bull markets.
Uses longer-term EMAs for smoother signals.

- Entry: Bull market + low VIX + stock uptrend + price above average
- Exit: Trend reversal or significant pullback

Expected: Medium frequency, smoother equity curve.
"""


BREAKOUT_MOMENTUM = Strategy(
    name="Breakout_Momentum",
    entry_long=(
        "spy_trend(20) >= 0 "
        "AND bb_position(20, 2.0) > 0.9 "
        "AND volume_intensity(20, 1.5) > 0.5 "
        "AND ema_trend(9, 21) == 1.0"
    ),
    exit_long=(
        "bb_position(20, 2.0) < 0.5 "
        "OR norm_rsi(14) > 0.7"
    ),
)
"""
Breakout Momentum: Catch explosive moves.

Logic: Trade breakouts above Bollinger Bands with volume confirmation.
High-momentum plays that can capture large moves.

- Entry: Market uptrend + price at upper band + high volume + trend
- Exit: Price fades back or becomes extremely overbought

Expected: Lower win rate, higher reward/risk per trade.
"""


# =============================================================================
# MEAN REVERSION STRATEGIES
# =============================================================================

QUALITY_PULLBACK = Strategy(
    name="Quality_Pullback",
    entry_long=(
        "spy_trend(20) >= 0 "
        "AND earnings_quality() > 0.5 "
        "AND norm_rsi(14) < -0.4 "
        "AND ema_trend(20, 50) == 1.0"
    ),
    exit_long=(
        "norm_rsi(14) > 0.3"
    ),
)
"""
Quality Pullback: Buy the dip in quality stocks.

Logic: When high-quality companies (strong cash flows) pull back
in an uptrend, it's often a buying opportunity.

- Entry: Market uptrend + high earnings quality + oversold + long-term uptrend
- Exit: RSI returns to normal

Expected: Higher win rate, moderate gains per trade.
"""


RSI_OVERSOLD_BOUNCE = Strategy(
    name="RSI_Oversold_Bounce",
    entry_long=(
        "spy_trend(20) >= 0 "
        "AND vix_regime(14) >= 0 "
        "AND norm_rsi(14) < -0.6 "
        "AND bb_position(20, 2.0) < 0.1"
    ),
    exit_long=(
        "norm_rsi(14) > 0.0 "
        "OR bb_position(20, 2.0) > 0.5"
    ),
)
"""
RSI Oversold Bounce: Classic mean reversion.

Logic: Deeply oversold stocks in calm markets tend to bounce.
Requires both RSI and Bollinger confirmation.

- Entry: Market uptrend + low VIX + deeply oversold
- Exit: Return to mean

Expected: Quick trades, higher win rate in calm markets.
"""


BOLLINGER_SQUEEZE = Strategy(
    name="Bollinger_Squeeze",
    entry_long=(
        "spy_trend(20) >= 0 "
        "AND bb_width_percentile(20) < 0.2 "
        "AND norm_rsi(14) > 0.0 "
        "AND volume_intensity(20, 1.5) > 0.3"
    ),
    exit_long=(
        "bb_width_percentile(20) > 0.7 "
        "OR norm_rsi(14) > 0.6"
    ),
)
"""
Bollinger Squeeze: Catch volatility expansion.

Logic: When Bollinger Bands contract (low volatility), an expansion
is coming. Enter with slight bullish bias and volume.

- Entry: Market uptrend + tight bands + slight momentum + volume
- Exit: Bands expand or overbought

Expected: Catches trending moves after consolidation.
"""


# =============================================================================
# FUNDAMENTAL-DRIVEN STRATEGIES
# =============================================================================

GROWTH_BREAKOUT = Strategy(
    name="Growth_Breakout",
    entry_long=(
        "spy_trend(20) >= 0 "
        "AND revenue_cagr(3) > 0.1 "
        "AND bb_position(20, 2.0) > 0.8 "
        "AND ema_trend(9, 21) == 1.0"
    ),
    exit_long=(
        "bb_position(20, 2.0) < 0.2 "
        "OR norm_rsi(14) > 0.7"
    ),
)
"""
Growth Breakout: Momentum in growth stocks.

Logic: Companies with strong revenue growth (>10% CAGR) breaking out
technically often have further upside.

- Entry: Market uptrend + high revenue growth + breakout + trend
- Exit: Price fades or overbought

Expected: Captures growth stock momentum.
"""


INSIDER_CLUSTER = Strategy(
    name="Insider_Cluster",
    entry_long=(
        "spy_trend(20) >= 0 "
        "AND insider_cluster_buy(60, 2) == 1.0 "
        "AND ema_trend(9, 21) == 1.0"
    ),
    exit_long=(
        "norm_rsi(14) > 0.5 "
        "OR ema_trend(9, 21) == -1.0"
    ),
)
"""
Insider Cluster: Multiple insiders buying = high conviction.

Logic: When 2+ insiders buy within 60 days, it's a strong signal.
This is the highest-conviction insider signal.

- Entry: Market uptrend + cluster buying + technical uptrend
- Exit: Overbought or trend reversal

Expected: Rare but high-quality signals.
"""


LOW_RISK_MOMENTUM = Strategy(
    name="Low_Risk_Momentum",
    entry_long=(
        "spy_trend(20) >= 0 "
        "AND risk_change_intensity() < 0.3 "
        "AND earnings_quality() > 0.4 "
        "AND ema_trend(9, 21) == 1.0"
    ),
    exit_long=(
        "ema_trend(9, 21) == -1.0"
    ),
)
"""
Low Risk Momentum: Avoid companies disclosing new risks.

Logic: Companies with stable risk factors (not adding new 10-K risks)
and decent fundamentals in uptrends.

- Entry: Market uptrend + low risk change + decent quality + trend
- Exit: Trend reversal

Expected: Avoids blowups, trades stable companies.
"""


# =============================================================================
# VOLATILITY-AWARE STRATEGIES
# =============================================================================

CALM_MARKET_MOMENTUM = Strategy(
    name="Calm_Market_Momentum",
    entry_long=(
        "spy_trend(20) >= 0 "
        "AND vix_regime(14) == 1.0 "
        "AND ema_trend(9, 21) == 1.0 "
        "AND norm_rsi(14) > 0.0"
    ),
    exit_long=(
        "vix_regime(14) < 0 "
        "OR ema_trend(9, 21) == -1.0"
    ),
)
"""
Calm Market Momentum: Only trade in low volatility.

Logic: Trend following works best in calm markets.
Exit when VIX spikes (regime change).

- Entry: Market uptrend + very low VIX + stock uptrend + slight momentum
- Exit: VIX spikes or trend reversal

Expected: Smooth equity curve, avoids volatile periods.
"""


HIGH_ATR_MEAN_REVERSION = Strategy(
    name="High_ATR_Mean_Reversion",
    entry_long=(
        "spy_trend(20) >= 0 "
        "AND atr_regime(14) == 1.0 "
        "AND norm_rsi(14) < -0.5"
    ),
    exit_long=(
        "norm_rsi(14) > 0.2"
    ),
)
"""
High ATR Mean Reversion: Bigger swings = bigger bounces.

Logic: High-volatility stocks that get oversold tend to have
larger mean reversion bounces.

- Entry: Market uptrend + high volatility stock + oversold
- Exit: Return toward mean

Expected: Larger wins, but also more volatile.
"""


# =============================================================================
# CONSERVATIVE STRATEGIES
# =============================================================================

SAFE_TREND = Strategy(
    name="Safe_Trend",
    entry_long=(
        "spy_trend(50) >= 0 "
        "AND spy_above_sma(200) == 1.0 "
        "AND ema_trend(50, 200) == 1.0"
    ),
    exit_long=(
        "spy_trend(50) < 0 "
        "OR ema_trend(50, 200) == -1.0"
    ),
)
"""
Safe Trend: Very conservative, long-term trend following.

Logic: Only trade when everything aligns - SPY above 200 SMA,
in uptrend, and stock in long-term uptrend.

- Entry: Strong market + strong stock trend
- Exit: Either weakens

Expected: Fewer trades, but higher quality setups.
"""


QUALITY_GROWTH = Strategy(
    name="Quality_Growth",
    entry_long=(
        "spy_trend(20) >= 0 "
        "AND earnings_quality() > 0.6 "
        "AND revenue_cagr(3) > 0.05 "
        "AND ema_trend(20, 50) == 1.0"
    ),
    exit_long=(
        "ema_trend(20, 50) == -1.0"
    ),
)
"""
Quality Growth: Only the best fundamentals.

Logic: Combines earnings quality (cash flow backing) with revenue
growth for selecting fundamentally strong companies in uptrends.

- Entry: Market uptrend + high quality + growing revenue + trend
- Exit: Trend reversal

Expected: Lower frequency, higher conviction.
"""


# =============================================================================
# ALL STRATEGIES
# =============================================================================

ALL_STRATEGIES = [
    # Momentum
    INSIDER_MOMENTUM,
    TREND_FOLLOWING,
    BREAKOUT_MOMENTUM,
    # Mean Reversion
    QUALITY_PULLBACK,
    RSI_OVERSOLD_BOUNCE,
    BOLLINGER_SQUEEZE,
    # Fundamental
    GROWTH_BREAKOUT,
    INSIDER_CLUSTER,
    LOW_RISK_MOMENTUM,
    # Volatility-Aware
    CALM_MARKET_MOMENTUM,
    HIGH_ATR_MEAN_REVERSION,
    # Conservative
    SAFE_TREND,
    QUALITY_GROWTH,
]


def get_seed_strategies(category: str = "all") -> list[Strategy]:
    """
    Get seed strategies by category.

    Args:
        category: One of "all", "momentum", "mean_reversion", "fundamental",
                  "volatility", "conservative"

    Returns:
        List of Strategy objects
    """
    if category == "all":
        return ALL_STRATEGIES.copy()
    elif category == "momentum":
        return [INSIDER_MOMENTUM, TREND_FOLLOWING, BREAKOUT_MOMENTUM]
    elif category == "mean_reversion":
        return [QUALITY_PULLBACK, RSI_OVERSOLD_BOUNCE, BOLLINGER_SQUEEZE]
    elif category == "fundamental":
        return [GROWTH_BREAKOUT, INSIDER_CLUSTER, LOW_RISK_MOMENTUM]
    elif category == "volatility":
        return [CALM_MARKET_MOMENTUM, HIGH_ATR_MEAN_REVERSION]
    elif category == "conservative":
        return [SAFE_TREND, QUALITY_GROWTH]
    else:
        raise ValueError(f"Unknown category: {category}")


def get_default_strategies() -> list[Strategy]:
    """
    Get the default strategies for shadow trading.

    Returns a balanced subset suitable for initial deployment:
    - One momentum strategy
    - One mean reversion strategy
    - One fundamental strategy
    """
    return [
        INSIDER_MOMENTUM,
        QUALITY_PULLBACK,
        GROWTH_BREAKOUT,
    ]


# =============================================================================
# STRATEGY VALIDATION
# =============================================================================

def validate_strategy(strategy: Strategy) -> list[str]:
    """
    Validate a strategy against design rules.

    Args:
        strategy: Strategy to validate

    Returns:
        List of validation errors (empty if valid)
    """
    errors = []

    # Rule 1: Must have market filter
    market_filters = ["spy_trend", "vix_regime", "spy_above_sma", "spy_momentum"]
    has_market_filter = any(f in strategy.entry_long for f in market_filters)
    if not has_market_filter:
        errors.append("Entry must include a market filter (spy_trend, vix_regime, etc.)")

    # Rule 2: Max 5 primitives in entry
    entry_parts = strategy.entry_long.count("AND") + 1
    if entry_parts > 5:
        errors.append(f"Entry has {entry_parts} conditions, max is 5")

    # Rule 3: Must have exit condition
    if not strategy.exit_long or len(strategy.exit_long.strip()) == 0:
        errors.append("Must have exit_long condition")

    # Rule 4: Check for common mistakes
    if "insider" in strategy.entry_long.lower() and "spy_trend" not in strategy.entry_long:
        errors.append("Insider signals should be combined with market filter")

    return errors


def validate_all_seed_strategies() -> dict[str, list[str]]:
    """
    Validate all seed strategies.

    Returns:
        Dict mapping strategy name -> list of errors (empty if valid)
    """
    results = {}
    for strategy in ALL_STRATEGIES:
        errors = validate_strategy(strategy)
        if errors:
            results[strategy.name] = errors
    return results


if __name__ == "__main__":
    # Quick validation
    print("=== Seed Strategy Validation ===")
    print(f"Total strategies: {len(ALL_STRATEGIES)}")

    errors = validate_all_seed_strategies()
    if errors:
        print("\nValidation errors:")
        for name, errs in errors.items():
            print(f"  {name}:")
            for e in errs:
                print(f"    - {e}")
    else:
        print("\nAll strategies valid!")

    print("\n=== Strategy Summary ===")
    for strategy in ALL_STRATEGIES:
        print(f"\n{strategy.name}:")
        print(f"  Entry: {strategy.entry_long[:60]}...")
        print(f"  Exit:  {strategy.exit_long[:60]}...")
