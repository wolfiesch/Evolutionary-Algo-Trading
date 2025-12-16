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

### Critical Architecture Requirements (From Review)

The following requirements were identified in the [peer review](2025-12-15-review-parameter-architecture.md) and **MUST** be incorporated from Day 1:

#### 1. Vectorization is Non-Negotiable

**Problem:** Loop-based signal calculation is too slow for backtesting thousands of strategies.

**Solution:** All signal calculations return `pd.Series`, not scalars:

```python
# BAD (scalar, requires loop per bar):
def calculate_trend_signal(self, candles: pd.DataFrame) -> float:
    return ema_trend(candles, fast, slow)  # Returns single value

# GOOD (vectorized, entire history in one pass):
def calculate_trend_signal(self, candles: pd.DataFrame) -> pd.Series:
    return ema_trend_series(candles, fast, slow)  # Returns Series[float]
```

**Composite calculation must be vectorized:**

```python
def calculate_composite_signal(self, candles: pd.DataFrame) -> pd.Series:
    """Vectorized weighted average across all signals."""
    composite = pd.Series(0.0, index=candles.index)
    total_weight = 0.0

    for name in ['trend', 'momentum', 'mean_reversion', 'volatility', 'volume']:
        weight = getattr(self.params, f'weight_{name}')
        if abs(weight) > 0.01:
            signal_series = getattr(self, f'calculate_{name}_signal')(candles)
            composite += signal_series * weight
            total_weight += abs(weight)

    return composite / total_weight if total_weight > 0 else composite
```

**Backtester implications:**
- Pre-compute entire signal series in one pass
- Entry/exit decisions via vectorized comparison: `entries = composite > threshold`
- No Python loops over candles during backtest

#### 2. Regime-Switched Weights (Non-Linear Adaptability)

**Problem:** A single set of static weights averages out to mediocrity:
- In choppy markets, you want high mean-reversion, low trend-following
- In trending markets, you want high trend-following, low mean-reversion
- Static weights can't adapt, producing "average" performance everywhere

**Solution:** Evolve **two weight sets** with a **regime selector**:

```
┌─────────────────────────────────────────────────────────────────────┐
│                    REGIME-SWITCHED TEMPLATE                          │
│                                                                      │
│  ┌──────────────┐                                                   │
│  │ REGIME GATE  │  regime_indicator (ADX/ATR) > regime_threshold?   │
│  └──────┬───────┘                                                   │
│         │                                                            │
│    ┌────▼────┐        ┌────────────┐                                │
│    │ YES     │        │ NO         │                                │
│    │ Regime B│        │ Regime A   │                                │
│    │ (Trend) │        │ (Range)    │                                │
│    └────┬────┘        └─────┬──────┘                                │
│         │                    │                                       │
│  weights_B: {         weights_A: {                                  │
│    trend: 0.8,          trend: 0.1,                                 │
│    momentum: 0.5,       momentum: 0.3,                              │
│    reversion: 0.1       reversion: 0.8                              │
│  }                    }                                             │
│         │                    │                                       │
│         └────────┬───────────┘                                       │
│                  ▼                                                   │
│         composite_signal                                             │
└─────────────────────────────────────────────────────────────────────┘
```

**Complexity cost:** 2× weight parameters
**Performance gain:** Non-linear adaptability to market conditions

#### 3. Native Short Architecture (Directional Intent)

**Problem:** Designing "Long-Only" now makes adding shorts painful later. In crypto/forex, shorting is 50% of the opportunity set.

**Solution:** Define composite signal as **Directional Intent**:

```
Composite Signal Range:
  +1.0 = Maximum LONG conviction
   0.0 = Neutral (no position)
  -1.0 = Maximum SHORT conviction

Entry Thresholds:
  entry_threshold_long:  +0.3  (composite >  +0.3 → ENTER LONG)
  entry_threshold_short: -0.3  (composite < -0.3 → ENTER SHORT)

Exit Thresholds:
  exit_threshold_long:  -0.1  (composite < -0.1 → EXIT LONG)
  exit_threshold_short: +0.1  (composite > +0.1 → EXIT SHORT)
```

