# Comprehensive Codebase Review - Oil-Stonks Trading System

**Date**: 12/09/2025 06:57 AM PST (via pst-timestamp)
**Review Method**: 8 parallel Codex agents analyzing different system domains
**Status**: Phase 1 (Plumbing) - Pre-completion assessment

## Executive Summary

A comprehensive parallel review of the Oil-Stonks crypto/forex trading system identified **24 prioritized action items** across 4 tiers. The system has solid foundational architecture but requires critical fixes before Phase 1 completion:

- **8 Critical blockers** prevent system startup or would cause data corruption/losses
- **6 High-priority issues** affect reliability and safety for 48+ hour operation
- **6 Medium-priority items** improve quality and maintainability
- **4 Lower-priority tasks** enable Phase 2 and forex expansion

**Key Finding**: Core infrastructure exists but critical safety nets (kill switches, risk controls, data quality, logging) are incomplete or missing. Estimated **50-72 hours** to resolve all critical blockers.

---

## Review Domains & Methodology

Eight specialized Codex agents reviewed the codebase in parallel (~7 minutes wall-clock time):

1. **Crypto System** - Data pipeline, indicators, shadow trading, config
2. **Shared Infrastructure** - Gene pool, backtesting, evolution, fitness
3. **Risk Management** - Kill switches, position sizing, parameter enforcement
4. **Data Quality** - Anomaly detection, validation, backfill, storage
5. **Testing & Phase 2** - Test coverage, validation infrastructure, LLM integration
6. **Forex Status** - Implementation gaps, roadmap vs crypto
7. **Documentation** - Code/doc alignment, TODOs, architecture
8. **Operations** - Logging, observability, monitoring, deployment

---

## 🔴 CRITICAL PRIORITY - T0 (Phase 1 Blockers)

### **1. Fix Logging Infrastructure to Enable System Startup** ⚠️ *BLOCKS ALL OPERATIONS*

**Issue**: `crypto/main.py:9` imports non-existent `logs.setup_logging()` → application crashes on startup

**Impact**: System cannot run at all; zero operational capability

**Root Cause**: Logging module referenced in code but never implemented

**Files Affected**:
- `crypto/main.py:9` (bad import)
- `crypto/logs/__init__.py` or `crypto/logs.py` (missing)
- `crypto/execution/shadow/trader.py` (uses undefined loggers)

**Action Required**:
- Implement structured logging setup using `structlog` or Python `logging`
- Create FileHandlers for:
  - `trades.log` (INFO+) - All trade state vectors
  - `errors.log` (ERROR+) - Exceptions only
- Configure JSON formatting for trade logs per CLAUDE.md schema
- Add log rotation (daily files: `trades_YYYY-MM-DD.log`)

**Effort**: Low (1-2 hours)

**Validation**:
- [ ] `python crypto/main.py` starts without import errors
- [ ] Trade log writes to correct file with JSON format
- [ ] Error log captures exceptions only

---

### **2. Fix Backtester Capital Accounting** ⚠️ *CORRUPTS ALL BACKTEST RESULTS*

**Issue**: Equity never reduced when opening positions → P&L, Sharpe, drawdowns materially overstated

**Impact**:
- All Phase 2 evolution will be based on fantasy returns
- Strategies that appear profitable are actually bankrupt
- Risk checks meaningless (always have 100% cash available)

**Root Cause**: `shared/evolution/backtester/engine.py:72` and `portfolio_engine.py:82` don't debit position value from equity

**Files Affected**:
- `shared/evolution/backtester/engine.py:72-135`
- `shared/evolution/backtester/portfolio_engine.py:82-172`
- `shared/evolution/backtester/config.py` (`risk_per_trade`, throttle fields unused)

**Action Required**:
- Debit `position_value` (including friction) from `equity` on entry
- Mark-to-market: `equity = cash + sum(position_values at current prices)`
- Enforce `risk_per_trade` parameter
- Respect `min_position_interval_bars` throttle
- Portfolio: measure exposure vs **current** equity, not initial

**Effort**: Medium (4-6 hours)

