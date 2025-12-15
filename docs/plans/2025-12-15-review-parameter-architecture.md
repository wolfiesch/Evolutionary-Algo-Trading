# Review: Parameter Evolution Architecture

**Date:** 2025-12-15
**Reviewer:** Antigravity (Senior Engineer)
**Target:** [2025-12-15-parameter-evolution-architecture.md](2025-12-15-parameter-evolution-architecture.md)

## Executive Summary

The proposed shift from **Structure Evolution (Logic Strings)** to **Parameter Evolution (Fixed Template)** is the correct architectural decision. It addresses the core scalability issues of the current system:

1.  **Search Efficiency**: Reduces an infinite search space to a bounded, convex-like optimization surface.
2.  **Robustness**: Eliminates syntax errors and "nonsense" logic.
3.  **Transferability**: Parameters are easier to analyze and transfer between regimes than discrete logic trees.

However, the current proposal has three valid concerns that should be addressed before implementation to ensure it meets the "Hedge Fund Standard":

1.  **Performance (Vectorization)**: The proposed `calculate_composite_signal` loop is inefficient for backtesting.
2.  **Expressiveness (Linearity)**: A pure weighted average is too linear and loses the power of "conditional" logic (e.g., "Only look at Trend if Volatility is Low").
3.  **Asymmetry (Long-Only)**: The architecture implicitly bakes in "Long-Only" bias which limits alpha in crypto bear markets.

---

## Critical Feedback

### 1. Vectorization is Non-Negotiable

The plan implies calculating signals iteratively:

```python
# From plan:
for name, calc_func in signal_map.items():
    # ...
    signals.append(calc_func(candles)) # Implies single scalar return?
```

**Issue:** If `calc_func(candles)` returns a scalar for a single point, backtesting will be exceedingly slow (Python loop overhead).
**Fix:** The architecture **MUST** be vectorized from Day 1.

- `calculate_trend_signal(candles: pd.DataFrame)` should return a `pd.Series` (or numpy array) of the same length.
- `calculate_composite_signal` should perform vector algebra: `composite = w1*s1 + w2*s2 + ...`
- The backtester should compute the entire signal column in one pass, then apply vector logic for entry/exit simulation.

### 2. The "Linearity Trap" & Regime-Switched Weights

**Issue:** A simple weighted average `Composite = w_trend * Trend + w_mean_rev * MeanRev` fails to capture **conditional dependency**.
_Example:_ In a choppy market, you want `w_mean_rev = 1.0, w_trend = 0`. In a trending market, you want `w_trend = 1.0, w_mean_rev = 0`.
A single set of static weights will wash out, resulting in a mediocre "average" strategy that fails to excel in either.

**Proposal: Regime-Dependent DNA**
Instead of one set of weights, evolve **Two Sets** and a **Selector**:

```python
@dataclass
class StrategyParameters:
    # Selector
    regime_indicator: str = "adx" # or "atr", "volatility"
    regime_threshold: float = 25.0

    # Regime A (e.g., Low Vol / Range)
    weights_A: WeightVector  # High mean reversion, Low trend

    # Regime B (e.g., High Vol / Trend)
    weights_B: WeightVector  # High trend, Low mean reversion
```

_Complexity Cost:_ Low (2x parameters).
_Performance Gain:_ High (Non-linear adaptability).

### 3. Native "Short" Architecture

**Issue:** The plan defers Shorting to Phase X. In Crypto/Forex, shorting is 50% of the game. Baking "Long Only" assumptions into the `StrategyTemplate` now (e.g. `entry_threshold > 0`) will make adding shorts painful later.
**Fix:** Define the composite signal as **Directional Intent**.

- `+1.0` = Max Long Intent
- `-1.0` = Max Short Intent
- `entry_threshold_long`: e.g., +0.3
- `entry_threshold_short`: e.g., -0.3
- `weight_*` params can remain the same (negative weight = contrarian).

---

## Detailed Suggestions

### Implementation

- **JIT Compilation**: Consider using `numba` for the signal calculation loop strategies if vectorization isn't flexible enough (though pandas is usually fine).
- **Property-Based Testing**: Use `hypothesis` to generate random valid/invalid parameters to stress-test your `validate()` logic. It's much better than writing manual test cases for "trend_fast < trend_slow".

### Schema Extensions

- **Interaction Terms**: If you don't do "Regime-Dependent DNA", consider adding explicitly "Interaction Weights" (e.g., `weight_trend_vol_interaction`).
- **Timeframe Gene**: `min_bars_between_trades` behaves differently on 1m vs 1h candles. Add `candle_interval` (1m, 5m, 15m, 1h) to the DNA if the backtester supports multi-timeframe.

### Migration

- **Don't Convert, Compete**: Do not waste time writing a "String -> Param" converter. It will be lossy and frustrating.
  - Keep the _Legacy_ runner for existing winners.
  - Let the _New_ runner evolve from scratch.
  - If the new architecture is good, it will naturally beat the legacy strategies in the population pool (assuming you allow them to compete in the same portfolio).

---

## Verdict

**Status:** **APPROVED WITH MODIFICATIONS**

Proceed to **Phase 1 (Schema & Validation)**, but incorporate the **Vectorization** requirement immediately into the design. Consider the **Regime-Switched Weights** for Phase 3 (Asset Templates) if the baseline performance is "meh".
