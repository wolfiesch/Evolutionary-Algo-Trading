# Equities Swing Trading System - Implementation Plan

**Created:** 12/15/2025 12:40 PM PST (via pst-timestamp)
**Status:** Planning Complete, Ready for Phase 0

---

## Strategic Priorities (Impact/Effort Matrix)

### T0: High Impact, Foundation Required
These are blockers - must be completed first.

1. **Market Data Pipeline** - Without price data, nothing works
2. **SPY/VIX Market Filters** - Core safety mechanism
3. **Universe Manager** - Defines what we trade
4. **Backtest Adaptation** - Validate everything before live

### T1: High Impact, Unique Alpha
These leverage your SEC EDGAR competitive advantage.

5. **Insider Activity Primitives** (Form 4) - Strongest signal
6. **Financial Trajectory Primitives** (10-K/10-Q) - Revenue CAGR, margins
7. **Risk Change Detection** - Unique defensive signal
8. **EDGAR Caching Layer** - Performance critical

### T2: Medium Impact, Evolution Quality
These improve strategy generation.

9. **Equities Regime Classifier** - SPY/VIX based
10. **LLM Prompt Engineering** - Fundamental + technical combinations
11. **Walk-Forward Validation** - Prevent overfitting
12. **Sector/Peer Signals** - Relative strength

### T3: Operational Excellence
These are required for production but not alpha-generating.

13. **Shadow Trading Engine** - Paper trading validation
14. **Discord Notifications** - Alerting
15. **Broker Integration** - Live execution
16. **Kill Switches** - Risk management

---

## Phase 0: Foundation (Est. 2-3 days intensive work)

### 0.1 Directory Structure & Configuration
**Priority:** T0 | **Effort:** Low

Create the project skeleton:

```
equities/
├── __init__.py
├── config.py
├── main.py
├── data/
│   ├── __init__.py
│   ├── ingestion/
│   │   ├── __init__.py
│   │   ├── market_data.py      # Yahoo/Polygon client
│   │   ├── edgar_client.py     # SEC EDGAR HTTP client
│   │   └── universe.py         # Universe management
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── repository.py       # SQLite abstraction
│   │   ├── models.py           # Data models
│   │   └── fundamental_cache.py
│   └── quality/
│       ├── __init__.py
│       └── filters.py
├── engine/
│   ├── __init__.py
│   ├── gene_pool/
│   │   ├── __init__.py
│   │   ├── market_filter.py    # spy_trend, vix_regime
│   │   └── fundamental.py      # EDGAR-derived primitives
│   └── strategy_logic/
│       ├── __init__.py
│       └── parser.py           # Extended primitive registry
├── execution/
│   ├── __init__.py
│   ├── shadow/
│   │   ├── __init__.py
│   │   ├── trader.py
│   │   └── pool_manager.py
│   └── live/
│       ├── __init__.py
│       └── broker.py
├── tests/
│   ├── __init__.py
│   ├── conftest.py             # Pytest fixtures
│   ├── test_market_filter.py
│   ├── test_fundamental.py
│   └── test_backtest.py
├── logs/
└── docs/
    └── plans/
```

**Tasks:**
- [ ] Create directory structure
- [ ] Create config.py with equities-specific settings
- [ ] Create __init__.py files
- [ ] Set up pytest configuration

### 0.2 Market Data Ingestion
**Priority:** T0 | **Effort:** Medium

Implement daily OHLCV data fetching:

```python
# equities/data/ingestion/market_data.py

class MarketDataClient:
    """
    Fetches daily OHLCV data from Yahoo Finance (free) or Polygon (paid).
    """

    async def fetch_daily_bars(
        self,
        symbol: str,
        start_date: date,
        end_date: date
    ) -> pd.DataFrame:
        """
        Returns DataFrame with columns:
        date, open, high, low, close, volume, adj_close
        """
        pass

    async def fetch_spy_bars(self, days: int = 252) -> pd.DataFrame:
        """Fetch SPY data for market filter."""
        pass

    async def fetch_vix_bars(self, days: int = 252) -> pd.DataFrame:
        """Fetch VIX data for volatility regime."""
        pass

    async def bulk_fetch(
        self,
        symbols: list[str],
        start_date: date,
        end_date: date
    ) -> dict[str, pd.DataFrame]:
        """Parallel fetch for multiple symbols."""
        pass
```

