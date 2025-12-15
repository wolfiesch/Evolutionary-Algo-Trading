# Parameter Evolution Architecture: Fixed Templates, Evolvable DNA

**Created:** 12/15/2025 09:14 AM PST (via pst-timestamp)
**Status:** Planning
**Priority:** T0 - Architectural Foundation

---

## Executive Summary

**The Problem:** The current system evolves *logic expressions* (string-based boolean combinations of primitives). While constrained to a gene pool, this is essentially "code evolution" with:
- Infinite search space (any combination of N primitives with M parameters)
- Structural brittleness (string parsing, typos break strategies)
- LLM making structural changes when parameter tuning would be better
- Difficult to reason about "what made this strategy better"

**The Solution:** Migrate to **Strategy Templates** where:
- **FIXED:** The logic structure (signal aggregation, entry/exit rules, risk management)
- **EVOLVED:** Only the parameters (weights, periods, thresholds)

**The Analogy:**
```
BAD:  Evolving "if random() > 0.5: buy()"  ← arbitrary code
ALSO BAD: Evolving "norm_rsi(14) < -0.3 AND ema_trend(9,21) == 1.0"  ← logic strings
GOOD: Evolving {weight_momentum: 0.6, rsi_period: 14, entry_threshold: -0.3}  ← parameters only
```

---

## Table of Contents

