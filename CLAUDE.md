# Systematic Alpha Generation Platform

Multi-asset trading system using LLM-driven evolutionary search to discover and optimize trading strategies. Prioritizes **robustness over returns** through regime testing, shadow trading validation, and strict risk controls.

## Active Trading Systems

**Equal Priority — Parallel Development Tracks:**

| System | Status | Location | Documentation |
|--------|--------|----------|---------------|
| **Crypto** | Phase 1 (Plumbing) | `/crypto/` | [CRYPTO.md](crypto/CRYPTO.md) |
| **Forex (4X)** | Planning / Design | `/forex/` | [FOREX.md](forex/FOREX.md) |

**Shared Infrastructure:** `/shared/` — Gene pool primitives, backtesting engine, evolution logic, risk management

**Note:** Both crypto and forex are **equally important strategic directions**. Crypto is further along in implementation (Phase 1), while forex is in planning/design phase. The goal is to develop robust infrastructure that works across both asset classes.

## Universal Design Principles

### Core Philosophy
- **Robustness over returns** — Systems must survive black swans
- **Shadow trading validation** — Prove on live data before real capital
- **Survival-first risk** — Conservative position sizing, aggressive kill switches
- **Gene Pool constraint** — LLM assembles pre-validated primitives, not arbitrary code
- **Regime testing required** — Strategies must work across market conditions

### Gene Pool Rules (Universal)
- **Max 5 primitives per strategy** — Complexity limit prevents overfitting
- **Integer parameters only** — No hyper-tuning (14, not 14.231)
- **Normalized outputs** — All primitives return -1.0 to +1.0 (or bounded)
- **Market filter required** — All directional entries must check broader market conditions

### Risk Engine Rules (Default — Override in Asset Config)
- **1% risk per trade** — Single trade can't hurt you
- **10% max position** — No concentration risk
- **5 max open positions** — Diversification enforcement
- **50% max exposure** — Always have dry powder
- **1 new position per 5 minutes** — Throttle correlated entries

### Kill Switch Framework (MANDATORY)
| Trigger | Action |
|---------|--------|
| Drawdown > 5% in 1 hour | Close all, pause 1 hour |
| Drawdown > 10% in 24 hours | Close all, pause 24 hours |
| Drawdown > 20% from peak | **Full shutdown**, manual restart required |
| Single position loss > 3% equity | Force close (stop-loss failed) |
| Main process unresponsive > 60s | Kill and close all positions |

## Shared Tech Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.11+ |
| Data Storage | SQLite (MVP) → PostgreSQL |
| Technical Analysis | `pandas-ta` |
| Backtesting | Custom lightweight engine (`/shared/evolution/backtester/`) |
| LLM API | Anthropic Claude or OpenAI |
| Process Management | `supervisor` or `systemd` |

## Universal Development Guidelines

### Data Quality Standards
- **Anomaly detection:** Reject candles with abnormal moves (asset-specific thresholds)
- **Volume validation:** Reject zero-volume or suspicious volume candles
- **Reconnect protocol:** On ANY disconnect → pause trading → fetch historical data → recalculate indicators → resume
- **Clock sync:** UTC everywhere, no local timezone conversions

### Backtest Validity Requirements
- **Regime testing required:** Sharpe > 0.5 in 4/5 market regimes
  - Bull calm, bull volatile, bear calm, bear volatile, sideways
- **Walk-forward validation:** Rolling train/test windows
- **Incubation purgatory:** Minimum 7 days paper trading before shadow pool
- **Friction modeling:** Include realistic fees + slippage (asset-specific)

### Logging Standards
- **Trade logs** (`trades.log`) — JSON state vectors for every signal/fill/exit
- **Error logs** (`errors.log`) — **Exceptions only** (check every morning)
- **Required fields:** timestamp, strategy_id, asset, signal, prices, gene_expression, market_filter_value, market_regime

### Trade Log Schema (Universal)
```json
{
  "timestamp": "2025-01-15T14:23:45.123Z",
  "strategy_id": "strat_abc123",
  "asset_class": "crypto",  // or "forex"
  "asset": "BTC-USDT",  // or "EUR/USD"
  "signal": "entry_long",
  "entry_price": 42350.50,
  "position_size": 0.05,
  "gene_expression": {
    "market_filter_60": 1.0,
    "ema_trend_9_21": 1.0,
    "norm_rsi_14": -0.42
  },
  "market_regime": "bull_calm",
  "market_filter": "market_filter(60) >= 0"
}
```

## Shared Gene Pool Primitives

These primitives work across all asset classes (located in `/shared/engine/gene_pool/`):

```python
# TREND
ema_trend(fast: int, slow: int) -> float      # +1.0 or -1.0
price_position(period: int) -> float          # (Price - EMA) / ATR, capped ±3.0

# MEAN REVERSION
norm_rsi(period: int) -> float                # (RSI - 50) / 50, range -1.0 to +1.0
bb_position(period: int, std: float) -> float # Position in Bollinger Bands
bb_width_percentile(period: int) -> float     # Band width vs historical

# VOLUME
volume_intensity(period: int, threshold: float) -> float
vwap_distance() -> float                      # Z-score vs VWAP

# VOLATILITY
atr_regime(period: int) -> float              # +1.0 high, 0.0 normal, -1.0 low
atr_percentile(period: int) -> float          # Current ATR vs history
```

