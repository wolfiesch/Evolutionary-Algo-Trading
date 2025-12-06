# Critical Review: ProFiT Research Analysis for Oil-Stonks

**Review Date:** 2025-12-04
**Reviewer:** Claude Code (Critical Analysis Mode)
**Document Reviewed:** `2025-12-04-profit-research-analysis.md`
**Status:** Critical Assessment Complete

---

## Executive Summary

**Overall Assessment:** ⚠️ **PROCEED WITH CAUTION - POC STRONGLY RECOMMENDED**

The plan is technically feasible and conceptually sound, but contains **several optimistic assumptions** that need validation before full commitment. The proposed approach of using ProFiT-inspired methods for technical indicator optimization is valid, but the cost estimates are **likely understated by 3-5x**, the alpha expectations lack empirical grounding, and critical implementation risks are underweighted.

**Biggest Concerns:**
1. 🔴 LLM API costs severely underestimated ($50-200 → likely $500-2000 for 50-100 generations)
2. 🔴 5-10% alpha assumption has no empirical basis for oil sector specifically
3. 🟡 Overfitting risk is acknowledged but mitigation strategy is insufficient
4. 🟡 POC timeline (2-3 days) is optimistic for a first implementation

**Key Recommendation:**
Run the POC, but extend it to **5-7 days** with **stricter success criteria**. Set LLM budget cap at $100 for POC. If POC beats baseline by <2%, abandon or significantly revise approach.

---

## 1. Technical Accuracy & Feasibility

### ✅ Strengths

1. **Architecture is sound**: The proposed simplified ProFiT system (LLM mutation → backtest → evolution) is technically valid
2. **Tool selection is appropriate**: Backtrader/VectorBT, pandas, OpenAI/Anthropic APIs are standard and well-supported
3. **MacBook feasibility confirmed**: No GPU needed, computational requirements are modest
4. **Separation of concerns**: Keeping fundamentals manual while evolving technical indicators is pragmatic

### 🔴 Critical Issues

**Issue 1: LLM Token Consumption Severely Underestimated**

The document estimates $50-200 for 50-100 generations. This is **unrealistic**.

**Reality check:**
- Each strategy evaluation requires sending:
  - Current code (~500-1000 tokens)
  - Performance feedback (~200-500 tokens)
  - Historical context (~300-500 tokens)
  - Instructions (~500 tokens)
  - **Total input: ~1,500-2,500 tokens per generation**
- LLM response (mutated code + reasoning): ~1,000-2,000 tokens
- **Per-generation cost (GPT-4)**: ~$0.03-0.10 input + $0.30-0.60 output = **$0.33-0.70 each**
- **50 generations**: $16.50-35 (best case)
- **100 generations with 20 strategies in population**: **$660-1,400**

**Fix:** Revise cost estimate to **$500-2,000** for full implementation. POC should budget **$50-100** (10-15 generations only).

---

**Issue 2: No Validation of LLM Code Generation Quality**

The document assumes LLMs will generate valid, non-hallucinated Python code. **This is not guaranteed.**

**Problems:**
- LLMs can generate syntactically valid but semantically broken code
- May hallucinate indicators that don't exist in `ta` or `pandas_ta` libraries
- Could introduce look-ahead bias unknowingly
- May create overly complex strategies that overfit by construction

**Fix:**
- Add **syntax validation** step before backtesting
- Implement **static analysis** to detect look-ahead bias (e.g., using future data)
- Use **code complexity metrics** (cyclomatic complexity) to penalize overfitting-prone strategies
- Consider limiting LLM to **parameter tuning** only (safer than full code generation)

---

**Issue 3: Backtesting Framework Integration Complexity Underestimated**

The document treats backtesting as plug-and-play. **It's not.**

**Challenges:**
- Dynamically compiling LLM-generated code is a security risk (use `ast` module carefully)
- Backtrader requires specific strategy class structure - LLM must follow exact format
- Transaction costs, slippage models, and execution delays need careful modeling
- Walk-forward validation requires sophisticated data splitting (not trivial)

**Fix:**
- Budget **16-24 hours** just for backtesting harness (not 8-12)
- Use **sandboxed execution** (RestrictedPython or similar) for LLM code
- Create **strategy template** with fixed structure, allow LLM to modify only indicator logic

---

### 🟡 Important Warnings

**Warning 1: Oil Sector Characteristics Not Addressed**

