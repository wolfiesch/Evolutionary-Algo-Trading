# Equities Swing Trading System

**Status:** Planning Phase
**Created:** 12/15/2025 12:36 PM PST (via pst-timestamp)
**Asset Class:** US Public Equities
**Edge:** LLM-driven evolution with SEC EDGAR fundamental integration

---

## Executive Summary

This system combines the proven evolutionary strategy infrastructure from Oil-Stonks with the SEC EDGAR agent's fundamental analysis capabilities to create a **fundamentals-enhanced technical trading system** for US equities. Unlike crypto (pure technicals) or traditional quant (pure fundamentals), this system uses **EDGAR-derived signals as filters and catalysts** while letting technical primitives handle timing.

**Key Differentiator:** Most retail algo traders have access to price data. Very few have structured, real-time access to:
- Insider buying/selling patterns (Form 4)
- Risk factor changes between filings (10-K/10-Q diffs)
- Material event timing (8-K filings)
- Institutional positioning shifts (13F)
- Financial trajectory signals (revenue/earnings CAGR)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        EQUITIES SWING TRADING SYSTEM                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────┐    ┌─────────────────────┐    ┌────────────────┐  │
│  │   SEC EDGAR Agent   │    │   Market Data Feed  │    │  Shared Infra  │  │
│  │  (Fundamental Data) │    │   (Price/Volume)    │    │  (Oil-Stonks)  │  │
│  └──────────┬──────────┘    └──────────┬──────────┘    └───────┬────────┘  │
│             │                          │                       │           │
│             ▼                          ▼                       ▼           │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                         GENE POOL (EXTENDED)                          │  │
│  │  ┌──────────────────┐  ┌──────────────────┐  ┌────────────────────┐  │  │
│  │  │ Technical Prims  │  │ Fundamental Prims │  │  Market Filters   │  │  │
│  │  │ (from shared/)   │  │  (EDGAR-derived)  │  │  (SPY/VIX/Sector) │  │  │
│  │  └──────────────────┘  └──────────────────┘  └────────────────────┘  │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                    │                                       │
│                                    ▼                                       │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                        EVOLUTION ENGINE                               │  │
│  │  Strategy Generation → Backtesting → Fitness → Selection → Mutation  │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                    │                                       │
│                                    ▼                                       │
│  ┌────────────────┐    ┌────────────────┐    ┌─────────────────────────┐  │
│  │ Shadow Trading │ ──►│  Validation    │ ──►│  Live Trading (Phase 3) │  │
│  │   (Paper)      │    │  (7+ days)     │    │  (Real Capital)         │  │
│  └────────────────┘    └────────────────┘    └─────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Alpha Signal Categories

### Category 1: Insider Activity Signals (Form 4)

**Hypothesis:** Insiders have asymmetric information. Clustered buying by multiple insiders is a strong bullish signal. Selling is noisy (could be tax/diversification), but buying is intentional.

**Primitives:**
```python
# Insider buying intensity over N days
insider_buy_intensity(ticker, days: int) -> float  # 0.0 to 1.0
# Number of distinct insiders buying / total insider transactions

# Insider buy/sell ratio
insider_net_sentiment(ticker, days: int) -> float  # -1.0 to +1.0
# (buy_value - sell_value) / (buy_value + sell_value)

# Cluster detection (multiple insiders buying in short window)
insider_cluster_signal(ticker, days: int, min_insiders: int) -> float  # 1.0 or 0.0
# Returns 1.0 if >= min_insiders bought in the window
```

**Data Source:** SEC EDGAR Form 4 via `get_insider_trades()`

**Example Strategy Usage:**
```
entry_long: spy_trend(20) >= 0 AND insider_cluster_signal(30, 2) == 1.0 AND norm_rsi(14) < 0.0
```

---

### Category 2: Financial Trajectory Signals (10-K/10-Q)

**Hypothesis:** Companies with improving fundamentals (accelerating revenue, expanding margins) tend to outperform, especially when technicals align.