**Implementation Options:**
1. **yfinance** (free, rate-limited, good for development)
2. **Polygon.io** (paid, reliable, production-ready)
3. **Alpaca** (free with account, limited history)

**Tasks:**
- [ ] Implement yfinance client for development
- [ ] Add rate limiting (5 req/sec for yfinance)
- [ ] Implement bulk fetcher with async parallelism
- [ ] Add retry logic for transient failures
- [ ] Write unit tests with mocked responses

### 0.3 SQLite Repository
**Priority:** T0 | **Effort:** Medium

Set up data storage:

```python
# equities/data/storage/repository.py

class EquitiesRepository:
    """SQLite storage for equities data."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_schema()

    def save_daily_candles(self, symbol: str, candles: pd.DataFrame) -> None:
        pass

    def get_daily_candles(
        self,
        symbol: str,
        start_date: date,
        end_date: date
    ) -> pd.DataFrame:
        pass

    def get_latest_candles(
        self,
        symbol: str,
        count: int
    ) -> pd.DataFrame:
        """Get most recent N candles for indicator calculation."""
        pass

    def save_fundamental_signal(
        self,
        symbol: str,
        signal_type: str,
        signal_value: float,
        signal_date: date
    ) -> None:
        pass

    def get_fundamental_signal(
        self,
        symbol: str,
        signal_type: str,
        as_of_date: date
    ) -> Optional[float]:
        """Point-in-time signal lookup (no look-ahead bias)."""
        pass
```

**Tasks:**
- [ ] Create SQLite schema (see EQUITIES.md)
- [ ] Implement repository class
- [ ] Add indexes for common queries
- [ ] Implement point-in-time queries (critical for backtesting)
- [ ] Write unit tests

### 0.4 Universe Manager
**Priority:** T0 | **Effort:** Medium

Define tradable universe:

```python
# equities/data/ingestion/universe.py

class UniverseManager:
    """Manages the tradable stock universe."""

    FILTERS = {
        "min_market_cap": 1e9,      # $1B minimum
        "min_avg_volume": 10e6,     # $10M ADV minimum
        "min_price": 10.0,          # No penny stocks
        "exchanges": ["NYSE", "NASDAQ", "AMEX"],
        "exclude_etfs": True,
        "require_edgar": True,
    }

    def __init__(self, market_client: MarketDataClient):
        self.market_client = market_client

    async def refresh_universe(self) -> list[str]:
        """
        Fetch and filter universe. Run weekly.
        Returns list of tradable symbols.
        """
        pass

    async def get_universe(self) -> list[str]:
        """Get current universe (cached)."""
        pass

    def get_sector_breakdown(self) -> dict[str, list[str]]:
        """Group universe by sector for diversification."""
        pass
```

**Data Sources for Universe:**
1. **Finviz** - Free screener, good for development
2. **SEC EDGAR** - Get all companies with recent filings
3. **Polygon** - Ticker list with metadata

**Tasks:**
- [ ] Implement universe fetcher
- [ ] Add sector classification
- [ ] Store universe in JSON with metadata
- [ ] Weekly refresh job
- [ ] Initial universe: ~200-500 stocks

### 0.5 SPY/VIX Market Filters
**Priority:** T0 | **Effort:** Low

Implement market regime filters:

