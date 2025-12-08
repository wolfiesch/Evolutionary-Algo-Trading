# Phase 2: LLM-Driven Strategy Evolution - Implementation Plan

**Created:** 2025-12-08
**Status:** Planning
**Prerequisites:** Phase 1 Complete (37+ hour stability test passed)

## Overview

Phase 2 implements the core LLM-driven evolutionary search system. The goal is to discover robust trading strategies by:
1. Generating candidate strategies from the gene pool
2. Backtesting them across multiple market regimes
3. Scoring with a multi-objective fitness function
4. Evolving the best performers through LLM-guided mutation

**Key Principle:** Robustness over returns. We optimize for survival across regimes, not peak performance.

---

## 0. Architecture: Shared vs Asset-Specific

All Phase 2 components live in `/shared/` and MUST be **asset-agnostic**. Asset-specific behavior
is injected via configuration or thin wrappers.

```
/shared/evolution/           # ALL Phase 2 code goes here
├── backtester/              # Asset-agnostic backtesting engine
├── fitness/                 # Asset-agnostic fitness calculation
└── mutator/                 # Asset-agnostic LLM integration

/crypto/                     # Crypto-specific configuration/wrappers
├── config.py                # BacktestConfig with crypto friction (0.25%)
├── evolution_config.py      # Crypto-specific: BTC as benchmark, symbols list
└── primitives/              # btc_trend() - injected into shared engine

/forex/                      # Forex-specific (future)
├── config.py                # Forex friction, session hours
├── evolution_config.py      # DXY as benchmark, pairs list
└── primitives/              # dxy_trend() - injected into shared engine
```

**Design Rules:**
1. **Shared code NEVER imports from `/crypto/` or `/forex/`** - dependencies flow downward only
2. **Asset-specific primitives** (btc_trend, dxy_trend) are registered via a primitive registry pattern
3. **Benchmark candles** parameter is generic (`benchmark_candles: pd.DataFrame`) - crypto passes BTC, forex passes DXY
4. **Friction/costs** come from `BacktestConfig` - each asset class configures its own
5. **Symbol universe** is passed as parameter, not hardcoded

**Example - Asset-Agnostic Backtester Call:**
```python
# In /crypto/run_evolution.py
from shared.evolution.backtester import VectorizedBacktester
from crypto.config import BACKTEST_CONFIG  # friction=0.0025, etc.

backtester = VectorizedBacktester(config=BACKTEST_CONFIG)
results = backtester.run(
    strategy=strategy,
    candles={"SOLUSDT": sol_df, "ETHUSDT": eth_df},
    benchmark_candles=btc_df,  # Crypto uses BTC
)
```

---

## 1. Fitness Function Design

### Location: `/shared/evolution/fitness/`

### 1.1 Multi-Objective Fitness Score

```python
# fitness/calculator.py

@dataclass
class FitnessResult:
    """Complete fitness evaluation result."""
    sharpe_ratio: float           # Risk-adjusted returns
    regime_scores: dict[str, float]  # Sharpe per regime
    regime_pass_count: int        # How many regimes passed (need 4/5)
    max_drawdown: float           # Peak-to-trough decline
    drawdown_penalty: float       # Penalty applied for excessive DD
    trade_count: int              # Number of trades
    win_rate: float               # Winning trade percentage
    profit_factor: float          # Gross profit / gross loss
    final_score: float            # Composite fitness score
    disqualified: bool            # Hard fail conditions
    disqualification_reason: str | None

def calculate_fitness(backtest_results: BacktestResults) -> FitnessResult:
    """
    Calculate multi-objective fitness score.

    Formula:
        final_score = sharpe_ratio * regime_multiplier * drawdown_multiplier

    Where:
        - regime_multiplier = 0 if <4 regimes pass (Sharpe >= 0.5), else (passed/5)
        - drawdown_multiplier = drawdown_penalty(max_dd)  # See tiered function below

    Regime Rules (complementary, not contradictory):
        1. HARD FAIL: Any regime with negative Sharpe → disqualified
           (Strategy is actively losing money in some conditions)
        2. PASS REQUIREMENT: Sharpe >= 0.5 in at least 4/5 regimes
           (Strategy with Sharpe 0.1 in one regime passes rule 1, but
           needs Sharpe >= 0.5 in the other 4 to pass rule 2)

    Disqualification (score = 0):
        - Less than 30 trades (insufficient sample)
        - Any regime with negative Sharpe (hard fail)
        - Max drawdown > 25% (see drawdown_penalty function)
        - Win rate < 25% (severely broken)
    """
```