**Validation**:
- [ ] Equity decreases on position open
- [ ] Final equity matches initial ± PnL ± friction
- [ ] Exposure limits enforced against current equity
- [ ] Test: open position with 10k equity @ 10% sizing → equity = 9k cash + 1k position

---

### **3. Implement Reconnect Protocol** ⚠️ *TRADING ON STALE/CORRUPTED DATA*

**Issue**: System continues trading through disconnects/gaps without:
- Pausing trading
- Refilling missing data
- Recomputing indicators
- Waiting for fresh candles

**Impact**:
- Will generate signals from incomplete data after any network hiccup
- Catastrophic losses from stale indicators during volatile reconnects
- Violates Phase 1 "Reconnect protocol tested" requirement

**Root Cause**:
- `crypto/data/ingestion/bybit_ws.py:43-189` - `_warmup` only called on initial connect
- `crypto/data/quality_filters.py:70-85` - Gap detection sets flag but doesn't trigger remediation
- `crypto/main.py:59-158` - No pause/resume trading mechanism

**Files Affected**:
- `crypto/data/ingestion/bybit_ws.py` (WebSocket client)
- `crypto/data/quality_filters.py` (CandleValidator)
- `crypto/main.py` (orchestration)
- `crypto/execution/shadow/trader.py` (needs pause/resume hooks)

**Action Required**:

**On Disconnect or Gap Detection**:
1. **Pause trading** - Stop evaluating signals, set `trading_paused = True`
2. **Flatten open positions** - Close all shadow positions to avoid risk during outage
3. **Fetch historical data** - REST call for ≥100 candles per symbol to fill gap
4. **Rebuild indicator state** - Recompute all indicator history with complete data
5. **Wait for confirmation** - Require 2 new **confirmed** candles (`confirm == True`)
6. **Resume trading** - Re-enable signal evaluation

**Add Heartbeat/Ping**:
- Implement ping/pong with 30s timeout
- Subscription ack verification with exponential backoff
- Exception handling inside `_handle_message` triggers backoff, not just logging

**Effort**: High (8-12 hours)

**Validation**:
- [ ] Disconnect simulation → trading pauses
- [ ] Gap >5min → historical backfill triggered
- [ ] Indicators recalculated after reconnect
- [ ] No trades for 2 candles after reconnect
- [ ] Test: inject 10-minute gap → verify no signals until refill complete

---

### **4. Filter Partial/Unconfirmed Candles** ⚠️ *INDICATOR CORRUPTION*

**Issue**: Every kline update stored without checking Bybit's `confirm` flag → partial candles treated as final

**Impact**:
- Indicators see mid-candle noise and phantom patterns
- Trades execute on incomplete data
- Determinism broken (same historical period gives different results)

**Root Cause**: `crypto/data/ingestion/bybit_ws.py:108-172` - `_handle_kline` processes all updates

**Files Affected**:
- `crypto/data/ingestion/bybit_ws.py:108-172` (kline handler)
- `crypto/main.py:70-109` (candle callback)

**Action Required**:
- Parse `confirm` field from Bybit kline messages
- **Only persist** when `confirm == True` (1)
- **Only emit** to callbacks when `confirm == True`
- Gate `_candle_count` increments on actual inserts (not overwrites)
- Add logging: "Received partial candle, waiting for confirmation"

**Effort**: Low-Medium (3-4 hours)

**Validation**:
- [ ] Partial candles logged but not stored
- [ ] Only confirmed candles in database
- [ ] Candle count matches confirmed candles only
- [ ] Test: subscribe to live stream, verify 1 insert per interval

---

### **5. Implement Kill Switch Framework** ⚠️ *NO SAFETY NET*

**Issue**: `shared/risk/watchdog/` empty, no drawdown/timeout/loss triggers wired anywhere

**Impact**:
- System can bleed capital indefinitely without automatic halt
- No protection against runaway losses, stuck processes, or data feed failures
- Violates mandatory kill-switch requirements in CLAUDE.md

**Root Cause**:
- `shared/risk/watchdog/__init__.py` empty
- `crypto/risk/watchdog/__init__.py` empty
- No runtime integration in `crypto/main.py` or `trader.py`

