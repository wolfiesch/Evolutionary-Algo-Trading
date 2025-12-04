# Oil-Stonks E&P Ranking System - Design Document

**Created:** 2025-12-04
**Status:** Draft - Pending Review
**Author:** Wolfgang Schoenberger + Claude

---

## 1. Executive Summary

A decision-support system for investing in U.S. Oil & Gas Exploration & Production (E&P) equities. Combines fundamental analysis (60% weight) with technical analysis (40% weight) to generate weekly stock rankings and buy/sell recommendations.

**Goals:**
- Beat S&P 500 benchmark over rolling 1-year periods
- Start with 10-15 stocks, scale to full U.S. E&P universe (~80 companies)
- Validate strategy with 5-year backtest (2020-2024)
- Provide decision support with path to semi/full automation

---

## 2. Scoring System

### 2.1 Overall Score Formula

```
Overall Score = (Fundamental Score × 0.60) + (Technical Score × 0.40)
```

Scores normalized to 0-100 scale for comparability.

---

### 2.2 Fundamental Score (60% of Overall)

Four factors, equally weighted at 25% each:

| Factor | Metric | Scoring Logic | Why It Matters |
|--------|--------|---------------|----------------|
| **Free Cash Flow Yield** | FCF / Market Cap | Higher = better (0-100 scale) | Shows actual cash generation vs. valuation |
| **Debt Levels** | Net Debt / EBITDA | Lower = better (inverted scale) | E&P leverage kills in downturns |
| **Breakeven Oil Price** | All-in cost per BOE | Lower = better | Survivability when oil drops |
| **Hedging Quality** | % production hedged + hedge price vs. strip | Higher % at good prices = better | Downside protection |

**Fundamental Score Calculation:**
```
Fundamental Score = (FCF_Score × 0.25) + (Debt_Score × 0.25) +
                    (Breakeven_Score × 0.25) + (Hedge_Score × 0.25)
```

**Data Refresh:** Quarterly (after earnings) + event-driven updates

**Scoring Details:**

**FCF Yield (25%):**
- Calculate: TTM Free Cash Flow / Current Market Cap
- Percentile rank within universe → Score 0-100
- Example: 12% FCF yield in top 10% of peers → Score 90

**Debt/EBITDA (25%):**
- Calculate: Net Debt / TTM EBITDA
- Invert and percentile rank (lower debt = higher score)
- Thresholds: <1.0x = excellent, 1-2x = good, 2-3x = caution, >3x = danger
- Example: 1.5x debt/EBITDA → Score 70

**Breakeven Oil Price (25%):**
- Source from company guidance, investor presentations, or analyst estimates
- Lower breakeven = higher score
- Thresholds: <$40 WTI = excellent, $40-50 = good, $50-60 = fair, >$60 = risky
- Example: $45 breakeven → Score 75

**Hedging Quality (25%):**
- Composite of: % of next 12mo production hedged + weighted avg hedge price vs. current strip
- Well-hedged at good prices = stability
- Example: 60% hedged at $75 WTI (strip at $70) → Score 80

---

### 2.3 Technical Score (40% of Overall)

Three components:

| Component | Indicators | Weight | Purpose |
|-----------|-----------|--------|---------|
| **Trend** | Price vs. 50/200 SMA, SMA slope | 40% | Identify direction |
| **Momentum** | RSI(14), MACD histogram | 35% | Identify strength |
| **Volume** | Volume vs. 20-day avg, OBV trend | 25% | Confirm conviction |

**Technical Score Calculation:**
```
Technical Score = (Trend_Score × 0.40) + (Momentum_Score × 0.35) + (Volume_Score × 0.25)
```

**Data Refresh:** Daily (scores recalculated weekly for ranking)

**Scoring Details:**

**Trend Score (40%):**
- Price > 50 SMA: +20 points
- Price > 200 SMA: +20 points
- 50 SMA > 200 SMA (golden cross): +20 points
- 50 SMA slope positive (20-day): +20 points
- 200 SMA slope positive (50-day): +20 points
- Max: 100 points