```python
# equities/engine/gene_pool/market_filter.py

def spy_trend(spy_candles: pd.DataFrame, period: int) -> float:
    """
    Market filter based on SPY trend.

    Logic (same as btc_trend):
    1. Price >= 98% of long EMA
    2. Short EMA > Long EMA

    Returns:
        +1.0 if both conditions met (uptrend)
        -1.0 otherwise (defensive)
    """
    if len(spy_candles) < period + 10:
        return -1.0  # Conservative default

    close = spy_candles["close"]
    long_ema = close.ewm(span=period, adjust=False).mean()
    short_ema = close.ewm(span=period // 2, adjust=False).mean()

    current_price = close.iloc[-1]
    current_long_ema = long_ema.iloc[-1]
    current_short_ema = short_ema.iloc[-1]

    # Two conditions for uptrend
    price_above_ema = current_price >= 0.98 * current_long_ema
    short_above_long = current_short_ema > current_long_ema

    if price_above_ema and short_above_long:
        return 1.0
    return -1.0


def vix_regime(vix_candles: pd.DataFrame, period: int) -> float:
    """
    Volatility regime based on VIX level.

    Returns:
        +1.0 if VIX < 15 (low vol, risk-on)
        0.0 if VIX 15-25 (normal)
        -1.0 if VIX > 25 (high vol, risk-off)
    """
    if len(vix_candles) < period:
        return 0.0  # Neutral default

    # Use SMA of VIX for smoothing
    vix_sma = vix_candles["close"].rolling(period).mean().iloc[-1]

    if vix_sma < 15:
        return 1.0
    elif vix_sma > 25:
        return -1.0
    return 0.0
```

**Tasks:**
- [ ] Implement spy_trend primitive
- [ ] Implement vix_regime primitive
- [ ] Write unit tests with market regime fixtures
- [ ] Validate against historical SPY/VIX data

---

## Phase 1: EDGAR Integration (Est. 3-4 days)

### 1.1 EDGAR HTTP Client
**Priority:** T1 | **Effort:** Medium

Create HTTP client for SEC EDGAR agent:

```python
# equities/data/ingestion/edgar_client.py

class EdgarClient:
    """HTTP client for SEC EDGAR agent API."""

    def __init__(
        self,
        base_url: str = "http://localhost:8000/api/v1",
        timeout: float = 30.0
    ):
        self.base_url = base_url
        self.timeout = timeout
        self.session = None

    async def get_insider_trades(
        self,
        ticker: str,
        days: int = 90
    ) -> list[dict]:
        """
        Fetch Form 4 insider transactions.

        Returns list of:
        {
            "insider_name": str,
            "title": str,
            "transaction_date": str,
            "transaction_type": "buy" | "sell",
            "shares": int,
            "price_per_share": float,
            "shares_owned_after": int
        }
        """
        pass

    async def get_financials(
        self,
        ticker: str,
        form_type: str = "10-K",  # or "10-Q"
        years: int = 3
    ) -> dict:
        """
        Fetch income statement, balance sheet, cash flow.

        Returns structured financial data.
        """
        pass

    async def get_risk_changes(
        self,
        ticker: str,
        year1: int,
        year2: int
    ) -> dict:
        """
        Detect risk factor changes between filings.

        Returns:
        {
            "new_risks": list[str],
            "removed_risks": list[str],
            "modified_risks": list[str],
            "change_percentage": float
        }
        """
        pass

    async def get_company_info(self, ticker: str) -> dict:
        """Get CIK, SIC code, sector, etc."""
        pass
```

**Tasks:**
- [ ] Implement async HTTP client with aiohttp
- [ ] Add retry logic with exponential backoff
- [ ] Handle API errors gracefully
- [ ] Add request caching (30-min TTL)
- [ ] Write integration tests

### 1.2 Fundamental Signal Cache
**Priority:** T1 | **Effort:** Medium

Cache EDGAR data to avoid repeated API calls:

```python
# equities/data/storage/fundamental_cache.py

class FundamentalCache:
    """
    Caches EDGAR-derived fundamental signals.

    Purpose:
    1. Reduce API calls to EDGAR agent
    2. Enable point-in-time backtesting
    3. Pre-compute expensive calculations
    """

    TTL = {
        "insider_trades": timedelta(hours=24),
        "financials": timedelta(days=7),
        "risk_changes": timedelta(days=7),
        "company_info": timedelta(days=30),
    }

    def __init__(
        self,
        repository: EquitiesRepository,
        edgar_client: EdgarClient
    ):
        self.repository = repository
        self.edgar_client = edgar_client

    async def get_insider_buy_intensity(
        self,
        symbol: str,
        days: int,
        as_of_date: date
    ) -> float:
        """
        Calculate and cache insider buy intensity.

        Point-in-time: only considers filings before as_of_date.
        """
        pass

    async def get_revenue_cagr(
        self,
        symbol: str,
        years: int,
        as_of_date: date
    ) -> float:
        """
        Calculate revenue CAGR from cached financials.
        """
        pass

    async def refresh_cache(self, symbols: list[str]) -> None:
        """Daily job to refresh fundamental signals."""
        pass
```