**Primitives:**
```python
# Revenue growth trajectory
revenue_cagr(ticker, years: int) -> float  # Continuous, capped at ±0.5
# 3-year CAGR from income statements

# Earnings quality (net income / operating cash flow)
earnings_quality(ticker) -> float  # 0.0 to 1.0
# Higher = earnings backed by real cash flow

# Margin expansion signal
margin_trend(ticker, quarters: int) -> float  # -1.0 to +1.0
# Compares current gross margin to N-quarter average

# Debt trajectory
leverage_change(ticker, years: int) -> float  # -1.0 to +1.0
# Positive = deleveraging (good), negative = increasing debt
```

**Data Source:** SEC EDGAR via `get_income_statement()`, `get_balance_sheet()`, `get_cash_flow()`, `analyze_historical_trends()`

**Example Strategy Usage:**
```
entry_long: spy_trend(20) >= 0 AND revenue_cagr(3) > 0.10 AND ema_trend(20, 50) == 1.0
exit_long: ema_trend(20, 50) == -1.0 OR margin_trend(4) < -0.3
```

---

### Category 3: Risk & Event Signals (8-K, 10-K Item 1A)

**Hypothesis:** Material events (8-Ks) and risk factor changes can signal upcoming volatility or fundamental shifts.

**Primitives:**
```python
# Recent 8-K filing count (material events)
event_activity(ticker, days: int) -> float  # 0.0 to 1.0
# Normalized count of 8-K filings in period

# Risk factor delta (new risks added between filings)
risk_change_intensity(ticker) -> float  # 0.0 to 1.0
# % of risk factors that are new or significantly modified

# Specific 8-K event type detection
has_material_event(ticker, event_type: str, days: int) -> float  # 1.0 or 0.0
# Event types: "acquisition", "restructuring", "leadership_change", "earnings"
```

**Data Source:** SEC EDGAR via `detect_risk_changes()`, 8-K filing search

**Example Strategy Usage:**
```
# Avoid stocks with increasing risk profile
entry_long: spy_trend(20) >= 0 AND risk_change_intensity() < 0.3 AND ema_trend(9, 21) == 1.0
```

---

### Category 4: Institutional Positioning (13F)

**Hypothesis:** When multiple top-tier institutions add to positions, it's a bullish signal. Conversely, coordinated selling is bearish.

**Primitives:**
```python
# Institutional ownership change
inst_ownership_delta(ticker, quarters: int) -> float  # -1.0 to +1.0
# Change in total institutional ownership

# Smart money concentration
inst_concentration(ticker) -> float  # 0.0 to 1.0
# Top 10 holders as % of institutional ownership

# New position count
inst_new_positions(ticker, quarters: int) -> float  # 0.0 to 1.0
# Number of new institutional positions / total institutions
```

**Data Source:** SEC EDGAR Form 13F-HR

**Limitations:** 13F data is quarterly with 45-day delay. Use as background filter, not timing signal.

---

### Category 5: Market Regime Filters (SPY/VIX)

**Hypothesis:** Just as BTC trend filters crypto entries, SPY trend and VIX regime should filter equity entries.

**Primitives:**
```python
# SPY trend (market filter equivalent)
spy_trend(period: int) -> float  # +1.0 or -1.0
# Same logic as btc_trend but for SPY

# VIX regime
vix_regime(period: int) -> float  # +1.0 (low vol), 0.0 (normal), -1.0 (high vol)
# VIX < 15 = low vol, 15-25 = normal, > 25 = high vol

# Sector relative strength
sector_rs(ticker, period: int) -> float  # -1.0 to +1.0
# Stock's sector ETF performance vs SPY
```

**Data Source:** Market data feed (Yahoo Finance, Polygon, or similar)

**Example Strategy Usage:**
```
entry_long: spy_trend(20) >= 0 AND vix_regime(14) >= 0 AND norm_rsi(14) < -0.4
```