**Asset-Specific Primitives:**
- Crypto: `btc_trend()`, `funding_rate_regime()`, `btc_dominance_trend()` — See [CRYPTO.md](crypto/CRYPTO.md)
- Forex: TBD (DXY filter, interest rate differential, risk-on/risk-off) — See [FOREX.md](forex/FOREX.md)

## Strategy Output Format (Universal)

```json
{
  "strategy_name": "MeanReversion_Pullback_V1",
  "asset_class": "crypto",  // or "forex"
  "entry_long": "market_filter(60) >= 0 AND ema_trend(9,21) == 1.0 AND norm_rsi(14) < -0.4",
  "exit_long": "norm_rsi(14) > 0.6 OR ema_trend(9,21) == -1.0",
  "entry_short": null,  // Enable per asset class
  "exit_short": null
}
```

## Directory Structure

```
/Oil-Stonks/
├── /shared/                 # Cross-asset infrastructure
│   ├── /engine/
│   │   ├── /gene_pool/     # Universal primitives (EMA, RSI, ATR, etc.)
│   │   └── /strategy_logic/ # Strategy parsing framework
│   ├── /evolution/
│   │   ├── /backtester/    # Historical simulation
│   │   ├── /fitness/       # Sharpe, regime calculations
│   │   └── /mutator/       # LLM prompts and parsing
│   └── /risk/
│       └── /watchdog/      # Kill switch logic
│
├── /crypto/                 # Crypto-specific (see CRYPTO.md)
│   ├── CRYPTO.md
│   ├── /data/              # Bybit WebSocket, storage
│   ├── /execution/         # Shadow + live trading
│   ├── /engine/gene_pool/  # Crypto-specific primitives (btc_trend, etc.)
│   ├── /engine/strategy_logic/  # Crypto parser with primitive registry
│   ├── /logs/
│   ├── config.py
│   └── main.py
│
├── /forex/                  # Forex-specific (see FOREX.md)
│   ├── FOREX.md
│   ├── /data/              # Forex data feeds (TBD)
│   ├── /execution/         # Forex broker API (TBD)
│   ├── /gene_pool_ext/     # Forex-specific primitives (TBD)
│   ├── /logs/
│   ├── config.py           # Placeholder
│   └── main.py             # Placeholder
│
├── /docs/
│   ├── /plans/
│   │   ├── crypto-alpha-system-design.md
│   │   └── (forex design TBD)
│   └── shared-architecture.md (future)
│
├── CLAUDE.md               # This file - universal principles
└── requirements.txt        # Shared dependencies
```

## Development Workflow

### Working on Asset-Specific Features
When working on crypto or forex features, reference both:
1. **This file (CLAUDE.md)** — Universal principles and shared infrastructure
2. **Asset-specific file** — Implementation details
   - Crypto: [crypto/CRYPTO.md](crypto/CRYPTO.md)
   - Forex: [forex/FOREX.md](forex/FOREX.md)

### Working on Shared Infrastructure
Changes to `/shared/` affect both systems:
- Test against both crypto and forex use cases (when forex is implemented)
- Maintain asset-agnostic interfaces
- Document breaking changes in both CRYPTO.md and FOREX.md

### Agent-Driven Development
- **Parallel work:** Crypto and forex agents can work simultaneously on `/crypto/` and `/forex/`
- **Shared work:** Extract common patterns to `/shared/` when identified
- **Codex delegation:** Use `/handoffcodex` for mechanical refactoring across systems
  - Example: `/handoffcodex "update all imports to use shared/ primitives"`
  - Example: `/handoffcodex "extract common backtesting logic to shared/evolution/backtester"`

## Phase Gating (Per Asset Class)

Each asset class progresses independently through phases:

**Phase 1: Plumbing** — Infrastructure stability
- [ ] Data pipeline runs 48+ hours without crashes
- [ ] Indicators match reference platform within 0.1%
- [ ] Shadow trader logs correctly for 24+ hours
- [ ] Data quality filters working
- [ ] Reconnect protocol tested

**Phase 2: Evolution** — LLM strategy generation
- Not started for any asset class

**Status:**
- **Crypto:** Phase 1 in progress
- **Forex:** Planning / design phase (Phase 0)

See asset-specific docs for detailed success criteria.

## Related Documents

### Crypto
- [Crypto System Design](docs/plans/2025-12-04-crypto-alpha-system-design.md)
- [Phase 1 Implementation Plan](docs/plans/2025-12-05-phase1-implementation-plan.md)
- [ProFiT Research](docs/plans/2025-12-04-profit-research-analysis.md)
- [ProFiT Review](docs/plans/2025-12-04-profit-review-findings.md)

### Forex
- Design documents TBD (planning phase)

### General
- [Oil-Stonks Design (Paused)](docs/plans/2025-12-04-oil-stonks-design.md) — Original oil trading concept

## Notes

- **Both crypto and forex are equally important** — Different phases, same priority
- The "edge" in Phase 1 is not the LLM — it's systems that stay online when markets move
- Do NOT build Phase 2 until Phase 1 runs 48 hours without intervention
- Each asset class maintains independent phase progression
- Shared infrastructure should be extracted as common patterns emerge