**Tasks:**
- [ ] Implement cache layer
- [ ] Add point-in-time query support (critical!)
- [ ] Implement daily refresh job
- [ ] Add cache invalidation logic
- [ ] Monitor cache hit rates

### 1.3 Insider Activity Primitives
**Priority:** T1 | **Effort:** Medium

The highest-alpha fundamental signals:

```python
# equities/engine/gene_pool/fundamental.py

def insider_buy_intensity(
    symbol: str,
    days: int,
    cache: FundamentalCache,
    as_of_date: date
) -> float:
    """
    Measures insider buying activity intensity.

    Formula: buy_transactions / total_transactions over N days

    Returns:
        0.0 to 1.0 (higher = more buying)
        0.0 if no transactions
    """
    trades = cache.get_insider_trades(symbol, days, as_of_date)

    if not trades:
        return 0.0

    buys = sum(1 for t in trades if t["transaction_type"] == "buy")
    total = len(trades)

    return buys / total


def insider_net_sentiment(
    symbol: str,
    days: int,
    cache: FundamentalCache,
    as_of_date: date
) -> float:
    """
    Net insider sentiment based on dollar values.

    Formula: (buy_value - sell_value) / (buy_value + sell_value)

    Returns:
        -1.0 to +1.0 (positive = net buying)
    """
    trades = cache.get_insider_trades(symbol, days, as_of_date)

    if not trades:
        return 0.0

    buy_value = sum(
        t["shares"] * t["price_per_share"]
        for t in trades if t["transaction_type"] == "buy"
    )
    sell_value = sum(
        t["shares"] * t["price_per_share"]
        for t in trades if t["transaction_type"] == "sell"
    )

    total_value = buy_value + sell_value
    if total_value == 0:
        return 0.0

    return (buy_value - sell_value) / total_value


def insider_cluster_signal(
    symbol: str,
    days: int,
    min_insiders: int,
    cache: FundamentalCache,
    as_of_date: date
) -> float:
    """
    Detects cluster buying (multiple insiders buying in window).

    Returns:
        1.0 if >= min_insiders bought in the window
        0.0 otherwise

    This is the strongest insider signal - when 2+ insiders
    independently decide to buy, it's highly bullish.
    """
    trades = cache.get_insider_trades(symbol, days, as_of_date)

    buyers = set(
        t["insider_name"]
        for t in trades if t["transaction_type"] == "buy"
    )

    if len(buyers) >= min_insiders:
        return 1.0
    return 0.0
```

**Tasks:**
- [ ] Implement insider_buy_intensity
- [ ] Implement insider_net_sentiment
- [ ] Implement insider_cluster_signal
- [ ] Add edge cases (no trades, missing prices)
- [ ] Write comprehensive unit tests
- [ ] Backtest against historical data

### 1.4 Financial Trajectory Primitives
**Priority:** T1 | **Effort:** Medium