---

### Category 6: Sector & Peer Signals

**Hypothesis:** Relative performance within sector matters. A strong stock in a weak sector is different from a strong stock in a strong sector.

**Primitives:**
```python
# Sector momentum
sector_momentum(ticker, period: int) -> float  # -1.0 to +1.0
# Sector ETF's performance rank vs other sectors

# Peer relative strength
peer_percentile(ticker, period: int) -> float  # 0.0 to 1.0
# Stock's return percentile within its SIC code peer group

# Industry group trend
industry_trend(ticker, period: int) -> float  # +1.0 or -1.0
# EMA trend of the stock's industry ETF
```

**Data Source:** SEC EDGAR for peer identification (SIC codes), market data for prices

---

## Universe Selection

### Criteria for Tradable Universe

1. **Market Cap:** > $1B (avoid illiquidity and manipulation)
2. **Average Daily Volume:** > $10M (ensure execution without slippage)
3. **Exchange:** NYSE, NASDAQ, AMEX (no OTC/pink sheets)
4. **Price:** > $10 (avoid low-float dynamics)
5. **EDGAR Coverage:** Must have 10-K and 10-Q filings in EDGAR
6. **Options Chain:** Preferably have liquid options (future enhancement)

### Dynamic Universe Management

```python
UniverseManager:
  - refresh_frequency: weekly
  - filter_by_market_cap(min=1e9)
  - filter_by_adv(min=10e6)
  - filter_by_edgar_coverage(min_filings=4)
  - exclude_list: ["SPY", "QQQ", "IWM"]  # No ETFs in stock strategies
  - sector_balance: True  # Ensure sector diversity
```

**Target Universe Size:** 200-500 stocks

---

## Data Architecture

### Data Sources & Refresh Rates

| Data Type | Source | Refresh Rate | Storage |
|-----------|--------|--------------|---------|
| OHLCV (Daily) | Yahoo Finance / Polygon | Daily EOD | SQLite |
| OHLCV (Intraday) | Polygon / Alpaca | 1-min during market | SQLite |
| SEC Filings | EDGAR Agent | Daily scan | SQLite + ChromaDB |
| Form 4 (Insider) | EDGAR Agent | Daily scan | SQLite |
| Form 13F | EDGAR Agent | Quarterly | SQLite |
| SPY/VIX | Market Data | 1-min during market | SQLite |
| Universe | Computed | Weekly | JSON |

### Schema Design

```sql
-- Price data (daily for backtesting)
CREATE TABLE daily_candles (
    symbol TEXT NOT NULL,
    date DATE NOT NULL,
    open REAL, high REAL, low REAL, close REAL,
    volume INTEGER, adj_close REAL,
    PRIMARY KEY (symbol, date)
);

-- Fundamental signals (cached from EDGAR)
CREATE TABLE fundamental_signals (
    symbol TEXT NOT NULL,
    signal_date DATE NOT NULL,
    signal_type TEXT NOT NULL,  -- 'insider_buy', 'revenue_cagr', 'risk_change', etc.
    signal_value REAL,
    raw_data JSON,  -- Full context for debugging
    PRIMARY KEY (symbol, signal_date, signal_type)
);

-- Filing events (for event-driven signals)
CREATE TABLE filing_events (
    symbol TEXT NOT NULL,
    filing_date DATE NOT NULL,
    form_type TEXT NOT NULL,  -- '10-K', '10-Q', '8-K', 'Form 4', '13F'
    accession_number TEXT,
    summary TEXT,
    PRIMARY KEY (symbol, filing_date, form_type, accession_number)
);

-- Universe membership
CREATE TABLE universe (
    symbol TEXT PRIMARY KEY,
    company_name TEXT,
    sector TEXT,
    industry TEXT,
    market_cap REAL,
    avg_volume REAL,
    last_updated DATE
);
```

---

## Gene Pool Design (Extended)

### Inheritance from Shared Infrastructure

