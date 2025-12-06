# Crypto Alpha Generation System - Design Document

**Created:** 2025-12-04
**Status:** Approved for Development
**Author:** Wolfgang Schoenberger + Claude
**Reviewed By:** Gemini (Senior Quant Simulation)

---

## 1. Executive Summary

A systematic trading system for mid-cap cryptocurrency that uses LLM-driven evolutionary search to discover and optimize trading strategies. The system prioritizes **robustness over returns** through regime testing, shadow trading validation, and strict risk controls.

**Key Characteristics:**
- **Universe:** Mid-cap crypto (Top 50-200 by market cap)
- **Timeframe:** Minutes to hours (high frequency for crypto)
- **Strategy Discovery:** ProFiT-style evolution with constrained Gene Pool
- **Execution:** Shadow trading on real order books, then live
- **Risk Posture:** Long-only, 50% max exposure, survival-first

**Timeline:**
- Phase 1-2 (Weeks 1-4): Build system
- Phase 3 (Weeks 5-8): Shadow trading validation
- Phase 4 (Month 3+): Live trading with real capital

---

## 2. Strategic Rationale

### 2.1 Why Crypto Mid-Caps?

| Factor | Advantage |
|--------|-----------|
| **24/7 Markets** | More data, no overnight gaps |
| **High Volatility** | More signal to capture |
| **Retail Dominated** | Less efficient, more alpha potential |
| **No Fundamentals** | Pure technical analysis playground |
| **Capital Flexibility** | Can trade where big funds can't |

### 2.2 Why Evolutionary Strategy Discovery?

Traditional approach: Human designs strategy → backtest → deploy
Our approach: LLM proposes strategies → backtest → evolve → validate → deploy

**Benefits:**
- Discovers patterns humans wouldn't think of
- Adapts as market conditions change
- Removes emotional attachment to strategies
- Systematic, reproducible process

### 2.3 Why Long-Only (Phase 1)?

Shorting mid-cap crypto carries asymmetric risk:
- Long max loss: 100% of position (coin goes to zero)
- Short max loss: **Unlimited** (200%, 500%, 1000% pumps happen)

**Decision:** Long-only for first 3 months. Master the upside before fighting pumps.

---

## 3. System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         CRYPTO ALPHA SYSTEM                                  │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Data Ingestion │────▶│ Strategy Engine │────▶│ Shadow Executor │
│  (WebSocket)    │     │ (Gene Pool)     │     │ (Real Order Book)│
└─────────────────┘     └─────────────────┘     └─────────────────┘
         │                      │                        │
         ▼                      ▼                        ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│ Data Quality    │     │    Evolution    │     │   Kill Switch   │
│ Filter          │     │ (LLM + Backtest)│     │ (Watchdog)      │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

---

## 4. Data Infrastructure

### 4.1 Exchange Selection: Bybit

| Factor | Bybit | Binance |
|--------|-------|---------|
| **US Access** | Works | Restricted |
| **API Quality** | Excellent | Good but complex |
| **Mid-cap Selection** | 200+ altcoins | More, but US restrictions |
| **Fees** | 0.1% maker/taker | Similar |

### 4.2 Data Collection

**Live Data (WebSocket):**
- OHLCV candles: 1m, 5m, 15m intervals
- Trade stream for order book simulation
- Funding rates (useful signal)

**Storage:** SQLite for MVP, PostgreSQL for scale

### 4.3 Coin Universe

**Criteria:**
- Daily volume > $10M
- Listed > 3 months (enough history)
- Not stablecoins or wrapped assets
- Perpetual futures (more liquid than spot)

**Initial Universe:** 30-50 coins meeting criteria

### 4.4 Data Quality Filters

```python
def validate_candle(candle, prev_candle):
    # Flash crash detection
    if abs(candle.close / prev_candle.close - 1) > 0.50:
        return False  # 50% move in one candle = bad data

    # Missing data detection
    if candle.volume == 0:
        return False

    return True
```

**Cost:** Zero. Bybit API is free. Historical data is free.

---

## 5. Gene Pool (Safe Primitives)

The LLM does NOT write arbitrary code. It assembles pre-validated building blocks.

### 5.1 Design Principles

