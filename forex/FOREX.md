# Forex (4X) Alpha Generation System

**Parent Doc:** [../CLAUDE.md](../CLAUDE.md) — Universal principles and shared infrastructure

## Status: Planning / Design Phase

**Important:** Forex is an **equally important strategic direction** alongside crypto. While crypto is further along in implementation (Phase 1), forex represents significant potential for systematic alpha generation. This document serves as a placeholder for forex-specific design and will be expanded as we formalize the approach.

## Why Forex?

Potential advantages identified through community feedback (Grok/X quant discussions):

- **Deeper liquidity** — Major pairs (EUR/USD, GBP/USD, etc.) have tighter spreads and better execution
- **Lower volatility** — More predictable regime characteristics compared to crypto
- **Macro-driven** — Strong correlation with interest rates, economic data, central bank policy
- **24/5 markets** — Less weekend gap risk than crypto
- **Established infrastructure** — Mature brokers, regulatory frameworks, data providers

**[*TO-DO*]** — Incorporate specific feedback from Grok discussion about forex edge opportunities

## Forex-Specific Considerations (Preliminary)

### Broker/Exchange Options
- **OANDA** — Good API, US-accessible, reasonable spreads
- **Interactive Brokers** — Institutional-grade, excellent data, complex API
- **Forex.com** — US retail-friendly, decent spreads
- **Oanda fxTrade Practice** — Paper trading environment

**[*TO-DO*]** — Evaluate broker options, compare spreads, API quality, backtesting data availability

### Target Currency Pairs (Initial Thoughts)
- **Majors:** EUR/USD, GBP/USD, USD/JPY, USD/CHF
- **Minors:** EUR/GBP, EUR/JPY, GBP/JPY
- **Exotics:** TBD (higher spreads, but potentially more exploitable)

Focus on majors for Phase 1 due to liquidity and lower friction.

### Forex-Specific Gene Pool Primitives (Conceptual)

In addition to shared primitives, forex would benefit from:

```python
# MARKET FILTER (Forex equivalent of btc_trend)
dxy_trend(window: int) -> float
  # US Dollar Index trend
  # +1.0 = USD strengthening, -1.0 = USD weakening
  # Critical for USD-based pairs

risk_sentiment(window: int) -> float
  # Risk-on/risk-off regime indicator
  # Could use VIX, stock market correlation
  # +1.0 = risk-on (carry trades), -1.0 = risk-off (flight to safety)

interest_rate_differential(pair: str) -> float
  # Central bank rate differential
  # Drives carry trade dynamics

# TIME-BASED (Forex-specific)
session_filter() -> str
  # "asian", "london", "nyc", "overlap"
  # Different volatility/trend characteristics by session

news_proximity(hours: int) -> bool
  # Avoid trading near major economic releases (NFP, FOMC, etc.)
  # Requires economic calendar integration
```

**[*TO-DO*]** — Research and formalize forex-specific primitives based on market microstructure

### Forex Risk Parameters (Preliminary)

Expected adjustments from universal defaults:

| Parameter | Forex Value (Est.) | Rationale |
|-----------|-------------------|-----------|
| Max position | 15-20% | Lower volatility than crypto |
| Position risk | 0.5-1% | Standard for forex |
| Max exposure | 50% | Same as crypto |
| Leverage | 1-5x | Use cautiously (retail accounts often offer 50x+) |
| Stop-loss | -1.5% to -2% | Tighter than crypto due to lower vol |

**[*TO-DO*]** — Refine risk parameters based on historical forex volatility analysis

### Forex Friction Model (Preliminary)

**Estimated Per-Trade Costs:**
- Spread: 0.5-2 pips on EUR/USD ≈ 0.005-0.02% (varies by broker, session)
- Commission: 0.00% (some brokers) to 0.005% (IBKR-style commission model)
- Slippage: 0.01-0.05% (minimal on majors, higher during news)
- **Estimated total friction:** 0.02-0.07% per side ≈ **0.04-0.14% round-trip**

Much lower than crypto (0.41%), which could support higher-frequency strategies.

