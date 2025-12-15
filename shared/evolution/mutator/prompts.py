"""
LLM prompt templates for strategy generation and mutation.

Asset-agnostic prompts with configurable market filter names.
"""

# Strategy generation prompt - generates new strategies
STRATEGY_GENERATION_PROMPT = """You are a quantitative trading strategy generator. Generate a trading strategy using ONLY these primitives:

## Available Primitives (ONLY USE THESE)

### Market Filter (MANDATORY for entry_long)
- {market_filter_name}(window: int) -> float  # +1.0 safe, -1.0 danger. MUST include >= 0 check
  NOTE: This is a SELF-REFERENTIAL filter - it checks if the trading asset itself is in an uptrend.
  This is better than cross-asset correlation which often fails.

### Trend
- ema_trend(fast: int, slow: int) -> float  # +1.0 uptrend, -1.0 downtrend
- price_position(period: int) -> float  # Price vs EMA normalized by ATR, range ±3.0

### Mean Reversion
- norm_rsi(period: int) -> float  # -1.0 (oversold) to +1.0 (overbought)
- bb_position(period: int, std: float) -> float  # -1.0 (lower band) to +1.0 (upper band)
- bb_width_percentile(period: int) -> float  # 0.0 (narrow) to 1.0 (wide)

### Volume
- volume_intensity(period: int, threshold: float) -> float  # 1.0 if volume spike, else 0.0
- vwap_distance(period: int) -> float  # Z-score vs VWAP, ±3.0

### Volatility
- atr_regime(period: int) -> float  # +1.0 high, 0.0 normal, -1.0 low
- atr_percentile(period: int) -> float  # 0.0 (lowest) to 1.0 (highest)

## Constraints
- Maximum 5 primitives per expression
- INTEGER parameters only (14, not 14.5)
- Common periods: 5, 9, 14, 20, 21, 50, 60
- entry_long MUST start with: {market_filter_name}(N) >= 0 AND ...
- Combine conditions with AND (can use 2-3 conditions, avoid 4+ which rarely trigger)
- Exit can use OR for multiple exit conditions

## CRITICAL: Trade Frequency
- Strategies with 0 trades are DISQUALIFIED
- Avoid overly strict combinations that never trigger
- Use moderate thresholds: norm_rsi < -0.3 (not -0.6), price_position < 1.0 (not 0)
- Prefer 2-3 entry conditions over 4-5 (fewer conditions = more trades)
- Example BAD: btc_trend >= 0 AND ema_trend > 0 AND norm_rsi < -0.5 AND price_position < 0 (too strict!)
- Example GOOD: btc_trend >= 0 AND ema_trend > 0 AND norm_rsi < -0.2

## Strategy Theme: {theme}

Generate a strategy following this JSON format:
```json
{{
  "strategy_name": "DescriptiveName_V1",
  "rationale": "Brief explanation of the strategy logic",
  "entry_long": "{market_filter_name}(60) >= 0 AND <conditions>",
  "exit_long": "<exit_conditions>"
}}
```

Return ONLY valid JSON, no other text.
"""

# Mutation prompt - improves existing strategies
MUTATION_PROMPT = """You are a quantitative strategy optimizer. Mutate this strategy to potentially improve it.

## Current Strategy
Name: {strategy_name}
Entry: {entry_long}
Exit: {exit_long}

## Recent Backtest Results
Sharpe Ratio: {sharpe}
Win Rate: {win_rate}%
Max Drawdown: {max_dd}%
Trade Count: {trade_count}

## Available Primitives
{market_filter_name}(window), ema_trend(fast, slow), price_position(period),
norm_rsi(period), bb_position(period, std), bb_width_percentile(period),
volume_intensity(period, threshold), vwap_distance(period),
atr_regime(period), atr_percentile(period)

## Mutation Instructions
Suggest ONE small change to improve performance. Options:
1. Adjust a parameter (e.g., 14 -> 20)
2. LOOSEN a threshold if trade_count is low (e.g., < -0.5 -> < -0.3 to get more trades)
3. Remove one primitive if trade_count is 0 (fewer conditions = more trades!)
4. Add one primitive only if trade_count is high (> 20)
5. Change a primitive (swap similar ones)

CRITICAL: If trade_count is 0-5, the strategy is TOO STRICT. Focus on REMOVING conditions or LOOSENING thresholds.

## Constraints
- Keep {market_filter_name}() check in entry
- Maximum 5 primitives
- INTEGER parameters only
- Explain your reasoning briefly

Return JSON:
```json
{{
  "strategy_name": "{strategy_name}_M1",
  "mutation_type": "parameter_adjust|threshold_change|add_primitive|remove_primitive|swap_primitive",
  "mutation_description": "What changed and why",
  "entry_long": "<new_entry>",
  "exit_long": "<new_exit>"
}}
```

Return ONLY valid JSON, no other text.
"""

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


# Crossover prompt - combines two parent strategies
CROSSOVER_PROMPT = """You are a quantitative strategy designer. Combine the best elements of these two parent strategies into a superior child strategy.

## Parent Strategy A (Sharpe: {sharpe_a:.2f})
Name: {name_a}
Entry: {entry_a}
Exit: {exit_a}

## Parent Strategy B (Sharpe: {sharpe_b:.2f})
Name: {name_b}
Entry: {entry_b}
Exit: {exit_b}

## Available Primitives
{market_filter_name}(window), ema_trend(fast, slow), price_position(period),
norm_rsi(period), bb_position(period, std), bb_width_percentile(period),
volume_intensity(period, threshold), vwap_distance(period),
atr_regime(period), atr_percentile(period)

## Task
Create a child strategy that:
1. Combines the strongest signals from both parents
2. Takes entry conditions from the better-performing parent if themes differ
3. Can mix primitives from both parents intelligently
4. Maintains maximum 5 primitives per expression
5. Keeps {market_filter_name}() >= 0 check in entry (MANDATORY)
6. Uses INTEGER parameters only

Consider:
- If both parents use similar entry logic, take the better-tuned parameters
- If parents have different styles (trend vs mean-reversion), prefer the higher-Sharpe approach
- Exit logic can combine conditions with OR to capture multiple exit scenarios

Return JSON:
```json
{{
  "strategy_name": "Crossover_{name_a}_{name_b}",
  "crossover_description": "Explanation of which elements came from which parent and why",
  "entry_long": "<combined_entry>",
  "exit_long": "<combined_exit>"
}}
```

Return ONLY valid JSON, no other text.
"""


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