All technical primitives from `/shared/engine/gene_pool/` are reused:
- `ema_trend(fast, slow)` → +1.0/-1.0
- `price_position(period)` → -3.0 to +3.0
- `norm_rsi(period)` → -1.0 to +1.0
- `bb_position(period, std)` → -1.0 to +1.0
- `bb_width_percentile(period, lookback)` → 0.0 to 1.0
- `volume_intensity(period, threshold)` → 0.0/1.0
- `vwap_distance(period)` → -3.0 to +3.0
- `atr_regime(period, lookback)` → -1.0/0.0/+1.0
- `atr_percentile(period, lookback)` → 0.0 to 1.0

### New Equities-Specific Primitives

```python
# File: equities/engine/gene_pool/market_filter.py

def spy_trend(candles: pd.DataFrame, period: int) -> float:
    """
    Market filter using SPY trend.
    Returns +1.0 if SPY in uptrend, -1.0 if downtrend.
    """
    # Same implementation as btc_trend but for SPY data
    pass

def vix_regime(vix_candles: pd.DataFrame, period: int) -> float:
    """
    Volatility regime based on VIX level.
    Returns +1.0 (low vol), 0.0 (normal), -1.0 (high vol/fear).
    """
    current_vix = vix_candles["close"].iloc[-1]
    if current_vix < 15:
        return 1.0  # Low vol, risk-on
    elif current_vix > 25:
        return -1.0  # High vol, risk-off
    else:
        return 0.0  # Neutral
```

```python
# File: equities/engine/gene_pool/fundamental.py

def insider_buy_intensity(symbol: str, days: int, edgar_cache: dict) -> float:
    """
    Measures insider buying activity intensity.
    Returns 0.0 to 1.0 (higher = more buying).
    """
    # Query cached Form 4 data
    # Calculate: buy_transactions / total_transactions
    pass

def revenue_cagr(symbol: str, years: int, edgar_cache: dict) -> float:
    """
    Revenue CAGR from 10-K filings.
    Returns continuous value, capped at ±0.5 for normalization.
    """
    # Query cached financials
    # Calculate CAGR, cap at [-0.5, +0.5]
    pass

def earnings_quality(symbol: str, edgar_cache: dict) -> float:
    """
    Net Income / Operating Cash Flow ratio.
    Returns 0.0 to 1.0 (higher = better quality).
    """
    pass

def risk_change_intensity(symbol: str, edgar_cache: dict) -> float:
    """
    Percentage of risk factors that changed between filings.
    Returns 0.0 to 1.0 (higher = more change/uncertainty).
    """
    pass
```

### Primitive Registry (Extended)

```python
# File: equities/engine/strategy_logic/parser.py

PRIMITIVES = {
    # Technical (inherited)
    "ema_trend": shared.gene_pool.trend.ema_trend,
    "price_position": shared.gene_pool.trend.price_position,
    "norm_rsi": shared.gene_pool.mean_reversion.norm_rsi,
    "bb_position": shared.gene_pool.mean_reversion.bb_position,
    "bb_width_percentile": shared.gene_pool.mean_reversion.bb_width_percentile,
    "volume_intensity": shared.gene_pool.volume.volume_intensity,
    "vwap_distance": shared.gene_pool.volume.vwap_distance,
    "atr_regime": shared.gene_pool.volatility.atr_regime,
    "atr_percentile": shared.gene_pool.volatility.atr_percentile,

    # Market Filters (equities-specific)
    "spy_trend": equities.gene_pool.market_filter.spy_trend,
    "vix_regime": equities.gene_pool.market_filter.vix_regime,
    "sector_momentum": equities.gene_pool.market_filter.sector_momentum,

    # Fundamental (EDGAR-derived)
    "insider_buy_intensity": equities.gene_pool.fundamental.insider_buy_intensity,
    "insider_cluster_signal": equities.gene_pool.fundamental.insider_cluster_signal,
    "revenue_cagr": equities.gene_pool.fundamental.revenue_cagr,
    "earnings_quality": equities.gene_pool.fundamental.earnings_quality,
    "risk_change_intensity": equities.gene_pool.fundamental.risk_change_intensity,
    "margin_trend": equities.gene_pool.fundamental.margin_trend,
}
```