### 1.2 Regime Testing Requirements

From CLAUDE.md: "Sharpe > 0.5 in 4/5 market regimes"

```python
# fitness/regime_classifier.py

REGIME_DEFINITIONS = {
    "bull_calm": {
        "btc_return_min": 0.05,      # +5% over period
        "btc_return_max": None,
        "volatility_percentile_max": 70,
    },
    "bull_volatile": {
        "btc_return_min": 0.05,
        "btc_return_max": None,
        "volatility_percentile_min": 70,
    },
    "bear_calm": {
        "btc_return_min": None,
        "btc_return_max": -0.05,     # -5% over period
        "volatility_percentile_max": 70,
    },
    "bear_volatile": {
        "btc_return_min": None,
        "btc_return_max": -0.05,
        "volatility_percentile_min": 70,
    },
    "sideways": {
        "btc_return_min": -0.05,
        "btc_return_max": 0.05,      # Within ±5%
    },
}

def classify_period(btc_candles: pd.DataFrame, period_days: int = 7) -> str:
    """Classify a period into one of 5 regimes."""

def split_by_regime(
    candles: pd.DataFrame,
    btc_candles: pd.DataFrame
) -> dict[str, pd.DataFrame]:
    """Split historical data into regime-specific chunks."""
```

### 1.3 Drawdown Penalties

```python
# fitness/drawdown.py

def calculate_max_drawdown(equity_curve: pd.Series) -> float:
    """Calculate maximum drawdown from equity curve."""
    peak = equity_curve.expanding().max()
    drawdown = (equity_curve - peak) / peak
    return abs(drawdown.min())

def drawdown_penalty(max_dd: float) -> float:
    """
    Calculate drawdown penalty multiplier.

    - DD < 10%: No penalty (multiplier = 1.0)
    - DD 10-20%: Linear penalty (1.0 -> 0.5)
    - DD 20-25%: Severe penalty (0.5 -> 0.0)
    - DD > 25%: Disqualified (multiplier = 0)
    """
    if max_dd < 0.10:
        return 1.0
    elif max_dd < 0.20:
        return 1.0 - 0.5 * ((max_dd - 0.10) / 0.10)
    elif max_dd < 0.25:
        return 0.5 - 0.5 * ((max_dd - 0.20) / 0.05)
    else:
        return 0.0  # Disqualified
```

### 1.4 Implementation Tasks

**Location:** `/shared/evolution/fitness/` (asset-agnostic)

| Task | Priority | Effort | Files |
|------|----------|--------|-------|
| Create `FitnessResult` dataclass | T0 | S | `shared/evolution/fitness/models.py` |
| Implement Sharpe ratio calculator | T0 | S | `shared/evolution/fitness/metrics.py` |
| Implement max drawdown calculator | T0 | S | `shared/evolution/fitness/drawdown.py` |
| Implement regime classifier | T0 | M | `shared/evolution/fitness/regime_classifier.py` |
| Build composite fitness calculator | T0 | M | `shared/evolution/fitness/calculator.py` |
| Add disqualification logic | T1 | S | `shared/evolution/fitness/calculator.py` |
| Unit tests for fitness functions | T1 | M | `shared/tests/test_fitness.py` |

**Note:** Regime classifier uses generic `benchmark_candles` parameter. Crypto passes BTC, forex passes DXY.

---

## 2. Backtesting Framework

### Location: `/shared/evolution/backtester/`

### 2.1 Vectorized Backtester Design

For speed during evolution, use a vectorized approach (not event-driven):