1. [Current State Analysis](#current-state-analysis)
2. [Target Architecture](#target-architecture)
3. [Parameter Schema Design](#parameter-schema-design)
4. [Strategy Template Specification](#strategy-template-specification)
5. [Asset-Specific Extensions](#asset-specific-extensions)
6. [Evolution Engine Changes](#evolution-engine-changes)
7. [Migration Strategy](#migration-strategy)
8. [Implementation Plan](#implementation-plan)
9. [Open Questions](#open-questions)
10. [Changelog](#changelog)

---

## Current State Analysis

### How Strategies Are Represented Today

```json
{
  "strategy_name": "MeanReversion_V3",
  "entry_long": "asset_trend(60) >= 0 AND bb_position(20, 1) < -0.5 AND norm_rsi(14) < 0.3",
  "exit_long": "norm_rsi(14) > 0.7 OR bb_position(20,1) > 0.5"
}
```

**What Gets Evolved:**
1. Primitive selection (swap `norm_rsi` for `bb_position`)
2. Parameter values (14 → 21, 60 → 50)
3. Thresholds (-0.3 → -0.4)
4. Condition count (add/remove conditions)
5. Logical structure (flip `<` to `>`)

**Problems With This Approach:**

| Issue | Impact |
|-------|--------|
| **Infinite search space** | LLM explores randomly, slow convergence |
| **String parsing overhead** | Runtime evaluation per signal |
| **Structural changes dominate** | LLM prefers "swap RSI for Bollinger" over "tune RSI period" |
| **Hard to analyze** | "Why did this strategy improve?" is unclear |
| **Deduplication challenges** | 30% of strategies are duplicates (LLM regenerates similar logic) |
| **Overfitting risk** | Can craft perfectly-fitted logic to historical data |

### What Works Well (Keep)

- **Gene pool primitives** - Pre-validated, bounded outputs (-1 to +1)
- **Integer-only parameters** - Prevents hyper-tuning
- **Market filter requirement** - Forced regime awareness
- **Regime testing** - Robustness validation
- **Continuous fitness scoring** - Preserves learning signal

---

## Target Architecture

### The Strategy Template Concept

```
┌─────────────────────────────────────────────────────────────────┐
│                     STRATEGY TEMPLATE                            │
│                                                                  │
│  ┌──────────────────┐    ┌──────────────────┐                   │
│  │   SIGNAL LAYER   │    │  DECISION LAYER  │                   │
│  │                  │    │                  │                   │
│  │ trend_signal     │    │ FIXED LOGIC:     │                   │
│  │ momentum_signal  │───>│ composite > thr  │──> ENTRY/EXIT     │
│  │ reversion_signal │    │                  │                   │
│  │ volatility_signal│    │                  │                   │
│  │ market_filter    │    │                  │                   │
│  └──────────────────┘    └──────────────────┘                   │
│           │                                                      │
│           │ Parameters (THE DNA)                                 │
│           │                                                      │
│  ┌────────┴────────────────────────────────────────────────┐    │
│  │ weight_trend: 0.8      | trend_fast: 9   | trend_slow: 21│    │
│  │ weight_momentum: 0.5   | momentum_period: 14             │    │
│  │ weight_reversion: -0.3 | reversion_period: 20            │    │
│  │ entry_threshold: 0.4   | exit_threshold: -0.3            │    │
│  │ stop_loss_atr: 2.0     | take_profit_atr: 3.0            │    │
│  └──────────────────────────────────────────────────────────┘    │
│                                                                  │
│  ▲ ONLY THIS GETS EVOLVED ▲                                      │
└─────────────────────────────────────────────────────────────────┘
```

### Key Design Principles

1. **Signal Aggregation, Not Logic Assembly**
   - Each primitive contributes a weighted signal
   - Composite = weighted average of enabled signals
   - Entry when composite > threshold, exit when < threshold

2. **Weight = 0 Disables Signal**
   - No need to "remove conditions"
   - Evolution can effectively disable signals by setting weight to 0
   - Simpler search space

3. **Signed Weights Enable Contrarian Usage**
   - `weight_momentum: -0.5` means "use RSI in reverse"
   - No need for separate "contrarian" primitives
   - Increases expressiveness without code changes

4. **Fixed Risk Management Logic**
   - Stop-loss always at N × ATR
   - Take-profit always at M × ATR
   - Position sizing fixed by risk engine
   - Parameters tune N and M, not the logic

---

## Parameter Schema Design

### Universal Parameters (All Asset Classes)

```python
@dataclass
class UniversalParameters:
    """Parameters that apply to all asset classes"""

    # === SIGNAL WEIGHTS ===
    # Range: -1.0 to +1.0 (0 = disabled, negative = contrarian)
    weight_trend: float = 0.0           # EMA crossover signal
    weight_momentum: float = 0.0        # RSI-based momentum
    weight_mean_reversion: float = 0.0  # Bollinger Band position
    weight_volatility: float = 0.0      # ATR regime signal
    weight_volume: float = 0.0          # Volume intensity signal

    # === SIGNAL PERIODS (Integers Only) ===
    # Trend
    trend_fast_period: int = 9          # Range: 3-50
    trend_slow_period: int = 21         # Range: 10-200

    # Momentum
    momentum_period: int = 14           # Range: 5-50

    # Mean Reversion
    reversion_period: int = 20          # Range: 10-100
    reversion_std_dev: int = 2          # Range: 1-3 (Bollinger std)

    # Volatility
    volatility_period: int = 14         # Range: 5-50

    # Volume
    volume_period: int = 20             # Range: 10-100

    # === DECISION THRESHOLDS ===
    entry_threshold: float = 0.3        # Range: 0.1-0.8
    exit_threshold: float = -0.2        # Range: -0.8 to 0.2

    # === RISK PARAMETERS ===
    stop_loss_atr_mult: float = 2.0     # Range: 1.0-5.0
    take_profit_atr_mult: float = 3.0   # Range: 1.5-8.0

    # === TIMING PARAMETERS ===
    min_bars_between_trades: int = 5    # Range: 1-50
    max_position_bars: int = 100        # Range: 20-500 (0 = unlimited)

    # === MARKET FILTER (Required) ===
    market_filter_period: int = 60      # Range: 20-200
    market_filter_threshold: float = 0.0  # Range: -1.0 to 1.0
```

### Parameter Constraints & Validation

```python
PARAMETER_CONSTRAINTS = {
    # Weights: bounded, continuous
    "weight_*": {"min": -1.0, "max": 1.0, "type": float},

    # Periods: bounded, integer-only
    "trend_fast_period": {"min": 3, "max": 50, "type": int},
    "trend_slow_period": {"min": 10, "max": 200, "type": int},
    "momentum_period": {"min": 5, "max": 50, "type": int},
    "reversion_period": {"min": 10, "max": 100, "type": int},
    "volatility_period": {"min": 5, "max": 50, "type": int},
    "volume_period": {"min": 10, "max": 100, "type": int},

    # Thresholds: bounded, continuous
    "entry_threshold": {"min": 0.1, "max": 0.8, "type": float},
    "exit_threshold": {"min": -0.8, "max": 0.2, "type": float},

    # Risk: bounded, continuous
    "stop_loss_atr_mult": {"min": 1.0, "max": 5.0, "type": float},
    "take_profit_atr_mult": {"min": 1.5, "max": 8.0, "type": float},

    # Cross-parameter constraints
    "trend_fast_period < trend_slow_period": True,
    "entry_threshold > exit_threshold": True,
    "take_profit_atr_mult > stop_loss_atr_mult": True,
}
```

### Parameter Discretization

To prevent overfitting and maintain search tractability:

```python
DISCRETIZATION = {
    "weights": 0.1,          # Round to nearest 0.1 (-1.0, -0.9, ..., 0.9, 1.0)
    "thresholds": 0.05,      # Round to nearest 0.05
    "atr_multipliers": 0.5,  # Round to nearest 0.5 (1.0, 1.5, 2.0, ...)
    "periods": 1,            # Already integers
}

# Effective search space per parameter:
# - Weights: 21 values each (21^5 = 4M weight combinations)
# - Periods: ~40 values each
# - Thresholds: ~20 values each
# Total: Still large but FINITE and ENUMERABLE
```

---

## Strategy Template Specification

### Base Template Interface

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Optional
import pandas as pd

@dataclass
class StrategyParameters:
    """Base class for strategy parameters (DNA)"""

    # Universal parameters
    weight_trend: float = 0.0
    weight_momentum: float = 0.0
    weight_mean_reversion: float = 0.0
    weight_volatility: float = 0.0
    weight_volume: float = 0.0

    trend_fast_period: int = 9
    trend_slow_period: int = 21
    momentum_period: int = 14
    reversion_period: int = 20
    reversion_std_dev: int = 2
    volatility_period: int = 14
    volume_period: int = 20

    entry_threshold: float = 0.3
    exit_threshold: float = -0.2

    stop_loss_atr_mult: float = 2.0
    take_profit_atr_mult: float = 3.0

    min_bars_between_trades: int = 5
    max_position_bars: int = 100

    market_filter_period: int = 60
    market_filter_threshold: float = 0.0

    def to_dict(self) -> Dict:
        """Serialize for storage/transmission"""
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict) -> 'StrategyParameters':
        """Deserialize from storage"""
        return cls(**d)

    def validate(self) -> tuple[bool, list[str]]:
        """Validate all constraints"""
        errors = []

        # Weight bounds
        for attr in ['weight_trend', 'weight_momentum', 'weight_mean_reversion',
                     'weight_volatility', 'weight_volume']:
            val = getattr(self, attr)
            if not -1.0 <= val <= 1.0:
                errors.append(f"{attr} must be in [-1.0, 1.0], got {val}")

        # Period ordering
        if self.trend_fast_period >= self.trend_slow_period:
            errors.append(f"trend_fast_period ({self.trend_fast_period}) must be < "
                         f"trend_slow_period ({self.trend_slow_period})")

        # Threshold ordering
        if self.entry_threshold <= self.exit_threshold:
            errors.append(f"entry_threshold ({self.entry_threshold}) must be > "
                         f"exit_threshold ({self.exit_threshold})")

        # Risk ordering
        if self.take_profit_atr_mult <= self.stop_loss_atr_mult:
            errors.append(f"take_profit_atr_mult ({self.take_profit_atr_mult}) must be > "
                         f"stop_loss_atr_mult ({self.stop_loss_atr_mult})")

        # At least one signal enabled
        weights_sum = sum(abs(getattr(self, f'weight_{sig}'))
                         for sig in ['trend', 'momentum', 'mean_reversion',
                                    'volatility', 'volume'])
        if weights_sum < 0.1:
            errors.append("At least one signal weight must be non-zero")

        return len(errors) == 0, errors


class StrategyTemplate(ABC):
    """
    Base strategy template with FIXED LOGIC.

    Subclasses implement asset-specific signal calculations,
    but the aggregation and decision logic is universal.
    """

    def __init__(self, params: StrategyParameters):
        self.params = params
        self._validate()

    def _validate(self):
        valid, errors = self.params.validate()
        if not valid:
            raise ValueError(f"Invalid parameters: {errors}")

    # === SIGNAL CALCULATION (Override in subclasses for asset-specific) ===

    @abstractmethod
    def calculate_market_filter(self, candles: pd.DataFrame) -> float:
        """Asset-specific market filter. Returns -1.0 to +1.0"""
        pass

    def calculate_trend_signal(self, candles: pd.DataFrame) -> float:
        """EMA crossover: +1.0 (uptrend) or -1.0 (downtrend)"""
        from shared.engine.gene_pool.trend import ema_trend
        return ema_trend(candles, self.params.trend_fast_period,
                        self.params.trend_slow_period)

    def calculate_momentum_signal(self, candles: pd.DataFrame) -> float:
        """Normalized RSI: -1.0 (oversold) to +1.0 (overbought)"""
        from shared.engine.gene_pool.mean_reversion import norm_rsi
        return norm_rsi(candles, self.params.momentum_period)

    def calculate_mean_reversion_signal(self, candles: pd.DataFrame) -> float:
        """Bollinger position: -1.0 (lower band) to +1.0 (upper band)"""
        from shared.engine.gene_pool.mean_reversion import bb_position
        return bb_position(candles, self.params.reversion_period,
                          float(self.params.reversion_std_dev))

    def calculate_volatility_signal(self, candles: pd.DataFrame) -> float:
        """ATR regime: +1.0 (high vol), 0.0 (normal), -1.0 (low vol)"""
        from shared.engine.gene_pool.volatility import atr_regime
        return atr_regime(candles, self.params.volatility_period)

    def calculate_volume_signal(self, candles: pd.DataFrame) -> float:
        """Volume intensity: 0.0 (low) to +1.0 (high)"""
        from shared.engine.gene_pool.volume import volume_intensity
        return volume_intensity(candles, self.params.volume_period, 1.5)

    # === FIXED AGGREGATION LOGIC (Never override) ===

    def calculate_composite_signal(self, candles: pd.DataFrame) -> float:
        """
        FIXED LOGIC: Weighted average of all enabled signals.

        This is the core innovation - the STRUCTURE is fixed,
        only the WEIGHTS are evolved.
        """
        signals = []
        weights = []

        signal_map = {
            'trend': self.calculate_trend_signal,
            'momentum': self.calculate_momentum_signal,
            'mean_reversion': self.calculate_mean_reversion_signal,
            'volatility': self.calculate_volatility_signal,
            'volume': self.calculate_volume_signal,
        }

        for name, calc_func in signal_map.items():
            weight = getattr(self.params, f'weight_{name}')
            if abs(weight) > 0.01:  # Skip disabled signals
                try:
                    signal_value = calc_func(candles)
                    signals.append(signal_value)
                    weights.append(weight)
                except Exception:
                    pass  # Skip failed signals

        if not signals:
            return 0.0

        # Weighted average (weights can be negative for contrarian)
        total_weight = sum(abs(w) for w in weights)
        return sum(s * w for s, w in zip(signals, weights)) / total_weight

    # === FIXED DECISION LOGIC (Never override) ===

    def should_enter_long(self, candles: pd.DataFrame) -> bool:
        """
        FIXED LOGIC: Enter when market filter OK AND composite > threshold
        """
        market_filter = self.calculate_market_filter(candles)
        if market_filter < self.params.market_filter_threshold:
            return False

        composite = self.calculate_composite_signal(candles)
        return composite > self.params.entry_threshold

    def should_exit_long(self, candles: pd.DataFrame) -> bool:
        """
        FIXED LOGIC: Exit when composite drops below exit threshold
        """
        composite = self.calculate_composite_signal(candles)
        return composite < self.params.exit_threshold

    def get_stop_loss_distance(self, candles: pd.DataFrame) -> float:
        """
        FIXED LOGIC: Stop at N × ATR below entry
        """
        from shared.engine.gene_pool.volatility import get_atr
        atr = get_atr(candles, 14)  # Fixed ATR period for stops
        return atr * self.params.stop_loss_atr_mult

    def get_take_profit_distance(self, candles: pd.DataFrame) -> float:
        """
        FIXED LOGIC: Take profit at M × ATR above entry
        """
        from shared.engine.gene_pool.volatility import get_atr
        atr = get_atr(candles, 14)
        return atr * self.params.take_profit_atr_mult

    # === EXPLAIN (For analysis) ===

    def explain_signal(self, candles: pd.DataFrame) -> Dict:
        """
        Returns breakdown of all signal contributions.
        Useful for understanding WHY a strategy triggered.
        """
        breakdown = {
            'market_filter': self.calculate_market_filter(candles),
            'composite_signal': self.calculate_composite_signal(candles),
            'signals': {},
            'entry_decision': self.should_enter_long(candles),
            'exit_decision': self.should_exit_long(candles),
        }

        for name in ['trend', 'momentum', 'mean_reversion', 'volatility', 'volume']:
            weight = getattr(self.params, f'weight_{name}')
            if abs(weight) > 0.01:
                calc_func = getattr(self, f'calculate_{name}_signal')
                raw_signal = calc_func(candles)
                weighted_signal = raw_signal * weight
                breakdown['signals'][name] = {
                    'weight': weight,
                    'raw_signal': raw_signal,
                    'weighted_contribution': weighted_signal,
                }

        return breakdown
```

### Template Inheritance Hierarchy

```
StrategyTemplate (abstract base)
│
├── CryptoStrategyTemplate
│   ├── calculate_market_filter() → uses btc_trend()
│   └── Additional: weight_btc_correlation, funding_rate_period, etc.
│
├── ForexStrategyTemplate
│   ├── calculate_market_filter() → uses dxy_trend()
│   └── Additional: weight_session, weight_rate_differential, etc.
│
└── (Future) EquitiesStrategyTemplate
    ├── calculate_market_filter() → uses spy_trend()
    └── Additional: weight_sector_rotation, earnings_proximity, etc.
```

---

## Asset-Specific Extensions

### Crypto-Specific Parameters

```python
@dataclass
class CryptoParameters(StrategyParameters):
    """Crypto-specific parameter extensions"""

    # BTC correlation (crypto trades with BTC)
    weight_btc_correlation: float = 0.0  # How much to weight BTC trend
    btc_trend_period: int = 60           # Period for BTC trend calc

    # Funding rate (perps-specific)
    weight_funding_rate: float = 0.0     # Contrarian funding signal
    funding_rate_threshold: float = 0.01 # Extreme funding level

    # Altcoin-specific
    weight_btc_dominance: float = 0.0    # BTC.D trend for alt timing
    btc_dominance_period: int = 30


class CryptoStrategyTemplate(StrategyTemplate):
    """Crypto-specific strategy template"""

    def __init__(self, params: CryptoParameters):
        super().__init__(params)
        self.params: CryptoParameters = params

    def calculate_market_filter(self, candles: pd.DataFrame) -> float:
        """Crypto market filter: BTC trend"""
        from crypto.engine.gene_pool.market_filter import btc_trend
        return btc_trend(candles, self.params.market_filter_period)

    def calculate_btc_correlation_signal(self, candles: pd.DataFrame) -> float:
        """BTC trend as a signal (for alts that follow BTC)"""
        from crypto.engine.gene_pool.market_filter import btc_trend
        return btc_trend(candles, self.params.btc_trend_period)

    def calculate_composite_signal(self, candles: pd.DataFrame) -> float:
        """Extended to include crypto-specific signals"""
        # Get base composite
        base_composite = super().calculate_composite_signal(candles)

        # Add crypto-specific signals
        extra_signals = []
        extra_weights = []

        if abs(self.params.weight_btc_correlation) > 0.01:
            btc_signal = self.calculate_btc_correlation_signal(candles)
            extra_signals.append(btc_signal)
            extra_weights.append(self.params.weight_btc_correlation)

        # ... funding rate, btc dominance, etc.

        if not extra_signals:
            return base_composite

        # Combine base and crypto-specific
        # Weight base signals by sum of their weights
        base_weight = sum(abs(getattr(self.params, f'weight_{s}'))
                         for s in ['trend', 'momentum', 'mean_reversion',
                                  'volatility', 'volume'])

        all_signals = [base_composite] + extra_signals
        all_weights = [base_weight] + extra_weights

        total = sum(abs(w) for w in all_weights)
        return sum(s * w for s, w in zip(all_signals, all_weights)) / total
```

### Forex-Specific Parameters

```python
@dataclass
class ForexParameters(StrategyParameters):
    """Forex-specific parameter extensions"""

    # Session timing (forex has distinct session behaviors)
    weight_session: float = 0.0          # Session-aware trading
    preferred_session: str = "london"    # "asian", "london", "newyork", "overlap"

    # Dollar index correlation
    weight_dxy: float = 0.0              # DXY trend correlation
    dxy_trend_period: int = 60

    # Interest rate differential
    weight_rate_diff: float = 0.0        # Carry trade signal

    # Risk sentiment
    weight_risk_sentiment: float = 0.0   # Risk-on/risk-off


class ForexStrategyTemplate(StrategyTemplate):
    """Forex-specific strategy template"""

    def calculate_market_filter(self, candles: pd.DataFrame) -> float:
        """Forex market filter: DXY trend for USD pairs"""
        from forex.engine.gene_pool.market_filter import dxy_trend
        return dxy_trend(candles, self.params.market_filter_period)

    # ... additional forex-specific signal methods
```

### Why Separate Templates Per Asset Class?

| Factor | Same Template | Separate Templates |
|--------|---------------|-------------------|
| **Market characteristics** | Forces generic signals | Asset-optimized signals |
| **Available data** | Lowest common denominator | Use all available data |
| **Code maintenance** | Simpler, one class | More code, but clearer |
| **Cross-asset learning** | Parameters transferable | Need mapping layer |
| **Signal relevance** | BTC trend meaningless for forex | Each asset has relevant signals |

**Recommendation:** **Separate templates with shared base class**
- Common logic (aggregation, thresholds) in base
- Asset-specific signals and market filters in subclasses
- Shared parameter validation
- Allows cross-pollination of universal parameters while respecting asset differences

---

## Evolution Engine Changes

### Current vs. New Mutation Approach

**Current (Logic Mutation):**
```python
# LLM mutates string expressions
MUTATION_OPTIONS:
1. SWAP primitive: Replace norm_rsi with bb_position
2. CHANGE params: 14->9 or 20->21
3. ADJUST thresholds: -0.3->-0.2
4. ADD condition to exit (if <3 conditions)
5. REMOVE weakest entry condition
6. FLIP logic: change < to >
```

**New (Parameter Mutation):**
```python
# LLM tunes parameters only
MUTATION_OPTIONS:
1. ADJUST weight: weight_momentum 0.5 -> 0.6 (strengthen signal)
2. DISABLE signal: weight_volatility 0.3 -> 0.0 (remove from composite)
3. ENABLE signal: weight_volume 0.0 -> 0.4 (add to composite)
4. TUNE period: momentum_period 14 -> 21 (slower momentum)
5. ADJUST threshold: entry_threshold 0.3 -> 0.4 (stricter entry)
6. ADJUST risk: stop_loss_atr_mult 2.0 -> 2.5 (wider stops)
7. FLIP polarity: weight_mean_reversion 0.5 -> -0.5 (contrarian)
```

### New Mutation Prompts

```python
PARAMETER_MUTATION_SYSTEM_PROMPT = """
You are evolving trading strategy PARAMETERS (not logic).

The strategy template has FIXED logic:
- Calculates weighted signals from: trend, momentum, mean_reversion, volatility, volume
- Entry when: market_filter >= threshold AND composite_signal > entry_threshold
- Exit when: composite_signal < exit_threshold

Your job: TUNE THE PARAMETERS to improve performance.

PARAMETER TYPES:
1. WEIGHTS (-1.0 to +1.0): How much each signal contributes
   - Positive = use signal normally
   - Negative = use signal in reverse (contrarian)
   - Zero = signal disabled

2. PERIODS (integers): Lookback windows for calculations
   - Smaller = faster, more reactive, more noise
   - Larger = slower, smoother, more lag

3. THRESHOLDS: Decision boundaries
   - Higher entry_threshold = fewer trades, higher conviction
   - Lower exit_threshold = hold longer, wider swings

4. RISK: Stop-loss and take-profit ATR multipliers
   - Higher = wider stops/targets, fewer stopped out, larger swings
   - Lower = tighter stops/targets, more stopped out, smaller swings

MUTATION GUIDANCE:
- If Sharpe is positive but low: Fine-tune weights and thresholds
- If win rate is low: Tighten entry_threshold or adjust signal weights
- If drawdown is high: Lower risk multipliers or disable volatile signals
- If regime testing failed: Add volatility weighting or adjust market filter
"""

PARAMETER_MUTATION_PROMPT = """
Current strategy parameters:
{current_params_json}

Performance metrics:
- Sharpe: {sharpe}
- Win Rate: {win_rate}%
- Max Drawdown: {max_drawdown}%
- Trade Count: {trade_count}
- Regime Results: {regime_results}

Previous mutations tried: {previous_mutations}

Suggest ONE parameter change. Return JSON:
{{
  "mutation_type": "adjust_weight|tune_period|adjust_threshold|adjust_risk|flip_polarity|enable_signal|disable_signal",
  "parameter_name": "the exact parameter name",
  "old_value": <current value>,
  "new_value": <proposed value>,
  "reasoning": "why this change should help"
}}
"""
```

### Crossover for Parameters

```python
def crossover_parameters(parent1: StrategyParameters,
                         parent2: StrategyParameters) -> StrategyParameters:
    """
    Crossover two parameter sets.

    Options:
    1. UNIFORM: Each parameter randomly from parent1 or parent2
    2. GROUPED: All weights from one, all periods from another, etc.
    3. BLEND: Average numerical parameters
    """
    child = StrategyParameters()

    # Group-based crossover (keeps related parameters together)
    groups = {
        'weights': ['weight_trend', 'weight_momentum', 'weight_mean_reversion',
                   'weight_volatility', 'weight_volume'],
        'periods': ['trend_fast_period', 'trend_slow_period', 'momentum_period',
                   'reversion_period', 'volatility_period', 'volume_period'],
        'thresholds': ['entry_threshold', 'exit_threshold'],
        'risk': ['stop_loss_atr_mult', 'take_profit_atr_mult'],
        'timing': ['min_bars_between_trades', 'max_position_bars'],
        'market_filter': ['market_filter_period', 'market_filter_threshold'],
    }

    for group_name, params in groups.items():
        # Randomly select which parent provides this group
        source = random.choice([parent1, parent2])
        for param in params:
            setattr(child, param, getattr(source, param))

    # Validate and repair if needed
    child = repair_constraints(child)

    return child


def repair_constraints(params: StrategyParameters) -> StrategyParameters:
    """Fix any constraint violations after crossover"""

    # trend_fast < trend_slow
    if params.trend_fast_period >= params.trend_slow_period:
        params.trend_fast_period = params.trend_slow_period - 5

    # entry > exit threshold
    if params.entry_threshold <= params.exit_threshold:
        gap = (params.entry_threshold - params.exit_threshold) / 2
        params.entry_threshold += abs(gap) + 0.1
        params.exit_threshold -= abs(gap) + 0.1

    # take_profit > stop_loss
    if params.take_profit_atr_mult <= params.stop_loss_atr_mult:
        params.take_profit_atr_mult = params.stop_loss_atr_mult + 0.5

    return params
```

### Parameter Space Statistics

```
Universal Parameters: 17 parameters
Crypto Extension: +4 parameters = 21 total
Forex Extension: +4 parameters = 21 total

With discretization:
- 5 weights × 21 values = 105 weight combinations
- 6 periods × ~40 values = 240 period combinations
- 2 thresholds × ~20 values = 40 threshold combinations
- 2 risk × ~8 values = 16 risk combinations
- Market filter: ~100 combinations

Approximate search space: 10^8 combinations

Compare to string-based logic:
- Unlimited combinations (any subset of primitives, any params, any thresholds)
- Effectively infinite

The parameter approach is TRACTABLE for optimization.
```

---

## Migration Strategy

### Phase 1: Parallel Implementation

1. Build new template system alongside existing string-based system
2. Both systems can run simultaneously during transition
3. Compare performance on same backtest data

### Phase 2: Strategy Conversion

Convert existing top-performing strategies to parameter form:

```python
def convert_string_strategy_to_params(
    entry_long: str,
    exit_long: str
) -> StrategyParameters:
    """
    Attempt to convert a string-based strategy to parameter form.

    Example:
    "asset_trend(60) >= 0 AND ema_trend(9,21) == 1.0 AND norm_rsi(14) < -0.3"

    Becomes:
    - market_filter_period: 60
    - weight_trend: 1.0 (enabled)
    - trend_fast_period: 9
    - trend_slow_period: 21
    - weight_momentum: 1.0 (enabled, using RSI)
    - momentum_period: 14
    - entry_threshold: based on threshold in string
    """
    params = StrategyParameters()

    # Parse and extract... (complex string parsing)
    # This is a one-time migration, doesn't need to be perfect

    return params
```

### Phase 3: Deprecate String-Based

1. Stop evolving new string-based strategies
2. Keep parser for backward compatibility (reading old strategies)
3. All new evolution uses parameter templates

### Backward Compatibility

```python
class LegacyStrategyAdapter:
    """
    Wraps old string-based strategies to match StrategyTemplate interface.
    Allows gradual migration while keeping old strategies functional.
    """

    def __init__(self, entry_long: str, exit_long: str, parser: GeneExpressionParser):
        self.entry_long = entry_long
        self.exit_long = exit_long
        self.parser = parser

    def should_enter_long(self, candles: pd.DataFrame) -> bool:
        return self.parser.evaluate_expression(self.entry_long, candles)

    def should_exit_long(self, candles: pd.DataFrame) -> bool:
        return self.parser.evaluate_expression(self.exit_long, candles)
```

---

## Implementation Plan

### Phase 1: Schema & Validation (Week 1)
- [ ] Define `StrategyParameters` dataclass with all universal parameters
- [ ] Define `CryptoParameters` extension
- [ ] Define `ForexParameters` extension
- [ ] Implement parameter validation
- [ ] Implement discretization utilities
- [ ] Unit tests for validation

### Phase 2: Base Template (Week 1-2)
- [ ] Implement `StrategyTemplate` abstract base class
- [ ] Implement signal calculation methods
- [ ] Implement composite signal aggregation (weighted average)
- [ ] Implement entry/exit decision logic
- [ ] Implement `explain_signal()` for debugging
- [ ] Unit tests for template logic

### Phase 3: Asset Templates (Week 2)
- [ ] Implement `CryptoStrategyTemplate`
  - [ ] Wire up market filter to `btc_trend()`
  - [ ] Add BTC correlation signal
  - [ ] Add funding rate signal (if data available)
- [ ] Implement `ForexStrategyTemplate` (placeholder)
- [ ] Integration tests with real candle data

### Phase 4: Evolution Integration (Week 2-3)
- [ ] Update mutation prompts for parameter-only changes
- [ ] Implement `mutate_parameters()` function
- [ ] Implement `crossover_parameters()` function
- [ ] Update `EvolutionEngine` to use templates
- [ ] Add parameter history tracking (which params changed)
- [ ] Integration tests for evolution loop

### Phase 5: Fitness & Backtesting (Week 3)
- [ ] Update `MinimalBacktester` to accept `StrategyTemplate`
- [ ] Verify fitness calculation works with templates
- [ ] Benchmark: compare backtest speed (template vs string parsing)
- [ ] Verify regime testing works

### Phase 6: Migration & Cleanup (Week 3-4)
- [ ] Convert top 10 existing strategies to parameter form
- [ ] Implement `LegacyStrategyAdapter` for old strategies
- [ ] Update strategy persistence (`StrategyRecord`)
- [ ] Update analysis tools
- [ ] Documentation updates

### Phase 7: Validation (Week 4)
- [ ] Run parallel evolution: string-based vs template-based
- [ ] Compare convergence speed
- [ ] Compare strategy quality (Sharpe, robustness)
- [ ] Compare LLM token usage (should be lower)
- [ ] Make go/no-go decision on full migration

---

## Open Questions

### 1. Should We Support Multiple Template Types?

**Option A: Single Template Type**
- One weighted-average template for all strategies
- Simplest, most constrained
- May miss strategies that need different aggregation logic

**Option B: Multiple Template Types**
- `WeightedAverageTemplate` (proposed)
- `ThresholdCascadeTemplate` (if signal1 > X AND signal2 > Y)
- `HierarchicalTemplate` (nested conditions)
- More expressive, but larger search space

**Current Recommendation:** Start with **Option A**, add templates only if we hit expressiveness limits.

### 2. Should Weights Be Continuous or Discrete?

**Continuous (-1.0 to +1.0):**
- Pro: Fine-grained control
- Con: Harder for LLM to reason about small differences

**Discrete (-1.0, -0.5, 0.0, +0.5, +1.0):**
- Pro: Finite search space, easier for LLM
- Con: May miss optimal values

**Current Recommendation:** **Continuous with discretization** (round to 0.1)

### 3. How Do We Handle Strategies That Don't Fit the Template?

Some discovered strategies might not be expressible as weighted averages (e.g., "enter when RSI oversold AND volatility expanding").

**Options:**
1. Accept template limitations, those strategies can't be represented
2. Add more templates (threshold-based, etc.)
3. Keep string-based system for "outlier" strategies

**Current Recommendation:** Accept limitations initially. Monitor what strategies can't be expressed, add templates if pattern emerges.

### 4. Should We Allow Short Strategies?

Current system is long-only. Templates could support short:
- `entry_short`: opposite of `entry_long` (flip signs)
- `exit_short`: opposite of `exit_long`

**Current Recommendation:** Defer until long-only is working well. Add as separate phase.

---

## Success Criteria

1. **Convergence Speed**: Evolution finds profitable strategies 2x faster
2. **Strategy Quality**: Higher Sharpe ratio in top strategies
3. **Robustness**: Better regime test pass rate
4. **Interpretability**: Can explain WHY a strategy works (signal contributions)
5. **Token Efficiency**: 30% reduction in LLM token usage
6. **Duplicate Rate**: <10% duplicates (vs. ~30% with strings)
7. **Maintainability**: Single template file vs. complex parser

---

## Changelog

| Timestamp | Change | Author |
|-----------|--------|--------|
| 12/15/2025 09:14 AM PST | Initial plan created | Claude |

---

**Next Step:** Review this plan and decide on Open Questions before implementation.

**Estimated Implementation Time:** 3-4 weeks for full migration (but functional prototype in Week 2)