---

## Strategy Expression Format

```json
{
  "strategy_name": "InsiderMomentum_V1",
  "asset_class": "equities",
  "timeframe": "daily",
  "entry_long": "spy_trend(20) >= 0 AND insider_buy_intensity(30) > 0.5 AND ema_trend(9, 21) == 1.0",
  "exit_long": "ema_trend(9, 21) == -1.0 OR norm_rsi(14) > 0.7",
  "entry_short": null,
  "exit_short": null,
  "universe_filter": "market_cap > 1e9 AND avg_volume > 10e6",
  "position_sizing": "equal_weight",
  "max_positions": 10
}
```

---

## Backtesting Considerations

### Friction Model (Equities vs Crypto)

| Parameter | Crypto | Equities |
|-----------|--------|----------|
| Commission | 0.25% per side | $0 (modern brokers) |
| Slippage | 0.10% estimate | 0.02% (liquid stocks) |
| Spread | Included in slippage | 0.01% (liquid stocks) |
| **Total Round-Trip** | **0.70%** | **0.06%** |

```python
# Equities backtest config
BacktestConfig:
  friction_per_side: 0.0003  # 0.03% (slippage + spread)
  min_trade_value: 1000  # Avoid tiny positions
```

### Data Considerations

1. **Survivorship Bias:** Include delisted stocks in backtest universe
2. **Look-ahead Bias:** Fundamental signals use filing_date, not period_end_date
3. **Point-in-Time Data:** EDGAR filings have known publication timestamps
4. **Stock Splits/Dividends:** Use adjusted prices for returns

### Regime Classification (Equities)

Replace BTC-based regimes with SPY-based:

```python
EQUITY_REGIMES = [
    "bull_calm",      # SPY uptrend, VIX < 20
    "bull_volatile",  # SPY uptrend, VIX >= 20
    "bear_calm",      # SPY downtrend, VIX < 25
    "bear_volatile",  # SPY downtrend, VIX >= 25
    "sideways"        # SPY range-bound
]
```

---

## Risk Management (Equities-Specific)

### Position Limits

```python
RiskConfig:
  max_position_pct: 0.05  # 5% per stock (more diversified than crypto)
  max_sector_pct: 0.20  # 20% max in any sector
  max_positions: 20  # Up to 20 concurrent positions
  max_exposure: 0.80  # 80% max invested (20% cash buffer)
  min_position_hold: "1_day"  # Pattern day trader rule avoidance
```

### Kill Switches

Same framework as crypto, adjusted thresholds:

| Trigger | Action |
|---------|--------|
| Drawdown > 3% in 1 day | Close all, pause 1 day |
| Drawdown > 7% in 1 week | Close all, pause 1 week |
| Drawdown > 15% from peak | Full shutdown |
| Single position > 5% loss | Force close |

### Market Hours Handling

```python
MarketHours:
  regular: "09:30-16:00 ET"
  pre_market: "04:00-09:30 ET"  # Optional
  after_hours: "16:00-20:00 ET"  # Optional

  # Trade execution
  entry_window: "09:35-15:55 ET"  # Avoid open/close volatility
  overnight_positions: True  # Hold positions overnight (swing trading)
```

---

## Implementation Phases

### Phase 0: Foundation (Week 1-2)
- [ ] Create directory structure under `/equities/`
- [ ] Set up market data ingestion (Yahoo Finance/Polygon)
- [ ] Implement SPY/VIX market filter primitives
- [ ] Create universe manager with filtering logic
- [ ] Set up SQLite schema for equities data
- [ ] Integrate with SEC EDGAR agent (HTTP client)