```python
def revenue_cagr(
    symbol: str,
    years: int,
    cache: FundamentalCache,
    as_of_date: date
) -> float:
    """
    Revenue Compound Annual Growth Rate.

    Returns:
        Continuous value, capped at [-0.5, +0.5]
        0.0 if insufficient data
    """
    financials = cache.get_financials(symbol, years, as_of_date)

    if not financials or len(financials) < 2:
        return 0.0

    revenues = [f["revenue"] for f in financials if f.get("revenue")]
    if len(revenues) < 2:
        return 0.0

    # CAGR formula: (end/start)^(1/years) - 1
    start_rev = revenues[-1]  # Oldest
    end_rev = revenues[0]     # Most recent

    if start_rev <= 0:
        return 0.0

    cagr = (end_rev / start_rev) ** (1 / years) - 1

    # Cap at ±0.5 for normalization
    return max(-0.5, min(0.5, cagr))


def earnings_quality(
    symbol: str,
    cache: FundamentalCache,
    as_of_date: date
) -> float:
    """
    Earnings quality: Net Income / Operating Cash Flow.

    High quality = earnings backed by real cash flow.
    Low quality = accounting profits without cash.

    Returns:
        0.0 to 1.0 (higher = better quality)
    """
    financials = cache.get_financials(symbol, 1, as_of_date)

    if not financials:
        return 0.5  # Neutral default

    net_income = financials[0].get("net_income", 0)
    operating_cf = financials[0].get("operating_cash_flow", 0)

    if operating_cf <= 0:
        return 0.0  # Red flag if negative OCF

    # Ratio capped at 1.0
    ratio = min(1.0, net_income / operating_cf) if operating_cf > 0 else 0.0

    return max(0.0, ratio)


def margin_trend(
    symbol: str,
    quarters: int,
    cache: FundamentalCache,
    as_of_date: date
) -> float:
    """
    Gross margin trend over N quarters.

    Returns:
        -1.0 to +1.0 (positive = expanding margins)
    """
    financials = cache.get_financials(symbol, quarters // 4 + 1, as_of_date)

    if not financials or len(financials) < 2:
        return 0.0

    margins = []
    for f in financials:
        revenue = f.get("revenue", 0)
        gross_profit = f.get("gross_profit", 0)
        if revenue > 0:
            margins.append(gross_profit / revenue)

    if len(margins) < 2:
        return 0.0

    # Compare recent to historical average
    recent_margin = margins[0]
    avg_margin = sum(margins[1:]) / len(margins[1:])

    if avg_margin == 0:
        return 0.0

    # Percentage change, capped at ±100%
    change = (recent_margin - avg_margin) / avg_margin
    return max(-1.0, min(1.0, change))
```

**Tasks:**
- [ ] Implement revenue_cagr
- [ ] Implement earnings_quality
- [ ] Implement margin_trend
- [ ] Add leverage_change primitive
- [ ] Handle missing data gracefully
- [ ] Write unit tests

### 1.5 Risk Change Detection
**Priority:** T1 | **Effort:** Medium

```python
def risk_change_intensity(
    symbol: str,
    cache: FundamentalCache,
    as_of_date: date
) -> float:
    """
    Percentage of risk factors that changed between filings.

    High intensity = company is disclosing new/changed risks.
    Can be bearish (new problems) or just uncertainty.

    Returns:
        0.0 to 1.0 (higher = more change)
    """
    risk_data = cache.get_risk_changes(symbol, as_of_date)

    if not risk_data:
        return 0.0

    new_risks = len(risk_data.get("new_risks", []))
    modified_risks = len(risk_data.get("modified_risks", []))
    removed_risks = len(risk_data.get("removed_risks", []))
    total_risks = risk_data.get("total_risks", 1)

    # Weight: new risks are more significant than modifications
    change_score = (new_risks * 1.0 + modified_risks * 0.5 + removed_risks * 0.3) / total_risks

    return min(1.0, change_score)
```

**Tasks:**
- [ ] Implement risk_change_intensity
- [ ] Test with known 10-K comparisons
- [ ] Consider adding specific risk type filters

---

## Phase 2: Backtesting (Est. 2-3 days)

### 2.1 Equities Backtest Adaptation
**Priority:** T0 | **Effort:** Medium

Adapt shared backtester for equities:

```python
# equities/evolution/backtester/config.py

EQUITIES_BACKTEST_CONFIG = BacktestConfig(
    initial_equity=100_000,
    friction_per_side=0.0003,   # 0.03% (lower than crypto)
    max_position_pct=0.05,     # 5% (more diversified)
    risk_per_trade=0.01,
    max_open_positions=20,      # More positions
    max_total_exposure=0.80,
    stop_loss_pct=0.05,         # 5% stop (wider than crypto)
    min_position_interval_bars=1,  # Daily bars
)
```

**Key Differences from Crypto:**
1. Lower friction (0.03% vs 0.25%)
2. More positions (20 vs 5)
3. Wider stops (daily volatility)
4. Daily bars (not 1-min)

**Tasks:**
- [ ] Create equities-specific backtest config
- [ ] Adjust warmup period for daily bars
- [ ] Handle market hours (no overnight gaps in crypto)
- [ ] Add fundamental signal injection to evaluator

