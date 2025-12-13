# Forex Phase 1: Plumbing Implementation Plan

**Date:** 2025-12-11
**Status:** Planning

## 1. Objective

Establish the foundational "plumbing" for the Forex trading track. This involves setting up data ingestion from OANDA, reliable local storage, and a shadow trading loop that operates on livestreams.

**Success Criteria:**

- [ ] OANDA V20 Data Stream running for 48h+ without crash.
- [ ] Candles stored consistently in `data/candles_forex.db`.
- [ ] Shadow Trader executing "paper" trades based on random signals (sanity check).
- [ ] Latency < 500ms from Socket -> db -> Strategy.

## 2. Broker & Technology

- **Broker:** **OANDA** (V20 API).
  - _Reasoning:_ Excellent API documentation, robust Python wrappers (`v20` or `oandapyV20`), US-friendly, support for sub-accounts (good for hedging/shadow separation).
- **Pairs:** EUR/USD, GBP/USD, USD/JPY, USD/CHF (The Majors).
- **Data Store:** SQLite (`forex/data/candles.db`) - matching Crypto architecture.

## 3. Architecture Changes

We will verify the directory structure in `forex/` and populate it:

```
forex/
├── config.py                 # OANDA Creds, Pair Configs
├── main.py                   # Entry point (supervisor)
├── data/
│   ├── ingestion/
│   │   └── oanda_stream.py   # Connects to OANDA Stream API
│   └── storage/
│       └── repository.py     # Writes/Reads from DB
├── execution/
│   └── shadow/
│       └── trader.py         # Paper trading logic (Forex specific)
└── gene_pool_ext/            # Forex-specific indicators
    ├── primitives_volatility.py # e.g. ATR normalized by pip value
    └── primitives_macro.py      # Placeholders for News/Rate diffs
```

## 4. Implementation Steps

### Step 4.1: Configuration & Scaffolding

- Create `forex/config.py` using `pydantic-settings`.
- Setup logging in `forex/logs/`.

### Step 4.2: Data Pipeline (The "Heart")

- Implement `OandaStreamer` class.
  - Must handle: Connection drops, Heartbeats, converting ticks to 1-min candles.
  - _Note:_ OANDA streams _ticks_. We must aggregate them into 1m candles locally or poll the 5-second candle stream.
  - _Decision:_ Polling 5s candles is safer for consistency than local tick aggregation, OR we can stick to 1-minute polling if HFT isn't the goal.
  - _Better Approach:_ OANDA offers a streaming API for _Pricing_ (Ticks). For accurate 1m candles, we should subscribe to the Pricing Stream for "live" triggers, but fetch completed Candles via REST API every minute to ensure data integrity/correctness.

### Step 4.3: Storage Layer

- Copy/Adapt `crypto/data/storage/` logic.
- Schema: `candles_forex` table.

### Step 4.4: Shadow Execution

- Adapt `StrategyLifecycleManager` and `ShadowPoolManager` to work with Forex assets.
- Note: Forex has "Pip" cost model vs Crypto "Percentage".
  - Need `ForexFrictionModel`.

## 5. Risk & Validation

- **Validation Rule 1:** "No Data Gap > 2 minutes" (auto-restart).
- **Validation Rule 2:** Spread check (Don't trade if spread > 5 pips).

## 6. Timeline Estimate

- **Day 1:** Scaffolding + OANDA Connection + Streamer.
- **Day 2:** Storage + Candle integrity tests.
- **Day 3:** Shadow Trader adaptation + Dry Run.
