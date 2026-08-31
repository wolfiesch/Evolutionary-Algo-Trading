"""
LLM Prompts for Equities Swing Trading Strategy Evolution.

Customizes shared evolution prompts for fundamental + technical combinations.
Key difference from crypto: includes SEC EDGAR-derived fundamental primitives.
"""

# =============================================================================
# SYSTEM PROMPT - Defines LLM role and constraints
# =============================================================================

EQUITIES_SYSTEM_PROMPT = """You are an expert quantitative analyst designing swing trading strategies for US equities. You combine technical analysis with SEC EDGAR fundamental data to find alpha.

AVAILABLE PRIMITIVES:

Technical (timing):
- ema_trend(fast, slow): +1.0 uptrend, -1.0 downtrend (common: 9,21 or 12,26)
- price_position(period): (Price - EMA) / ATR, capped ±3.0
- norm_rsi(period): -1.0 oversold to +1.0 overbought (common: 14)
- bb_position(period, std): position in Bollinger Bands -1 to +1 (common: 20,2)
- bb_width_percentile(period): band width vs history 0 to 1
- volume_intensity(period, threshold): volume spike 0 to 1 (common: 20, 2.0)
- atr_regime(period): +1 high vol, 0 normal, -1 low vol
- atr_percentile(period): current ATR vs history 0 to 1

Market Filters (mandatory - one must be first in entry):
- spy_trend(period): +1.0 bull market, -1.0 bear market (common: 20, 50)
- vix_regime(period): +1.0 calm (<15), 0.0 normal (15-25), -1.0 fear (>25)
- spy_momentum(period): SPY return over period -1 to +1
- spy_above_sma(period): +1 if SPY above SMA, -1 below

Fundamental (EDGAR-derived, slower signals):
- insider_intensity: -1 to +1 (positive = net buying)
- insider_cluster: 1.0 if 3+ insiders bought recently, else 0
- revenue_cagr: -1 to +1 (scaled revenue growth)
- earnings_growth: -1 to +1 (net income growth)
- earnings_quality: -1 to +1 (OCF vs net income)
- risk_change: -1 to +1 (risk factor changes in filings)
- fundamental_score: -1 to +1 (weighted composite)

RULES:
1. Entry MUST start with a market filter: "spy_trend(20) >= 0 AND ..."
2. Combine at least one fundamental AND one technical primitive
3. Maximum 5 primitives per strategy
4. Use integer parameters only (9, 14, 20, 21, 50)
5. Fundamental signals filter (long-term), technicals time (short-term)
6. Exits should be simpler than entries (1-2 conditions)

GOOD PATTERNS:
- Insider momentum: insider_intensity > 0.3 + ema_trend confirmation
- Quality pullback: earnings_quality > 0.3 + RSI oversold + uptrend
- Growth breakout: revenue_cagr > 0.2 + volume spike + trend
- Low risk momentum: risk_change < 0.3 + strong momentum

BAD PATTERNS TO AVOID:
- Pure fundamental (no timing signal) - will buy too early
- Pure technical (ignores fundamental edge) - no alpha
- Too many conditions (>5) - overfitting
- Conflicting signals (oversold AND overbought)
- Missing market filter in entry"""


# =============================================================================
# STRATEGY GENERATION PROMPT
# =============================================================================

EQUITIES_GENERATION_PROMPT = """Generate a NEW equities swing trading strategy for theme: "{theme}"

{system_prompt}

CRITICAL: Entry expression MUST start with "spy_trend(20) >= 0 AND " or similar market filter.

Return ONLY valid JSON:
{{"name": "Strategy_Name", "entry_long": "spy_trend(20) >= 0 AND ...", "exit_long": "...", "rationale": "Brief explanation"}}"""


# =============================================================================
# MUTATION PROMPT
# =============================================================================

