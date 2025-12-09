# Phase 3: Gauntlet - Statistical Validation Plan

**Created:** 12/09/2025 06:52 AM PST (via pst-timestamp)
**Status:** Planning
**Prerequisites:** Phase 2 Complete (Evolution Engine + Production Integration)

## Overview

Phase 3 is the **statistical validation phase** — we run the evolution system on live data via shadow trading to prove strategies work before risking real capital.

**Goal:** Accumulate statistical evidence that evolved strategies generate alpha in real-time conditions.

**Duration:** 4-8 weeks of continuous operation

---

## 1. Phase 3 Objectives

### Primary Goals

1. **Prove Strategy Alpha**: Shadow equity curve trending up over 4+ weeks
2. **Validate Robustness**: Strategies survive regime changes in real-time
3. **Tune Execution Model**: Calibrate slippage and friction estimates against real market data
4. **Accumulate Evidence**: 100+ trades per top strategy for statistical significance
5. **System Stability**: Run 7+ days without manual intervention

### Success Criteria

| Metric | Target | Hard Fail |
|--------|--------|-----------|
| Shadow equity curve | Trending up over 4 weeks | Down >15% |
| Max drawdown | < 10% | > 15% |
| Profit factor | > 1.5 | < 1.0 |
| Win rate | > 45% | < 35% |
| Sharpe ratio | > 1.0 | < 0.5 |
| Strategies in shadow pool | ≥ 3 | 0 |
| Uptime | > 95% | < 80% |

---

## 2. System Architecture (Phase 3)

### 2.1 Components to Deploy