**Momentum Score (35%):**
- RSI(14) scoring:
  - 30-50: +25 (oversold recovery zone)
  - 50-70: +50 (healthy uptrend)
  - 70-80: +25 (strong but extended)
  - <30 or >80: 0 (extreme, likely to reverse)
- MACD histogram:
  - Positive and rising: +50
  - Positive and falling: +25
  - Negative and rising: +25
  - Negative and falling: 0
- Max: 100 points

**Volume Score (25%):**
- Current volume > 20-day avg on up days: +50
- OBV (On-Balance Volume) trending up (20-day regression): +50
- Max: 100 points

---

### 2.4 Combined Ranking & Recommendations

Weekly output categorizes stocks into quintiles:

| Quintile | Score Range | Recommendation | Action |
|----------|-------------|----------------|--------|
| Top 20% | 80-100 | **Strong Buy** | Primary candidates for new positions |
| 60-80% | 60-79 | **Buy** | Secondary candidates, add on dips |
| 40-60% | 40-59 | **Hold** | Maintain existing positions |
| 20-40% | 20-39 | **Sell** | Reduce or exit positions |
| Bottom 20% | 0-19 | **Strong Sell** | Avoid or short candidates |

---

## 3. Risk Management

### 3.1 Position Sizing

| Rule | Value | Rationale |
|------|-------|-----------|
| Max positions | 5-7 | Concentrated enough for alpha, diversified enough for risk |
| Position size | Equal weight (~15% each for 6 positions) | Simplicity, prevents overconfidence bias |
| Max single position | 20% | No single stock can destroy portfolio |
| Cash buffer | 10-20% | Dry powder for opportunities, drawdown cushion |

### 3.2 Risk Controls

| Control | Trigger | Action |
|---------|---------|--------|
| Position stop-loss | -15% from entry | Flag for review (not automatic sell) |
| Portfolio drawdown | -20% from peak | Pause new buys, review thesis |
| Correlation alert | Portfolio beta to WTI > 1.5 | Consider hedging or cash increase |
| Concentration alert | Single position > 25% (due to gains) | Trim back to 20% |

### 3.3 Rebalancing

- **Frequency:** Weekly (every Sunday/Monday)
- **Process:**
  1. Refresh fundamental scores (if new data)
  2. Recalculate technical scores
  3. Generate new rankings
  4. Flag positions that changed quintiles
  5. Review and decide on trades

---

## 4. Data Sources

### 4.1 Primary Sources

| Data Type | Source | Cost | Refresh |
|-----------|--------|------|---------|
| Price/Volume (historical) | EODHD API | ~$20/mo (existing) | Daily |
| Fundamentals (financials) | EODHD API | Included | Quarterly |
| Oil prices (WTI, Brent) | EIA or FRED | Free | Daily |
| Natural gas (Henry Hub) | EIA or FRED | Free | Daily |
| Rig counts | Baker Hughes (via EIA) | Free | Weekly |

### 4.2 Supplementary Sources (Manual or Scraped)

| Data Type | Source | Notes |
|-----------|--------|-------|
| Breakeven oil prices | Company investor presentations, earnings calls | Update quarterly |
| Hedging details | 10-Q/10-K filings, earnings call transcripts | Update quarterly |
| Production guidance | Company press releases | Event-driven |

### 4.3 Data Pipeline

```
[EODHD API] ──→ [Raw Data Store] ──→ [Processing/Calculation] ──→ [Scores DB]
                      ↑                        ↑
[EIA/FRED APIs] ──────┘                        │
[Manual Inputs] ───────────────────────────────┘
```

---

## 5. Initial Stock Universe (10-15 Companies)

Curated list for initial testing - mix of large, mid, and small cap E&P:

| Ticker | Company | Market Cap | Basin Focus | Notes |
|--------|---------|------------|-------------|-------|
| XOM | Exxon Mobil | Mega | Diversified | Benchmark/reference |
| CVX | Chevron | Mega | Diversified | Benchmark/reference |
| EOG | EOG Resources | Large | Permian, Eagle Ford | Best-in-class operator |
| PXD | Pioneer Natural Resources | Large | Permian | Pure-play Permian (now part of XOM) |
| DVN | Devon Energy | Large | Multi-basin | Good hedging practices |
| FANG | Diamondback Energy | Large | Permian | Low-cost operator |
| OVV | Ovintiv | Mid | Multi-basin | Undervalued, improving |
| PR | Permian Resources | Mid | Permian | Pure-play, growth |
| MTDR | Matador Resources | Mid | Permian, Eagle Ford | Growth-oriented |
| CHRD | Chord Energy | Mid | Bakken | Consolidated Bakken player |
| CRC | California Resources | Mid | California | Unique, different risk profile |
| SM | SM Energy | Small | Permian, Eagle Ford | Value play |
| CIVI | Civitas Resources | Mid | DJ Basin, Permian | Growing Permian presence |
| MGY | Magnolia Oil & Gas | Small | South Texas | Conservative, low debt |
| CPE | Callon Petroleum | Small | Permian | Higher leverage, turnaround |

**Note:** PXD merged with XOM in 2024 - will need to adjust for backtest or replace.

---

## 6. Backtesting Plan

### 6.1 Parameters

| Parameter | Value |
|-----------|-------|
| Period | Jan 2020 - Dec 2024 (5 years) |
| Initial capital | $100,000 (hypothetical) |
| Rebalancing | Weekly |
| Transaction costs | 0.1% per trade (conservative estimate) |
| Slippage | 0.05% (liquid stocks) |
| Dividends | Reinvested |

### 6.2 Benchmarks

| Benchmark | Ticker | Description |
|-----------|--------|-------------|
| S&P 500 | SPY | Primary benchmark (must beat) |
| Energy Select | XLE | Sector benchmark |
| Oil & Gas E&P ETF | XOP | Direct peer benchmark |
| WTI Crude Oil | CL1 | Commodity correlation reference |

### 6.3 Metrics to Track

| Metric | Target | Description |
|--------|--------|-------------|
| Total Return | > SPY | Absolute performance |
| CAGR | > 12% | Annualized return |
| Sharpe Ratio | > 1.0 | Risk-adjusted return |
| Max Drawdown | < 40% | Worst peak-to-trough |
| Win Rate | > 55% | % of profitable trades |
| Avg Win / Avg Loss | > 1.5 | Reward-to-risk ratio |
| Beta to SPY | Track | Market correlation |
| Beta to WTI | Track | Commodity correlation |

### 6.4 Walk-Forward Validation

To avoid overfitting:
1. **In-sample:** 2020-2022 (train/tune parameters)
2. **Out-of-sample:** 2023-2024 (validate)
3. Ensure strategy works in both periods before live deployment

---

## 7. Technical Architecture

### 7.1 Tech Stack (Proposed)

| Component | Technology | Rationale |
|-----------|------------|-----------|
| Language | Python 3.11+ | Data science ecosystem, backtesting libraries |
| Data Storage | SQLite → PostgreSQL | Start simple, scale later |
| Backtesting | Backtrader or VectorBT | Mature, well-documented |
| Data Fetching | EODHD SDK, pandas-datareader | API wrappers |
| Visualization | Plotly, Matplotlib | Interactive charts |
| Scheduling | Cron or APScheduler | Weekly refresh automation |
| UI (future) | Streamlit or Dash | Simple dashboards |

### 7.2 Project Structure