**Files Affected**:
- `shared/risk/watchdog/` (needs full implementation)
- `crypto/main.py` (needs watchdog integration)
- `crypto/execution/shadow/trader.py` (needs to emit metrics, receive halt signals)

**Action Required**:

**Implement Watchdog Engine** (`shared/risk/watchdog/engine.py`):
- Monitor equity time-series, position data, process heartbeat
- Enforce all triggers from CLAUDE.md:

| Trigger | Action |
|---------|--------|
| Drawdown > 5% in 1 hour | Close all positions, pause 1 hour |
| Drawdown > 10% in 24 hours | Close all positions, pause 24 hours |
| Drawdown > 20% from peak | **Full shutdown**, manual restart required |
| Single position loss > 3% equity | Force close (stop-loss failed) |
| Main process unresponsive > 60s | Kill and close all positions |

**Integration Points**:
- Trader emits: equity updates, position PnL, heartbeat timestamp
- Watchdog commands: pause trading, flatten positions, shutdown
- Persistence: store peak equity, drawdown windows in SQLite

**Effort**: High (10-16 hours including testing)

**Validation**:
- [ ] Simulated 6% drawdown in 1 hour → auto-pause
- [ ] Simulated 21% drawdown from peak → full shutdown
- [ ] Heartbeat stops → watchdog detects within 60s
- [ ] Single position -4% → forced liquidation
- [ ] All triggers tested with synthetic equity curves

---

### **6. Implement Risk-Based Position Sizing with Stop-Loss** ⚠️ *RISK PER TRADE UNCONTROLLED*

**Issue**:
- Sizes are `equity * risk_pct` capped by `max_position_pct`, no link to stop distance
- `Position.stop_loss_price` never set or enforced
- Actual risk per trade can far exceed 1%

**Impact**:
- Single position can lose entire allocated notional (10% of equity)
- Violates core "1% risk per trade" principle
- No stop-loss execution → positions held until strategy exit

**Root Cause**:
- `crypto/execution/shadow/trader.py:171-199` - Incorrect sizing formula
- `crypto/execution/shadow/position.py` - Stop-loss field unused

**Files Affected**:
- `crypto/execution/shadow/trader.py:171-199` (position sizing)
- `crypto/execution/shadow/position.py:1-26` (Position model)
- `crypto/main.py:139-158` (needs stop-loss evaluation loop)

**Action Required**:

**Risk-Based Sizing**:
```python
# Calculate position size to risk exactly 1% of equity
atr = calculate_atr(symbol, period=14)
stop_distance = 2.0 * atr  # 2 ATR stop
intended_risk = equity * config.risk_per_trade  # 1% = 0.01

size_usdt = intended_risk / stop_distance
size_usdt = min(size_usdt, equity * config.max_position_pct)  # Cap at 10%
```

**Stop-Loss Enforcement**:
- Set `position.stop_loss_price = entry_price - stop_distance` on long entry
- Set `position.stop_loss_price = entry_price + stop_distance` on short entry
- Check every candle: if `current_price <= stop_loss_price` (long) → force close
- Log stop-loss hits separately from strategy exits

**Effort**: Medium (6-8 hours)

**Validation**:
- [ ] Position size respects ATR-based stop distance
- [ ] Max loss per position ≤ 1% of equity
- [ ] Stop-loss triggered correctly on price move
- [ ] Test: $10k equity, 2% ATR, $40k BTC → size = ($100 / $800) = 0.125 BTC = $5k position
- [ ] Test: Price drops 2 ATR → position auto-closed

---

### **7. Implement Gap Remediation** ⚠️ *INDICATORS RUN ON HOLES*

**Issue**: Gap detection flags `requires_warmup` but system continues trading on incomplete data

**Impact**:
- Indicators see holes in price history
- Signals based on incomplete data
- EMA/RSI calculations corrupted after gaps

**Root Cause**:
- `crypto/data/quality_filters.py:72-85` - Sets flag but no action taken
- `crypto/main.py:70-76` - Flag checked but only resets validator state

**Files Affected**:
- `crypto/data/quality_filters.py:70-85` (gap detection)
- `crypto/main.py:70-76` (gap handling)
- `crypto/data/ingestion/bybit_ws.py` (needs backfill trigger)

**Action Required**:

**On Gap Detection** (>5 minutes missing data):
1. Pause trading immediately
2. Trigger REST backfill for missing window
3. Rebuild indicator history with complete data
4. Clear validator warmup flag
5. Resume trading

**Add Persistence**:
- Store `last_timestamp` per symbol in SQLite side table
- On startup, check for gaps since last run
- Seed validator with last-seen timestamps

**Effort**: Medium (4-6 hours)

**Validation**:
- [ ] Simulated 10-minute gap → trading pauses
- [ ] Historical data backfilled to fill gap
- [ ] Indicators recalculated with complete history
- [ ] Process restart detects gap correctly
- [ ] Test: delete 10 candles from DB → startup triggers backfill

---

### **8. Fix Trade Log Schema** ⚠️ *AUDIT TRAIL INCOMPLETE*

**Issue**: Trade logs missing required fields from CLAUDE.md universal schema

**Current Schema** (`crypto/execution/shadow/trader.py:21-41`):
- Has: timestamp, strategy_id, symbol, action, price, size, pnl
- Missing: `asset_class`, `asset`, `entry_price`, `exit_price`, `position_size`, `gene_expression` (as dict), `market_filter_value`, `market_regime`

**Impact**:
- Cannot audit trades properly
- Cannot debug strategy logic
- Cannot analyze performance by regime or primitive
- Violates Phase 1 "24h shadow logging with auditability" requirement

**Files Affected**:
- `crypto/execution/shadow/trader.py:21-41, 203-217, 249-265` (log emission)
- `crypto/logs/` (log file setup)

**Action Required**:

**Align to CLAUDE.md Schema**:
```json
{
  "timestamp": "2025-12-09T14:23:45.123Z",  // ISO8601 UTC
  "strategy_id": "strat_abc123",
  "asset_class": "crypto",
  "asset": "BTC-USDT",
  "signal": "entry_long",  // or exit_long, entry_short, exit_short
  "entry_price": 42350.50,
  "exit_price": null,  // or actual exit price
  "position_size": 0.05,
  "position_size_usdt": 2117.53,
  "gene_expression": {
    "market_filter_60": 1.0,
    "ema_trend_9_21": 1.0,
    "norm_rsi_14": -0.42
  },
  "market_filter": "market_filter(60) >= 0",  // The filter expression
  "market_regime": "bull_calm",
  "stop_loss_price": 41550.00,
  "friction_applied": 10.59,
  "pnl": null  // or realized PnL on exit
}
```

**File Naming**:
- Daily rotation: `logs/trades_2025-12-09.log` (not `shadow_trades.jsonl`)
- One JSON object per line (JSONL format)

**Effort**: Low-Medium (3-4 hours)

**Validation**:
- [ ] All required fields present in log entries
- [ ] Timestamps in ISO8601 UTC format
- [ ] Gene expression logged as dict with primitive values
- [ ] Market regime and filter values captured
- [ ] Test: execute trade → verify complete log entry

---

## 🟠 HIGH PRIORITY - T1 (Reliability & Safety)

### **9. Fix Walk-Forward Validation**

**Issue**:
- Train windows ignored (no re-fit or parameter freeze)
- Aggregated equity incorrectly appends independent runs (each starting at 10k initial equity)
- Metrics from last window only

**Impact**: Phase 2 will approve overfit strategies; walk-forward gate is broken

**Files**: `shared/evolution/backtester/walk_forward.py:96-211`