```
┌─────────────────────────────────────────────────────────────┐
│                    FLY.IO (Frankfurt)                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐     ┌──────────────┐     ┌─────────────┐ │
│  │  WebSocket   │────▶│    Data      │────▶│   SQLite    │ │
│  │   Client     │     │  Processor   │     │   Storage   │ │
│  └──────────────┘     └──────────────┘     └─────────────┘ │
│         │                    │                    │        │
│         ▼                    ▼                    ▼        │
│  ┌──────────────┐     ┌──────────────┐     ┌─────────────┐ │
│  │   Signal     │◀────│   Shadow     │────▶│   Trade     │ │
│  │  Generator   │     │   Trader     │     │    Logs     │ │
│  └──────────────┘     └──────────────┘     └─────────────┘ │
│         │                    │                    │        │
│         ▼                    ▼                    ▼        │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              Evolution Scheduler                      │  │
│  │         (Nightly runs at 2 AM UTC)                   │  │
│  └──────────────────────────────────────────────────────┘  │
│                          │                                  │
│                          ▼                                  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              Monitoring Dashboard                     │  │
│  │          (Health checks, alerts)                      │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Process Supervision

All processes should be managed by supervisor/systemd for auto-restart:

| Process | Purpose | Restart Policy |
|---------|---------|----------------|
| `main.py` | WebSocket + Shadow Trader | Always restart |
| `scheduler.py --start` | Nightly evolution | Always restart |
| Health check cron | Alerts on failure | Every 5 minutes |

---

## 3. Implementation Phases

### Phase 3A: Shadow Trader Completion ✅ **COMPLETE**
**Goal:** Get shadow trading working end-to-end

**Tasks:**
- [x] Create shadow trader that reads strategies from shadow pool
- [x] Implement signal generation from strategy expressions
- [x] Add position tracking (open/close shadow positions)
- [x] Log all trades to `shadow_trades.jsonl`
- [x] Calculate running P&L and equity curve

**Files Created/Modified:**
- `crypto/execution/shadow/pool_manager.py` - Multi-strategy shadow pool manager (NEW)
- `crypto/execution/shadow/trader.py` - Single strategy trader (existing, still works)
- `crypto/execution/shadow/position.py` - Position tracking (existing)
- `crypto/main.py` - Added --shadow-pool flag for Phase 3 mode

**Implementation Notes (12/09/2025 07:29 AM PST):**
- `ShadowPoolManager` loads strategies from `logs/shadow_pool/*.json`
- Per-strategy performance tracking with `StrategyPerformance` dataclass
- Kill switches: 5% hourly DD pauses 1 hour, 15% total DD full stop
- Stop-loss: 3% automatic exit for all positions
- Hot-reload support via `reload_strategies()` method
- Run with: `python main.py --shadow-pool`

### Phase 3B: Live System Integration ✅ **COMPLETE**
**Goal:** Connect all components for continuous operation

**Tasks:**
- [x] Integrate shadow trader with live WebSocket data
- [x] Set up process supervision (supervisor.conf)
- [x] Configure scheduler for nightly evolution runs
- [x] Implement strategy hot-reload (load new strategies without restart)
- [x] Add shadow position sizing based on paper equity

**Files Created/Modified:**
- `crypto/main.py` - Added hot-reload signal checking
- `crypto/supervisor.conf` - Process supervision for 3 processes (NEW)
- `crypto/execution/shadow/hot_reload.py` - File watcher with debounce (NEW)
- `crypto/Dockerfile` - Updated to use supervisord

**Implementation Notes (12/09/2025 09:04 AM PST):**
- Supervisor manages: shadow_trader, scheduler, hot_reload processes
- Hot-reload watcher polls every 5s with 3s debounce
- Signal file `.reload_strategies` triggers reload in main process
- Main.py checks for reload every ~50 candles (~50 seconds)
- Position sizing uses `risk_per_trade` (1%) and `max_position_pct` (10%)

### Phase 3C: Monitoring & Alerting ✅ **COMPLETE**
**Goal:** Know immediately when something goes wrong

**Tasks:**
- [x] Extend monitoring dashboard for shadow trading metrics
- [x] Add Slack/Discord webhook alerts
- [x] Create daily performance summary reports
- [x] Implement health check endpoint
- [ ] Add regime detection monitoring (deferred to Phase 3E)

**Files Created/Modified:**
- `crypto/monitoring.py` - Extended with paper equity tracking, webhook alerts, daily reports, health check

**Implementation Notes (12/09/2025 09:13 AM PST):**
- New dashboard sections: Paper Equity (with drawdown %), Today's Performance
- `WebhookAlerter` class supports both Slack and Discord webhook formats
- Alert thresholds from CLAUDE.md: 5% DD warning, 10% DD critical, 15% DD emergency
- New CLI options: `--daily-report`, `--send-alert`, `--health-check`, `--send-alerts`
- Health check returns exit codes: 0=OK, 1=CRITICAL (for cron/scripts)
- Daily reports saved to `logs/daily_reports/` and optionally sent via webhook
- Set `ALERT_WEBHOOK_URL` env var to enable webhook alerts

**Alert Conditions:**
- Shadow drawdown > 5% (warning), > 10% (critical), > 15% (emergency)
- No trades in 24 hours (warning)
- Evolution run failed (warning)
- Data staleness > 60 minutes (warning/critical)
- Process crash (critical) - handled by supervisor autorestart

### Phase 3D: Slippage Calibration ✅ **COMPLETE**
**Goal:** Tune friction model to match reality

**Tasks:**
- [x] Track simulated fill price vs actual candle prices
- [x] Calculate realized slippage per regime
- [ ] Adjust backtest friction model based on findings (requires live data)
- [ ] Re-run evolution with calibrated friction (requires live data)

**Files Modified:**
- `crypto/execution/shadow/trader.py` - Extended TradeLog with slippage fields
- `crypto/execution/shadow/pool_manager.py` - Capture candle OHLC for slippage tracking
- `crypto/monitoring.py` - Added `get_slippage_analysis()` method and dashboard section

**Implementation Notes (12/09/2025 09:23 AM PST):**
- TradeLog now includes: candle_open, candle_high, candle_low, candle_close, implied_slippage_pct
- Slippage analysis calculates: avg, min, max slippage, entry vs exit breakdown
- Per-regime slippage tracking for calibration (bull_calm, bear_volatile, etc.)
- Dashboard shows comparison: configured friction vs realized slippage
- "Friction accuracy" indicator: warns if >0.1% deviation from configured value

**Slippage Analysis:**
```python
# Log for each shadow trade:
{
    "signal_price": 42350.50,    # Price when signal triggered
    "next_candle_open": 42352.00, # Actual fill price (conservative)
    "candle_high": 42380.00,
    "candle_low": 42340.00,
    "implied_slippage_pct": 0.0035,  # (fill - signal) / signal
    "regime": "bull_calm"
}
```

### Phase 3E: Strategy Lifecycle Management
**Goal:** Retire underperformers, promote winners

**Tasks:**
- [ ] Implement performance tracking per strategy
- [ ] Add automatic retirement criteria (losing for N trades)
- [ ] Create strategy report generation
- [ ] Track strategy lineage (parent → child mutations)
- [ ] Add strategy versioning

**Retirement Criteria:**
- Sharpe < 0.0 over 50 trades → retire
- Max drawdown > 15% → retire
- Win rate < 30% over 50 trades → retire
- No trades in 14 days → flag for review

---

## 4. Data Requirements

### 4.1 Current Data Status

From Phase 2E backfill (12/09/2025):
- **BTCUSDT**: 129,600 candles (90 days)
- **ETHUSDT**: 129,600 candles (90 days)
- **SOLUSDT**: 129,600 candles (90 days)

### 4.2 Ongoing Data Needs

| Requirement | Purpose |
|-------------|---------|
| Live 1-min candles | Shadow trade signals |
| BTC for market filter | btc_trend() calculation |
| Historical regime data | Context for analysis |

### 4.3 Regime Distribution Check

Before Phase 3 launch, verify regime distribution in historical data:

```python
# Expected: All 5 regimes have sufficient samples
python evolve.py --check-regimes
```

---

## 5. Shadow Trading Mechanics

### 5.1 Position Sizing

**Initial Paper Equity:** $10,000

**Risk per Trade:** 1% = $100 max loss

**Position Size Calculation:**
```python
position_size = (paper_equity * 0.01) / abs(entry_price - stop_loss)
```

### 5.2 Trade Execution Model

```python
# Signal at close of candle N
# Execute at open of candle N+1 (conservative)
# Stop-loss: -3% from entry
# Take-profit: Based on exit signal OR trailing stop

trade = {
    "strategy_id": "evo_20251209_...",
    "symbol": "SOLUSDT",
    "direction": "long",
    "signal_time": 1702123200000,
    "signal_price": 42350.50,
    "entry_time": 1702123260000,  # Next candle
    "entry_price": 42352.00,
    "stop_loss": 41081.44,  # -3%
    "position_size": 0.05,  # $2,117.60 notional
    "status": "open"
}
```

### 5.3 Exit Conditions

1. **Signal Exit**: Strategy's exit_long condition triggers
2. **Stop Loss**: Price drops 3% from entry
3. **Market Filter Exit**: btc_trend() goes negative
4. **Trailing Stop** (optional): Lock in profits after 2% gain

---

## 6. Monitoring Dashboard Enhancements

### 6.1 New Metrics to Track

**Shadow Trading:**
- Total shadow equity
- Open positions
- Daily P&L
- Running Sharpe ratio
- Per-strategy performance

**Evolution:**
- Strategies in shadow pool
- Best/worst performer
- Avg generation when promoted
- Diversity metrics

**System:**
- Uptime percentage
- Candles processed
- LLM API usage/costs
- Error rates

### 6.2 Dashboard Output Example

```
======================================================================
CRYPTO EVOLUTION SYSTEM MONITOR
Time: 2025-12-15T02:00:00 UTC
======================================================================

📊 DATA STATUS
------------------------------------------
  Database: /app/crypto/data/candles.db
  Total candles: 450,000
    ✅ BTCUSDT: 150,000 candles (last update: 1 min ago)
    ✅ ETHUSDT: 150,000 candles (last update: 1 min ago)
    ✅ SOLUSDT: 150,000 candles (last update: 1 min ago)

💹 SHADOW TRADING
------------------------------------------
  ✅ Status: ACTIVE
  Paper Equity: $10,543.21 (+5.43%)
  Open Positions: 2
  Total Trades: 47
  Win Rate: 51.1%
  Sharpe Ratio: 1.23
  Max Drawdown: 4.2%

🌑 SHADOW POOL
------------------------------------------
  ✅ Active strategies: 4
  Best: MeanReversion_V12 (Sharpe: 1.45)
  Worst: Breakout_V3 (Sharpe: 0.62)

🧬 EVOLUTION STATUS
------------------------------------------
  ✅ Last run: 2 hours ago (success)
  Total runs: 15
  Success rate: 93%
  Strategies evolved: 127
  Promoted to shadow: 8

======================================================================
```

---

## 7. Risk Management (Phase 3)

### 7.1 Shadow Trading Limits

| Limit | Value | Enforcement |
|-------|-------|-------------|
| Max open positions | 5 | Hard limit in trader |
| Max exposure | 50% | Paper equity check |
| Max loss per day | 5% | Pause trading |
| Max loss per trade | 3% | Stop-loss |

### 7.2 Kill Switch Triggers

From CLAUDE.md, applied to shadow trading:

| Trigger | Action |
|---------|--------|
| Shadow DD > 5% in 1 hour | Pause new entries 1 hour |
| Shadow DD > 10% in 24 hours | Pause new entries 24 hours |
| Shadow DD > 15% from peak | Close all shadow positions |

### 7.3 Data Quality Gates

- **Missing candles > 5 min**: Pause trading, backfill gap
- **Price anomaly > 20%**: Flag, don't trade that candle
- **Zero volume**: Skip candle for signals

---

## 8. Timeline

### Week 1: Phase 3A + 3B
- Complete shadow trader implementation
- Deploy to Fly.io with supervisor
- Start 24/7 shadow trading

### Week 2: Phase 3C
- Set up monitoring and alerts
- Daily manual review of trades
- Fix any bugs discovered

### Weeks 3-4: Phase 3D
- Calibrate slippage model
- Tune friction parameters
- Re-evolve strategies with better friction

### Weeks 5-8: Phase 3E + Observation
- Implement strategy lifecycle
- Accumulate 100+ trades per strategy
- Weekly performance reviews
- Prepare for Phase 4 (live trading)

---

## 9. Exit Criteria (Ready for Phase 4)

**Phase 3 Complete When:**

- [ ] Shadow equity up >5% over 4 weeks
- [ ] Max drawdown < 10% maintained
- [ ] At least 3 strategies with 100+ trades and Sharpe > 1.0
- [ ] System uptime > 95% for 2 weeks
- [ ] Slippage model calibrated (backtest matches shadow within 20%)
- [ ] No critical bugs in 7 days
- [ ] Documentation complete

**Phase 4 Prerequisites:**
- [ ] Exchange API with trade permissions ready
- [ ] Risk capital allocated ($500-$1000 initial)
- [ ] Emergency procedures documented
- [ ] Kill switch tested on live exchange

---

## 10. Open Questions

### Q1: How Many Symbols to Trade?

**Options:**
- A) Start with 3 (BTCUSDT, ETHUSDT, SOLUSDT) — conservative
- B) Expand to 10 mid-caps — more opportunities
- C) Dynamic selection from top 30 — most flexible

**Recommendation:** Start with A (3 symbols), expand to B after 2 weeks if stable.

### Q2: Evolution Frequency?

**Options:**
- A) Daily at 2 AM UTC — continuous improvement
- B) Weekly — less compute, more stable strategies
- C) On-demand only — manual trigger

**Recommendation:** A (daily), but limit to 10 generations per run to control costs.

### Q3: LLM Provider for Phase 3?

**Current:** OpenAI gpt-4o (Phase 2)

**Considerations:**
- Anthropic Claude Sonnet may produce better strategies
- Cost comparison needed for daily runs
- Consider caching common mutations

**Recommendation:** Stay with OpenAI gpt-4o for cost efficiency, benchmark Claude Sonnet for quality.

---

## 11. Implementation Checklist

### Pre-Launch

- [ ] Shadow trader code complete and tested
- [ ] Process supervision configured
- [ ] Monitoring dashboard extended
- [ ] Alert webhooks configured
- [ ] 90 days historical data verified
- [ ] Initial strategy population in shadow pool

### Launch Day

- [ ] Deploy updated code to Fly.io
- [ ] Start supervisor
- [ ] Verify WebSocket connected
- [ ] Verify shadow trader processing signals
- [ ] Confirm first shadow trade logged
- [ ] Enable monitoring alerts

### Daily Operations

- [ ] Check monitoring dashboard
- [ ] Review overnight trades
- [ ] Check evolution run results
- [ ] Monitor equity curve
- [ ] Review any alerts

### Weekly Review

- [ ] Export shadow trade report
- [ ] Calculate weekly metrics
- [ ] Review strategy performance
- [ ] Decide on promotions/retirements
- [ ] Document findings

---

## Changelog

| Date | Change | Author |
|------|--------|--------|
| 12/09/2025 06:52 AM PST | Initial Phase 3 plan created | Claude |
| 12/09/2025 07:29 AM PST | **Phase 3A COMPLETE**: Implemented ShadowPoolManager for multi-strategy trading. Features: load strategies from shadow pool, per-strategy performance tracking, stop-loss enforcement, kill switch (5% hourly / 15% total DD), hot-reload support. Updated main.py with --shadow-pool flag. | Claude |
| 12/09/2025 09:04 AM PST | **Phase 3B COMPLETE**: Implemented process supervision and hot-reload. Created `supervisor.conf` for managing 3 processes (shadow_trader, scheduler, hot_reload). Added `hot_reload.py` file watcher with debounce. Updated Dockerfile to use supervisord as entrypoint. Main.py now checks for reload signal every ~50 candles. | Claude |
| 12/09/2025 09:13 AM PST | **Phase 3C COMPLETE**: Extended monitoring with paper equity tracking, webhook alerts (Slack/Discord), daily performance reports, and health check endpoint. New CLI: `--daily-report`, `--send-alert`, `--health-check`. Alert thresholds from CLAUDE.md. Fixed dataclass ordering bug in strategy_store.py. | Claude |
| 12/09/2025 09:23 AM PST | **Phase 3D COMPLETE**: Implemented slippage tracking and calibration. Extended TradeLog with candle OHLC and implied_slippage_pct. Added `get_slippage_analysis()` to monitoring with per-regime breakdown. Dashboard shows friction accuracy indicator. | Claude |