```python
# backtester/engine.py

@dataclass
class BacktestConfig:
    """Backtest configuration."""
    initial_equity: float = 10_000
    friction_per_side: float = 0.0025  # 0.25% (crypto default)
    max_position_pct: float = 0.10
    risk_per_trade: float = 0.01
    max_open_positions: int = 5

@dataclass
class BacktestResults:
    """Complete backtest results."""
    equity_curve: pd.Series
    trades: list[Trade]
    sharpe_ratio: float
    max_drawdown: float
    total_return: float
    trade_count: int
    win_rate: float
    profit_factor: float
    regime_results: dict[str, RegimeResult]  # Per-regime stats

class VectorizedBacktester:
    """
    Fast vectorized backtester for strategy evaluation.

    Strategy execution flow:
    1. Pre-compute all indicator values for the entire period
    2. Vectorize entry/exit condition evaluation
    3. Walk through positions sequentially (can't vectorize position mgmt)
    4. Calculate final metrics
    """

    def __init__(self, config: BacktestConfig):
        self.config = config

    def run(
        self,
        strategy: Strategy,
        candles: dict[str, pd.DataFrame],  # symbol -> OHLCV
        benchmark_candles: pd.DataFrame,   # BTC for crypto, DXY for forex
    ) -> BacktestResults:
        """Run backtest on historical data."""

    def run_by_regime(
        self,
        strategy: Strategy,
        candles: dict[str, pd.DataFrame],
        benchmark_candles: pd.DataFrame,
    ) -> dict[str, BacktestResults]:
        """Run separate backtests per regime."""
```

### 2.2 Walk-Forward Validation

```python
# backtester/walk_forward.py

@dataclass
class WalkForwardConfig:
    """Walk-forward validation configuration."""
    train_days: int = 30      # Training window
    test_days: int = 7        # Out-of-sample test
    step_days: int = 7        # Step between windows
    min_windows: int = 8      # Minimum windows for validity

def walk_forward_validation(
    strategy: Strategy,
    candles: dict[str, pd.DataFrame],
    benchmark_candles: pd.DataFrame,
    config: WalkForwardConfig,
) -> WalkForwardResults:
    """
    Perform walk-forward validation.

    Returns aggregated out-of-sample performance across all windows.
    This prevents overfitting to specific time periods.
    """
```

### 2.3 Historical Data Requirements

For backtesting, we need sufficient historical data:

```python
# backtester/data_requirements.py

MINIMUM_DATA_REQUIREMENTS = {
    "candles_per_symbol": 10_000,  # ~7 days of 1-min data
    "benchmark_candles": 50_000,   # ~35 days for regime classification (BTC/DXY)
    "regime_samples": {
        "bull_calm": 1000,
        "bull_volatile": 1000,
        "bear_calm": 1000,
        "bear_volatile": 1000,
        "sideways": 1000,
    },
}
```

**Data Distribution Note:** With 50k BTC candles (~35 days), regime distribution will be uneven
based on market conditions during collection. Some regimes (e.g., bear_volatile) may be
undersampled. The system should:
1. Log actual samples per regime after classification
2. Warn if any regime has <500 samples
3. Consider extending data collection if undersampled

### 2.4 Implementation Tasks

**Location:** `/shared/evolution/backtester/` (asset-agnostic)

| Task | Priority | Effort | Files |
|------|----------|--------|-------|
| Create `BacktestConfig` and `BacktestResults` | T0 | S | `shared/evolution/backtester/models.py` |
| Implement indicator pre-computation | T0 | M | `shared/evolution/backtester/indicators.py` |
| Build vectorized condition evaluator | T0 | L | `shared/evolution/backtester/evaluator.py` |
| Implement position tracking | T0 | M | `shared/evolution/backtester/positions.py` |
| Build main backtest engine | T0 | L | `shared/evolution/backtester/engine.py` |
| Add regime-split backtesting | T1 | M | `shared/evolution/backtester/engine.py` |
| Implement walk-forward validation | T1 | L | `shared/evolution/backtester/walk_forward.py` |
| Add friction modeling | T0 | S | `shared/evolution/backtester/friction.py` |
| Unit tests for backtester | T1 | L | `shared/tests/test_backtester.py` |
| Integration test with real data | T2 | M | `shared/tests/test_backtest_integration.py` |