EQUITIES_MUTATION_PROMPT = """Mutate this equities strategy to improve performance:

Current strategy: {strategy_name}
Entry: {entry_long}
Exit: {exit_long}

Performance:
- Sharpe: {sharpe:.2f}
- Win rate: {win_rate:.1%}
- Max drawdown: {max_dd:.1%}
- Trade count: {trade_count}

{guidance}

Mutation options:
1. SWAP: Replace one primitive with another (fundamental<->technical mix)
2. PARAM: Adjust parameter (e.g., RSI 14->9, EMA 20->50)
3. THRESHOLD: Change comparison value (e.g., > 0.3 -> > 0.4)
4. ADD: Add a primitive (if <5 total)
5. REMOVE: Remove a primitive (keep market filter!)

{system_prompt}

Return ONLY valid JSON:
{{"name": "{strategy_name}_v2", "entry_long": "...", "exit_long": "...", "mutation_type": "SWAP|PARAM|THRESHOLD|ADD|REMOVE", "mutation_description": "What changed and why"}}"""


# =============================================================================
# CROSSOVER PROMPT
# =============================================================================

EQUITIES_CROSSOVER_PROMPT = """Combine these two equities strategies into a better one:

PARENT A ({sharpe_a:.2f} Sharpe):
Entry: {entry_a}
Exit: {exit_a}

PARENT B ({sharpe_b:.2f} Sharpe):
Entry: {entry_b}
Exit: {exit_b}

Take the best elements from each parent. Bias toward the higher-Sharpe parent's parameters.
Maintain the fundamental + technical combination pattern.

{system_prompt}

Return ONLY valid JSON:
{{"name": "Combined_Strategy", "entry_long": "spy_trend(...) >= 0 AND ...", "exit_long": "...", "rationale": "How parents were combined"}}"""


# =============================================================================
# STRATEGY THEMES - Diversity in initial population
# =============================================================================

EQUITIES_THEMES = [
    # Fundamental-led strategies
    "Insider buying momentum - wait for insiders to buy, then ride the trend",
    "Quality value - high earnings quality stocks at technical pullback",
    "Growth acceleration - revenue CAGR uptick with breakout confirmation",
    "Low risk momentum - stocks with stable risk factors and strong momentum",

    # Technical-led with fundamental filter
    "Trend following with fundamental quality filter",
    "Mean reversion with insider activity confirmation",
    "Breakout with volume and fundamental support",
    "Momentum with earnings quality screen",

    # Hybrid strategies
    "GARP (Growth At Reasonable Price) with technical timing",
    "Contrarian with insider cluster buying confirmation",
]

EQUITIES_MEAN_REVERSION_THEMES = [
    "RSI oversold with quality fundamentals",
    "Bollinger Band squeeze with insider buying",
    "Price below EMA with strong revenue growth",
    "Low ATR percentile with positive fundamental score",
    "Volume dry-up before reversal with earnings quality",
]


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_equities_generation_prompt(theme: str) -> str:
    """
    Format generation prompt with theme.

    Args:
        theme: Strategy theme to generate

    Returns:
        Formatted prompt string
    """
    return EQUITIES_GENERATION_PROMPT.format(
        theme=theme,
        system_prompt=EQUITIES_SYSTEM_PROMPT,
    )


def get_equities_mutation_prompt(
    strategy_name: str,
    entry_long: str,
    exit_long: str,
    sharpe: float,
    win_rate: float,
    max_dd: float,
    trade_count: int,
) -> str:
    """
    Format mutation prompt with strategy and performance data.

    Args:
        strategy_name: Current strategy name
        entry_long: Entry expression
        exit_long: Exit expression
        sharpe: Sharpe ratio
        win_rate: Win rate (0-1)
        max_dd: Max drawdown (0-1)
        trade_count: Number of trades

    Returns:
        Formatted prompt string
    """
    # Add guidance based on performance
    guidance_parts = []

    if sharpe < 0:
        guidance_parts.append("Strategy is losing money - consider more conservative entry or tighter exit.")
    elif sharpe < 0.5:
        guidance_parts.append("Sharpe is low - look for stronger signal combinations.")

    if trade_count < 10:
        guidance_parts.append("Too few trades - loosen entry thresholds to find more opportunities.")
    elif trade_count > 100:
        guidance_parts.append("Many trades - consider tightening entry for higher quality signals.")

    if max_dd > 0.20:
        guidance_parts.append("High drawdown - add defensive conditions or tighter stops.")

    if win_rate < 0.40:
        guidance_parts.append("Low win rate - may need better entry timing signals.")

    guidance = " ".join(guidance_parts) if guidance_parts else "Performance is reasonable - fine-tune parameters."

    return EQUITIES_MUTATION_PROMPT.format(
        strategy_name=strategy_name,
        entry_long=entry_long,
        exit_long=exit_long,
        sharpe=sharpe,
        win_rate=win_rate,
        max_dd=max_dd,
        trade_count=trade_count,
        guidance=guidance,
        system_prompt=EQUITIES_SYSTEM_PROMPT,
    )


