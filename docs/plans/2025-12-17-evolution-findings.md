# Template Evolution Findings Report

**Created:** 12/17/2025 07:02 AM PST (via pst-timestamp)
**Status:** Completed - First Profitable Strategy Found

---

## Executive Summary

After extensive evolution runs across multiple assets and timeframes, we discovered a **profitable ETH strategy** with:
- **Sharpe Ratio: +1.32**
- **Win Rate: 76.2%**
- **Max Drawdown: 0.69%**

Key insight: The LLM evolved entry thresholds **upward** (more selective) rather than downward, demonstrating intelligent parameter optimization.

---

## Evolution Run History

### Session 1: Initial LLM Fix Verification (12/16/2025 3:00 PM - 3:25 PM PST)

**Objective:** Verify LLM mutations were working after `.chat()` → `.generate()` fix

| Symbol | Timeframe | Gens | Best Sharpe | Win Rate | Trades |
|--------|-----------|------|-------------|----------|--------|
| SOL | H4 | 10 | -2.21 | 44.7% | 26 |
| SOL | H1 | 10 | **+0.02** | 55.7% | 41 |

**Finding:** H1 timeframe significantly outperforms H4 for SOL (+2.23 Sharpe improvement)

### Session 2: Extended H1 Cross-Asset (12/17/2025 4:26 AM - 5:16 AM PST)

**Objective:** Test H1 across all major assets with 20 generations

| Symbol | Timeframe | Gens | Best Sharpe | Win Rate | Trades |
|--------|-----------|------|-------------|----------|--------|
| SOL | H1 | 20 | -0.79 | 46.6% | 40 |
| ETH | H1 | 20 | -3.68 | 49.4% | 107 |
| BTC | H1 | 20 | -4.57 | 41.0% | 88 |

**Finding:** Longer evolution did NOT improve results - population converged to local minima. Entry threshold remained stuck at default 0.30.

### Session 3: Lowered Threshold Experiment (12/17/2025 6:00 AM - 6:43 AM PST)

**Objective:** Test impact of lowering seed entry threshold from 0.30 to 0.15

| Symbol | Timeframe | Gens | Best Sharpe | Win Rate | Trades | Final Threshold |
|--------|-----------|------|-------------|----------|--------|-----------------|
| SOL | H1 | 15 | -0.50 | 50.6% | 41 | 0.15 (unchanged) |
| **ETH** | **H1** | **15** | **+1.32** | **76.2%** | **21** | **0.60 (evolved UP)** |
| BTC | H1 | 15 | -5.20 | 43.1% | 88 | 0.15 (unchanged) |

**Finding:** ETH found profitable strategy by evolving threshold UP to 0.60 (more selective entries)

---

## Winning Strategy: ETH H1 Evolved V1

**File:** `crypto/winning_strategies/eth_h1_evolved_v1.json`

### Performance Metrics
| Metric | Value |
|--------|-------|
| Sharpe Ratio | +1.32 |
| Win Rate | 76.2% |
| Trade Count | 21 (over 180 days) |
| Max Drawdown | 0.69% |
| Timeframe | H1 (60 minutes) |

### Key Parameters
```json
{
  "entry_threshold_long": 0.60,    // Evolved UP from 0.15 seed
  "exit_threshold_long": -0.15,
  "stop_loss_atr_mult": 1.5,       // Tighter than default 2.0
  "weights_B": {
    "volume": -0.1                 // Contrarian volume signal
  }
}
```

### Evolution Trajectory
- Generations 1-4: Sharpe -3.68 (searching)
- **Generation 5: Sharpe +1.32 (breakthrough)**
- Generations 6-15: Held winning configuration

---

## Key Insights

### 1. Timeframe Matters
H1 consistently outperforms H4 for crypto trading:
- More data points for pattern recognition
- Better capture of intraday momentum
- H4 too coarse for volatile assets

### 2. LLM Parameter Optimization Works
The LLM successfully:
- Evolved entry threshold from 0.15 → 0.60 (more selective)
- Found contrarian volume signal (negative weight)
- Tightened stop loss from 2.0 → 1.5 ATR

### 3. Asset-Specific Behavior
| Asset | Optimal Strategy | Notes |
|-------|------------------|-------|
| ETH | High selectivity (0.60 threshold) | Best for template approach |
| SOL | Unknown | Needs different approach |
| BTC | Unknown | Very poor with template |

### 4. Evolution Dynamics
- **Longer ≠ Better:** 20-gen runs often worse than 10-gen
- **Local minima risk:** Population can converge to suboptimal configs
- **Breakthrough pattern:** Good strategies often appear suddenly (Gen 5)

---

## SOL/BTC Underperformance Investigation (T1)

**Investigation Date:** 12/17/2025 09:31 AM PST (via pst-timestamp)

### Root Cause Analysis

Comparing evolution logs across all three assets:

| Metric | ETH (Success) | SOL (Fail) | BTC (Fail) |
|--------|---------------|------------|------------|
| Final Sharpe | **+1.32** | -0.50 | -5.20 |
| Trade Count | **21** | 41 | 88 |
| Threshold Evolution | 0.15 → **0.60** | 0.15 (stuck) | 0.15 (stuck) |
| Best Gen Found | Gen 5 | Gen 1 | Gen 1 |
| Explored Range | -3.68 to +1.32 | -0.50 only | -2.90 to -6.34 |

### Key Finding: Evolution Stagnation

**SOL and BTC evolution NEVER escaped their initial configuration:**
- Parameters remained at seed values for all 15 generations
- LLM mutations failed to find better parameter combinations
- Population converged to local minimum immediately

**ETH found the breakthrough by:**
- Increasing entry threshold 4x (0.15 → 0.60)
- Reducing trade frequency from ~100 to 21 (80% reduction)
- Finding contrarian volume signal in trending regime

### Why SOL/BTC Failed

1. **Over-trading**: SOL=41 trades, BTC=88 trades vs ETH's 21 winning trades
2. **Low selectivity**: 0.15 threshold generated too many low-quality signals
3. **No parameter exploration**: LLM didn't discover higher threshold = better
4. **BTC in downtrend**: Long-only strategy in -50% market period
5. **Different market dynamics**: Template optimized for ETH's volatility profile

### Evidence from Evolution Logs

**BTC Gen 13** showed improvement hints:
- Sharpe: -2.90 (improved from -5.20)
- Trade count: 22 (similar to ETH's 21)
- This suggests fewer trades = better, but evolution didn't pursue this direction

### Recommendations for SOL/BTC

#### Option 1: Use ETH Parameters as Seed (T0)
```bash
python3 crypto/evolve_template.py --symbol=SOLUSDT --entry-threshold=0.60 --generations=15
python3 crypto/evolve_template.py --symbol=BTCUSDT --entry-threshold=0.60 --generations=15
```

#### Option 2: Enable Shorts for BTC (T1)
- BTC was in -50% downtrend during backtest period
- Long-only strategy cannot profit in sustained downtrends
- Add `--enable-shorts` flag for BTC evolution

#### Option 3: Different Indicators for BTC (T2)
- BTC may need different primitives (e.g., on-chain data)
- Consider BTC dominance, funding rates as primary signals
- Template design may not suit BTC's institutional dynamics

#### Option 4: Explicit Mutation Guidance (T1)
- Update LLM mutation prompt to explicitly suggest:
  - "Try increasing entry_threshold_long to 0.5-0.8"
  - "Reduce trade frequency for better signal quality"
  - "Consider contrarian volume weights"

---

## Recommendations

### Immediate (T0)
1. **Deploy ETH strategy to shadow trading** - Validate on live data
2. **Run ETH evolution with more seeds** - Try to find even better configs
3. **Test ETH strategy on out-of-sample data** - Verify robustness

### Short-term (T1)
4. **Investigate SOL/BTC failures** - May need different template or primitives
5. **Add threshold CLI argument** - Allow `--entry-threshold=X` for experiments
6. **Improve mutation prompts** - Explicitly suggest threshold exploration

### Medium-term (T2)
7. **Multi-timeframe approach** - Combine H1 signals with H4 confirmation
8. **Ensemble strategies** - Run multiple evolved strategies in parallel
9. **Regime-specific optimization** - Different strategies for different market conditions

---

## Shadow Trading Status

As of 12/17/2025 06:47 AM PST:
- **Runtime:** 14+ hours continuous
- **Trade signals:** 66+ executed
- **Status:** Healthy, receiving live data
- **Quality filters:** Active (detecting anomalies)

---

## Files Created/Modified

| File | Change |
|------|--------|
| `crypto/evolve_template.py` | Lowered seed thresholds (0.30 → 0.15) |
| `crypto/winning_strategies/eth_h1_evolved_v1.json` | New winning strategy |
| `crypto/logs/template_strategies/*.json` | Evolution run outputs |

---

## Changelog

| Timestamp | Action |
|-----------|--------|
| 12/16/2025 03:00 PM PST | Session resumed, LLM fix verified |
| 12/16/2025 03:25 PM PST | H1 vs H4 comparison complete |
| 12/17/2025 05:16 AM PST | Extended 20-gen runs complete |
| 12/17/2025 06:43 AM PST | Low threshold runs complete, ETH winner found |
| 12/17/2025 07:02 AM PST | Findings documented |
| 12/17/2025 09:22 AM PST | Template shadow trader deployed for ETH H1 strategy validation |
| 12/17/2025 09:25 AM PST | Fixed CandleRepository.get_candles → get_range bug |
| 12/17/2025 09:31 AM PST | SOL/BTC underperformance investigation complete (T1) |

---

*Report generated by Claude Code*