**Note:** Friction rates, position limits, and other asset-specific params come from `BacktestConfig`
passed by the caller (crypto or forex). Backtester code remains asset-agnostic.

---

## 3. LLM Prompt Templates

### Location: `/shared/evolution/mutator/`

### 3.1 Strategy Generation Prompt

```python
# mutator/prompts.py

STRATEGY_GENERATION_PROMPT = """
You are a quantitative trading strategy generator. Generate a trading strategy using ONLY these primitives:

## Available Primitives (ONLY USE THESE)

### Market Filter (MANDATORY for entry_long)
- btc_trend(window: int) -> float  # +1.0 safe, -1.0 danger. MUST include >= 0 check

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
- entry_long MUST start with: btc_trend(N) >= 0 AND ...
- Combine conditions with AND only (no OR in entry)
- Exit can use OR for multiple exit conditions

## Strategy Theme: {theme}

Generate a strategy following this JSON format:
```json
{{
  "strategy_name": "DescriptiveName_V1",
  "rationale": "Brief explanation of the strategy logic",
  "entry_long": "btc_trend(60) >= 0 AND <conditions>",
  "exit_long": "<exit_conditions>"
}}
```

Return ONLY valid JSON, no other text.
"""

STRATEGY_THEMES = [
    "Momentum continuation in uptrends",
    "Mean reversion on oversold bounces",
    "Breakout on volatility expansion",
    "Pullback buying in established trends",
    "Range trading in sideways markets",
    "Volume-confirmed trend following",
]
```

### 3.2 Mutation Prompt

```python
# mutator/prompts.py

MUTATION_PROMPT = """
You are a quantitative strategy optimizer. Mutate this strategy to potentially improve it.

## Current Strategy
Name: {strategy_name}
Entry: {entry_long}
Exit: {exit_long}

## Recent Backtest Results
Sharpe Ratio: {sharpe}
Win Rate: {win_rate}%
Max Drawdown: {max_dd}%
Trade Count: {trade_count}

## Regime Performance
{regime_performance}

## Mutation Instructions
Suggest ONE small change to improve performance. Options:
1. Adjust a parameter (e.g., 14 -> 20)
2. Tighten/loosen a threshold (e.g., < -0.4 -> < -0.5)
3. Add one primitive (if < 5 currently)
4. Remove one primitive (if redundant)
5. Change a primitive (swap similar ones)

## Constraints
- Keep btc_trend() check in entry
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
"""
```

### 3.3 Crossover Prompt

```python
# mutator/prompts.py

CROSSOVER_PROMPT = """
You are a quantitative strategy designer. Combine the best elements of these two strategies:

## Parent Strategy A (Sharpe: {sharpe_a})
Entry: {entry_a}
Exit: {exit_a}

## Parent Strategy B (Sharpe: {sharpe_b})
Entry: {entry_b}
Exit: {exit_b}

## Task
Create a child strategy that:
1. Combines the strongest signals from both parents
2. Maintains maximum 5 primitives
3. Keeps btc_trend() check in entry
4. Uses integer parameters only

Return JSON:
```json
{{
  "strategy_name": "Child_{parent_a}_{parent_b}",
  "crossover_description": "Which elements came from which parent",
  "entry_long": "<combined_entry>",
  "exit_long": "<combined_exit>"
}}
```
"""
```

### 3.4 LLM Logging & Retry Requirements

**Logging (REQUIRED for debugging):**
- Log every prompt sent to LLM (with timestamp, strategy context)
- Log every raw response received
- Log validation results (pass/fail, error messages)
- Log retry attempts with failure reasons
- Store in `logs/llm_interactions.jsonl` for analysis

**Retry Logic:**
- Max 3 attempts per generation/mutation request
- On JSON parse failure: retry with explicit error feedback in prompt
- On validation failure: retry with specific constraint violation in prompt
- On rate limit: exponential backoff (1s, 2s, 4s)
- After 3 failures: discard and generate new strategy from scratch