### 2.2 Equities Regime Classifier
**Priority:** T2 | **Effort:** Low

```python
# equities/evolution/fitness/regime_classifier.py

def classify_equity_regime(
    spy_candles: pd.DataFrame,
    vix_candles: pd.DataFrame,
    window: int = 20
) -> str:
    """
    Classify market regime for equities.

    Regimes:
    - bull_calm: SPY uptrend, VIX < 20
    - bull_volatile: SPY uptrend, VIX >= 20
    - bear_calm: SPY downtrend, VIX < 25
    - bear_volatile: SPY downtrend, VIX >= 25
    - sideways: SPY range-bound
    """
    # SPY trend
    spy_return = (
        spy_candles["close"].iloc[-1] /
        spy_candles["close"].iloc[-window] - 1
    )

    # VIX level
    vix_level = vix_candles["close"].iloc[-1]

    # Classify
    if abs(spy_return) < 0.02:  # < 2% move
        return "sideways"
    elif spy_return > 0:
        if vix_level < 20:
            return "bull_calm"
        else:
            return "bull_volatile"
    else:
        if vix_level < 25:
            return "bear_calm"
        else:
            return "bear_volatile"
```

**Tasks:**
- [ ] Implement regime classifier
- [ ] Create historical regime labels for backtest data
- [ ] Validate regime distribution (should have all 5)

### 2.3 Historical Data Preparation
**Priority:** T0 | **Effort:** Medium

Prepare multi-year backtest dataset:

**Tasks:**
- [ ] Download 5 years of daily data for universe (500 stocks)
- [ ] Download SPY/VIX history
- [ ] Backfill fundamental signals (point-in-time)
- [ ] Handle stock splits/dividends (use adjusted prices)
- [ ] Handle delistings (survivorship bias)
- [ ] Store in SQLite with proper indexes

---

## Phase 3: Evolution (Est. 3-4 days)

### 3.1 Equities LLM Prompts
**Priority:** T2 | **Effort:** Medium

Customize LLM prompts for fundamental + technical:

```python
# equities/evolution/mutator/prompts.py

EQUITIES_SYSTEM_PROMPT = """
You are an expert quantitative analyst designing swing trading strategies
for US equities. You combine technical analysis with SEC EDGAR fundamental
data to find alpha.

AVAILABLE PRIMITIVES:

Technical (timing):
- ema_trend(fast, slow): +1.0 uptrend, -1.0 downtrend
- norm_rsi(period): -1.0 oversold to +1.0 overbought
- bb_position(period, std): position in Bollinger Bands
- volume_intensity(period, threshold): volume spike detection
- atr_percentile(period, lookback): volatility ranking

Market Filters (regime):
- spy_trend(period): +1.0 bull market, -1.0 bear market
- vix_regime(period): +1.0 calm, 0.0 normal, -1.0 fearful

Fundamental (EDGAR-derived):
- insider_buy_intensity(days): 0.0 to 1.0, higher = more insider buying
- insider_cluster_signal(days, min_insiders): 1.0 if cluster detected
- revenue_cagr(years): revenue growth rate, -0.5 to +0.5
- earnings_quality(): 0.0 to 1.0, earnings backed by cash flow
- margin_trend(quarters): -1.0 to +1.0, margin expansion/contraction
- risk_change_intensity(): 0.0 to 1.0, new risks in filings

RULES:
1. ALWAYS include spy_trend or vix_regime as first filter
2. Combine at least one fundamental AND one technical primitive
3. Maximum 5 primitives per strategy
4. Use integer parameters only (9, 14, 20, 21, 50)
5. Entry conditions should be specific, exits can be simpler

GOOD STRATEGY PATTERNS:
- "Insider momentum": insider_buy_intensity + ema_trend confirmation
- "Quality pullback": earnings_quality filter + RSI oversold + trend
- "Growth breakout": revenue_cagr filter + breakout confirmation
- "Risk-off avoidance": low risk_change_intensity + momentum

BAD PATTERNS TO AVOID:
- Pure fundamental (no timing signal)
- Pure technical (ignoring fundamental edge)
- Too many conditions (overfitting)
- Conflicting signals (RSI oversold AND overbought)
"""
```