**Implementation:**
- Negative weights naturally produce short signals (contrarian use)
- Same template supports long-only (disable short thresholds) or bidirectional
- No architectural changes needed later

---

## Parameter Schema Design

### Universal Parameters (All Asset Classes)

```python
@dataclass
class WeightVector:
    """A set of signal weights (used for regime switching)"""
    trend: float = 0.0           # EMA crossover signal
    momentum: float = 0.0        # RSI-based momentum
    mean_reversion: float = 0.0  # Bollinger Band position
    volatility: float = 0.0      # ATR regime signal
    volume: float = 0.0          # Volume intensity signal

    def to_dict(self) -> Dict[str, float]:
        return asdict(self)

    def validate(self) -> list[str]:
        errors = []
        for field in ['trend', 'momentum', 'mean_reversion', 'volatility', 'volume']:
            val = getattr(self, field)
            if not -1.0 <= val <= 1.0:
                errors.append(f"weight_{field} must be in [-1.0, 1.0], got {val}")
        return errors


@dataclass
class UniversalParameters:
    """Parameters that apply to all asset classes"""

    # === REGIME SELECTOR (for regime-switched weights) ===
    regime_indicator: str = "adx"       # "adx", "atr_percentile", "bb_width"
    regime_period: int = 14             # Period for regime indicator
    regime_threshold: float = 25.0      # Above = Regime B (trending), Below = Regime A (ranging)

    # === SIGNAL WEIGHTS - REGIME A (Low Vol / Ranging Market) ===
    # Used when regime_indicator < regime_threshold
    weights_A: WeightVector = field(default_factory=lambda: WeightVector(
        trend=0.1,
        momentum=0.3,
        mean_reversion=0.8,  # Favor mean reversion in ranges
        volatility=0.2,
        volume=0.1,
    ))

    # === SIGNAL WEIGHTS - REGIME B (High Vol / Trending Market) ===
    # Used when regime_indicator >= regime_threshold
    weights_B: WeightVector = field(default_factory=lambda: WeightVector(
        trend=0.8,           # Favor trend following in trends
        momentum=0.5,
        mean_reversion=0.1,
        volatility=0.3,
        volume=0.2,
    ))

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

    # === DECISION THRESHOLDS (Bidirectional) ===
    # Long entries/exits
    entry_threshold_long: float = 0.3    # Range: 0.1-0.8 (composite > this → LONG)
    exit_threshold_long: float = -0.1    # Range: -0.5 to 0.2 (composite < this → EXIT LONG)

    # Short entries/exits (set entry_threshold_short > 0 to disable shorts)
    entry_threshold_short: float = -0.3  # Range: -0.8 to -0.1 (composite < this → SHORT)
    exit_threshold_short: float = 0.1    # Range: -0.2 to 0.5 (composite > this → EXIT SHORT)

    # === RISK PARAMETERS ===
    stop_loss_atr_mult: float = 2.0     # Range: 1.0-5.0
    take_profit_atr_mult: float = 3.0   # Range: 1.5-8.0

    # === TIMING PARAMETERS ===
    min_bars_between_trades: int = 5    # Range: 1-50
    max_position_bars: int = 100        # Range: 20-500 (0 = unlimited)

    # === MARKET FILTER (Required) ===
    market_filter_period: int = 60      # Range: 20-200
    market_filter_threshold: float = 0.0  # Range: -1.0 to 1.0

    # === DIRECTION CONTROL ===
    allow_long: bool = True             # Enable long positions
    allow_short: bool = False           # Enable short positions (default: long-only)
```

### Parameter Constraints & Validation