**Provider-Agnostic Interface:**
```python
# mutator/llm_client.py

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

class LLMProvider(Enum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"

@dataclass
class LLMConfig:
    provider: LLMProvider
    model: str                    # e.g., "claude-sonnet-4-20250514" or "gpt-4o"
    api_key: str                  # From environment variable
    max_tokens: int = 1024
    temperature: float = 0.7      # Some creativity for strategy generation

class LLMClient(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    def generate(self, prompt: str) -> str:
        """Send prompt, return raw response text."""
        pass

class AnthropicClient(LLMClient):
    """Claude API implementation."""
    pass

class OpenAIClient(LLMClient):
    """OpenAI API implementation."""
    pass

def create_llm_client(config: LLMConfig) -> LLMClient:
    """Factory function to create appropriate client."""
    if config.provider == LLMProvider.OPENAI:
        return OpenAIClient(config)
    return AnthropicClient(config)
```

**Default:** OpenAI (gpt-4o) for cost efficiency. Can switch via config.

### 3.5 Implementation Tasks

**Location:** `/shared/evolution/mutator/` (asset-agnostic)

| Task | Priority | Effort | Files |
|------|----------|--------|-------|
| Create base prompt templates | T0 | M | `shared/evolution/mutator/prompts.py` |
| Build LLM client wrapper (OpenAI + Anthropic) | T0 | M | `shared/evolution/mutator/llm_client.py` |
| Implement strategy generator | T0 | M | `shared/evolution/mutator/generator.py` |
| Add response parser/validator | T0 | M | `shared/evolution/mutator/parser.py` |
| Implement mutation operator | T1 | M | `shared/evolution/mutator/mutation.py` |
| Implement crossover operator | T1 | M | `shared/evolution/mutator/crossover.py` |
| Add retry logic for invalid outputs | T1 | S | `shared/evolution/mutator/llm_client.py` |
| Add LLM interaction logging | T0 | S | `shared/evolution/mutator/llm_client.py` |
| Unit tests for LLM parsing | T1 | M | `shared/tests/test_mutator.py` |

**Note:** Prompt templates reference primitives generically. Asset-specific primitives (btc_trend, dxy_trend)
are injected via a primitive registry that each asset class populates.

---

## 4. Mutation Operators

### Location: `/shared/evolution/mutator/`

### 4.1 Operator Types

```python
# mutator/operators.py

from enum import Enum
from abc import ABC, abstractmethod

class MutationType(Enum):
    """Types of mutations."""
    PARAMETER_ADJUST = "parameter_adjust"    # Change integer params
    THRESHOLD_CHANGE = "threshold_change"    # Adjust comparison values
    ADD_PRIMITIVE = "add_primitive"          # Add new condition
    REMOVE_PRIMITIVE = "remove_primitive"    # Remove condition
    SWAP_PRIMITIVE = "swap_primitive"        # Replace with similar

class MutationOperator(ABC):
    """Base class for mutation operators."""

    @abstractmethod
    def mutate(self, strategy: Strategy) -> Strategy:
        """Apply mutation and return new strategy."""
        pass

class ParameterMutator(MutationOperator):
    """
    Mutate integer parameters by small amounts.

    Example: ema_trend(9, 21) -> ema_trend(10, 21)

    Rules:
    - Change by ±1 to ±5
    - Stay within valid ranges per primitive
    - Never mutate to 0 or negative
    """

    VALID_RANGES = {
        "ema_trend": {"fast": (5, 20), "slow": (15, 50)},
        "norm_rsi": {"period": (7, 28)},
        "bb_position": {"period": (10, 30), "std": (1, 3)},
        "atr_regime": {"period": (7, 28)},
        "btc_trend": {"window": (30, 120)},
        "price_position": {"period": (10, 50)},
        "volume_intensity": {"period": (10, 50), "threshold": (1, 4)},
        "vwap_distance": {"period": (10, 50)},
    }

class ThresholdMutator(MutationOperator):
    """
    Adjust comparison thresholds.

    Example: norm_rsi(14) < -0.4 -> norm_rsi(14) < -0.5

    Rules:
    - Adjust by ±0.1 increments
    - Stay within primitive output ranges
    """

class LLMMutator(MutationOperator):
    """
    Use LLM to suggest intelligent mutations.

    This is the primary mutation operator - it uses backtest
    results to inform mutation decisions.
    """

    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client

    def mutate(
        self,
        strategy: Strategy,
        fitness_result: FitnessResult
    ) -> Strategy:
        """Use LLM to suggest mutation based on performance."""
```