1. **State-based, not Event-based** — Signals persist, don't flash for one candle
2. **Normalized outputs** — All primitives return -1.0 to +1.0 (or bounded)
3. **Integer parameters only** — No hyper-tuning (14, not 14.231)
4. **Max 5 primitives per strategy** — Complexity limit prevents overfitting

### 5.2 Primitive Library

```python
# ═══════════════════════════════════════════════════════════
# TREND (State-based)
# ═══════════════════════════════════════════════════════════
def ema_trend(fast: int, slow: int) -> float:
    """Returns +1.0 (fast > slow), -1.0 (fast < slow)"""
    pass

def price_position(period: int) -> float:
    """Returns (Price - EMA) / ATR, capped at ±3.0"""
    pass

# ═══════════════════════════════════════════════════════════
# MEAN REVERSION (Normalized)
# ═══════════════════════════════════════════════════════════
def norm_rsi(period: int) -> float:
    """Returns (RSI - 50) / 50, range -1.0 to +1.0"""
    pass

def bb_position(period: int, std: float) -> float:
    """Returns position within Bollinger Bands, -1.0 to +1.0"""
    pass

def bb_width_percentile(period: int) -> float:
    """Returns band width vs history, 0.0 to 1.0"""
    pass

# ═══════════════════════════════════════════════════════════
# VOLUME (Regime-based)
# ═══════════════════════════════════════════════════════════
def volume_intensity(period: int, threshold: float) -> float:
    """Returns 1.0 if volume > threshold * avg, else 0.0"""
    pass

def vwap_distance() -> float:
    """Returns Z-score of price vs VWAP, capped at ±3.0"""
    pass

# ═══════════════════════════════════════════════════════════
# VOLATILITY (Regime classification)
# ═══════════════════════════════════════════════════════════
def atr_regime(period: int) -> float:
    """Returns 1.0 (high vol), 0.0 (normal), -1.0 (low vol)"""
    pass

def atr_percentile(period: int) -> float:
    """Returns current ATR vs historical, 0.0 to 1.0"""
    pass

# ═══════════════════════════════════════════════════════════
# MARKET FILTER (Mandatory for altcoin longs)
# ═══════════════════════════════════════════════════════════
def btc_trend(window: int) -> float:
    """Returns +1.0 (BTC stable/rising), -1.0 (BTC dumping)
    MANDATORY: All Long entries require btc_trend() >= 0"""
    pass
```

### 5.3 Strategy Output Format

```json
{
  "strategy_name": "MeanReversion_Pullback_V1",
  "entry_long": "btc_trend(60) >= 0 AND ema_trend(9,21) == 1.0 AND norm_rsi(14) < -0.4",
  "exit_long": "norm_rsi(14) > 0.6 OR ema_trend(9,21) == -1.0",
  "entry_short": null,
  "exit_short": null
}
```

**Constraints:**
- `btc_trend()` required for all Long entries
- `entry_short` and `exit_short` locked to `null` (Phase 1)
- No position sizing in gene (handled by Risk Engine)

---

## 6. Risk Engine

### 6.1 Position Sizing

**Formula:**
```python
calculated_size = (equity * risk_per_trade) / atr_distance
final_size = min(calculated_size, equity * max_position_pct)
```

**Constraints:**

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Risk per trade | 1% of equity | Single trade can't hurt you |
| Max position | 10% of equity | No concentration risk |
| Max open positions | 5 | Diversification |
| Max exposure | 50% of equity | Always have dry powder |

### 6.2 Kill Switch (Watchdog)

**Runs as separate process**, queries account every 10 seconds.

| Trigger | Action |
|---------|--------|
| Drawdown > 5% in 1 hour | Close all, pause 1 hour |
| Drawdown > 10% in 24 hours | Close all, pause 24 hours |
| Drawdown > 20% from peak | **Full shutdown**, manual restart required |
| Slippage Guard: Position loss > 3% equity | Force close (stop-loss failed) |
| Strategy process unresponsive > 60s | Kill and close all |

### 6.3 Trade Execution Rules

| Rule | Implementation |
|------|----------------|
| Latency buffer | Wait 500ms after signal before checking price |
| Liquidity gate | Reject if 1-min volume < $10k |
| Spread check | Reject if bid-ask spread > 0.5% |
| Friction model | 0.1% fee + 0.15% slippage = 0.25% per side |