E&P stocks have unique behaviors:
- High correlation with WTI crude prices (~0.7-0.9)
- Extreme volatility during oil price shocks
- Sector-wide drawdowns of 50-70% are common
- Technical indicators tuned on SPY/tech may fail completely

**Recommendation:** Include **oil price (WTI) as exogenous variable** in strategy evolution. Strategies that ignore oil are doomed.

---

**Warning 2: Sample Size Issues Not Mentioned**

- Testing on 10-15 stocks with 5 years of data = **~250 trading weeks × 12 stocks = 3,000 data points**
- Evolving strategies with 10-20 parameters on 3,000 points → **high overfitting risk**
- Walk-forward validation helps, but doesn't eliminate the problem

**Recommendation:** Use **cross-validation across stocks** (train on 8 stocks, validate on 4), not just time-based walk-forward.

---

## 2. Gaps & Missing Considerations

### 🔴 Critical Gaps

**Gap 1: No Discussion of Regime Detection**

Oil markets have distinct regimes:
- **Supply shock** (e.g., 2020 COVID crash): -60% in 2 months
- **Bull market** (e.g., 2021-2022): +100%+ gains
- **Contango/backwardation** effects on E&P stocks

**Impact:** A strategy optimized on 2020-2024 may include 2020 crash (extreme outlier). Results will be distorted.

**Fix:** Either:
1. Exclude extreme outliers (2020 Q2) from training
2. Or explicitly model regime-specific strategies

---

**Gap 2: Data Quality and Survivorship Bias**

