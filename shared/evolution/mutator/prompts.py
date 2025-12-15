"""
LLM prompt templates for strategy generation and mutation.

Asset-agnostic prompts with configurable market filter names.
"""

# Strategy generation prompt - COMPACT version for token efficiency
STRATEGY_GENERATION_PROMPT = """Generate trading strategy JSON using ONLY these primitives:

PRIMITIVES (use integer params: 5,9,14,20,21,50,60):
BINARY (use == 1.0 or == -1.0, NOT > or <):
- {market_filter_name}(w) -> exactly -1.0 or +1.0 (MUST use >= 0 in entry)
- ema_trend(fast,slow) -> exactly -1.0 or +1.0 (use == 1.0 for uptrend, == -1.0 for downtrend)
- volume_intensity(p,thresh) -> exactly 0 or 1 (use == 1 for high volume)
- volatility_spike(p,mult) -> 0 (safe) or 1 (spike detected, avoid entry)

CONTINUOUS (use > or < with thresholds):
- norm_rsi(p) -> -1.0 to +1.0 (e.g., < -0.3 for oversold)
- bb_position(p,std) -> -1.0 to +1.0 (e.g., < -0.5 for lower band)
- price_position(p) -> -3.0 to +3.0
- vwap_distance(p) -> -3.0 to +3.0
- atr_regime(p) -> -1.0 to +1.0
- trend_strength(p) -> 0.0 to 1.0 (ADX-based, >0.5 = strong trend)
- recent_range_position(p) -> 0.0 to 1.0 (0=at low, 1=at high)
- volatility_contraction(p,lookback) -> -1.0 to 1.0 (positive = squeeze)

RULES: Max 5 primitives. Use 2-3 entry conditions (4+ rarely trigger). Loose thresholds (rsi<-0.3 not -0.6).

Theme: {theme}

```json
{{"strategy_name":"Name_V1","rationale":"brief","entry_long":"{market_filter_name}(60)>=0 AND ...","exit_long":"..."}}
```
JSON only:"""

# Mutation prompt - COMPACT version with diversity guidance
MUTATION_PROMPT = """Mutate strategy. Current: {strategy_name}
Entry: {entry_long}
Exit: {exit_long}
Stats: Sharpe={sharpe}, WinRate={win_rate}%, Trades={trade_count}

MUTATION OPTIONS (pick ONE you haven't tried):
1. SWAP primitive: Replace norm_rsi with bb_position, or ema_trend with atr_regime
2. CHANGE params: 14->9 or 20->21, 50->60
3. ADJUST thresholds: -0.3->-0.2 or 0.5->0.6
4. ADD condition to exit (if <3 conditions)
5. REMOVE weakest entry condition (if >2 conditions)
6. FLIP logic: change < to > or entry condition to exit

If trades<10: LOOSEN thresholds significantly (-0.3->-0.1) or REMOVE a condition.
If Sharpe>2: Try ADDING a condition or TIGHTENING thresholds for quality.
Keep {market_filter_name}() in entry. Max 5 primitives. Integer params only.

IMPORTANT: Make a DIFFERENT change than previous mutations!

```json
{{"strategy_name":"{strategy_name}_M1","mutation_type":"param|threshold|add|remove|swap|flip","mutation_description":"specific change made","entry_long":"...","exit_long":"..."}}
```
JSON only:"""

# Strategy themes for diversity
STRATEGY_THEMES = [
    "Simple trend following with just 2 conditions",  # NEW: simpler strategies
    "Momentum continuation in uptrends",
    "Mean reversion on oversold bounces (use RSI < -0.3, not -0.5)",  # Clearer threshold
    "Breakout on volatility expansion",
    "Pullback buying with loose thresholds",  # Emphasize loose
    "Range trading in sideways markets",
    "Volume-confirmed trend following",
    "Basic RSI mean reversion (keep it simple)",  # NEW: simpler
]

# Mean-reversion focused themes (for assets in choppy/sideways markets)
MEAN_REVERSION_THEMES = [
    "Ultra-simple RSI bounce: buy when RSI < -0.2, sell when RSI > 0.3. Just 2 conditions total!",
    "Bollinger Band mean reversion: buy at lower band, sell at upper band",
    "Oversold bounce with VWAP confirmation",
    "Simple oversold dip buyer with loose thresholds (RSI < -0.2 is enough!)",
    "Range trading: buy oversold, exit neutral RSI",
]


# Crossover prompt - COMPACT version
CROSSOVER_PROMPT = """Combine best elements of two strategies:

A ({sharpe_a:.2f}): {entry_a} | Exit: {exit_a}
B ({sharpe_b:.2f}): {entry_b} | Exit: {exit_b}

Take better params from higher-Sharpe parent. Keep {market_filter_name}()>=0. Max 5 primitives.

```json
{{"strategy_name":"Crossover_{name_a}_{name_b}","crossover_description":"brief","entry_long":"...","exit_long":"..."}}
```
JSON only:"""


def get_generation_prompt(
    theme: str,
    market_filter_name: str = "btc_trend"
) -> str:
    """
    Get strategy generation prompt with theme and market filter.

    Args:
        theme: Strategy theme (e.g., "Momentum continuation in uptrends")
        market_filter_name: Name of market filter primitive (btc_trend for crypto)

    Returns:
        Formatted prompt string
    """
    return STRATEGY_GENERATION_PROMPT.format(
        theme=theme,
        market_filter_name=market_filter_name,
    )


def get_mutation_prompt(
    strategy_name: str,
    entry_long: str,
    exit_long: str,
    sharpe: float,
    win_rate: float,
    max_dd: float,
    trade_count: int,
    market_filter_name: str = "btc_trend"
) -> str:
    """
    Get mutation prompt with strategy details and performance.

    Args:
        strategy_name: Current strategy name
        entry_long: Current entry expression
        exit_long: Current exit expression
        sharpe: Sharpe ratio from backtest
        win_rate: Win rate as decimal (0.55 = 55%)
        max_dd: Max drawdown as decimal (0.15 = 15%)
        trade_count: Number of trades
        market_filter_name: Name of market filter primitive

    Returns:
        Formatted prompt string
    """
    return MUTATION_PROMPT.format(
        strategy_name=strategy_name,
        entry_long=entry_long,
        exit_long=exit_long,
        sharpe=f"{sharpe:.2f}",
        win_rate=f"{win_rate * 100:.1f}",
        max_dd=f"{max_dd * 100:.1f}",
        trade_count=trade_count,
        market_filter_name=market_filter_name,
    )


def get_crossover_prompt(
    name_a: str,
    entry_a: str,
    exit_a: str,
    sharpe_a: float,
    name_b: str,
    entry_b: str,
    exit_b: str,
    sharpe_b: float,
    market_filter_name: str = "btc_trend",
) -> str:
    """
    Get crossover prompt for combining two parent strategies.

    Args:
        name_a: Parent A strategy name
        entry_a: Parent A entry expression
        exit_a: Parent A exit expression
        sharpe_a: Parent A Sharpe ratio
        name_b: Parent B strategy name
        entry_b: Parent B entry expression
        exit_b: Parent B exit expression
        sharpe_b: Parent B Sharpe ratio
        market_filter_name: Name of market filter primitive

    Returns:
        Formatted prompt string
    """
    return CROSSOVER_PROMPT.format(
        name_a=name_a,
        entry_a=entry_a,
        exit_a=exit_a,
        sharpe_a=sharpe_a,
        name_b=name_b,
        entry_b=entry_b,
        exit_b=exit_b,
        sharpe_b=sharpe_b,
        market_filter_name=market_filter_name,
    )