### 6.4 Shadow Trader Logging

Every trade (shadow or real) logs full state:

```json
{
  "timestamp": 1701820000,
  "strategy_id": "gen_4_variant_12",
  "coin": "ARB-USDT",
  "signal": "ENTRY_LONG",
  "gene_expression": "ema_trend(9,21)==1.0 AND norm_rsi(14)<-0.4",
  "price_at_signal": 1.2050,
  "price_after_500ms": 1.2055,
  "bid_ask_spread": 0.0012,
  "simulated_fill": 1.2067,
  "stop_loss_price": 1.1850,
  "intended_risk_pct": 0.01,
  "position_size_usdt": 500,
  "btc_trend": 1.0,
  "atr_regime": 0.0,
  "market_regime": "low_volatility_uptrend"
}
```

---

## 7. Evolution Loop

### 7.1 Fitness Function

**Minimum Thresholds (must pass all):**
- Trade count ≥ 100 (backtest + shadow combined)
- Max drawdown < 20%
- Profit factor > 1.0
- **Per-regime Sharpe > 0.6** (no hiding losses in averages) *(updated per X feedback)*

**Composite Score:**
```python
def fitness(results):
    # Hard filters
    if results.trade_count < 100:
        return -999
    if results.max_drawdown > 0.20:
        return -999
    if results.profit_factor < 1.0:
        return -999

    # Regime consistency check (updated: 0.5 → 0.6 per X feedback)
    for regime in REGIMES:
        if results.regime_sharpe[regime] < 0.6:
            return -999  # Bleeding in any regime = kill

    # Weighted score
    score = (
        results.sharpe_ratio * 0.4 +
        results.profit_factor * 0.3 +
        (1 - results.max_drawdown) * 0.2 +
        min(results.trade_count / 200, 1.0) * 0.1
    )
    return score
```

### 7.2 Market Regime Classification

```python
def classify_regime(btc_data, window=168):  # 1 week hourly
    returns = btc_data['close'].pct_change()
    trend = btc_data['close'].iloc[-1] / btc_data['close'].iloc[0] - 1
    volatility = returns.std()

    if trend > 0.05 and volatility < 0.03:
        return "bull_calm"
    elif trend > 0.05:
        return "bull_volatile"
    elif trend < -0.05 and volatility < 0.03:
        return "bear_calm"
    elif trend < -0.05:
        return "bear_volatile"
    else:
        return "sideways"
```

**Requirement:** Strategy must have Sharpe > 0.5 in at least 4 of 5 regimes.

### 7.3 Anti-Overfitting Measures

| Defense | Implementation |
|---------|----------------|
| Regime testing | Profitable in Bull, Bear, AND Sideways |
| Walk-forward validation | Train months 1-3, test month 4, rolling |
| Complexity penalty | Max 5 primitives per strategy |
| Parameter stability | RSI(14) must be similar to RSI(13,15) |
| Out-of-sample holdout | 20% of data never seen during evolution |
| **Incubation purgatory** | 14-day virtual trading before shadow pool *(updated per X feedback)* |

### 7.4 Incubation Process

```
Backtest Pass
     │
     ▼
Incubation Queue (14 days of paper trading)  ← Updated per X feedback
     │
     ▼
Compare: Incubation Sharpe vs Backtest Sharpe
     │
     ├─── If Incubation < 50% of Backtest → DISCARD (overfitted)
     │
     └─── If Incubation ≥ 50% of Backtest → Promote to Shadow Pool
```

### 7.5 Evolution Cycle (Every 48 Hours) ← *Updated per X feedback: "Daily is aggressive"*

```
1. GATHER
   └─ Collect last 48h of shadow trade logs

2. EVALUATE
   └─ Calculate fitness for each active strategy
   └─ Breakdown by regime

3. SELECT
   └─ Keep top 3 strategies (elites, unchanged)

4. MUTATE
   └─ LLM generates 5-7 new variants from top performer
   └─ Constrained to Gene Pool primitives only

5. BACKTEST
   └─ Test variants on 3 months historical
   └─ Walk-forward validation
   └─ Regime testing (must pass 4/5)

6. INCUBATE
   └─ Passing variants enter 14-day incubation
   └─ Compare to backtest expectations

7. DEPLOY
   └─ Survivors join shadow trading pool
   └─ Max 10 active strategies
   └─ Cull bottom performers weekly
```