def get_equities_crossover_prompt(
    entry_a: str,
    exit_a: str,
    sharpe_a: float,
    entry_b: str,
    exit_b: str,
    sharpe_b: float,
) -> str:
    """
    Format crossover prompt with two parent strategies.

    Args:
        entry_a: Parent A entry expression
        exit_a: Parent A exit expression
        sharpe_a: Parent A Sharpe ratio
        entry_b: Parent B entry expression
        exit_b: Parent B exit expression
        sharpe_b: Parent B Sharpe ratio

    Returns:
        Formatted prompt string
    """
    return EQUITIES_CROSSOVER_PROMPT.format(
        entry_a=entry_a,
        exit_a=exit_a,
        sharpe_a=sharpe_a,
        entry_b=entry_b,
        exit_b=exit_b,
        sharpe_b=sharpe_b,
        system_prompt=EQUITIES_SYSTEM_PROMPT,
    )


# =============================================================================
# ANALYSIS PROMPT - For deep strategy analysis
# =============================================================================

EQUITIES_ANALYSIS_PROMPT = """Analyze this equities swing trading strategy:

Name: {strategy_name}
Entry: {entry_long}
Exit: {exit_long}

Performance over 5 years:
- Sharpe ratio: {sharpe:.2f}
- Max drawdown: {max_dd:.1%}
- Win rate: {win_rate:.1%}
- Total trades: {trade_count}
- Total return: {total_return:.1%}

Regime performance:
{regime_performance}

PRIMITIVES USED:
{primitives_doc}

Analyze:
1. MARKET HYPOTHESIS: What market behavior does this exploit?
2. LOGIC ASSESSMENT: Do the primitive combinations make sense?
3. EDGE SOURCE: Is this exploiting a known inefficiency or overfitting?
4. FAVORABLE CONDITIONS: Which market regimes favor this strategy?
5. FAILURE MODES: When would this strategy fail badly?
6. ROBUSTNESS RATING: 1-10 (10 = robust across regimes)
7. IMPROVEMENT SUGGESTIONS: How could this be improved?

Be critical and honest. We want robust strategies, not curve-fitted ones."""