**Action**:
- Add train/test split hooks for parameter freezing
- Compound per-window returns when aggregating (don't concatenate equity curves)
- Fix aggregation: weight by window coverage or compute cumulative return

**Effort**: Medium-High (6-10 hours)

---

### **10. Fix Regime Testing Equity Accounting**

**Issue**:
- Each regime reruns backtest with fresh `initial_equity = 10k`
- `aggregate_regime_results` stitches these independent curves
- Produces inflated Sharpe/drawdown

**Impact**: Regime filtering doesn't work; Phase 2 strategies won't survive regime shifts

**Files**:
- `shared/evolution/backtester/engine.py:175-205`
- `shared/evolution/fitness/calculator.py:240-306`

**Action**:
- Aggregate by weighting per-regime returns, not concatenating equity
- Enforce `MIN_TRADES_PER_REGIME` and `MIN_CANDLES_PER_REGIME`
- Use configured initial equity, not hard-coded 10k

**Effort**: Medium (5-7 hours)

---

### **11. Enforce Risk Parameters Mark-to-Market**

**Issue**:
- Exposure checked only at entry using sum of entry notionals
- Never recomputed after price moves or equity changes
- No time-based entry throttle (1 per 5 minutes)

**Impact**:
- Exposure can drift >50% undetected
- Burst of signals can open multiple positions in same minute

**Files**: `crypto/execution/shadow/trader.py:157-271`

**Action**:
- Recompute exposure each candle: `sum(position_value_at_current_prices) / current_equity`
- Re-check limits; block new entries if breached
- Add throttle: track last entry timestamp, block entries within 5 minutes

**Effort**: Medium (4-6 hours)

---

### **12. Add Comprehensive Data Quality Filters**

**Issue**:
- Only catches zero volume and >50% single-candle moves
- Missing: spread checks, frozen feeds, out-of-order timestamps, duplicates, ATR-based thresholds

**Impact**: Bad ticks can still corrupt indicators

**Files**: `crypto/data/quality_filters.py:31-85`

**Action**:
- Add spread >5% filter (high - low) / close
- Frozen-feed: reject N consecutive identical candles
- Out-of-order timestamps: reject if timestamp ≤ last_timestamp
- Negative/NaN price/volume checks
- Price integrity: high ≥ max(open, close), low ≤ min(open, close)
- ATR-based volatility thresholds (per symbol, not static 50%)

**Effort**: Medium (5-7 hours)

---

### **13. Add Monitoring, Alerting, and Heartbeat**

**Issue**: No health metrics, drawdown tracking, or operational alerts

**Impact**: Cannot detect stuck process, data gaps, runaway losses

**Action**:
- Emit heartbeat every 10 seconds with: equity, drawdown, exposure, open positions, last price timestamp
- Create monitoring endpoint or log stream for watchdog
- Wire alerts (log entries or external service) for threshold breaches
- Add "no data for 60s" alert

**Effort**: Medium-High (6-10 hours)

---

### **14. Enforce CLAUDE.md Strategy Rules in Parser**

**Issue**: Parser allows floats, unlimited primitives, no market filter requirement

**Impact**: Mutated strategies can bypass gene-pool constraints

**Files**: `crypto/engine/strategy_logic/parser.py:65-175`

**Action**:
- Enforce max 5 primitives per expression
- Reject float parameters (only integers allowed)
- Require `market_filter` or `btc_trend` in all entry_long conditions
- Normalize boolean operators (handle case, whitespace)

**Effort**: Low-Medium (3-5 hours)

---

## 🟡 MEDIUM PRIORITY - T2 (Quality & Maintainability)

### **15. Add Comprehensive Test Coverage for Shared Components**

**Issue**: Zero tests for `shared/evolution/` (backtester, regime classifier, walk-forward, mutator)

**Impact**: Phase 2 components can regress silently

**Action**: Create `shared/tests/` with deterministic unit tests using fixtures

**Effort**: High (12-20 hours)

---

### **16. Normalize Gene Pool Outputs**

**Issue**: `price_position` and `vwap_distance` return ±3.0, not -1..1 per CLAUDE.md

**Impact**: Violates spec; limits forex reuse (volume-dependent)

**Files**:
- `shared/engine/gene_pool/trend.py:45`
- `shared/engine/gene_pool/volume.py:44`

**Action**:
- Normalize outputs: divide by 3 or clamp to [-1, 1]
- Add volume-agnostic fallbacks (tick volume, spread-based liquidity proxy)

**Effort**: Low (2-3 hours)

---

### **17. Fix Portfolio Backtester Alignment and Exposure**

**Issue**:
- Timestamp alignment truncates to shortest series (silently drops data)
- Exposure uses `initial_equity` not current equity

**Impact**: Multi-asset backtests distorted; limits can be breached

**Files**: `shared/evolution/backtester/portfolio_engine.py:82-172`

**Action**:
- Align on timestamps: inner join or reindex with forward-fill
- Recompute exposure vs current equity + unrealized PnL

**Effort**: Medium (4-6 hours)

---

### **18. Standardize UTC/Clock Handling**

**Issue**: Timestamps mix local tz and UTC conversions

**Impact**: Timestamp bugs, audit confusion

**Action**: Use `datetime.fromtimestamp(..., tz=timezone.utc)` everywhere

**Files**: Throughout `crypto/data/` modules

**Effort**: Low-Medium (3-4 hours)

---

### **19. Tighten LLM Integration Validation**

**Issue**: `StrategyGenerator` allows float params, doesn't enforce structure rules

**Impact**: Mutator can emit invalid strategies

**Files**: `shared/evolution/mutator/generator.py:248-297`

**Action**:
- Enforce integer params only
- Primitive count ≤5
- AND-only boolean operators
- Mandatory market filter presence
- Add timeout/backoff to `LLMClient`

**Effort**: Low-Medium (3-4 hours)

---

### **20. Add Historical Backfill Resiliency**

**Issue**: No retries, single short page ends run, no gap verification

**Impact**: Backfill can be incomplete

**Files**: `crypto/data/backfill.py:58-198`

**Action**:
- Add retry with exponential backoff
- Verify continuity against DB before stopping
- Surface gaps/duplicates after insert

**Effort**: Low (2-3 hours)

---

## 🟢 LOWER PRIORITY - T3 (Future Work)

### **21. Create Shared Strategy Parser/Registry**

**Issue**: `shared/engine/strategy_logic/` empty; crypto parser can't be reused by forex

**Impact**: Code duplication, harder to maintain

**Action**: Extract parser from crypto, add primitive registry, enable asset-specific extensions

**Effort**: Medium (5-8 hours)

---

### **22. Document and Align Architecture**

**Issue**: Multiple doc/code mismatches (friction values, required fields, regime definitions)

**Impact**: Confusion, maintenance burden

**Action**: Reconcile all TODO/INCOMPLETE markers, align docs with code

**Effort**: Low-Medium (4-6 hours)

---

### **23. Build Forex System (Phase 0)**

**Issue**: Forex is completely stub (empty files, no broker, no primitives)

**Impact**: Second revenue stream delayed

**Roadmap** (8 steps from review):
1. Foundations & config (broker selection: OANDA practice)
2. Data model & quality layer
3. Ingestion pipeline (WS/REST with warmup)
4. Strategy engine & forex-specific primitives (`dxy_trend`, `risk_sentiment`, `interest_rate_differential`, `session_filter`)
5. Shadow execution & risk controls
6. Testing & validation (indicator parity, fixtures)
7. Docs & planning (design doc, market research)
8. Readiness gate (48h stable, 3-5 major pairs)

**Effort**: Very High (40-80 hours)

---

### **24. Add Process Management Artifacts**

**Issue**: No supervisor/systemd configs, minimal Fly config, no ops runbook

**Impact**: Harder to deploy/operate

**Action**:
- Create systemd unit files
- Add Fly health checks and restart policy
- Write operational runbook: start/stop, log review, incident recovery

**Effort**: Low-Medium (4-6 hours)

---

## 📊 Effort Summary by Tier

| Tier | Priority | Total Items | Estimated Effort | % of Total |
|------|----------|-------------|------------------|------------|
| **T0** | Critical Blockers | 8 items | 50-72 hours | 30% |
| **T1** | High (Reliability) | 6 items | 30-48 hours | 20% |
| **T2** | Medium (Quality) | 6 items | 35-58 hours | 25% |
| **T3** | Lower (Future) | 4 items | 53-98 hours | 25% |
| **Total** | | **24 items** | **168-276 hours** | 100% |

---

## 🎯 Recommended Execution Strategy

### **Sprint 1: Make it Run (Days 1-3)**
**Goal**: System can start and won't trade on corrupted data

**Tasks**:
1. Fix logging infrastructure (T0.1) - 2h
2. Fix backtester capital accounting (T0.2) - 6h
3. Filter confirmed candles only (T0.4) - 4h
4. Implement reconnect protocol (T0.3) - 12h

**Duration**: ~3 days (24 hours work)
**Exit Criteria**:
- [ ] `python crypto/main.py` starts successfully
- [ ] Backtest equity changes correctly on trades
- [ ] Only confirmed candles stored
- [ ] Reconnect test: gap simulation triggers backfill

---

### **Sprint 2: Make it Safe (Days 4-7)**
**Goal**: Survival-first controls in place

**Tasks**:
1. Kill switch framework (T0.5) - 16h
2. Risk-based position sizing (T0.6) - 8h
3. Gap remediation (T0.7) - 6h
4. Fix trade log schema (T0.8) - 4h

**Duration**: ~4 days (34 hours work)
**Exit Criteria**:
- [ ] Watchdog process monitoring equity
- [ ] Kill switch triggers tested (5% 1h, 10% 24h, 20% peak)
- [ ] Position sizing respects ATR stops
- [ ] Trade logs have all required fields

---

### **Sprint 3: Make it Reliable (Days 8-12)**
**Goal**: Pass Phase 1 "48 hours without crashes" gate

**Tasks**:
1. Fix walk-forward validation (T1.9) - 10h
2. Fix regime testing accounting (T1.10) - 7h
3. Mark-to-market risk enforcement (T1.11) - 6h
4. Comprehensive data quality filters (T1.12) - 7h
5. Monitoring & alerting (T1.13) - 10h
6. Enforce parser rules (T1.14) - 5h

**Duration**: ~5 days (45 hours work)
**Exit Criteria**:
- [ ] Walk-forward aggregation correct
- [ ] Regime testing uses weighted returns
- [ ] Exposure recomputed every candle
- [ ] All data quality filters implemented
- [ ] Heartbeat and alerts working
- [ ] Parser rejects invalid strategies

---

### **Sprint 4+: Quality & Forex (Days 13+)**
**Goal**: Address technical debt, prepare for Phase 2, enable forex

**Tasks**: T2 (quality improvements) and T3 (forex, docs, ops)

**Duration**: Variable based on priorities

---

## 🔍 Testing & Validation Protocol

### **Unit Test Requirements** (Before any item marked complete):
- Deterministic test with synthetic data
- Edge case coverage (boundary conditions)
- Error handling verification
- Integration test where applicable

### **Integration Test Requirements** (Before sprint completion):
- End-to-end smoke test with real data fixtures
- Failure mode injection (disconnect, gap, bad data)
- Performance/stability test (1000+ candles)

### **Phase 1 Gate Criteria** (Before declaring Phase 1 complete):
- [ ] System runs 48+ hours without crashes or intervention
- [ ] Indicators match TradingView reference within 0.1%
- [ ] Shadow trader logs correctly for 24+ hours
- [ ] All data quality filters validated
- [ ] Reconnect protocol tested successfully
- [ ] Kill switch triggers tested
- [ ] All T0 and T1 items resolved

---

## 📝 Documentation Gaps & TODOs

### **Found TODO/INCOMPLETE Markers**:
- `docs/plans/2025-12-05-phase1-implementation-plan.md:2305` - Fetch symbols dynamically
- `shared/evolution/backtester/engine.py:78` - Increase MIN_CANDLES when more data available
- `shared/evolution/fitness/calculator.py:19` - Increase MIN_TRADES to 30 when more data available
- `crypto/evolve.py:408` - Increase population to 200+
- `crypto/evolve.py:437` - Increase population to 200+
- `crypto/main.py:28` - Fetch symbols dynamically in Phase 2
- `FOREX.md` - Multiple TODOs covering all aspects of forex system

### **Code/Doc Misalignments**:
- Friction: CRYPTO.md says 0.41% round-trip, code uses 0.25% per side (0.5% RT)
- Trade log schema: Code missing 8+ required fields from CLAUDE.md
- Regime definitions: Code uses 4h/1% threshold, CRYPTO.md specifies monthly/ATR
- Market filter enforcement: Docs say "MANDATORY", parser doesn't enforce
- Gene pool outputs: Docs say -1..1, code returns ±3.0

### **Missing Documentation**:
- Operational runbook (start/stop, deployment, log review, incident recovery)
- Forex design document (as planned in FOREX.md TODOs)
- Forex market research document
- Root-level `requirements.txt` (shown in CLAUDE.md but doesn't exist)

---

## 🏗️ Architectural Observations

### **What's Working Well**:
- Clean separation of concerns (data/execution/strategy/evolution)
- Asset-agnostic shared primitives foundation
- Pydantic config management pattern
- SQLite for MVP storage (appropriate for Phase 1)
- Gene pool constraint concept (though not enforced)

### **Architectural Concerns**:
- **Shared infrastructure incomplete**: Risk/watchdog, strategy parser not implemented
- **Cross-asset reuse limited**: Volume-dependent primitives, crypto-specific hardcoding
- **Safety controls as afterthought**: Kill switches, monitoring not integrated into core loops
- **Testing gaps**: Shared components untested, evolution logic unvalidated
- **Operational maturity low**: No runbooks, minimal process management, logging broken

### **Design Debt**:
- Config ignored at runtime (hard-coded symbols/strategy)
- Parser doesn't enforce gene pool rules it's supposed to validate
- Backtester doesn't enforce risk parameters it accepts in config
- Trade logs diverge from universal schema they're supposed to follow
- Reconnect protocol documented but not implemented

---

## 💡 Key Insights & Recommendations

### **Phase Gating is Critical**:
The system correctly identifies Phase 1 (Plumbing) as prerequisite to Phase 2 (Evolution). Current state: **Phase 1 incomplete**. Do NOT proceed to Phase 2 until:
- 48+ hour stability achieved
- All T0 and T1 items resolved
- Data quality and safety controls validated

### **Robustness Over Returns**:
The design philosophy is sound, but implementation doesn't match. Critical gap: **safety controls missing or incomplete** (kill switches, risk sizing, data quality). These must be T0 priority.

### **Testing as Insurance**:
Zero tests for shared evolution components means Phase 2 will build on unvalidated foundations. Recommend:
- Test-first for all new T0/T1 implementations
- Backfill tests for shared components in T2

### **Forex Can Wait**:
Forex is appropriately deprioritized (T3). Focus on crypto Phase 1 completion first. Forex roadmap is solid; execute after crypto proves 48h stability.

### **Documentation Hygiene**:
Code/doc drift is significant. Recommend:
- Update docs **after** code changes, not before
- Single source of truth for schemas (generate from code?)
- Automated doc validation in CI

---

## 📦 Deliverables from This Review

**Generated Artifacts**:
1. This consolidated planning document
2. Eight detailed domain reviews (in `/tmp/`, git-ignored)
3. Prioritized action plan with effort estimates
4. Phase 1 readiness checklist
5. Testing & validation protocol
6. Forex implementation roadmap

**Next Actions**:
1. **Immediate**: Fix logging (T0.1) to enable system startup
2. **Week 1**: Execute Sprint 1 (Make it Run)
3. **Week 2**: Execute Sprint 2 (Make it Safe)
4. **Week 3**: Execute Sprint 3 (Make it Reliable)
5. **Post-Sprint 3**: Run 48-hour stability test for Phase 1 gate

---

## 🔄 Change Log

| Date | Milestone | Status |
|------|-----------|--------|
| 12/09/2025 06:57 AM PST | Comprehensive codebase review completed | ✅ Complete |
| 12/09/2025 06:57 AM PST | Planning document created | ✅ Complete |
| TBD | Sprint 1 execution (Make it Run) | ⏳ Pending |
| TBD | Sprint 2 execution (Make it Safe) | ⏳ Pending |
| TBD | Sprint 3 execution (Make it Reliable) | ⏳ Pending |
| TBD | Phase 1 48-hour stability test | ⏳ Pending |
| TBD | Phase 1 gates passed | ⏳ Pending |

---

**Review Completed**: 12/09/2025 06:57 AM PST (via pst-timestamp)
**Review Method**: 8 parallel Codex agents (gpt-5.1-codex-max)
**Wall-Clock Time**: ~7 minutes
**Total Findings**: 24 prioritized action items across 4 tiers
**Critical Blockers**: 8 items requiring immediate attention
**Estimated Effort to Phase 1 Ready**: 80-120 hours (Sprints 1-3)