### 7.6 LLM Mutation Prompt

```
You are a quantitative trading researcher. Given a strategy and its performance, suggest ONE modification.

CURRENT STRATEGY:
- Entry: {entry_expression}
- Exit: {exit_expression}

PERFORMANCE:
- Sharpe: {sharpe}, Profit Factor: {pf}, Max DD: {dd}%, Trades: {n}
- Weak in: {weak_regime} regime (PF: {regime_pf})

AVAILABLE PRIMITIVES (you may ONLY use these):
- ema_trend(fast, slow), price_position(period)
- norm_rsi(period), bb_position(period, std), bb_width_percentile(period)
- volume_intensity(period, threshold), vwap_distance()
- atr_regime(period), atr_percentile(period)
- btc_trend(window)

CONSTRAINTS:
- Max 5 primitives total
- All periods must be integers
- btc_trend() required for entry_long
- Do NOT include position sizing

OUTPUT FORMAT (JSON only):
{
  "strategy_name": "descriptive_name",
  "entry_long": "expression",
  "exit_long": "expression",
  "mutation_rationale": "why this change might help"
}
```

---

## 8. Implementation Roadmap

### Phase 1: Plumbing (Weeks 1-2)

**Goal:** A dumb bot that doesn't crash.

**Deliverables:**
- [ ] WebSocket connection to Bybit
- [ ] Save 1-minute candles to SQLite
- [ ] Implement Gene Pool functions (all primitives)
- [ ] Build Shadow Trader (logs to JSON)
- [ ] Basic data quality filters

**Test:** Hardcode one strategy (e.g., "Buy if RSI < 30"). Run 24 hours. Verify logging and disconnect handling.

### Phase 2: Brain (Weeks 3-4)

**Goal:** The Evolution Loop.

**Deliverables:**
- [ ] Backtester engine
- [ ] Fitness function (Sharpe, PF, regime detection)
- [ ] LLM integration (OpenAI/Anthropic API)
- [ ] Gene expression parser and validator
- [ ] Walk-forward validation framework

**Test:** Can the loop evolve a losing strategy into a winning one on 3 months of historical data?

### Phase 3: Gauntlet (Weeks 5-8)

**Goal:** Statistical validation (no real money).

**Actions:**
- [ ] Turn on system with live WebSocket data
- [ ] Let it evolve and shadow trade
- [ ] Monitor shadow equity curve
- [ ] Fix bugs, tune slippage model
- [ ] Accumulate 100+ trades per top strategy

**Success Criteria:**
- Shadow equity curve trending up
- Max drawdown < 10%
- Profit factor > 1.5 on shadow trades
- Consistent across regime changes

### Phase 4: Live Fire (Month 3+)

**Goal:** Real alpha.

**Actions:**
- [ ] Connect to real exchange API (trade permissions)
- [ ] Start with $500 capital
- [ ] 1% risk per trade = $5 risk
- [ ] Scale only when real-money PF > 1.5 over 100 trades

**Scaling Plan:**
- $500 → $1,000 after first 100 profitable trades
- $1,000 → $2,500 after 200 profitable trades
- Continue doubling until risk tolerance reached

---

## 9. Tech Stack

| Component | Technology | Rationale |
|-----------|------------|-----------|
| Language | Python 3.11+ | Data science ecosystem |
| Data Storage | SQLite → PostgreSQL | Start simple, scale later |
| WebSocket | `websockets` or `ccxt` | Exchange connectivity |
| Technical Analysis | `pandas-ta` | Indicator calculations |
| Backtesting | Custom (lightweight) | Full control over simulation |
| LLM API | Anthropic Claude or OpenAI | Strategy mutation |
| Process Management | `supervisor` or `systemd` | Watchdog process |
| Logging | JSON files → TimescaleDB | Trade state vectors |

---

## 10. Cost Analysis