def get_equities_analysis_prompt(
    strategy_name: str,
    entry_long: str,
    exit_long: str,
    sharpe: float,
    max_dd: float,
    win_rate: float,
    trade_count: int,
    total_return: float,
    regime_scores: dict[str, float],
) -> str:
    """
    Format analysis prompt for deep strategy evaluation.

    Args:
        strategy_name: Strategy name
        entry_long: Entry expression
        exit_long: Exit expression
        sharpe: Overall Sharpe ratio
        max_dd: Max drawdown
        win_rate: Win rate
        trade_count: Total trades
        total_return: Total return
        regime_scores: Dict of regime -> Sharpe

    Returns:
        Formatted analysis prompt
    """
    # Format regime performance
    regime_lines = []
    for regime, score in sorted(regime_scores.items()):
        status = "PASS" if score >= 0.5 else "WEAK" if score >= 0 else "FAIL"
        regime_lines.append(f"  - {regime}: Sharpe {score:.2f} [{status}]")
    regime_performance = "\n".join(regime_lines) if regime_lines else "  No regime data available"

    # Primitives documentation (condensed)
    primitives_doc = """
Technical primitives (timing):
- ema_trend(fast, slow): EMA crossover direction +1/-1
- norm_rsi(period): Normalized RSI from -1 (oversold) to +1 (overbought)
- bb_position(period, std): Position in Bollinger Bands -1 to +1
- volume_intensity(period, threshold): Relative volume spike 0 to 1

Market filters (market regime):
- spy_trend(period): SPY trend direction +1 bull / -1 bear
- vix_regime(period): VIX level +1 calm / 0 normal / -1 fear

Fundamental primitives (EDGAR-derived):
- insider_intensity: Net insider buying/selling -1 to +1
- insider_cluster: 1.0 if cluster buying detected, else 0
- revenue_cagr: Revenue growth rate -1 to +1
- earnings_quality: Cash flow backing earnings -1 to +1
- risk_change: Risk factor changes -1 to +1
- fundamental_score: Weighted composite -1 to +1
"""

    return EQUITIES_ANALYSIS_PROMPT.format(
        strategy_name=strategy_name,
        entry_long=entry_long,
        exit_long=exit_long,
        sharpe=sharpe,
        max_dd=max_dd,
        win_rate=win_rate,
        trade_count=trade_count,
        total_return=total_return,
        regime_performance=regime_performance,
        primitives_doc=primitives_doc,
    )


# =============================================================================
# QUICK TEST
# =============================================================================

def quick_test():
    """Test prompt generation."""
    print("Testing equities prompts...")

    # Test generation prompt
    gen_prompt = get_equities_generation_prompt(EQUITIES_THEMES[0])
    print(f"\n=== Generation Prompt (theme: {EQUITIES_THEMES[0][:30]}...) ===")
    print(f"Length: {len(gen_prompt)} chars")
    assert "spy_trend" in gen_prompt
    assert "insider" in gen_prompt.lower()

    # Test mutation prompt
    mut_prompt = get_equities_mutation_prompt(
        strategy_name="Test_Strategy",
        entry_long="spy_trend(20) >= 0 AND insider_intensity > 0.3",
        exit_long="norm_rsi(14) > 0.5",
        sharpe=0.8,
        win_rate=0.55,
        max_dd=0.12,
        trade_count=25,
    )
    print(f"\n=== Mutation Prompt ===")
    print(f"Length: {len(mut_prompt)} chars")
    assert "SWAP" in mut_prompt

    # Test crossover prompt
    cross_prompt = get_equities_crossover_prompt(
        entry_a="spy_trend(20) >= 0 AND insider_intensity > 0.3",
        exit_a="norm_rsi(14) > 0.5",
        sharpe_a=1.2,
        entry_b="spy_trend(50) >= 0 AND revenue_cagr > 0.2",
        exit_b="ema_trend(9, 21) < 0",
        sharpe_b=0.9,
    )
    print(f"\n=== Crossover Prompt ===")
    print(f"Length: {len(cross_prompt)} chars")
    assert "PARENT A" in cross_prompt

    # Test analysis prompt
    analysis_prompt = get_equities_analysis_prompt(
        strategy_name="Quality_Pullback",
        entry_long="spy_trend(20) >= 0 AND earnings_quality > 0.3 AND norm_rsi(14) < -0.3",
        exit_long="norm_rsi(14) > 0.5",
        sharpe=1.5,
        max_dd=0.08,
        win_rate=0.58,
        trade_count=45,
        total_return=0.35,
        regime_scores={
            "bull_calm": 1.8,
            "bull_volatile": 0.9,
            "bear_calm": 0.4,
            "bear_volatile": -0.2,
            "sideways": 0.6,
        },
    )
    print(f"\n=== Analysis Prompt ===")
    print(f"Length: {len(analysis_prompt)} chars")
    assert "ROBUSTNESS RATING" in analysis_prompt

    print("\nAll prompt tests passed!")


if __name__ == "__main__":
    quick_test()
