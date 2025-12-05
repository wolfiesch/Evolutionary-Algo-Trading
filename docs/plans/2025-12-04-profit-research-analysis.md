# ProFiT Research Paper Analysis & Applicability to Oil-Stonks

**Created:** 2025-12-04
**Status:** Research & Assessment
**Author:** Wolfgang Schoenberger + Claude
**Related:** [Oil-Stonks Design Document](./2025-12-04-oil-stonks-design.md)

---

## 1. Executive Summary

This document analyzes the ProFiT (Program Search for Financial Trading) research paper and evaluates its applicability to the Oil-Stonks E&P ranking system. ProFiT uses LLM-driven evolutionary search to automatically discover and optimize trading strategies.

**Key Findings:**
- ✅ ProFiT's methods are **highly applicable** to Oil-Stonks technical analysis components
- ✅ Can be implemented on MacBook with standard Python tools + LLM API
- ⚠️ Paper published ~2 days ago (2025-12-02) - no open source code yet
- ⚠️ Best suited for **technical strategy optimization**, not fundamental factor discovery
- 💡 Recommended approach: Build simplified ProFiT-inspired system for technical scoring

---

## 2. ProFiT Paper Overview

### 2.1 Research Details

| Attribute | Details |
|-----------|---------|
| **Title** | ProFiT: Program Search for Financial Trading |
| **Publication** | ResearchGate (preprint) |
| **Date** | ~December 2-3, 2025 |
| **Lead Author** | Matthew Siper |
| **Contributors** | Julian Togelius, Ahmed Khalifa, and others |
| **Paper URL** | [ResearchGate Link](https://www.researchgate.net/publication/398248186_ProFiT_Program_Search_for_Financial_Trading) |

### 2.2 Core Methodology

**What is ProFiT?**
- LLM-driven evolutionary search system for trading strategy discovery
- Uses genetic programming where trading algorithms (Python code) evolve over time
- Integrates code mutation, self-analysis, and walk-forward validation in closed loop

**How It Works:**
```
1. Start with seed strategy (e.g., Bollinger Bands mean reversion)
   ↓
2. LLM proposes code mutations/improvements
   ↓
3. Backtest each variant on historical data
   ↓
4. Select best performers (fitness evaluation)
   ↓
5. Feed winners back to LLM for further evolution
   ↓
6. Repeat for N generations
```

**Technical Approach:**
- Search space: Trading algorithms encoded as syntax trees (Python code)
- Mutation engine: Large Language Model (GPT-4 or similar)
- Fitness function: Sharpe ratio, returns, drawdown
- Validation: Walk-forward testing (train on past, test on future)
- Data: 1-hour timeframe, January 2008 - October 2025

### 2.3 Performance Results

| Metric | Result | Comparison |
|--------|--------|------------|
| **Sharpe Ratio Improvement** | +0.57 ± 0.04 | vs. baseline strategies |
| **Annualized Return Increase** | +63% to +90% | Best strategies (williams_r_strategy) |
| **Beat Buy-and-Hold** | 77% of cases | Across all strategy-asset pairs |
| **Beat Random** | 100% of cases | - |
| **Improve Seed Strategy** | 94% of runs | Starting strategies got better |

**Strategy Types Tested:**
- ✅ Trend-following (e.g., CCI strategy)
- ✅ Mean-reverting (e.g., Bollinger Bands)
- ✅ Momentum (e.g., Williams %R)
- ✅ Multi-indicator combinations

### 2.4 Key Strengths

1. **Automatic Discovery:** No manual strategy design required
2. **Adaptation:** Strategies evolve as market conditions change
3. **Walk-Forward Validation:** Built-in protection against overfitting
4. **Interpretable:** Output is readable Python code (not black-box)
5. **Generalizes:** Works across trending and mean-reverting regimes

### 2.5 Limitations & Considerations

1. **No Open Source Code:** Implementation must be built from scratch
2. **LLM API Costs:** ~$0.01-0.10 per strategy evaluation (adds up over 100s of generations)
3. **Computational Time:** Evolution takes hours to days depending on generations
4. **Technical Focus:** Works best for technical indicators, not fundamental analysis
5. **Data Requirements:** Needs clean, high-quality historical data
6. **Recent Publication:** Limited peer review or independent validation yet

---

## 3. Applicability to Oil-Stonks System

### 3.1 Where ProFiT Fits

**HIGHLY APPLICABLE:**

| Oil-Stonks Component | ProFiT Use Case | Value Proposition |
|---------------------|-----------------|-------------------|
| **Technical Score (40%)** | Evolve optimal indicator combinations | Discover better trend/momentum/volume scoring |
| **Weighting Optimization** | Find optimal fundamental/technical split | Adapt 60/40 split based on market regime |
| **Entry/Exit Timing** | Optimize rebalancing frequency | Weekly vs. daily vs. adaptive |
| **Risk Controls** | Discover optimal stop-loss levels | Evolve -15% stop to dynamic threshold |

**NOT APPLICABLE:**

| Oil-Stonks Component | Why ProFiT Doesn't Help | Reason |
|---------------------|------------------------|--------|
| **Fundamental Factors** | FCF yield, debt, breakeven, hedging | These are domain-specific, require expert knowledge |
| **Stock Selection** | Which 10-15 stocks to include | Requires fundamental research, not technical patterns |
| **Data Sourcing** | API selection, data quality | Infrastructure problem, not optimization target |

### 3.2 Integration Strategy

**Recommended Approach: Hybrid System**

```
Oil-Stonks System (Current)
├── Fundamental Score (60%) ───────────→ Manual/Expert-Driven (keep as-is)
│   ├── FCF Yield
│   ├── Debt/EBITDA
│   ├── Breakeven Oil Price
│   └── Hedging Quality
│
└── Technical Score (40%) ─────────────→ ProFiT-Enhanced (optimize)
    ├── Trend (40%) ──────────────────→ Evolve: Which SMAs? What slopes?
    ├── Momentum (35%) ────────────────→ Evolve: RSI thresholds, MACD params
    └── Volume (25%) ──────────────────→ Evolve: OBV vs. other volume indicators
```

**Key Insight:** Use ProFiT to optimize the technical scoring system while keeping fundamental analysis human-curated.

### 3.3 Specific Use Cases

#### Use Case 1: Optimize Technical Indicator Weights
**Current:** Trend (40%), Momentum (35%), Volume (25%)
**ProFiT Approach:** Evolve weight combinations, test all permutations
**Expected Benefit:** Find optimal weights for E&P sector specifically

#### Use Case 2: Discover New Technical Patterns
**Current:** Standard indicators (RSI, MACD, SMA)
**ProFiT Approach:** Let LLM discover novel combinations or custom indicators
**Expected Benefit:** Sector-specific technical signals (E&P stocks behave differently than tech)

#### Use Case 3: Adaptive Regime Switching
**Current:** Static 60/40 fundamental/technical split
**ProFiT Approach:** Evolve rules for when to weight technical more (volatile markets) vs. fundamental (stable)
**Expected Benefit:** Dynamic adaptation to oil price volatility regimes

#### Use Case 4: Multi-Timeframe Optimization
**Current:** Daily data, weekly rebalancing
**ProFiT Approach:** Discover optimal lookback windows (7-day vs. 20-day vs. 50-day)
**Expected Benefit:** Better timing for sector-specific cyclicality

---

## 4. Implementation Feasibility Assessment

### 4.1 Can You Run This on Your MacBook?

**YES! Here's what you need:**

| Requirement | Solution | Cost | Difficulty |
|-------------|----------|------|-----------|
| **Python Environment** | Python 3.11+ (you already have) | Free | ✅ Easy |
| **LLM API Access** | OpenAI GPT-4 or Anthropic Claude | $20-100/mo | ✅ Easy |
| **Historical Market Data** | EODHD API (you already have) | $20/mo | ✅ Easy |
| **Backtesting Framework** | Backtrader or VectorBT | Free | ⭐ Medium |
| **ProFiT Implementation** | Build from paper (no open source) | Time | ⭐⭐ Hard |

**Hardware Requirements:**
- ✅ MacBook M1/M2/M3 (plenty of power)
- ✅ 16GB RAM recommended (8GB minimum)
- ✅ 50GB disk space for historical data
- ✅ Internet connection for LLM API calls

**No GPU required** (LLM runs on API, backtesting is CPU-bound)

### 4.2 Estimated Development Effort

**Full ProFiT Clone (from paper):**
- **Time:** 40-80 hours
- **Difficulty:** Hard (requires understanding evolutionary algorithms, LLM prompting, backtesting)

**Simplified ProFiT (Oil-Stonks specific):**
- **Time:** 15-30 hours
- **Difficulty:** Medium (focus on technical score optimization only)

**Phased Approach (Recommended):**

| Phase | Description | Hours | Skills Required |
|-------|-------------|-------|----------------|
| **Phase 0** | Paper reading & understanding | 4-6 | Research, critical thinking |
| **Phase 1** | Simple LLM-based strategy generator | 8-12 | Python, LLM APIs, prompting |
| **Phase 2** | Backtesting integration | 8-12 | Backtrader/VectorBT, pandas |
| **Phase 3** | Evolutionary loop (selection, mutation) | 8-16 | Algorithms, optimization |
| **Phase 4** | Walk-forward validation | 4-8 | Statistics, time series |
| **Phase 5** | Integration with Oil-Stonks | 8-12 | System integration |
| **Total** | End-to-end implementation | **40-66 hours** | |

### 4.3 Dependencies & Tech Stack

```python
# Core Dependencies
- python >= 3.11
- pandas >= 2.0
- numpy >= 1.24
- openai >= 1.0 (or anthropic >= 0.7)  # LLM API
- backtrader >= 1.9 (or vectorbt >= 0.25)  # Backtesting
- yfinance >= 0.2 (or eodhd-apis)  # Data fetching
- scikit-learn >= 1.3  # For walk-forward validation helpers
- matplotlib >= 3.7  # Visualization
- tqdm >= 4.65  # Progress bars

# Optional but Recommended
- jupyter >= 1.0  # Exploration
- pytest >= 7.4  # Testing
- black >= 23.0  # Code formatting
- pre-commit >= 3.3  # Git hooks
```

**External Services:**
- OpenAI API key (GPT-4) or Anthropic API key (Claude Opus/Sonnet)
- EODHD API key (you already have)

### 4.4 Barriers & Risks

| Barrier | Severity | Mitigation |
|---------|----------|------------|
| **No open source code** | High | Implement simplified version, skip advanced features |
| **LLM API costs** | Medium | Start with small tests (10-20 generations), monitor spending |
| **Complex evolutionary logic** | Medium | Use simple genetic algorithm (crossover + mutation) first |
| **Overfitting risk** | High | Mandatory walk-forward validation, out-of-sample testing |
| **Long execution time** | Medium | Run overnight, use parallel backtesting where possible |
| **Integration complexity** | Low | ProFiT outputs standalone strategies, easy to plug in |

---

## 5. Proposed Architecture (Simplified ProFiT for Oil-Stonks)

### 5.1 System Design

```
┌─────────────────────────────────────────────────────────────┐
│                    Oil-Stonks ProFiT Module                  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  1. Seed Strategy Library                                    │
│     - Baseline technical scoring (current system)            │
│     - Standard indicators (RSI, MACD, SMA, etc.)             │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  2. LLM Strategy Generator                                   │
│     Input: Current strategy code + performance feedback      │
│     Output: Mutated strategy code (Python function)          │
│     Model: GPT-4 or Claude Opus                              │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  3. Backtesting Engine                                       │
│     Framework: Backtrader or VectorBT                        │
│     Data: EODHD historical prices (2020-2024)                │
│     Metrics: Sharpe ratio, returns, drawdown, win rate       │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  4. Fitness Evaluator                                        │
│     - Calculate performance metrics                          │
│     - Rank strategies (population of N variants)             │
│     - Select top K performers                                │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  5. Evolutionary Loop                                        │
│     - Keep top strategies (elitism)                          │
│     - Mutate via LLM (exploration)                           │
│     - Repeat for M generations                               │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  6. Walk-Forward Validation                                  │
│     - Train on 2020-2022 (in-sample)                         │
│     - Validate on 2023-2024 (out-of-sample)                  │
│     - Ensure no overfitting                                  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  7. Best Strategy → Oil-Stonks Integration                   │
│     - Export optimized technical scoring function            │
│     - Replace manual technical score calculation             │
│     - Keep fundamental score (60%) unchanged                 │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 Project Structure Addition

```
Oil-Stonks/
├── docs/
│   └── plans/
│       ├── 2025-12-04-oil-stonks-design.md       # Main design (existing)
│       └── 2025-12-04-profit-research-analysis.md # This document
├── src/
│   ├── profit/                                    # NEW: ProFiT module
│   │   ├── __init__.py
│   │   ├── strategy_generator.py                 # LLM-based code mutation
│   │   ├── backtester.py                         # Strategy evaluation
│   │   ├── evolution.py                          # Genetic algorithm loop
│   │   ├── fitness.py                            # Performance metrics
│   │   └── validator.py                          # Walk-forward validation
│   ├── scoring/
│   │   ├── fundamental.py                        # (existing)
│   │   ├── technical.py                          # (existing - to be enhanced)
│   │   └── combined.py                           # (existing)
│   └── ...
├── notebooks/
│   └── profit_experiments.ipynb                  # NEW: ProFiT testing
└── ...
```

### 5.3 Key Components

#### Component 1: Strategy Generator (LLM Integration)

```python
# src/profit/strategy_generator.py

import openai  # or anthropic

class StrategyGenerator:
    """Generate trading strategy code mutations via LLM."""

    def __init__(self, model="gpt-4"):
        self.model = model
        self.client = openai.OpenAI()

    def mutate_strategy(self, current_code: str, performance_feedback: str) -> str:
        """
        Given current strategy code and performance, generate improved version.

        Args:
            current_code: Python function defining technical score calculation
            performance_feedback: "Sharpe: 0.8, Win rate: 52%, Max DD: -25%"

        Returns:
            Mutated strategy code (Python function as string)
        """
        prompt = f"""
        You are a quantitative trading expert specializing in technical analysis.

        Current strategy code:
        ```python
        {current_code}
        ```

        Performance on backtests:
        {performance_feedback}

        Task: Propose ONE mutation to improve this strategy. Options:
        1. Adjust indicator parameters (e.g., RSI period 14 → 10)
        2. Add new technical indicator
        3. Change weight allocation
        4. Modify entry/exit logic

        Output ONLY valid Python code (same function signature).
        Focus on strategies that work for Oil & Gas E&P stocks.
        """

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.8  # Higher temp for exploration
        )

        return response.choices[0].message.content
