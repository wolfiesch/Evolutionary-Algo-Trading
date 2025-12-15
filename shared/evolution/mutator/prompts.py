"""
LLM prompt templates for strategy generation and mutation.

Asset-agnostic prompts with configurable market filter names.
"""

# Strategy generation prompt - COMPACT version for token efficiency
STRATEGY_GENERATION_PROMPT = """Generate trading strategy JSON.

*** MANDATORY: entry_long MUST start with "{market_filter_name}(60) >= 0 AND" ***

PRIMITIVES (integer params: 5,9,14,20,21,50,60):

REQUIRED FIRST (always include in entry):
- {market_filter_name}(60) >= 0  <-- ALWAYS START ENTRY WITH THIS

BINARY (use == 1.0 or == -1.0):
- ema_trend(fast,slow) -> +1.0 uptrend, -1.0 downtrend
- volume_intensity(p,thresh) -> 0 or 1

CONTINUOUS (use > or < with thresholds):
- norm_rsi(p) -> -1.0 to +1.0 (< -0.3 oversold, > 0.3 overbought)
- bb_position(p,std) -> -1.0 to +1.0
- price_position(p) -> -3.0 to +3.0
- atr_regime(p) -> -1.0 to +1.0
- trend_strength(p) -> 0.0 to 1.0

RULES: Max 5 primitives. 2-3 entry conditions. Loose thresholds.

Theme: {theme}

```json
{{"strategy_name":"Name_V1","rationale":"brief","entry_long":"{market_filter_name}(60) >= 0 AND ema_trend(9,21) == 1.0 AND norm_rsi(14) < 0.3","exit_long":"norm_rsi(14) > 0.6"}}
```
JSON only:"""

# Mutation prompt - COMPACT version with diversity guidance
MUTATION_PROMPT = """Mutate strategy. Current: {strategy_name}
Entry: {entry_long}
Exit: {exit_long}
Stats: Sharpe={sharpe}, WinRate={win_rate}%, Trades={trade_count}

*** KEEP "{market_filter_name}(60) >= 0 AND" AT START OF ENTRY ***

MUTATION OPTIONS (pick ONE):
1. SWAP: norm_rsi->bb_position, ema_trend->atr_regime
2. PARAMS: 14->9, 20->21, 50->60
3. THRESHOLDS: -0.3->-0.2, 0.5->0.6
4. ADD exit condition (if <3)
5. REMOVE entry condition (if >2, but NEVER remove {market_filter_name})

If trades<10: LOOSEN thresholds (-0.3->-0.1) or REMOVE a non-filter condition.
Make a DIFFERENT change than previous mutations!

```json
{{"strategy_name":"{strategy_name}_M1","mutation_type":"swap|param|threshold|add|remove","mutation_description":"change made","entry_long":"{market_filter_name}(60) >= 0 AND ...","exit_long":"..."}}
```
JSON only:"""

# Strategy themes for diversity - each should produce distinct strategies
STRATEGY_THEMES = [
    # Trend-based (3)
    "Simple EMA crossover: buy when ema_trend(9,21)==1.0, sell on reversal",
    "Strong trend filter: require trend_strength(20) > 0.5 with ema_trend",
    "Momentum continuation: price_position(50) > 0.5 in uptrend",
    # Mean reversion (3)
    "RSI bounce: norm_rsi(14) < -0.3 oversold, exit at neutral",
    "Bollinger mean reversion: bb_position(20,2) < -0.5, exit at 0",
    "VWAP reversion: vwap_distance(20) < -1.0, exit near VWAP",
    # Volume-based (2)
    "Volume breakout: volume_intensity(20,15) == 1 with trend",
    "Volume confirmation: require volume_intensity on trend entry",
    # Volatility-based (2)
    "Low volatility trend: atr_regime(14) < 0 with ema_trend",
    "Volatility expansion: atr_regime(14) > 0.3 momentum play",
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

*** entry_long MUST start with "{market_filter_name}(60) >= 0 AND" ***

Take better params from higher-Sharpe parent. Max 5 primitives.

```json
{{"strategy_name":"Crossover_V1","crossover_description":"brief","entry_long":"{market_filter_name}(60) >= 0 AND ...","exit_long":"..."}}
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