| Item | Cost | Notes |
|------|------|-------|
| Exchange API | Free | Bybit API is free |
| Historical Data | Free | Bybit provides historical candles |
| LLM API | ~$50-100/month | For evolution mutations |
| Server (optional) | $20-50/month | If running 24/7 off local machine |
| **Total MVP** | **~$50-150/month** | Much cheaper than equities data |

---

## 11. Risk Factors

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Exchange API changes | Medium | High | Abstract exchange layer, monitor announcements |
| Strategy degradation | High | Medium | Continuous evolution, regime monitoring |
| Flash crash losses | Low | High | Kill switch, liquidity gates |
| Overfitting | High | High | Regime testing, incubation, walk-forward |
| LLM hallucination | Medium | Medium | Gene Pool constraint, expression validation |
| Data quality issues | Medium | Medium | Quality filters, anomaly detection |

---

## 12. Success Criteria

### Minimum Viable Success (must achieve):
- [ ] Shadow trading shows positive equity curve over 4 weeks
- [ ] Max drawdown < 15% during shadow phase
- [ ] At least 3 strategies survive incubation
- [ ] System runs stable for 7+ days without manual intervention

### Target Success:
- [ ] Sharpe ratio > 1.5 on shadow trades
- [ ] Profit factor > 2.0
- [ ] Real money profitable after 100 trades
- [ ] Scalable to $5,000+ capital

---

## 13. Design Decisions (Resolved)

*Decisions made during final review to prevent analysis paralysis during build.*

### Q1: Coin Selection — Static or Dynamic?

**Decision:** Static (Top 30 by Volume)

**Rationale:** Dynamic selection introduces survivorship bias (bot picks coins that already pumped). For Phases 1-3:
- Pick Top 30 coins on Bybit Futures by volume
- Exclude stablecoins and wrapped assets
- Lock that list for the duration of validation
- Do NOT let the bot hunt for "new gems" yet

### Q2: Multi-Strategy Allocation — Equal Weight or Fitness-Weighted?

**Decision:** Equal Weight

**Rationale:** Fitness-weighting is complex and prone to overfitting (giving 90% capital to a strategy that had one lucky month).

**Rule:** Every active strategy gets 1 "Unit" of risk. Simple, robust.

### Q3: Correlation Management — What if All Strategies Buy at Once?

**Decision:** Time-Based Throttling

**Rationale:** Calculating real-time correlation matrices is CPU heavy and complex.

**Simple Rule:** Max 1 new position entry per 5 minutes.

If the market pumps and 10 strategies trigger "Buy," the system:
1. Takes the first one
2. Waits 5 minutes
3. Takes the next (if signal still valid)

This prevents buying the exact top of a spike with the whole account.

### Q4: Fee Tier Optimization?

**Decision:** Ignore It

**Rationale:** If your strategy depends on VIP fee tiers to be profitable, it is not robust.

Build for base tier (0.1% maker / 0.06% taker). Any fee reduction later is bonus profit.

---

## 14. Operational Guidelines

*Critical implementation details to get right in Phase 1.*

### 14.1 Data Gap Handling (WebSocket Disconnects)

**Scenario:** Bot disconnects for 5 minutes, then reconnects.

**Risk:** Indicators (EMA, RSI) will be wrong because they missed data.

**Mandatory Fix:**
```python
def on_reconnect():
    # 1. Pause all trading
    trading_enabled = False

    # 2. Fetch last 100 candles via REST to "warm up" indicators
    historical = fetch_historical_candles(symbol, limit=100)

    # 3. Recalculate all indicators from scratch
    recalculate_indicators(historical)

    # 4. Only then resume trading
    trading_enabled = True
```

**Rule:** On ANY reconnect, pause trading, warm up indicators, then resume.

### 14.2 Directory Structure

Don't dump everything in one file. Structure correctly in Week 1 to avoid pain in Month 3.

```
/crypto-alpha/
├── /data/
│   ├── /ingestion/          # WebSocket clients
│   └── /storage/            # SQLite/Parquet handlers
├── /engine/
│   ├── /gene_pool/          # Primitive library (ema_trend, norm_rsi, etc.)
│   └── /strategy_logic/     # JSON parsing to executable code
├── /execution/
│   ├── /shadow/             # Paper trading logic
│   └── /live/               # Bybit API connectors
├── /evolution/
│   ├── /backtester/         # Historical simulation
│   ├── /fitness/            # Sharpe, regime calculations
│   └── /mutator/            # LLM prompts and parsing
├── /risk/
│   └── /watchdog/           # Kill switch (separate process)
├── /logs/
│   ├── trades.log           # Trade state vectors (JSON)
│   └── errors.log           # Exceptions only (see 14.3)
├── main.py
├── config.py
└── requirements.txt
```