### 4.2 Selection Strategy

```python
# mutator/selection.py

def tournament_selection(
    population: list[tuple[Strategy, FitnessResult]],
    tournament_size: int = 3,
) -> Strategy:
    """Select best strategy from random tournament."""

def elite_selection(
    population: list[tuple[Strategy, FitnessResult]],
    elite_count: int = 2,
) -> list[Strategy]:
    """Always keep top N strategies unchanged."""

def roulette_selection(
    population: list[tuple[Strategy, FitnessResult]],
) -> Strategy:
    """Probability proportional to fitness score."""
```

### 4.3 Evolution Loop

```python
# mutator/evolution.py

@dataclass
class EvolutionConfig:
    """Evolution configuration."""
    population_size: int = 20
    generations: int = 50
    elite_count: int = 2          # Unchanged survivors
    mutation_rate: float = 0.8    # Probability of mutation
    crossover_rate: float = 0.2   # Probability of crossover
    tournament_size: int = 3

class EvolutionEngine:
    """
    Main evolution loop.

    Each generation:
    1. Evaluate fitness for all strategies
    2. Select elite (top N) - unchanged
    3. Select parents via tournament
    4. Apply mutation or crossover
    5. Validate offspring (discard invalid)
    6. Form new generation
    """

    def __init__(
        self,
        backtester: VectorizedBacktester,
        fitness_calculator: FitnessCalculator,
        llm_mutator: LLMMutator,
        config: EvolutionConfig,
    ):
        pass

    def run(
        self,
        initial_population: list[Strategy],
        candles: dict[str, pd.DataFrame],
        benchmark_candles: pd.DataFrame,
    ) -> list[tuple[Strategy, FitnessResult]]:
        """Run evolution and return final population with fitness."""
```

### 4.4 Implementation Tasks

**Location:** `/shared/evolution/mutator/` (asset-agnostic)

| Task | Priority | Effort | Files |
|------|----------|--------|-------|
| Create `MutationType` enum | T0 | S | `shared/evolution/mutator/operators.py` |
| Implement `ParameterMutator` | T1 | M | `shared/evolution/mutator/operators.py` |
| Implement `ThresholdMutator` | T1 | M | `shared/evolution/mutator/operators.py` |
| Implement `LLMMutator` | T0 | L | `shared/evolution/mutator/llm_mutator.py` |
| Implement selection functions | T1 | M | `shared/evolution/mutator/selection.py` |
| Build `EvolutionEngine` | T1 | L | `shared/evolution/mutator/evolution.py` |
| Add strategy validation | T0 | M | `shared/evolution/mutator/validator.py` |
| Unit tests for operators | T1 | M | `shared/tests/test_operators.py` |

**Note:** Parameter valid ranges are defined generically. Asset-specific constraints
can override via config if needed.

---

## 5. Implementation Phases

**Philosophy:** Build thin vertical slices, not horizontal layers. Get end-to-end working first,
then deepen each component. This validates integration early and finds issues faster.

### Phase 2A: Minimal End-to-End Loop ✅ **COMPLETE**
**Goal:** Single strategy → backtest → fitness score → mutate → repeat (on 1 symbol)

1. [x] Minimal backtester: single symbol, basic metrics (Sharpe, DD, trade count)
2. [x] Minimal fitness: Sharpe-only score, no regime testing yet
3. [x] Minimal LLM: hardcoded prompt → parse response → validate primitives
4. [x] Minimal loop: generate 3 strategies → evaluate → pick best → mutate → repeat 3x
5. [x] Verify: end-to-end runs without crashing

**Success:** Can run `python evolve.py --generations=3 --symbol=SOLUSDT` ✅