**Tasks:**
- [ ] Create equities-specific system prompt
- [ ] Create mutation prompt with fundamental primitives
- [ ] Create crossover prompt for combining strategies
- [ ] Test prompt quality with sample generations

### 3.2 Evolution Configuration
**Priority:** T2 | **Effort:** Low

```python
# equities/evolution/config.py

EQUITIES_EVOLUTION_CONFIG = EvolutionConfig(
    population_size=20,          # Larger than crypto
    generations=50,              # More iterations
    elite_count=3,
    mutation_rate=0.6,
    crossover_rate=0.4,
    tournament_size=4,
    max_stagnation=10,
    checkpoint_interval=5,
    min_trades=20,               # Lower bar (daily trading)
    target_trades=60,            # ~1 trade every 4 days average
)
```

**Tasks:**
- [ ] Configure evolution parameters
- [ ] Set up checkpointing
- [ ] Configure multi-processing for parallel backtests

### 3.3 Walk-Forward Validation
**Priority:** T2 | **Effort:** Medium

Prevent overfitting with rolling validation:

```python
def walk_forward_validate(
    strategy: Strategy,
    full_data: pd.DataFrame,
    train_months: int = 12,
    test_months: int = 3,
    step_months: int = 3
) -> list[BacktestResults]:
    """
    Rolling train/test validation.

    Example with 5 years of data:
    - Train: Jan 2020 - Dec 2020, Test: Jan 2021 - Mar 2021
    - Train: Apr 2020 - Mar 2021, Test: Apr 2021 - Jun 2021
    - ... continues ...

    Returns results for each test period.
    """
    pass
```

**Tasks:**
- [ ] Implement walk-forward validator
- [ ] Create summary metrics across periods
- [ ] Add consistency scoring (stable performance = better)

---

## Phase 4: Shadow Trading (Est. 2-3 days)

### 4.1 Paper Trading Engine
**Priority:** T3 | **Effort:** Medium

Shadow trade top strategies:

```python
# equities/execution/shadow/trader.py

class EquitiesShadowTrader:
    """
    Paper trading engine for strategy validation.

    Runs during market hours, generates signals,
    logs hypothetical trades.
    """

    def __init__(
        self,
        strategies: list[Strategy],
        market_client: MarketDataClient,
        cache: FundamentalCache,
        repository: EquitiesRepository
    ):
        pass

    async def run_daily_scan(self) -> list[Signal]:
        """
        Run at market close (4:00 PM ET):
        1. Fetch latest prices for universe
        2. Update fundamental cache
        3. Evaluate all strategies on all symbols
        4. Log signals and hypothetical trades
        """
        pass
```

**Tasks:**
- [ ] Implement shadow trader
- [ ] Add Discord webhook for signals
- [ ] Create daily summary report
- [ ] Track hypothetical P&L

### 4.2 Validation Period
**Priority:** T3 | **Effort:** Low

Minimum 7-day shadow trading before live:

**Validation Criteria:**
- [ ] Signal generation matches backtest frequency (within 50%)
- [ ] No crashes or data issues
- [ ] P&L tracking within expected range
- [ ] Fundamental cache refresh working

---

## Phase 5: Live Trading (Future)

### 5.1 Broker Integration
**Priority:** T3 | **Effort:** High

**Options:**
1. **Alpaca** - Free, API-native, paper + live
2. **Interactive Brokers** - Professional, more markets
3. **TD Ameritrade** - Good API, being migrated to Schwab

**Tasks:**
- [ ] Implement broker abstraction layer
- [ ] Add Alpaca integration first
- [ ] Order management (limit orders, stops)
- [ ] Position tracking
- [ ] P&L calculation

### 5.2 Kill Switches
**Priority:** T3 | **Effort:** Medium

Same framework as crypto:

```python
EQUITIES_KILL_SWITCHES = {
    "daily_drawdown": 0.03,      # 3% daily max
    "weekly_drawdown": 0.07,     # 7% weekly max
    "peak_drawdown": 0.15,       # 15% from peak
    "single_position_loss": 0.05,  # 5% per position
}
```

