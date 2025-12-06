# Crypto Alpha Generation System

## Project Overview

A systematic trading system for mid-cap cryptocurrency (Top 50-200 by market cap) using LLM-driven evolutionary search to discover and optimize trading strategies. Prioritizes **robustness over returns** through regime testing, shadow trading validation, and strict risk controls.

**Key Design Decisions:**
- **Long-only** for Phase 1 (no shorting until mastered)
- **Bybit** exchange (US-accessible, good API, 200+ altcoins)
- **Gene Pool constraint** — LLM assembles pre-validated primitives, not arbitrary code
- **Shadow trading** — Strategies must prove themselves on live data before real capital
- **Survival-first** — 50% max exposure, kill switch at 20% drawdown

## Current Phase

**Phase 1: Plumbing** — Build infrastructure that doesn't crash.

See: `docs/plans/2025-12-04-crypto-alpha-system-design.md` for full design.

## Tech Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.11+ |
| Data Storage | SQLite (MVP) → PostgreSQL |
| WebSocket | `websockets` or `ccxt` |
| Technical Analysis | `pandas-ta` |
| Backtesting | Custom lightweight engine |
| LLM API | Anthropic Claude or OpenAI |
| Process Management | `supervisor` or `systemd` |

## Directory Structure

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
│   └── /watchdog/           # Kill switch (SEPARATE PROCESS)
├── /logs/
│   ├── trades.log           # Trade state vectors (JSON)
│   └── errors.log           # Exceptions only (black swan log)
├── main.py
├── config.py
└── requirements.txt
```

## Critical Constraints

### Gene Pool Rules
- **Max 5 primitives per strategy** — Complexity limit prevents overfitting
- **Integer parameters only** — No hyper-tuning (14, not 14.231)
- **Normalized outputs** — All primitives return -1.0 to +1.0 (or bounded)
- **`btc_trend()` required** — All long entries must check BTC isn't dumping

### Risk Engine Rules
- **1% risk per trade** — Single trade can't hurt you
- **10% max position** — No concentration risk
- **5 max open positions** — Diversification
- **50% max exposure** — Always have dry powder
- **1 new position per 5 minutes** — Throttle correlated entries

### Kill Switch Triggers (MANDATORY)
| Trigger | Action |
|---------|--------|
| Drawdown > 5% in 1 hour | Close all, pause 1 hour |
| Drawdown > 10% in 24 hours | Close all, pause 24 hours |
| Drawdown > 20% from peak | **Full shutdown**, manual restart |
| Position loss > 3% equity | Force close (stop-loss failed) |
| Main process unresponsive > 60s | Kill and close all |

## Development Guidelines

### Data Quality
- **Flash crash filter:** Reject candles with >50% move
- **Volume filter:** Reject zero-volume candles
- **Reconnect protocol:** On ANY disconnect, pause trading → fetch 100 historical candles → recalculate indicators → resume

### Backtest Validity
- **Regime testing required:** Strategy must have Sharpe > 0.5 in 4/5 regimes (bull_calm, bull_volatile, bear_calm, bear_volatile, sideways)
- **Walk-forward validation:** Train months 1-3, test month 4, rolling
- **Incubation purgatory:** 7 days paper trading before shadow pool
- **Friction model:** 0.1% fee + 0.15% slippage = 0.25% per side

### Logging Standards
- `trades.log` — Trade state vectors as JSON (every signal, fill, exit)
- `errors.log` — **Exceptions only** (check every morning)
- Trade logs must include: timestamp, strategy_id, coin, signal, prices, gene expression, btc_trend value, market_regime

## Available Gene Pool Primitives

```python
# TREND
ema_trend(fast: int, slow: int) -> float      # +1.0 or -1.0
price_position(period: int) -> float          # (Price - EMA) / ATR, capped ±3.0

# MEAN REVERSION
norm_rsi(period: int) -> float                # (RSI - 50) / 50, range -1.0 to +1.0
bb_position(period: int, std: float) -> float # Position in BB, -1.0 to +1.0
bb_width_percentile(period: int) -> float     # Band width vs history, 0.0 to 1.0

# VOLUME
volume_intensity(period: int, threshold: float) -> float  # 1.0 if above threshold
vwap_distance() -> float                      # Z-score vs VWAP, capped ±3.0

# VOLATILITY
atr_regime(period: int) -> float              # +1.0 high, 0.0 normal, -1.0 low
atr_percentile(period: int) -> float          # Current ATR vs history, 0.0 to 1.0

# MARKET FILTER (MANDATORY for longs)
btc_trend(window: int) -> float               # +1.0 stable/rising, -1.0 dumping
```

## Strategy Output Format

```json
{
  "strategy_name": "MeanReversion_Pullback_V1",
  "entry_long": "btc_trend(60) >= 0 AND ema_trend(9,21) == 1.0 AND norm_rsi(14) < -0.4",
  "exit_long": "norm_rsi(14) > 0.6 OR ema_trend(9,21) == -1.0",
  "entry_short": null,
  "exit_short": null
}
```

## Phase 1 Success Criteria

Before moving to Phase 2 (Evolution/LLM):
- [ ] WebSocket stays connected for **48 hours without crashing**
- [ ] Indicators match TradingView within 0.1%
- [ ] Shadow trader logs correctly for 24+ hours
- [ ] Data quality filters catch bad candles
- [ ] Reconnect protocol works (disconnect → warm up → resume)

## Related Documents

- [Full Design Doc](docs/plans/2025-12-04-crypto-alpha-system-design.md) — Complete system design
- [ProFiT Research](docs/plans/2025-12-04-profit-research-analysis.md) — Evolutionary strategy research
- [ProFiT Review](docs/plans/2025-12-04-profit-review-findings.md) — Critical review findings

## Notes

- **Oil-Stonks design is paused** — See `docs/plans/2025-12-04-oil-stonks-design.md` for reference
- The "edge" in Phase 1 is not the LLM — it's a system that stays online when markets move
- Do NOT build Phase 2 until Phase 1 runs 48 hours without intervention