### Phase 1: EDGAR Integration (Week 2-3)
- [ ] Build fundamental primitive cache layer
- [ ] Implement `insider_buy_intensity` primitive
- [ ] Implement `revenue_cagr` primitive
- [ ] Implement `earnings_quality` primitive
- [ ] Implement `risk_change_intensity` primitive
- [ ] Daily EDGAR scan job for universe

### Phase 2: Backtesting (Week 3-4)
- [ ] Adapt backtester for equities friction model
- [ ] Implement equities regime classifier (SPY/VIX based)
- [ ] Build historical fundamental signal database
- [ ] Run validation backtests on known strategies
- [ ] Verify no look-ahead bias in fundamental signals

### Phase 3: Evolution (Week 4-5)
- [ ] Create equities-specific LLM prompts
- [ ] Configure evolution engine for fundamental + technical
- [ ] Run first evolution experiment (1000 generations)
- [ ] Analyze top strategies for overfitting
- [ ] Implement walk-forward validation

### Phase 4: Shadow Trading (Week 5-6)
- [ ] Deploy shadow trader for top strategies
- [ ] Real-time EDGAR monitoring integration
- [ ] Discord notifications for signals
- [ ] 7-day minimum validation period

### Phase 5: Live Trading (Week 6+)
- [ ] Broker integration (Alpaca/IBKR)
- [ ] Order management system
- [ ] Position tracking and P&L
- [ ] Kill switch implementation
- [ ] Performance dashboard

---

## Directory Structure

```
/Oil-Stonks/
├── /shared/                     # Cross-asset infrastructure (existing)
│   ├── /engine/gene_pool/       # Technical primitives
│   ├── /evolution/              # Evolution engine
│   └── /risk/                   # Risk management
│
├── /equities/                   # NEW: Equities-specific
│   ├── EQUITIES.md              # This file
│   ├── config.py                # Equities configuration
│   ├── main.py                  # Entry point
│   │
│   ├── /data/
│   │   ├── /ingestion/
│   │   │   ├── market_data.py   # Yahoo/Polygon client
│   │   │   ├── edgar_client.py  # SEC EDGAR agent HTTP client
│   │   │   └── universe.py      # Universe management
│   │   ├── /storage/
│   │   │   ├── repository.py    # SQLite abstraction
│   │   │   └── fundamental_cache.py
│   │   └── /quality/
│   │       └── filters.py       # Equity-specific quality checks
│   │
│   ├── /engine/
│   │   ├── /gene_pool/
│   │   │   ├── market_filter.py # spy_trend, vix_regime, sector_momentum
│   │   │   └── fundamental.py   # EDGAR-derived primitives
│   │   └── /strategy_logic/
│   │       └── parser.py        # Extended primitive registry
│   │
│   ├── /execution/
│   │   ├── /shadow/
│   │   │   ├── trader.py        # Paper trading engine
│   │   │   └── pool_manager.py  # Multi-strategy orchestration
│   │   └── /live/
│   │       ├── broker.py        # Alpaca/IBKR integration
│   │       └── order_manager.py
│   │
│   ├── /logs/
│   │   ├── trades.log
│   │   └── errors.log
│   │
│   └── /tests/
│       ├── test_market_filter.py
│       ├── test_fundamental.py
│       └── test_backtest.py
│
└── /sec-edgar-agent/            # Existing EDGAR infrastructure
    └── (unchanged, accessed via HTTP API)
```

---

## Integration with SEC EDGAR Agent

### Communication Pattern

The equities system communicates with SEC EDGAR agent via HTTP:

```python
class EdgarClient:
    def __init__(self, base_url: str = "http://localhost:8000/api/v1"):
        self.base_url = base_url

    async def get_insider_trades(self, ticker: str, days: int = 90) -> dict:
        """Fetch Form 4 data for insider activity signals."""
        response = await self.client.get(
            f"{self.base_url}/filings/{ticker}/4",
            params={"days": days}
        )
        return response.json()

    async def get_financials(self, ticker: str, years: int = 3) -> dict:
        """Fetch income statement, balance sheet, cash flow."""
        # Use the agent's financial extraction tools
        pass

    async def get_risk_changes(self, ticker: str) -> dict:
        """Fetch risk factor diff between filings."""
        # Use detect_risk_changes tool
        pass
```