### 14.3 Black Swan Error Logging

**Problem:** If `trades.log` is flooded with "Heartbeat received" messages, you'll miss the critical "API Connection Refused" error at 3 AM.

**Solution:** Separate `errors.log` that captures ONLY exceptions.

```python
# In config.py or logging setup
import logging

# Normal operations log
trade_logger = logging.getLogger('trades')
trade_handler = logging.FileHandler('logs/trades.log')
trade_logger.addHandler(trade_handler)

# Errors only log (BLACK SWAN LOG)
error_logger = logging.getLogger('errors')
error_handler = logging.FileHandler('logs/errors.log')
error_handler.setLevel(logging.ERROR)  # Only ERROR and CRITICAL
error_logger.addHandler(error_handler)
```

**Rule:** Check `errors.log` every morning. If it's not empty, something went wrong overnight.

### 14.4 Phase 1 Reality Check

**Phase 1 is the hardest.**

You will:
- Write the WebSocket client, and it will disconnect every 2 hours
- Try to calculate RSI, and it won't match TradingView
- Hit rate limits you didn't expect
- Discover Bybit's API has quirks not in the docs

**This is normal.**

**Critical Rule:** Do NOT try to build the LLM part (Phase 2) until the Data/Shadow part (Phase 1) can run for **48 hours without crashing**.

The "edge" is not in the LLM yet. The edge is in a system that stays online when the market is moving.

---

## Changelog

| Date | Change | Author |
|------|--------|--------|
| 2025-12-04 | Initial design document created | Wolfgang + Claude |
| 2025-12-04 | Gemini review incorporated (Gene Pool v2, Shadow Trading) | Wolfgang + Claude |
| 2025-12-04 | Final approval, incubation purgatory added | Wolfgang + Claude |
| 2025-12-05 | Resolved open questions, added operational guidelines | Wolfgang + Claude |
| 2025-12-05 | Added: data gap handling, directory structure, error logging | Wolfgang + Claude |
| 2025-12-05 | Grok/X community feedback incorporated (Section 15) | Wolfgang + Claude + Grok |
| 2025-12-05 | Updated: incubation 7→14 days, regime Sharpe 0.5→0.6, evolution 24h→48h | Wolfgang + Claude |

---

## 15. Community Feedback (Quant Twitter/X)

*Compiled 2025-12-05 via Grok analysis of hundreds of posts from verified quants, traders, and AI researchers.*

### 15.1 Overall Assessment

> "This is one of the most thoughtful and robust trading system designs I've reviewed in years—especially for a crypto-focused algo... The ProFiT-inspired evolutionary approach is cutting-edge... It's not just hype; it's a systematic way to discover non-obvious edges while mitigating human bias."

**Key Validations:**
- Gene Pool constraints praised: "Limiting to validated primitives prevents LLM hallucinations"
- Risk Engine rated "top-tier" and "fund-level controls"
- Regime testing approach called "elite"
- Incubation purgatory described as "a gem"
- Operational guidelines rated "gold"

### 15.2 Recommended Enhancements (Phase 2+)

Based on X community insights, queue these improvements for after Phase 1 stability:

#### Gene Pool Expansion (Phase 2)
Add crypto-specific primitives that capture unique market dynamics:

```python
# ═══════════════════════════════════════════════════════════
# FUNDING (Crypto-specific edge)
# ═══════════════════════════════════════════════════════════
def funding_rate_percentile(period: int) -> float:
    """Current funding rate vs historical, 0.0 to 1.0
    High funding = crowded longs, reversal risk"""
    pass

# ═══════════════════════════════════════════════════════════
# ORDER FLOW (CVD divergence)
# ═══════════════════════════════════════════════════════════
def order_imbalance(period: int) -> float:
    """Cumulative Volume Delta divergence from price
    Returns -1.0 to +1.0 based on buy/sell pressure"""
    pass
```