```
Oil-Stonks/
├── docs/
│   └── plans/                    # Design docs, planning
├── src/
│   ├── data/
│   │   ├── fetchers/             # API integrations
│   │   ├── processors/           # Data cleaning, transforms
│   │   └── storage/              # Database operations
│   ├── scoring/
│   │   ├── fundamental.py        # Fundamental score calc
│   │   ├── technical.py          # Technical score calc
│   │   └── combined.py           # Overall score, ranking
│   ├── backtest/
│   │   ├── engine.py             # Backtesting framework
│   │   ├── strategies.py         # Strategy definitions
│   │   └── metrics.py            # Performance analytics
│   └── utils/
│       └── config.py             # Configuration, constants
├── data/
│   ├── raw/                      # Raw API responses
│   ├── processed/                # Cleaned data
│   └── manual/                   # Manual inputs (hedging, breakeven)
├── notebooks/                    # Jupyter exploration
├── tests/                        # Unit tests
├── config/
│   └── settings.yaml             # API keys, parameters
├── requirements.txt
└── README.md
```

---

## 8. Implementation Phases

### Phase 1: Foundation (MVP)
- [ ] Set up project structure and dependencies
- [ ] Implement EODHD data fetcher (prices, fundamentals)
- [ ] Implement EIA/FRED data fetcher (oil prices)
- [ ] Build basic technical score calculator
- [ ] Build simplified fundamental score (FCF yield, debt only - data available via API)
- [ ] Create simple ranking output (CLI or notebook)
- [ ] Basic backtest with equal-weight portfolio

### Phase 2: Full Scoring
- [ ] Add remaining fundamental factors (breakeven, hedging - manual input initially)
- [ ] Refine technical indicators
- [ ] Implement proper scoring normalization
- [ ] Add transaction costs and slippage to backtest
- [ ] Compare against benchmarks (SPY, XLE, XOP)

### Phase 3: Validation & Refinement
- [ ] Walk-forward validation (in-sample / out-of-sample)
- [ ] Parameter sensitivity analysis
- [ ] Analyze winning vs. losing trades
- [ ] Refine weights and thresholds

### Phase 4: Decision Support UI
- [ ] Build Streamlit dashboard
- [ ] Weekly ranking display
- [ ] Historical performance charts
- [ ] Individual stock drill-down

### Phase 5: Automation (Future)
- [ ] Automated weekly data refresh
- [ ] Email/SMS alerts for ranking changes
- [ ] Broker API integration (paper trading first)

---

## 9. Key Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Overfitting to historical data | Strategy fails live | Walk-forward validation, simple model |
| Fundamental data lag | Scores outdated | Supplement with manual updates, event monitoring |
| Oil price crash | All E&P stocks drop together | Cash buffer, stop-losses, accept sector concentration |
| Hedging data hard to get | Incomplete fundamental score | Start with 3 factors, add hedging manually over time |
| Small universe bias | Results don't generalize | Test on full universe once validated |
| Liquidity issues (small caps) | Slippage kills returns | Focus on mid/large caps initially |

---

## 10. Success Criteria

**Minimum Viable Success (must achieve all):**
- [ ] Backtest shows positive returns over 5-year period
- [ ] Beats SPY total return by any margin
- [ ] Max drawdown < 50%
- [ ] Sharpe ratio > 0.5

**Target Success:**
- [ ] Beats SPY by 5%+ annually
- [ ] Sharpe ratio > 1.0
- [ ] Win rate > 55%
- [ ] Strategy works in both bull (2021, 2022) and bear (2020, 2023) periods

---

## 11. Open Questions

1. **PXD merger:** Replace with another Permian pure-play (PR or FANG increased weight)?
2. **Weighting flexibility:** Should fundamental/technical split (60/40) be adjustable based on oil regime?
3. **Short selling:** Include in backtest or long-only?
4. **Dividend treatment:** Reinvest or track separately?
5. **Sector ETF alternative:** Compare against just buying XOP and doing nothing?

---

## Changelog

| Date | Change | Author |
|------|--------|--------|
| 2025-12-04 | Initial design document created | Wolfgang + Claude |

---

*Document ready for review. Once approved, proceed to implementation planning.*