### Caching Strategy

Fundamental data is slow-changing. Cache aggressively:

```python
FundamentalCache:
  insider_trades: 24_hours  # Form 4 filed within 2 business days
  financials: 7_days  # 10-K/10-Q quarterly
  risk_factors: 7_days  # Same as financials
  peer_data: 30_days  # SIC code mappings stable
```

---

## Example Evolved Strategies

### Strategy 1: Insider Momentum
```json
{
  "strategy_name": "InsiderMomentum_V1",
  "entry_long": "spy_trend(20) >= 0 AND insider_buy_intensity(30) > 0.6 AND ema_trend(9, 21) == 1.0 AND vix_regime(14) >= 0",
  "exit_long": "ema_trend(9, 21) == -1.0 OR insider_buy_intensity(30) < 0.2"
}
```

### Strategy 2: Quality Pullback
```json
{
  "strategy_name": "QualityPullback_V1",
  "entry_long": "spy_trend(20) >= 0 AND earnings_quality() > 0.7 AND norm_rsi(14) < -0.4 AND revenue_cagr(3) > 0.05",
  "exit_long": "norm_rsi(14) > 0.5 OR earnings_quality() < 0.4"
}
```

### Strategy 3: Risk-Off Filter
```json
{
  "strategy_name": "RiskAwareGrowth_V1",
  "entry_long": "spy_trend(20) >= 0 AND risk_change_intensity() < 0.2 AND revenue_cagr(3) > 0.10 AND bb_position(20, 2.0) < 0.0",
  "exit_long": "risk_change_intensity() > 0.5 OR bb_position(20, 2.0) > 0.8"
}
```

---

## Success Metrics

### Phase 1 (Plumbing) Success Criteria
- [ ] Market data pipeline runs 48+ hours without crashes
- [ ] EDGAR integration fetches data for 500+ symbols
- [ ] Fundamental signals calculate without look-ahead bias
- [ ] SPY/VIX filters match reference calculations

### Phase 2 (Evolution) Success Criteria
- [ ] Evolution generates 100+ unique strategies
- [ ] Top 10 strategies have Sharpe > 1.0 out-of-sample
- [ ] Regime testing shows robustness (4/5 regimes profitable)
- [ ] No strategy relies solely on fundamental or technical signals

### Phase 3 (Live) Success Criteria
- [ ] 30-day shadow trading with < 5% deviation from backtest
- [ ] Live trading execution within 0.1% of expected prices
- [ ] Kill switches trigger correctly on drawdown events
- [ ] Positive risk-adjusted returns over 3 months

---

## Open Questions & Decisions

1. **Broker Choice:** Alpaca (free, API-native) vs IBKR (professional, more markets)?
2. **Holding Period:** Pure swing (2-10 days) or include position trades (weeks)?
3. **Shorting:** Enable short strategies or long-only initially?
4. **Options:** Add options primitives for hedging/income?
5. **Market Cap Tier:** Include small-caps (more alpha, more risk) or large-cap only?
6. **Intraday vs Daily:** Start with daily bars or include intraday for timing?

---

## Changelog

| Date | Change | Author |
|------|--------|--------|
| 12/15/2025 12:36 PM PST | Initial planning document created | Claude |

---

## Related Documents

- [Oil-Stonks Main README](../CLAUDE.md) - Universal trading principles
- [Crypto System](../crypto/CRYPTO.md) - Reference implementation
- [SEC EDGAR Agent](../../sec-edgar-agent/README.md) - Fundamental data source
- [Shared Infrastructure](../shared/) - Reusable components