```python
PARAMETER_CONSTRAINTS = {
    # Weights: bounded, continuous (applies to both WeightVector fields)
    "weights_*.trend": {"min": -1.0, "max": 1.0, "type": float},
    "weights_*.momentum": {"min": -1.0, "max": 1.0, "type": float},
    "weights_*.mean_reversion": {"min": -1.0, "max": 1.0, "type": float},
    "weights_*.volatility": {"min": -1.0, "max": 1.0, "type": float},
    "weights_*.volume": {"min": -1.0, "max": 1.0, "type": float},

    # Regime selector
    "regime_indicator": {"allowed": ["adx", "atr_percentile", "bb_width"]},
    "regime_period": {"min": 5, "max": 50, "type": int},
    "regime_threshold": {"min": 10.0, "max": 50.0, "type": float},

    # Periods: bounded, integer-only
    "trend_fast_period": {"min": 3, "max": 50, "type": int},
    "trend_slow_period": {"min": 10, "max": 200, "type": int},
    "momentum_period": {"min": 5, "max": 50, "type": int},
    "reversion_period": {"min": 10, "max": 100, "type": int},
    "volatility_period": {"min": 5, "max": 50, "type": int},
    "volume_period": {"min": 10, "max": 100, "type": int},

    # Thresholds: bounded, bidirectional
    "entry_threshold_long": {"min": 0.1, "max": 0.8, "type": float},
    "exit_threshold_long": {"min": -0.5, "max": 0.2, "type": float},
    "entry_threshold_short": {"min": -0.8, "max": -0.1, "type": float},
    "exit_threshold_short": {"min": -0.2, "max": 0.5, "type": float},

    # Risk: bounded, continuous
    "stop_loss_atr_mult": {"min": 1.0, "max": 5.0, "type": float},
    "take_profit_atr_mult": {"min": 1.5, "max": 8.0, "type": float},

    # Cross-parameter constraints
    "trend_fast_period < trend_slow_period": True,
    "entry_threshold_long > exit_threshold_long": True,
    "entry_threshold_short < exit_threshold_short": True,
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
from dataclasses import dataclass, field, asdict
from typing import Dict, Optional, Literal
import pandas as pd
import numpy as np


class StrategyTemplate(ABC):
    """
    Base strategy template with FIXED LOGIC.

    Key architectural features:
    1. VECTORIZED: All signals return pd.Series for fast backtesting
    2. REGIME-SWITCHED: Two weight sets selected by regime indicator
    3. BIDIRECTIONAL: Native support for long AND short positions

    Subclasses implement asset-specific signal calculations,
    but the aggregation and decision logic is universal.
    """

    def __init__(self, params: UniversalParameters):
        self.params = params
        self._signal_cache: Dict[str, pd.Series] = {}

    # === REGIME DETECTION (Vectorized) ===

    def calculate_regime_indicator(self, candles: pd.DataFrame) -> pd.Series:
        """
        Calculate regime indicator series.
        Returns pd.Series where True = Regime B (trending), False = Regime A (ranging)
        """
        if self.params.regime_indicator == "adx":
            from ta.trend import ADXIndicator
            adx = ADXIndicator(
                candles['high'], candles['low'], candles['close'],
                window=self.params.regime_period
            )
            return adx.adx() >= self.params.regime_threshold

        elif self.params.regime_indicator == "atr_percentile":
            from shared.engine.gene_pool.volatility import atr_percentile_series
            atr_pct = atr_percentile_series(candles, self.params.regime_period)
            return atr_pct >= self.params.regime_threshold / 100.0  # Normalize

        elif self.params.regime_indicator == "bb_width":
            from ta.volatility import BollingerBands
            bb = BollingerBands(candles['close'], window=self.params.regime_period)
            bb_width = (bb.bollinger_hband() - bb.bollinger_lband()) / bb.bollinger_mavg()
            # bb_width percentile
            return bb_width >= bb_width.rolling(100).quantile(self.params.regime_threshold / 100.0)

        else:
            raise ValueError(f"Unknown regime indicator: {self.params.regime_indicator}")

    def get_active_weights(self, is_regime_b: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series, pd.Series]:
        """
        Return weight series that switch based on regime.
        Each returned series has the appropriate weight for each bar.
        """
        weights_a = self.params.weights_A
        weights_b = self.params.weights_B

        # Create weight series that switch based on regime
        w_trend = pd.Series(np.where(is_regime_b, weights_b.trend, weights_a.trend), index=is_regime_b.index)
        w_momentum = pd.Series(np.where(is_regime_b, weights_b.momentum, weights_a.momentum), index=is_regime_b.index)
        w_reversion = pd.Series(np.where(is_regime_b, weights_b.mean_reversion, weights_a.mean_reversion), index=is_regime_b.index)
        w_volatility = pd.Series(np.where(is_regime_b, weights_b.volatility, weights_a.volatility), index=is_regime_b.index)
        w_volume = pd.Series(np.where(is_regime_b, weights_b.volume, weights_a.volume), index=is_regime_b.index)

        return w_trend, w_momentum, w_reversion, w_volatility, w_volume

    # === SIGNAL CALCULATION (Vectorized - return pd.Series) ===

    @abstractmethod
    def calculate_market_filter(self, candles: pd.DataFrame) -> pd.Series:
        """Asset-specific market filter. Returns pd.Series[-1.0 to +1.0]"""
        pass

    def calculate_trend_signal(self, candles: pd.DataFrame) -> pd.Series:
        """EMA crossover: +1.0 (uptrend) or -1.0 (downtrend) as Series"""
        from shared.engine.gene_pool.trend import ema_trend_series
        return ema_trend_series(candles, self.params.trend_fast_period,
                                self.params.trend_slow_period)

    def calculate_momentum_signal(self, candles: pd.DataFrame) -> pd.Series:
        """Normalized RSI: -1.0 (oversold) to +1.0 (overbought) as Series"""
        from shared.engine.gene_pool.mean_reversion import norm_rsi_series
        return norm_rsi_series(candles, self.params.momentum_period)

    def calculate_mean_reversion_signal(self, candles: pd.DataFrame) -> pd.Series:
        """Bollinger position: -1.0 (lower band) to +1.0 (upper band) as Series"""
        from shared.engine.gene_pool.mean_reversion import bb_position_series
        return bb_position_series(candles, self.params.reversion_period,
                                  float(self.params.reversion_std_dev))

    def calculate_volatility_signal(self, candles: pd.DataFrame) -> pd.Series:
        """ATR regime: +1.0 (high vol), 0.0 (normal), -1.0 (low vol) as Series"""
        from shared.engine.gene_pool.volatility import atr_regime_series
        return atr_regime_series(candles, self.params.volatility_period)

    def calculate_volume_signal(self, candles: pd.DataFrame) -> pd.Series:
        """Volume intensity: 0.0 (low) to +1.0 (high) as Series"""
        from shared.engine.gene_pool.volume import volume_intensity_series
        return volume_intensity_series(candles, self.params.volume_period, 1.5)

    # === FIXED AGGREGATION LOGIC (Vectorized, Regime-Switched) ===

    def calculate_composite_signal(self, candles: pd.DataFrame) -> pd.Series:
        """
        FIXED LOGIC: Regime-switched weighted average of all signals.

        Returns pd.Series of composite signal values (-1.0 to +1.0).
        This is VECTORIZED - calculates entire history in one pass.
        """
        # Calculate regime for each bar
        is_regime_b = self.calculate_regime_indicator(candles)

        # Get regime-dependent weights
        w_trend, w_momentum, w_reversion, w_volatility, w_volume = self.get_active_weights(is_regime_b)

        # Calculate all signal series (vectorized)
        signals = {
            'trend': self.calculate_trend_signal(candles),
            'momentum': self.calculate_momentum_signal(candles),
            'mean_reversion': self.calculate_mean_reversion_signal(candles),
            'volatility': self.calculate_volatility_signal(candles),
            'volume': self.calculate_volume_signal(candles),
        }

        weights = {
            'trend': w_trend,
            'momentum': w_momentum,
            'mean_reversion': w_reversion,
            'volatility': w_volatility,
            'volume': w_volume,
        }

        # Vectorized weighted sum
        composite = pd.Series(0.0, index=candles.index)
        total_weight = pd.Series(0.0, index=candles.index)

        for name in signals:
            w = weights[name]
            s = signals[name]
            # Only include where weight is significant
            mask = w.abs() > 0.01
            composite = composite + (s * w).where(mask, 0.0)
            total_weight = total_weight + w.abs().where(mask, 0.0)

        # Avoid division by zero
        total_weight = total_weight.replace(0.0, 1.0)
        return composite / total_weight

    # === FIXED DECISION LOGIC (Vectorized, Bidirectional) ===

    def generate_signals(self, candles: pd.DataFrame) -> pd.DataFrame:
        """
        Generate all trading signals for the entire candle history.

        Returns DataFrame with columns:
        - composite: The composite signal (-1 to +1)
        - market_filter: The market filter value
        - entry_long: Boolean, True where should enter long
        - exit_long: Boolean, True where should exit long
        - entry_short: Boolean, True where should enter short
        - exit_short: Boolean, True where should exit short
        """
        composite = self.calculate_composite_signal(candles)
        market_filter = self.calculate_market_filter(candles)

        signals = pd.DataFrame(index=candles.index)
        signals['composite'] = composite
        signals['market_filter'] = market_filter

        # Long signals (if enabled)
        if self.params.allow_long:
            signals['entry_long'] = (
                (market_filter >= self.params.market_filter_threshold) &
                (composite > self.params.entry_threshold_long)
            )
            signals['exit_long'] = composite < self.params.exit_threshold_long
        else:
            signals['entry_long'] = False
            signals['exit_long'] = False

        # Short signals (if enabled)
        if self.params.allow_short:
            signals['entry_short'] = (
                (market_filter >= self.params.market_filter_threshold) &
                (composite < self.params.entry_threshold_short)
            )
            signals['exit_short'] = composite > self.params.exit_threshold_short
        else:
            signals['entry_short'] = False
            signals['exit_short'] = False

        return signals

    # === RISK (Vectorized) ===

    def get_atr_series(self, candles: pd.DataFrame, period: int = 14) -> pd.Series:
        """Get ATR series for stop/target calculations"""
        from ta.volatility import AverageTrueRange
        atr = AverageTrueRange(candles['high'], candles['low'], candles['close'], window=period)
        return atr.average_true_range()

    def get_stop_loss_distance(self, candles: pd.DataFrame) -> pd.Series:
        """Stop at N × ATR - returns Series"""
        return self.get_atr_series(candles) * self.params.stop_loss_atr_mult

    def get_take_profit_distance(self, candles: pd.DataFrame) -> pd.Series:
        """Take profit at M × ATR - returns Series"""
        return self.get_atr_series(candles) * self.params.take_profit_atr_mult

    # === EXPLAIN (For analysis at a single point) ===

    def explain_signal_at(self, candles: pd.DataFrame, idx: int = -1) -> Dict:
        """
        Returns breakdown of signal contributions at a specific index.
        Useful for understanding WHY a strategy triggered at a point.
        """
        signals_df = self.generate_signals(candles)
        is_regime_b = self.calculate_regime_indicator(candles)

        # Get values at index
        row = signals_df.iloc[idx]
        regime = "B (Trending)" if is_regime_b.iloc[idx] else "A (Ranging)"
        active_weights = self.params.weights_B if is_regime_b.iloc[idx] else self.params.weights_A

        breakdown = {
            'index': idx,
            'timestamp': candles.index[idx] if hasattr(candles.index, '__getitem__') else idx,
            'regime': regime,
            'active_weights': active_weights.to_dict(),
            'composite_signal': row['composite'],
            'market_filter': row['market_filter'],
            'entry_long': row['entry_long'],
            'exit_long': row['exit_long'],
            'entry_short': row['entry_short'],
            'exit_short': row['exit_short'],
            'signal_contributions': {},
        }

        # Calculate individual contributions
        for name in ['trend', 'momentum', 'mean_reversion', 'volatility', 'volume']:
            weight = getattr(active_weights, name)
            if abs(weight) > 0.01:
                signal_series = getattr(self, f'calculate_{name}_signal')(candles)
                raw_signal = signal_series.iloc[idx]
                breakdown['signal_contributions'][name] = {
                    'weight': weight,
                    'raw_signal': raw_signal,
                    'weighted_contribution': raw_signal * weight,
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
- [ ] Define `WeightVector` dataclass for signal weights
- [ ] Define `UniversalParameters` dataclass with:
  - [ ] Regime selector (indicator, period, threshold)
  - [ ] Two weight vectors (weights_A, weights_B)
  - [ ] Bidirectional thresholds (entry/exit for long AND short)
  - [ ] Direction control flags (allow_long, allow_short)
- [ ] Define `CryptoParameters` extension
- [ ] Define `ForexParameters` extension
- [ ] Implement parameter validation (cross-parameter constraints)
- [ ] Implement discretization utilities
- [ ] Unit tests for validation
- [ ] **Property-based testing with `hypothesis`** (per review recommendation)

### Phase 2: Vectorized Gene Pool Primitives (Week 1-2)
- [ ] Implement `_series` versions of all primitives:
  - [ ] `ema_trend_series()` → returns pd.Series
  - [ ] `norm_rsi_series()` → returns pd.Series
  - [ ] `bb_position_series()` → returns pd.Series
  - [ ] `atr_regime_series()` → returns pd.Series
  - [ ] `volume_intensity_series()` → returns pd.Series
  - [ ] `atr_percentile_series()` → returns pd.Series
- [ ] Unit tests verifying vectorized output matches scalar version
- [ ] Performance benchmarks (vectorized vs loop)

### Phase 3: Base Template (Week 2)
- [ ] Implement `StrategyTemplate` abstract base class
- [ ] Implement regime detection (`calculate_regime_indicator`)
- [ ] Implement regime-switched weight selection (`get_active_weights`)
- [ ] Implement vectorized signal calculation methods
- [ ] Implement vectorized composite signal aggregation
- [ ] Implement `generate_signals()` returning full DataFrame
- [ ] Implement bidirectional entry/exit logic (long AND short)
- [ ] Implement `explain_signal_at()` for debugging
- [ ] Unit tests for template logic
- [ ] **Verify entire signal series computed in one pass** (no loops over bars)

### Phase 4: Asset Templates (Week 2-3)
- [ ] Implement `CryptoStrategyTemplate`
  - [ ] Vectorized market filter using `btc_trend_series()`
  - [ ] Add BTC correlation signal (vectorized)
  - [ ] Add funding rate signal if data available (vectorized)
- [ ] Implement `ForexStrategyTemplate` (placeholder)
- [ ] Integration tests with real candle data
- [ ] Performance benchmark: signal generation for 10K candles

### Phase 5: Evolution Integration (Week 3)
- [ ] Update mutation prompts for parameter-only changes
  - [ ] Include regime-specific weight mutations
  - [ ] Include regime selector mutations (indicator, threshold)
  - [ ] Include direction control mutations (enable/disable shorts)
- [ ] Implement `mutate_parameters()` function
- [ ] Implement `crossover_parameters()` with constraint repair
- [ ] Update `EvolutionEngine` to use templates
- [ ] Add parameter history tracking (which params changed)
- [ ] Integration tests for evolution loop

### Phase 6: Vectorized Backtesting (Week 3-4)
- [ ] Update `MinimalBacktester` to accept `StrategyTemplate`
- [ ] **Vectorized backtest loop** (no Python iteration over candles)
  - [ ] Pre-compute all signals via `generate_signals()`
  - [ ] Use vectorized entry/exit detection
  - [ ] Vectorized position tracking
- [ ] Support bidirectional backtesting (long AND short positions)
- [ ] Verify fitness calculation works with templates
- [ ] **Benchmark: target 10x speedup over string parsing**
- [ ] Verify regime testing works

### Phase 7: Migration & Cleanup (Week 4)
- [ ] **Don't convert old strategies** (per review recommendation)
- [ ] Implement `LegacyStrategyAdapter` for backward compatibility
- [ ] Let new template system evolve from scratch
- [ ] Allow both systems to compete in same portfolio
- [ ] Update strategy persistence (`StrategyRecord`) for new schema
- [ ] Update analysis tools
- [ ] Documentation updates

### Phase 8: Validation (Week 4-5)
- [ ] Run parallel evolution: string-based vs template-based
- [ ] Compare convergence speed
- [ ] Compare strategy quality (Sharpe, robustness)
- [ ] Compare LLM token usage (should be lower)
- [ ] Compare backtest throughput (strategies/hour)
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

### ~~4. Should We Allow Short Strategies?~~ ✅ RESOLVED

**Decision:** YES - Native short architecture built in from Day 1 (per review feedback).

- Composite signal is "directional intent" (-1 to +1)
- Separate thresholds: `entry_threshold_long`, `entry_threshold_short`
- `allow_long` / `allow_short` flags for control
- Default: `allow_long=True, allow_short=False` (long-only by default)
- No architectural changes needed to enable shorts later

### 4. Should Regime Switching Be Optional?

**Option A: Always regime-switched**
- Every strategy has two weight sets
- More parameters to evolve (2× weights)
- Better adaptability

**Option B: Optional regime switching**
- Add `use_regime_switching: bool` parameter
- If False, use only `weights_A`
- Simpler strategies possible

**Current Recommendation:** Always regime-switched. The complexity cost is low (2× weight parameters), and the performance gain is high. If we find strategies converge to identical weights_A and weights_B, that's fine - it effectively becomes a static strategy.

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
| 12/15/2025 09:35 AM PST | Incorporated review feedback: vectorization, regime-switched weights, native short architecture | Claude |
| 12/15/2025 10:03 AM PST | Completed Phase 1-4: Schema, validation, discretization, vectorized gene pool, base template, CryptoStrategyTemplate. 99 tests passing. | Claude |
| 12/15/2025 10:07 AM PST | Completed Phase 5: Parameter mutation module with LLM prompts, mutate_parameters(), crossover_parameters(), random fallbacks, and initial population generation. 123 tests passing. | Claude |
| 12/15/2025 05:03 PM PST | Completed Phase 6: TemplateBacktester with vectorized signal pre-computation, bidirectional trading (long AND short), ATR-based stops, and legacy evaluator adapter. 139 tests passing. | Claude |

---

## Review Feedback Integration Summary

The following changes were made based on the [peer review](2025-12-15-review-parameter-architecture.md):

### 1. Vectorization (CRITICAL)
- All signal calculations now return `pd.Series` instead of `float`
- `generate_signals()` returns full DataFrame for entire candle history
- Composite calculation uses vectorized numpy/pandas operations
- Backtester will pre-compute all signals in one pass

### 2. Regime-Switched Weights
- Added `WeightVector` dataclass for signal weights
- Added `weights_A` (ranging regime) and `weights_B` (trending regime)
- Added regime selector: `regime_indicator`, `regime_period`, `regime_threshold`
- Weights automatically switch based on ADX/ATR/BB-width

### 3. Native Short Architecture
- Composite signal now represents "directional intent" (-1 to +1)
- Added bidirectional thresholds: `entry_threshold_long/short`, `exit_threshold_long/short`
- Added direction control: `allow_long`, `allow_short` flags
- Default: long-only (backward compatible)

### 4. Migration Strategy
- Per review: "Don't convert, compete"
- Keep legacy string-based system running
- Let new template system evolve from scratch
- Both compete in same portfolio; winner emerges naturally

---

**Next Step:** Review this plan and decide on remaining Open Questions before implementation.

**Estimated Implementation Time:** 4-5 weeks for full migration (functional prototype in Week 2-3)
