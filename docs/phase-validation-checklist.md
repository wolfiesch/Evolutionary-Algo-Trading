# Phase Validation Checklist

Systematic validation gates for each asset class. A phase is only complete when ALL criteria pass.

---

## Crypto System

### Phase 1: Plumbing ✅ COMPLETE
> Infrastructure stability - system stays online when markets move

| Criteria | Status | Evidence |
|----------|--------|----------|
| Data pipeline runs 48+ hours without crashes | ✅ | Production logs show multi-day runs |
| Indicators match reference platform within 0.1% | ✅ | Validated against TradingView |
| Shadow trader logs correctly for 24+ hours | ✅ | Trade logs in `crypto/logs/` |
| Data quality filters working | ✅ | `CandleValidator` in place |
| Reconnect protocol tested | ✅ | WebSocket reconnection logic implemented |

### Phase 2: Evolution 🔄 IN PROGRESS
> LLM-driven strategy generation and validation

| Criteria | Status | Evidence |
|----------|--------|----------|
| Walk-forward backtester operational | ✅ | `WalkForwardValidator` tested |
| Regime testing implemented | ✅ | 5-regime classification working |
| LLM mutation generates valid strategies | ✅ | `StrategyGenerator` + `parameter_mutation` |
| Template evolution wired up | ✅ | `evolve_template.py` created |
| 10+ strategies with Sharpe > 0.5 | ⏳ | Evolution runs in progress |
| Best strategy Sharpe > 1.0 in walk-forward | ⏳ | Pending evolution results |

### Phase 3: Shadow Trading Validation ⏳ NOT STARTED
> Prove strategies work on live data before real capital

| Criteria | Status | Evidence |
|----------|--------|----------|
| Shadow pool running 7+ days | ⏳ | - |
| Realized P&L within 20% of backtest | ⏳ | - |
| No unexpected drawdowns > 5% | ⏳ | - |
| Kill switches tested under simulated stress | ⏳ | - |
| Trade execution latency < 5s | ⏳ | - |

### Phase 4: Live Trading 🔒 BLOCKED
> Real capital deployment (requires Phase 3 sign-off)

| Criteria | Status | Evidence |
|----------|--------|----------|
| Phase 3 complete | 🔒 | Blocked |
| Risk limits configured | ⏳ | - |
| Kill switches armed | ⏳ | - |
| Monitoring dashboard live | ⏳ | - |
| Initial capital allocated | ⏳ | - |

---

## Equities System

### Phase 1: Data Infrastructure ✅ COMPLETE
> EDGAR integration and market data pipeline

| Criteria | Status | Evidence |
|----------|--------|----------|
| EDGAR API integration working | ✅ | `edgar_client.py` tested |
| Daily price data ingestion | ✅ | `market_data.py` with yfinance |
| Fundamental primitives operational | ✅ | insider_intensity, revenue_cagr, etc. |
| Universe management working | ✅ | `UniverseManager` implemented |
| Data quality validation | ✅ | Candle validation in place |

### Phase 2: Backtesting Framework ✅ COMPLETE
> Walk-forward validation with fundamental signals

| Criteria | Status | Evidence |
|----------|--------|----------|
| Walk-forward backtester operational | ✅ | `WalkForwardValidator` tested |
| Fundamental signals integrated | ✅ | `EquitiesEvaluator` with fundamentals |
| Regime classification working | ✅ | SPY trend + VIX regime |
| Friction model realistic | ✅ | Commission + slippage modeled |
| Position sizing correct | ✅ | Risk-based sizing implemented |

### Phase 3: Strategy Evolution ✅ COMPLETE
> LLM-driven strategy generation

| Criteria | Status | Evidence |
|----------|--------|----------|
| Strategy generator operational | ✅ | `generator.py` with LLM |
| Evolution engine working | ✅ | Selection, crossover, mutation |
| Fitness scoring validated | ✅ | Walk-forward fitness calculation |
| 5+ viable strategies generated | ✅ | Strategies in `strategies/` |

### Phase 4: Shadow Trading 🔄 IN PROGRESS
> Paper trading validation

| Criteria | Status | Evidence |
|----------|--------|----------|
| Shadow trader operational | ✅ | `EquitiesShadowTrader` implemented |
| Position tracker working | ✅ | Integration tests pass (16/16) |
| Trade logging complete | ✅ | JSON trade logs |
| 7+ days shadow trading | ⏳ | Needs extended run |
| P&L tracking accurate | ✅ | Reconciliation tests pass |

### Phase 5: Live Trading Infrastructure 🔄 IN PROGRESS
> Broker integration (Alpaca)

| Criteria | Status | Evidence |
|----------|--------|----------|
| Broker adapter abstraction | ✅ | `BrokerAdapter` protocol |
| Alpaca integration | ✅ | `AlpacaAdapter` implemented |
| Risk watchdog operational | ✅ | Kill switch tests pass (16/16) |
| Position sync working | ⏳ | Needs validation |
| Order execution tested | ⏳ | Paper trading mode |

### Phase 6: Live Trading 🔒 BLOCKED
> Real capital deployment (requires Phase 4+5 validation)

| Criteria | Status | Evidence |
|----------|--------|----------|
| Phase 4 shadow validation complete | 🔒 | Blocked |
| Phase 5 infrastructure validated | 🔒 | Blocked |
| Risk limits configured | ⏳ | - |
| Initial capital allocated | ⏳ | - |

---

## Validation Sign-off Protocol

### Before advancing to next phase:
1. All criteria in current phase must show ✅
2. Document evidence (log files, test results, screenshots)
3. Get explicit sign-off before proceeding
4. Record sign-off date and any caveats

### Sign-off Log

| System | Phase | Date | Notes |
|--------|-------|------|-------|
| Crypto | Phase 1 | 2025-12 | Infrastructure stable |
| Equities | Phase 1 | 2025-12 | EDGAR + market data working |
| Equities | Phase 2 | 2025-12 | Backtesting validated |
| Equities | Phase 3 | 2025-12 | Evolution producing strategies |

---

*Last updated: 12/16/2025 02:55 PM PST (via pst-timestamp)*
