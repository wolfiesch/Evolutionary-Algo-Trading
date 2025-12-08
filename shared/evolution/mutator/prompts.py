"""
LLM prompt templates for strategy generation and mutation.

Asset-agnostic prompts with configurable market filter names.
"""

# Strategy generation prompt - generates new strategies
STRATEGY_GENERATION_PROMPT = """You are a quantitative trading strategy generator. Generate a trading strategy using ONLY these primitives:

## Available Primitives (ONLY USE THESE)

### Market Filter (MANDATORY for entry_long)
- {market_filter_name}(window: int) -> float  # +1.0 safe, -1.0 danger. MUST include >= 0 check

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
- Combine conditions with AND only (no OR in entry)
- Exit can use OR for multiple exit conditions

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
2. Tighten/loosen a threshold (e.g., < -0.4 -> < -0.5)
3. Add one primitive (if < 5 currently)
4. Remove one primitive (if redundant)
5. Change a primitive (swap similar ones)

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
    "Momentum continuation in uptrends",
    "Mean reversion on oversold bounces",
    "Breakout on volatility expansion",
    "Pullback buying in established trends",
    "Range trading in sideways markets",
    "Volume-confirmed trend following",
    "Low volatility breakout anticipation",
    "RSI divergence with trend confirmation",
]


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