---

## Open Decisions

### Decision 1: Market Data Provider
**Options:**
| Provider | Cost | Pros | Cons |
|----------|------|------|------|
| Yahoo Finance | Free | Easy, no auth | Rate limits, unreliable |
| Polygon.io | $29/mo | Reliable, fast | Cost |
| Alpaca | Free | Broker integration | Limited history |
| Alpha Vantage | Free tier | Simple API | 5 calls/min limit |

**Recommendation:** Start with Yahoo Finance for development, migrate to Polygon for production.

### Decision 2: Holding Period
**Options:**
| Style | Holding | Pros | Cons |
|-------|---------|------|------|
| Day Trading | < 1 day | More signals | PDT rule, higher friction |
| Swing Trading | 2-10 days | EDGAR signals matter | Overnight risk |
| Position Trading | Weeks+ | Fundamental thesis plays out | Fewer opportunities |

**Recommendation:** Swing trading (2-10 days) - balances fundamental signal relevance with trade frequency.

### Decision 3: Short Selling
**Options:**
- Long-only: Simpler, lower risk, most retail-friendly
- Long/Short: More opportunities, hedge capability, complex

**Recommendation:** Start long-only, add shorting in v2.

### Decision 4: Universe Size
**Options:**
| Size | Pros | Cons |
|------|------|------|
| 50 stocks | Fast backtest, concentrated alpha | Limited opportunities |
| 200 stocks | Balance | Manual curation needed |
| 500+ stocks | Maximum opportunities | Compute heavy, noise |

**Recommendation:** Start with 200, expand to 500 once pipeline is stable.

---

## Execution Timeline

**Aggressive Timeline (2 weeks intensive):**

```
Week 1:
  Day 1-2: Phase 0 (Foundation)
  Day 3-4: Phase 1.1-1.2 (EDGAR client, cache)
  Day 5-6: Phase 1.3-1.5 (Fundamental primitives)
  Day 7: Phase 2.1 (Backtest adaptation)

Week 2:
  Day 8: Phase 2.2-2.3 (Regimes, data prep)
  Day 9-10: Phase 3.1-3.2 (LLM prompts, evolution)
  Day 11-12: Phase 3.3 (Walk-forward)
  Day 13-14: Phase 4 (Shadow trading)
```

**Realistic Timeline (3-4 weeks):**
- Phase 0: 3-4 days
- Phase 1: 4-5 days
- Phase 2: 3-4 days
- Phase 3: 4-5 days
- Phase 4: 3-4 days
- Phase 5: 5-7 days (future)

---

## Success Criteria Checklist

### Phase 0 Complete When:
- [ ] Market data fetches 500 symbols without errors
- [ ] SPY/VIX filters match reference calculations
- [ ] Universe manager returns 200+ tradable stocks
- [ ] Repository stores/retrieves candles correctly

### Phase 1 Complete When:
- [x] EDGAR client fetches insider trades for any ticker
- [x] Fundamental cache has 24h+ uptime (cache layer implemented with TTLs)
- [x] All 6 fundamental primitives implemented and tested (49 tests passing)
- [x] No look-ahead bias in point-in-time queries (repository supports this)

### Phase 2 Complete When:
- [ ] Backtest runs on 5 years of data
- [ ] Regime classifier labels all periods
- [ ] Walk-forward shows consistent results

### Phase 3 Complete When:
- [ ] Evolution generates 100+ unique strategies
- [ ] Top 10 strategies have Sharpe > 0.8
- [ ] No strategy is pure fundamental or pure technical

### Phase 4 Complete When:
- [ ] Shadow trading runs 7+ days without issues
- [ ] Signal frequency matches backtest expectations
- [ ] Discord alerts working

---

## Changelog

| Timestamp | Change | Author |
|-----------|--------|--------|
| 12/15/2025 12:40 PM PST | Initial implementation plan created | Claude |
| 12/15/2025 09:35 AM PST | Phase 0 complete: market data, repository, filters, universe | Claude |
| 12/15/2025 09:57 AM PST | Phase 1 complete: EDGAR integration (client, primitives, cache, scan job) | Claude |