```

#### Component 2: Backtester (Fitness Evaluation)

```python
# src/profit/backtester.py

import backtrader as bt
import pandas as pd

class StrategyBacktester:
    """Evaluate trading strategy via backtesting."""

    def __init__(self, data: pd.DataFrame):
        self.data = data

    def evaluate(self, strategy_code: str) -> dict:
        """
        Backtest strategy and return performance metrics.

        Args:
            strategy_code: Python function defining strategy

        Returns:
            {
                'sharpe_ratio': 1.2,
                'total_return': 0.45,
                'max_drawdown': -0.22,
                'win_rate': 0.58
            }
        """
        # 1. Parse and compile strategy code
        # 2. Run backtrader with historical data
        # 3. Calculate metrics
        # 4. Return performance dict
        pass
```

#### Component 3: Evolution Loop

```python
# src/profit/evolution.py

from typing import List

class EvolutionaryOptimizer:
    """Manage evolutionary search across strategy population."""

    def __init__(
        self,
        seed_strategies: List[str],
        population_size: int = 20,
        generations: int = 50,
        elite_size: int = 5
    ):
        self.population = seed_strategies
        self.pop_size = population_size
        self.generations = generations
        self.elite_size = elite_size

    def evolve(self) -> str:
        """
        Run evolutionary loop and return best strategy.

        Returns:
            Best strategy code (Python function)
        """
        for gen in range(self.generations):
            # 1. Evaluate all strategies (backtest)
            # 2. Rank by fitness (Sharpe ratio)
            # 3. Select top K elites
            # 4. Mutate via LLM to fill population
            # 5. Repeat
            pass

        return self.best_strategy