- Are you using all E&P stocks from 2020, or only survivors to 2024?
- If only survivors → **survivorship bias** (you're ignoring bankruptcies like Chesapeake Energy)
- EODHD may have data gaps for delisted stocks

**Fix:** Verify data includes **delisted stocks**. If not, acknowledge this as a limitation (biases results upward).

---

**Gap 3: No Mention of Execution Slippage**

The document mentions "0.05% slippage" in backtest plan, but evolutionary search doesn't account for:
- **Market impact**: Rebalancing 5-7 positions weekly on mid/small caps
- **Bid-ask spread**: Small caps like MGY, CPE have wider spreads
- **Liquidity constraints**: Some E&P stocks trade <1M shares/day

**Fix:** Model slippage as **function of position size and daily volume**. Don't use fixed 0.05%.

---

**Gap 4: Model Interpretability and Explainability**

Evolved strategies are Python code, but:
- Will users understand *why* a strategy works?
- Can you explain to a regulator or investor what the strategy does?
- LLM-generated code may be convoluted

**Fix:** Add **interpretability requirement** to fitness function. Penalize strategies with >100 lines of code or >5 indicators.

---

**Gap 5: Integration with Existing System Not Detailed**

- How exactly will evolved technical score integrate with fundamental score (60/40 split)?
- What if evolved strategy recommends opposite of fundamentals?
- Who has final say - the algorithm or human judgment?

**Fix:** Define **conflict resolution protocol**. Example: If fundamental = Strong Buy but technical = Sell, output = Hold (neutral).

---

### 🟡 Important Gaps

**Gap 6: No Discussion of Computational Time**

- Backtesting 20 strategies on 12 stocks over 5 years = **~240 backtests per generation**
- Assuming 5 seconds per backtest = **20 minutes per generation**
- 50 generations = **16-17 hours of compute**

**Fix:** Note this in timeline. Suggest running overnight or using parallel backtesting (Dask, Ray).

---

**Gap 7: Regulatory and Compliance Considerations Missing**

Are you managing money for others? If yes:
- SEC requires disclosing use of algorithmic strategies
- FINRA has rules on algo trading (even for retail)
- Tax implications of weekly rebalancing

**Fix:** Add disclaimer: "Assumes trading personal capital only. Consult advisor if managing others' money."

---

## 3. Cost-Benefit Analysis Realism

### 🔴 Critical Problems

**Problem 1: Alpha Assumption Has No Basis**

Document claims: "5-10% alpha on $100k portfolio = $5,000-10,000/year benefit"

**Questions:**
- Where does 5-10% come from? ProFiT paper shows Sharpe improvement, not absolute alpha.
- What if evolved strategy has Sharpe 1.2 but returns -5% in 2024 oil downturn?
- What's the probability you actually achieve 5-10%?

**Revised estimate:**
- **Conservative**: 0-3% alpha (might just match sector ETF XOP)
- **Realistic**: 3-5% alpha if POC is successful
- **Optimistic**: 5-10% alpha (requires everything going right)

**Impact on ROI:**
- Conservative: $0-3,000/year benefit → **Break-even: 10-12 months**
- Realistic: $3,000-5,000/year → **Break-even: 6-8 months**
- Optimistic: $5,000-10,000/year → **Break-even: 3-5 months**

---

**Problem 2: Ongoing Maintenance Costs Ignored**

The document treats this as a one-time build. **It's not.**

**Ongoing costs:**
- Re-running evolution quarterly: 10-15 hours/quarter
- Monitoring strategy performance: 2-4 hours/week
- Debugging failed strategies: 5-10 hours/quarter
- Data pipeline maintenance: 2-4 hours/month

**Annual maintenance:** ~100-150 hours = **$5,000-7,500** (at $50/hour)

**Revised ROI:**
- **Year 1**: -$2,500 (build) + $3,000-5,000 (benefit) = **$500-2,500 profit**
- **Year 2**: -$5,000 (maintenance) + $3,000-5,000 (benefit) = **-$2,000 to break-even**

**Conclusion:** ROI is **break-even in Year 1-2**, positive only if alpha ≥5% or portfolio >$200k.

---

**Problem 3: Opportunity Cost Not Quantified**

40-66 hours to build = **~1 week of focused work**. What else could you build?

**Alternatives with similar time investment:**
1. **Simple factor model** (20 hours): Just optimize fundamental factor weights via grid search
2. **Momentum + mean reversion overlay** (30 hours): Manually code 2-3 proven strategies
3. **Buy XOP and forget** (0 hours): Sector ETF with no effort

**Question:** Is ProFiT's complexity justified vs. simpler alternatives?

**Fix:** Add **POC decision criterion**: "If POC doesn't beat simple 50/200 SMA crossover by 3%+, abandon."

---

### 🟡 Important Considerations

**Hidden Cost: LLM API Rate Limits**

- OpenAI GPT-4: 10,000 tokens/min limit (Tier 1)
- 50 generations at 3,500 tokens each = **175,000 tokens total**
- At 10k/min limit = **17.5 minutes minimum** (if rate-limited)
- Tier 2+ required for faster iteration ($50/month minimum spend)

**Fix:** Note that POC may require upgrading OpenAI tier ($50 upfront cost).

---

## 4. Risks Not Covered

### 🔴 Critical Risks

**Risk 1: Look-Ahead Bias in LLM-Generated Code**

**Probability:** Medium | **Impact:** Critical

LLMs may unknowingly generate code that uses future information:
```python
# WRONG: Uses tomorrow's close to predict today
signal = df['close'].shift(-1) > df['close']  # Look-ahead!
```

**Why it's insidious:** Code looks syntactically valid, backtest shows amazing results, but fails immediately in live trading.

**Mitigation (MUST IMPLEMENT):**
- Static analysis to detect `.shift(-N)` where N < 0
- Require all indicators use only `.shift(N)` where N ≥ 0
- Manual code review before deploying any evolved strategy

---

**Risk 2: LLM Hallucination of Non-Existent Functions**

**Probability:** High (30-40% of generated code) | **Impact:** High

LLMs frequently hallucinate indicator functions that don't exist:
```python
# WRONG: No such function in ta-lib or pandas_ta
indicator = ta.advanced_momentum_oscillator(df, period=14)  # FAKE!
```

**Mitigation:**
- Whitelist allowed functions (only `ta.RSI`, `ta.MACD`, etc.)
- Syntax validation catches most (but not all) hallucinations
- Penalty: Failed code generation = wasted LLM API call ($0.50+)

---

**Risk 3: Strategy Degradation Over Time (Model Drift)**

**Probability:** Very High (80%+) | **Impact:** High

**Why it happens:**
- Markets change (2020 != 2024)
- Strategies optimized on past may fail on future
- Oil sector particularly prone to regime shifts

**Evidence from academic literature:**
- Typical quantitative strategy half-life: 2-4 years
- Momentum strategies degrade fastest in mean-reverting markets

**Mitigation:**
- Re-run evolution **quarterly** (not annually)
- Monitor Sharpe ratio monthly - if drops below 0.5, pause strategy
- Set **"strategy expiration"** - force re-evolution after 6 months

---

**Risk 4: Catastrophic Failure During Oil Price Shock**

**Probability:** Low (10-20% in any given year) | **Impact:** Catastrophic (-50% drawdown)

**Scenario:**
- Oil drops 40% in 6 weeks (like March 2020)
- All E&P stocks correlate to 1.0
- Technical indicators give conflicting signals
- Evolved strategy flails, maximum drawdown hits 50-60%

**Mitigation:**
- **Hard drawdown limit**: If portfolio drops 25%, force to 100% cash
- Include oil price as **circuit breaker**: If WTI drops >15% in 2 weeks, pause algo
- Keep 20% cash buffer minimum (not just 10%)

---

### 🟡 Important Risks

**Risk 5: Overfitting to Oil Bull Market (2020-2024)**

**Context:** 2020-2024 includes massive oil rebound (2020 lows → 2022 highs). Your evolved strategies may be tuned for **uptrends only**.

**Test:** Run evolved strategies on 2014-2016 data (oil bear market). If Sharpe <0, they're overfitted.

---

**Risk 6: Code Complexity Explosion**

**Problem:** LLMs love complex code. You may evolve a 500-line strategy with 15 indicators that's impossible to debug.

**Mitigation:** Add **simplicity penalty** to fitness function. Score = Sharpe - (0.01 × lines_of_code).

---

## 5. POC Plan Improvements

### 🔴 Critical Changes Needed

**Change 1: Extend Timeline from 2-3 Days to 5-7 Days**

**Why:**
- Setting up LLM integration: 4-6 hours (not 2)
- Backtesting harness: 12-16 hours (not 8)
- Debugging inevitable issues: 4-8 hours (not planned)
- Analysis and write-up: 4-6 hours (not 2)

**Revised POC timeline:**
- **Day 1-2:** LLM integration + strategy generator (12 hours)
- **Day 3-4:** Backtesting harness + validation (16 hours)
- **Day 5:** Generate and test 10-15 variants (8 hours)
- **Day 6:** Analysis, comparison, document (6 hours)
- **Day 7:** Buffer for issues

---

**Change 2: Test on 3-5 Stocks, Not Just 1**

Current plan tests EOG only. **This proves nothing about generalization.**

**Better POC:**
- Test on **5 stocks**: EOG (large), DVN (large), MTDR (mid), CIVI (mid), MGY (small)
- Ensures strategy works across market caps
- Reveals if small-cap slippage kills performance

---

**Change 3: Stricter Success Criteria**

Current: "At least 1 variant beats baseline"

**Problem:** With 10 variants, you're **guaranteed** 1 will beat baseline by random chance (p-value ~0.40).

**Better criteria:**
- ✅ **Mean of top 3 variants** beats baseline by 2%+ (statistical significance)
- ✅ **Best variant generalizes** (works on all 5 stocks, not just 1)
- ✅ **Out-of-sample Sharpe >0.8** (vs. in-sample Sharpe to detect overfitting)

---

**Change 4: Add Baseline Comparisons**

Current plan doesn't specify baselines clearly.

**Must compare against:**
1. **Buy-and-hold** (each stock individually)
2. **Buy-and-hold XOP** (sector ETF)
3. **Simple 50/200 SMA crossover** (momentum baseline)
4. **Current Oil-Stonks technical score** (manual baseline)

**Decision rule:** If evolved strategy doesn't beat ALL 4, POC fails.

---

### 🟡 Suggested Enhancements

**Enhancement 1: Log All LLM Prompts and Responses**

For debugging and cost tracking:
```python
with open("llm_log.jsonl", "a") as f:
    f.write(json.dumps({
        "timestamp": time.time(),
        "prompt_tokens": response.usage.prompt_tokens,
        "completion_tokens": response.usage.completion_tokens,
        "cost_usd": calculate_cost(response.usage),
        "strategy_code": response.choices[0].message.content
    }) + "\n")
```

**Why:** You'll want to analyze what worked/didn't work. Logging is cheap insurance.

---

**Enhancement 2: Visualize Evolved Strategies**

After POC, plot:
- **Equity curves** (all 10 variants vs. baselines)
- **Sharpe ratio distribution**
- **Parameter space exploration** (which indicators were tried)

**Why:** Visual confirmation beats staring at numbers.

---

## 6. Alternative Approaches to Consider

### 🔴 Alternative 1: Simpler Optimization (Recommended First Step)

**Instead of full ProFiT, do this:**

1. **Grid search** on existing technical indicators
   - Test all combinations of RSI(10, 14, 20), MACD(12,26,9 vs. 8,17,9), etc.
   - 20-30 parameter combinations = 2-3 hours of compute
   - Find optimal weights (trend 40% vs. 30% vs. 50%)

**Advantages:**
- **10x faster** (no LLM, no evolution)
- **10x cheaper** (just compute, no API costs)
- **Easier to explain** (no "AI generated this" black box)
- **Likely 80% of ProFiT's benefit** (most alpha comes from tuning, not novel indicators)

**Recommendation:** Try this first. If grid search beats baseline by <2%, then try ProFiT.

---

### 🔴 Alternative 2: Genetic Algorithm Without LLM

**Use traditional genetic programming:**
- Represent strategies as syntax trees (like ProFiT)
- Mutate via random tree modifications (not LLM)
- Free (no API costs), runs offline

**Advantages:**
- Proven track record (genetic algos used in finance since 1990s)
- No LLM hallucination risk
- Faster iteration (no API latency)

**Disadvantages:**
- Less "creative" than LLM (won't discover novel patterns)
- Requires implementing GP yourself (~40 hours)

**Libraries:**
- `gplearn` (Python, genetic programming for sklearn)
- `DEAP` (Distributed Evolutionary Algorithms in Python)

---

### 🟡 Alternative 3: Ensemble of Hand-Coded Strategies

**Instead of evolving:**
1. Code 5-7 proven strategies manually:
   - Momentum (50/200 SMA crossover)
   - Mean reversion (Bollinger Band bounce)
   - Breakout (price > 52-week high)
   - RSI(14) oversold/overbought
   - MACD crossover

2. Weight them via machine learning (simple linear regression)

**Advantages:**
- You control exactly what strategies are used
- Interpretable
- ~20 hours to implement

**Disadvantages:**
- No "discovery" - relies on known patterns only

---

### 🟡 Alternative 4: Use Existing Quantitative Platforms

**Don't reinvent the wheel:**
- **QuantConnect**: Cloud backtesting + live trading, Python/C#
- **Zipline**: Open-source backtesting (used by Quantopian)
- **Backtrader**: What you're already using, but has built-in optimization

**Advantage:** Battle-tested infrastructure, avoid edge cases you'll hit building from scratch.

**Disadvantage:** Less customizable for ProFiT-specific logic.

---

## 7. Revised Risk Assessment

| Risk | Original Probability | Original Impact | Revised Probability | Revised Impact | Must-Have Mitigation |
|------|---------------------|----------------|--------------------|-----------------|-----------------------|
| LLM generates invalid code | Not mentioned | - | **High (60%)** | High | Syntax validation + whitelist |
| Overfitting | High | Critical | **Very High (80%)** | Critical | Walk-forward + cross-validation across stocks |
| LLM cost overrun | Not mentioned | - | **Medium (40%)** | Medium | Set hard budget cap ($100 POC, $500 full) |
| Look-ahead bias | Not mentioned | - | **Medium (30%)** | Critical | Static analysis for `.shift(-N)` |
| Strategy degradation | Medium | High | **Very High (90%)** | High | Quarterly re-evolution + Sharpe monitoring |
| Oil price shock | Medium | High | **Medium (20% per year)** | Critical | 25% drawdown circuit breaker + WTI-based pause |
| Execution slippage | Low | Medium | **Medium (50%)** | High | Model slippage as f(volume, position size) |
| Small sample size | Not mentioned | - | **High (70%)** | High | Cross-validation across stocks |
| Survivorship bias | Not mentioned | - | **Medium (40%)** | Medium | Verify EODHD includes delisted stocks |
| API rate limits | Not mentioned | - | **Low (20%)** | Low | Upgrade OpenAI tier if needed |

---

## 8. Recommended Changes to Plan Document

### Sections to Add

1. **Section 8.5: Risk Mitigation Checklist**
   - [ ] Syntax validation implemented
   - [ ] Look-ahead bias detection implemented
   - [ ] LLM budget cap set and monitored
   - [ ] Overfitting detection (in-sample vs. out-of-sample Sharpe)
   - [ ] Drawdown circuit breaker configured
   - [ ] Slippage model validated

2. **Section 9.5: POC Failure Criteria**
   - If evolved strategies don't beat all 4 baselines → STOP
   - If LLM costs exceed $100 in POC → STOP and revise approach
   - If top 3 strategies have out-of-sample Sharpe <0.5 → STOP

3. **Section 10.5: Quarterly Review Protocol**
   - Re-run evolution every 3 months
   - If Sharpe drops below 0.5 for 2 consecutive months → pause strategy
   - If max drawdown exceeds 25% → force to cash and review

### Sections to Revise

1. **Section 4.2 (Estimated Development Effort)**
   - Change POC from "18-26 hours" to **"32-44 hours (5-7 days)"**
   - Change total from "40-66 hours" to **"60-90 hours"**

2. **Section 7.1 (Costs)**
   - Change LLM API from "$50-200" to **"$500-2,000 (full), $50-100 (POC)"**
   - Add ongoing maintenance: **"$5,000-7,500/year (100-150 hours)"**

3. **Section 7.3 (ROI Calculation)**
   - Revise conservative scenario: **Break-even in 10-12 months** (not 6)
   - Add note: **"Assumes 5%+ alpha. If alpha <3%, ROI negative in Year 1-2."**

4. **Section 6.1 (POC Plan)**
   - Test on **5 stocks** (not 1)
   - Extend to **5-7 days** (not 2-3)
   - Add stricter success criteria (mean of top 3 beats baseline by 2%+)

---

## 9. Go/No-Go Recommendation

### ✅ Proceed with POC IF:

1. ✅ You accept revised timeline (**5-7 days**, not 2-3)
2. ✅ You accept revised cost estimate (**$50-100 POC**, $500-2K full)
3. ✅ You're willing to **abandon if POC fails** strict criteria
4. ✅ You implement **must-have mitigations** (syntax validation, look-ahead detection, budget cap)
5. ✅ You try **simpler alternatives first** (grid search takes 3 hours - do that Day 0)

### 🛑 DO NOT Proceed IF:

1. ❌ You expect this to be "quick and easy" (it won't be)
2. ❌ You're counting on 5-10% alpha for portfolio viability (too uncertain)
3. ❌ You don't have time for quarterly re-evolution (required)
4. ❌ You're risk-averse about algo trading (this is experimental)

---

## 10. Final Verdict

**Rating:** ⭐⭐⭐ out of 5 (Promising but Risky)

**Strengths:**
- Conceptually innovative application of ProFiT to sector-specific investing
- Pragmatic hybrid approach (fundamental manual, technical evolved)
- Acknowledges most major risks

**Weaknesses:**
- Cost and timeline estimates too optimistic
- Alpha assumptions lack empirical basis
- POC success criteria too lax
- Missing critical mitigations (look-ahead bias, LLM hallucination)

**Recommendation:**
**CONDITIONAL GO** - Proceed with POC under revised parameters:
- Budget: $100 max (15 generations)
- Timeline: 5-7 days (not 2-3)
- Success: Beat all 4 baselines by 2%+ on average across 5 stocks
- Implement 4 must-have mitigations before generating first strategy

If POC succeeds, **revisit full implementation plan** with updated cost/benefit based on actual results.

If POC fails, **pivot to simpler alternatives** (grid search, ensemble of hand-coded strategies) before giving up on quantitative approach entirely.

---

## Appendix A: Recommended POC Task List

### Day 1-2: LLM Integration (12-16 hours)
- [ ] Set up OpenAI/Anthropic API (1 hour)
- [ ] Implement strategy generator with prompt templates (4-6 hours)
- [ ] Add syntax validation (ast module) (2-3 hours)
- [ ] Add look-ahead bias detection (regex for `.shift(-N)`) (2-3 hours)
- [ ] Test with 3-5 hand-crafted strategy mutations (2-3 hours)

### Day 3-4: Backtesting Harness (12-16 hours)
- [ ] Set up Backtrader or VectorBT (3-4 hours)
- [ ] Fetch data for 5 stocks (EOG, DVN, MTDR, CIVI, MGY) (2 hours)
- [ ] Implement dynamic strategy compilation (4-6 hours)
- [ ] Add transaction cost and slippage models (2-3 hours)
- [ ] Test with baseline strategies (SMA crossover, buy-hold) (1-2 hours)

### Day 5: Evolution and Testing (8-10 hours)
- [ ] Generate 10-15 strategy variants via LLM (3-4 hours of runtime)
- [ ] Backtest all variants on 5 stocks (3-4 hours of runtime)
- [ ] Calculate metrics (Sharpe, max DD, win rate) (1-2 hours)
- [ ] Track LLM costs and token usage (ongoing)

### Day 6: Analysis (6-8 hours)
- [ ] Compare top 3 variants against 4 baselines (2-3 hours)
- [ ] Test generalization (in-sample vs. out-of-sample) (2 hours)
- [ ] Visualize equity curves and parameter distributions (2 hours)
- [ ] Document findings and decision (1 hour)

### Day 7: Buffer for Issues
- [ ] Debug inevitable bugs
- [ ] Re-run experiments if needed
- [ ] Final decision: Go/No-Go for full implementation

---

**Review Complete: 2025-12-04 15:45 PM**