**Rationale:** X quants emphasize funding rates as "useful signal" and order flow (CVD divergence) as crypto-native edge.

#### Float Parameters (Phase 2)
Allow constrained float ranges for select primitives with stability checks:

| Primitive | Allowed Range | Stability Check |
|-----------|---------------|-----------------|
| `bb_position(period, std)` | std: 1.5-2.5 | Must pass at 1.5, 2.0, and 2.5 |
| `volume_intensity(period, threshold)` | threshold: 1.5-3.0 | ±0.5 must yield similar results |

#### Regime-Specific Slippage Model (Phase 3)
Current: Flat 0.15% slippage estimate
Enhanced: Use historical Bybit data to model regime-specific slippage:

| Regime | Estimated Slippage |
|--------|-------------------|
| bull_calm | 0.10% |
| bull_volatile | 0.20% |
| bear_calm | 0.12% |
| bear_volatile | 0.25% |
| sideways | 0.10% |

#### Exchange Failover (Phase 3)
Add abstraction layer for exchange redundancy:

```python
class ExchangeRouter:
    """Failover to backup exchange if primary is down."""
    primary: Exchange = Bybit()
    backup: Exchange = Binance()  # via CCXT

    def execute(self, order):
        try:
            return self.primary.execute(order)
        except ExchangeUnavailable:
            log.error("Primary exchange down, failover to backup")
            return self.backup.execute(order)
```

#### Post-Live Evolution Trigger (Phase 4)
Add automatic re-evolution when performance degrades:

```python
def check_strategy_health(strategy_id, lookback_trades=50):
    """Trigger re-evolution if strategy degrades."""
    recent_pf = calculate_profit_factor(last_n_trades=lookback_trades)
    baseline_pf = strategy.shadow_phase_pf

    if recent_pf < baseline_pf * 0.80:  # 20% degradation
        log.warning(f"Strategy {strategy_id} degraded, triggering re-evolution")
        evolution_queue.add(strategy_id, priority="high")
```

### 15.3 Parameter Updates (Incorporated)

Based on community feedback, the following parameters have been updated:

| Parameter | Original | Updated | Source |
|-----------|----------|---------|--------|
| Incubation period | 7 days | **14 days** | "More data for validation" |
| Min per-regime Sharpe | 0.5 | **0.6** | "Bleeding in any regime = kill" |
| Evolution cycle | Daily | **Every 48h** | "Daily is aggressive" |

### 15.4 Community Warnings

| Warning | Our Mitigation |
|---------|----------------|
| "LLMs are biased predictors, need new architectures for consistent alpha" | BTC filter + regime checks add robustness |
| "Retail dominated = traps" | Long-only avoids short squeeze traps |
| "Backtest overfitting ubiquitous" | Walk-forward, OOS holdout, incubation |
| "Phase 1 plumbing takes longer than planned" | 48-hour stability gate before Phase 2 |
| "API quirks not in docs" | Abstract exchange layer, error logging |

### 15.5 Validation from X Community

Key quotes from verified quant accounts:

- **On LLM/Evolutionary approach:** "Papers like 'Evolution Strategies at Scale' (outperforms RL) and ProFiT are hyped—constrained gene pool mirrors this best practice."

- **On regime testing:** "Profitable in bull/bear/sideways = real edge" — Matches our 4/5 regime requirement.

- **On risk controls:** "Kill switches for flash crashes, position sizing via ATR" — Our watchdog process implements exactly this.

- **On Phase 1 reality:** "Don't build LLM before data pipeline runs 48h crash-free" — Already in our Phase 1 Reality Check section.

---

## Appendix A: Related Documents

- [Oil-Stonks Design](./2025-12-04-oil-stonks-design.md) — Original equities project (paused)
- [ProFiT Research Analysis](./2025-12-04-profit-research-analysis.md) — Initial ProFiT paper review
- [ProFiT Review Findings](./2025-12-04-profit-review-findings.md) — Critical review of ProFiT approach
- [Phase 1 Implementation Plan](./2025-12-05-phase1-implementation-plan.md) — Detailed build plan with Codex batching

---

*Document approved for development. Community feedback incorporated 2025-12-05. Start Phase 1.*