```

---

## 6. Proof of Concept Plan

### 6.1 Minimal Viable ProFiT (MVP)

**Goal:** Demonstrate ProFiT concepts in < 2 days of work

**Scope:**
1. Generate 5 strategy variants via LLM (manual)
2. Backtest each on 1 stock (EOG) over 2023
3. Select best performer
4. Compare to baseline (current technical score)

**Success Criteria:**
- ✅ LLM successfully generates valid Python code
- ✅ Backtesting runs without errors
- ✅ At least 1 variant beats baseline

**Timeline:**
- **Hour 1-2:** Set up LLM API, write prompt templates
- **Hour 3-5:** Implement basic backtester wrapper
- **Hour 6-8:** Generate 5 variants, run backtests
- **Hour 9-10:** Analyze results, document findings

### 6.2 Proof of Concept Deliverables

1. **Notebook:** `notebooks/profit_poc.ipynb`
   - LLM prompt engineering
   - Strategy generation examples
   - Backtest results comparison

2. **Results Summary:** `docs/profit_poc_results.md`
   - Performance table (5 variants vs. baseline)
   - Key insights
   - Go/no-go recommendation

3. **Code:** `src/profit/` (minimal)
   - `strategy_generator.py` (50 lines)
   - `backtester.py` (100 lines)

### 6.3 Decision Gate

**After POC, evaluate:**

| Question | Go Threshold | No-Go Signal |
|----------|-------------|--------------|
| Did LLM generate valid code? | > 80% success rate | < 50% success rate |
| Did any variant beat baseline? | Yes (by any margin) | No |
| Was it faster than manual? | < 2 hours for 5 variants | > 4 hours |
| Are results reproducible? | Yes (same seed → same code) | No |

**If GO:** Proceed to Phase 1 (full implementation)
**If NO-GO:** Stick with manual technical scoring, revisit later

---

## 7. Cost-Benefit Analysis

### 7.1 Costs

| Cost Type | Estimate | Notes |
|-----------|----------|-------|
| **Development Time** | 40-66 hours | See §4.2 |
| **LLM API Costs** | $50-200 | POC: $10, Full: $50-200 (depends on generations) |
| **Opportunity Cost** | Medium | Time not spent on other Oil-Stonks features |
| **Risk of Overfitting** | High | Requires discipline in validation |

**Total Estimated Cost:** 40-66 hours + $50-200 = **~$2,000-3,300 equivalent** (at $50/hour)

### 7.2 Benefits

| Benefit | Value | Confidence |
|---------|-------|------------|
| **Improved Sharpe Ratio** | +0.3 to +0.6 | Medium (based on paper) |
| **Better Risk-Adjusted Returns** | +5-10% annually | Medium |
| **Reduced Manual Tuning** | Save 2-4 hours/month | High |
| **Adaptive to Regime Changes** | Strategies auto-update | High |
| **Learning Experience** | Valuable for future projects | High |

**Estimated Annual Value:** $5,000-10,000 (assuming $100k portfolio, 5-10% alpha)

### 7.3 ROI Calculation

**Conservative Scenario:**
- Implementation cost: 50 hours × $50/hour = $2,500
- Annual benefit: $5,000 (5% alpha on $100k)
- ROI: 100% in Year 1, 200%+ over 2 years

**Optimistic Scenario:**
- Implementation cost: $2,500
- Annual benefit: $10,000 (10% alpha on $100k)
- ROI: 300% in Year 1, 700%+ over 2 years

**Break-Even:** ~6 months (if delivers 5%+ alpha)

---

## 8. Recommendations

### 8.1 Short-Term (Next 2 Weeks)

**✅ RECOMMEND: Run Proof of Concept**

1. **Read ProFiT paper in detail** (4-6 hours)
   - Focus on methodology section
   - Understand walk-forward validation approach
   - Note fitness function design

2. **Build minimal LLM strategy generator** (8-12 hours)
   - Use GPT-4 or Claude Opus
   - Generate 5-10 technical score variants
   - Manual evaluation (no evolution loop yet)

3. **Simple backtest comparison** (4-6 hours)
   - Test on EOG, DVN, FANG (3 stocks)
   - 2023 data only (1 year)
   - Compare to baseline technical score

4. **Decision gate** (2 hours)
   - Analyze results
   - Go/no-go for full implementation

**Total Time:** 18-26 hours (2-3 days of focused work)

### 8.2 Medium-Term (1-2 Months)

**If POC succeeds:**

1. **Phase 1: Full ProFiT Implementation** (40-66 hours)
   - Evolutionary loop (selection, mutation, crossover)
   - Proper backtesting framework (Backtrader or VectorBT)
   - Walk-forward validation (2020-2022 train, 2023-2024 test)

2. **Phase 2: Integration with Oil-Stonks** (8-12 hours)
   - Replace manual technical scoring with evolved strategies
   - A/B test: manual vs. ProFiT-optimized
   - Production readiness (error handling, logging)

3. **Phase 3: Monitoring & Iteration** (ongoing)
   - Run evolution quarterly (adapt to market changes)
   - Track live performance vs. backtest
   - Refine based on real-world results

### 8.3 Long-Term (6-12 Months)

**Advanced applications:**

1. **Multi-Objective Optimization**
   - Optimize for Sharpe ratio AND max drawdown simultaneously
   - Pareto frontier exploration

2. **Regime Detection**
   - Evolve separate strategies for bull/bear/sideways markets
   - Automatic regime switching

3. **Fundamental-Technical Co-Evolution**
   - Use ProFiT to optimize fundamental factor weights too
   - Discover interaction effects (e.g., low debt + high momentum)

4. **Ensemble Strategies**
   - Combine multiple evolved strategies (voting or averaging)
   - Reduce single-strategy risk

---

## 9. Risks & Mitigations

### 9.1 Implementation Risks

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| **LLM generates invalid code** | Medium | High | Validate syntax before backtest, retry on failure |
| **Overfitting to historical data** | High | Critical | Mandatory walk-forward validation, out-of-sample testing |
| **Computational cost too high** | Low | Medium | Use vectorized backtesting (VectorBT), parallel execution |
| **LLM API costs exceed budget** | Medium | Low | Set spending caps, use cheaper models (GPT-3.5) for early gens |
| **Strategies fail in live trading** | Medium | High | Paper trading first, gradual rollout |

### 9.2 Strategic Risks

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| **Time better spent elsewhere** | Low | Medium | POC decides quickly (2-3 days) |
| **ProFiT doesn't fit Oil-Stonks** | Low | Medium | Focus on technical score only (safe sandbox) |
| **Open source version released** | Low | Low | Use it! Saves time, validates approach |
| **Market regime change** | Medium | High | Re-run evolution quarterly, stay adaptive |

---

## 10. Open Questions

### 10.1 Technical Questions

1. **LLM Model Selection:** GPT-4 (expensive, smart) vs. GPT-3.5 (cheap, less capable)?
2. **Fitness Function:** Sharpe ratio only, or multi-objective (return + drawdown + win rate)?
3. **Mutation Strategy:** Pure LLM-driven, or hybrid (LLM + rule-based)?
4. **Population Size:** 10 strategies (fast) vs. 50 strategies (better exploration)?
5. **Generations:** 20 (quick test) vs. 100 (thorough search)?

### 10.2 Strategic Questions

1. **Scope:** Optimize technical score only, or also fundamental weights?
2. **Integration:** Replace current system, or run in parallel (A/B test)?
3. **Frequency:** One-time optimization, or continuous evolution?
4. **Data:** Use same 2020-2024 period as main backtest, or extend further back?

### 10.3 Research Questions for Later

1. Can ProFiT discover sector-specific patterns (E&P vs. tech)?
2. Does LLM-based evolution outperform traditional genetic programming?
3. How sensitive is performance to LLM temperature parameter?
4. Can strategies evolved on individual stocks generalize to sector ETFs?

---

## 11. Resources & References

### 11.1 ProFiT Research

- **Paper:** [ProFiT: Program Search for Financial Trading](https://www.researchgate.net/publication/398248186_ProFiT_Program_Search_for_Financial_Trading)
- **Author Twitter:** [Julian Togelius announcement](https://x.com/togelius/status/1995942729558491591)
- **LinkedIn Post:** [Matthew Siper (lead author)](https://www.linkedin.com/posts/matthewsiper_pdf-profit-program-search-for-financial-activity-7401731565967396864-8Sec)

### 11.2 Related Research

- **Genetic Algorithms in Trading:**
  - [Evolving Financial Trading Strategies with Vectorial GP (arXiv)](https://arxiv.org/html/2504.05418v1)
  - [Designing Safe, Profitable Automated Trading Agents (ResearchGate)](https://www.researchgate.net/publication/220740465_Designing_safe_profitable_automated_stock_trading_agents_using_evolutionary_algorithms)

### 11.3 Implementation Tools

- **Backtesting:**
  - [Backtrader Documentation](https://www.backtrader.com/docu/)
  - [VectorBT Documentation](https://vectorbt.dev/)

- **LLM APIs:**
  - [OpenAI API (GPT-4)](https://platform.openai.com/docs)
  - [Anthropic API (Claude)](https://docs.anthropic.com/)

- **Data:**
  - [EODHD API Docs](https://eodhistoricaldata.com/financial-apis/)
  - [yfinance (fallback)](https://pypi.org/project/yfinance/)

### 11.4 Existing Open Source Algo Trading

While ProFiT itself isn't open source, similar evolutionary/genetic approaches exist:

- [OpenAlgo](https://github.com/marketcalls/openalgo) - Open source algo trading platform
- [Best of Algorithmic Trading (curated list)](https://github.com/merovinh/best-of-algorithmic-trading)

---

## 12. Next Steps

### 12.1 Immediate Actions (This Week)

- [ ] **Review ProFiT paper in depth** (Wolfgang - 4-6 hours)
- [ ] **Set up OpenAI or Anthropic API key** (Wolfgang - 15 min)
- [ ] **Create POC notebook template** (Wolfgang - 1 hour)
- [ ] **Decide: POC now or wait?** (Wolfgang - 30 min)

### 12.2 POC Phase (If Approved)

- [ ] Implement basic LLM strategy generator
- [ ] Write backtesting harness (minimal)
- [ ] Generate 5-10 strategy variants
- [ ] Run backtests on 3 stocks (EOG, DVN, FANG)
- [ ] Compare to baseline technical score
- [ ] Document results in `docs/profit_poc_results.md`
- [ ] **Decision gate:** Go/no-go for full implementation

### 12.3 Future Phases (If POC Succeeds)

- [ ] Full evolutionary loop implementation
- [ ] Walk-forward validation framework
- [ ] Integration with main Oil-Stonks system
- [ ] A/B testing (manual vs. evolved strategies)
- [ ] Production deployment

---

## 13. Changelog

| Date | Change | Author |
|------|--------|--------|
| 2025-12-04 14:15 | Initial research analysis document created | Wolfgang + Claude |

---

## 14. Conclusion

**Bottom Line:**

1. **ProFiT is real and applicable** to Oil-Stonks (specifically technical scoring)
2. **You can absolutely run this on your MacBook** (no special hardware needed)
3. **No open source code yet** (must implement from paper)
4. **Best use case:** Optimize technical score (40% of system), keep fundamentals manual
5. **Recommended path:** 2-3 day POC → decision gate → full implementation if promising

**Key Insight:**
ProFiT's evolutionary approach is a perfect fit for discovering technical indicator combinations that work specifically for E&P stocks. The energy sector has unique characteristics (high correlation with oil prices, cyclical patterns, debt sensitivity) that generic technical analysis may miss. Letting an LLM evolve sector-specific strategies could provide meaningful alpha.

**Risk/Reward:**
Low risk (POC is only 2-3 days), high potential reward (5-10% alpha if successful). The learning experience alone is valuable for future quantitative projects.

**Recommendation:**
✅ **Proceed with POC** - the opportunity cost is low, and the potential upside is significant.

---

*Document ready for review and decision on POC approval.*

**Current Date/Time:** 12/04/2025 02:28 PM