**[*TO-DO*]** — Get real broker quotes and measure actual slippage during different sessions

## Forex Market Regimes (Conceptual)

Unlike crypto (BTC-driven), forex regimes are macro-driven:

| Regime | Driver | Characteristics |
|--------|--------|-----------------|
| **risk_on** | Global growth optimism | Carry trades strong, USD weak vs. commodity currencies |
| **risk_off** | Global uncertainty | Flight to USD, JPY, CHF |
| **trending** | Strong directional move (rate hikes, policy divergence) | Momentum strategies excel |
| **ranging** | Low volatility, no clear driver | Mean-reversion, breakout traps |
| **volatility_spike** | Major news events (NFP, FOMC, geopolitical) | Avoid or trade with tight stops |

**[*TO-DO*]** — Formalize regime detection logic, backtest across different macro environments

## Data & Infrastructure (Planning)

### Required Data
- **OHLC candles** — 1-minute to 1-day (depending on strategy frequency)
- **Tick data** (optional) — For more precise backtesting
- **Economic calendar** — NFP, FOMC, ECB, BOE, BOJ events
- **Interest rate data** — Central bank policy rates
- **COT reports** (optional) — Commitment of Traders (positioning data)

**[*TO-DO*]** — Identify data sources (broker APIs vs. third-party like Bloomberg, Quandl)

### Execution Considerations
- **Session timing** — Asian (low vol), London (high vol), NYC (high vol), overlap periods
- **Rollover/Swap fees** — Holding overnight incurs interest differential charges
- **News blackout periods** — Pause trading 15 min before/after major releases

**[*TO-DO*]** — Design session-aware execution logic

## Forex Directory Structure (Placeholder)

```
/forex/
├── FOREX.md               # This file
├── /data/
│   ├── /ingestion/        # Broker WebSocket/REST clients (TBD)
│   └── /storage/          # SQLite/Parquet (same as crypto)
├── /execution/
│   ├── /shadow/           # Paper trading (broker testnet)
│   └── /live/             # Live broker API (Phase 2+)
├── /gene_pool_ext/        # Forex-specific primitives (DXY, interest diff, etc.)
├── /logs/
│   ├── trades.log
│   └── errors.log
├── config.py              # Forex-specific config (TBD)
└── main.py                # Entry point (TBD)
```

**Shared Infrastructure:** Uses `/shared/engine/gene_pool/` for universal primitives (EMA, RSI, ATR, etc.)

## Next Steps for Forex

### Phase 0: Planning & Research
- [ ] Finalize broker selection (OANDA vs. IB vs. Forex.com)
- [ ] Review Grok/X discussion — extract concrete edge ideas
- [ ] Research forex market microstructure (session effects, news impact, etc.)
- [ ] Define forex-specific primitives (DXY filter, interest differential, etc.)
- [ ] Acquire historical forex data for backtesting
- [ ] Write detailed forex system design doc (equivalent to crypto's 2025-12-04 design)

### Phase 1: Plumbing (Future)
- [ ] Implement broker WebSocket/REST client
- [ ] Build forex-specific primitives
- [ ] Adapt shadow trader for forex
- [ ] Validate indicators match broker's charts
- [ ] Test reconnect protocol
- [ ] Run 48-hour stability test

**Timeline:** TBD based on crypto Phase 1 completion and resource availability

## Related Forex Documents

**[*TO-DO*]** — Create forex design documents as planning progresses:
- `docs/plans/forex-alpha-system-design.md` — Full architecture (TBD)
- `docs/plans/forex-market-research.md` — Edge analysis from Grok discussion (TBD)

## Notes

- **Forex is equally important to crypto** — Just at an earlier stage
- Leverage shared infrastructure (gene pool, backtesting, evolution) to accelerate development
- Crypto learnings (reconnect protocol, shadow trading, regime testing) directly applicable
- Lower friction could enable higher-frequency strategies than crypto
- Different edge sources (macro vs. technical inefficiencies)

**Current Priority:** Finish crypto Phase 1, then allocate resources to forex planning/implementation in parallel.