**Implementation Notes (2025-12-08):**
- Files created: `shared/evolution/backtester/`, `shared/evolution/fitness/`, `shared/evolution/mutator/`
- Entry point: `crypto/evolve.py`
- Uses OpenAI gpt-4o by default (Anthropic fallback available)
- Currently testing with ~100 candles (need more data for meaningful results)
- Bybit API is geo-blocked from US - need to download data via Fly.io

### Phase 2B: Add Regime Testing
**Goal:** Evaluate strategies across market conditions

1. [ ] Implement regime classifier (5 regimes from BTC data)
2. [ ] Split backtest data by regime
3. [ ] Add regime_scores to FitnessResult
4. [ ] Implement regime multiplier in fitness
5. [ ] Add disqualification for negative regime Sharpe

**Success:** Strategies with poor bear-market performance get penalized.

### Phase 2C: Full Backtester
**Goal:** Multi-symbol, realistic execution

1. [ ] Multi-symbol backtesting (portfolio-level)
2. [ ] Position sizing with risk limits
3. [ ] Full friction modeling
4. [ ] Equity curve generation
5. [ ] Walk-forward validation

**Success:** Backtest results match shadow trader within 1%.

### Phase 2D: Full Evolution Engine
**Goal:** Robust evolution with selection pressure

1. [ ] Tournament selection
2. [ ] Elite preservation
3. [ ] LLM-guided mutation with performance context
4. [ ] Crossover operator
5. [ ] Population diversity tracking
6. [ ] Checkpoint/resume capability

**Success:** Average population Sharpe improves over 10 generations.

### Phase 2E: Production Integration
**Goal:** Connect to live system

1. [ ] Strategy persistence (save/load JSON)
2. [ ] Best strategy → shadow trader handoff
3. [ ] Evolution scheduling (nightly runs)
4. [ ] Monitoring dashboard / alerts
5. [ ] Documentation

---

## 6. Success Criteria

### Phase 2 Complete When:

- [ ] Backtester matches shadow trader results within 1%
- [ ] Fitness function correctly penalizes poor regime performance
- [ ] LLM generates valid strategies >90% of the time
- [ ] Evolution improves average Sharpe over 10 generations
- [ ] Walk-forward validation implemented and working
- [ ] At least 3 strategies pass all regime tests
- [ ] System can run overnight without intervention

### Metrics to Track:

| Metric | Target |
|--------|--------|
| Backtest speed | <1s per strategy per symbol |
| LLM success rate | >90% valid strategies |
| Evolution improvement | Sharpe +0.2 over 20 generations |
| Regime pass rate | 4/5 regimes for >50% of strategies |
| Memory usage | <2GB for 20-strategy population |

**Note:** These targets are initial benchmarks based on reasonable expectations.
They should be revisited after first experiments - actual market conditions and
strategy space may require adjustment. The "Sharpe +0.2" target in particular
depends on starting population quality.

---

## 7. Risk Mitigation

### Overfitting Risk
- Walk-forward validation (not just in-sample)
- Regime testing requirement
- Trade count minimum (30 trades)
- Max drawdown hard limits

### LLM Output Risk
- Strict JSON validation
- Primitive whitelist enforcement
- Parameter range validation
- Retry with explicit error feedback

### System Stability Risk
- Save state after each generation
- Graceful shutdown handling
- Memory monitoring
- Rate limiting for LLM calls

---

## Changelog

| Date | Change | Author |
|------|--------|--------|
| 2025-12-08 | Initial plan created | Claude |
| 2025-12-08 | Review: Fixed DD formula inconsistency, clarified regime rules, added LLM logging/retry requirements, restructured phases for vertical slice approach, added data distribution note, marked success criteria as initial benchmarks | Claude |
| 2025-12-08 | Added provider-agnostic LLM interface (OpenAI/Anthropic), added Section 0 for shared vs asset-specific architecture, updated all task tables with full paths and asset-agnostic notes, renamed btc_candles → benchmark_candles throughout | Claude |
| 2025-12-08 | **Phase 2A COMPLETE**: Implemented minimal backtester, fitness calculator, LLM client (OpenAI+Anthropic), strategy generator, and evolution loop. Successfully tested end-to-end pipeline with `crypto/evolve.py`. | Claude |

