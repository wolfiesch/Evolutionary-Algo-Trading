# Evolution Session Handoff - 12/14/2025 09:48 PM PST

## Executive Summary

This session focused on running LLM-driven strategy evolutions for crypto trading (BTC, ETH, SOL), dealing with API quota exhaustions across multiple providers, and optimizing token usage. We discovered key empirical insights about cross-asset vs self-referential market filters and implemented significant token optimizations.

---

## Key Empirical Findings

### 1. Cross-Asset Filters Beat Self-Referential for Altcoins

**Critical Discovery**: Using BTC's trend as a filter (`btc_trend`) works better for altcoins than using the asset's own trend (`asset_trend`).

| Asset | Filter Used | Sharpe Ratio | Result |
|-------|-------------|--------------|--------|
| SOL | `btc_trend` | 2.73 | SUCCESS |
| SOL | `asset_trend` | -10.0 | FAILED |
| ETH | `asset_trend` | -10.0 | FAILED |

**Code Change**: Updated `crypto/evolve.py:77-99` to automatically use `btc_trend` for altcoins:
```python
def get_market_filter_name(symbol: str) -> str:
    if symbol.upper().startswith("BTC"):
        return "asset_trend"  # Same as btc_trend for BTC
    return "btc_trend"  # Altcoins use cross-asset BTC filter
```

### 2. Simple Strategies Outperform Complex Ones

**BTC Winner** (Sharpe 3.49):
```json
{
  "entry_long": "btc_trend(60) >= 0 AND ema_trend(14, 60) > 0",
  "exit_long": "norm_rsi(14) > 0.7 OR price_position(14) > 2.0"
}
```
- Only 2 entry conditions
- 49 trades, 27% win rate, 1.7% max drawdown

**SOL Winner** (Sharpe 2.73):
- 5 entry conditions
- 42 trades, 31% win rate

**Insight**: Fewer conditions = more trades = less overfitting.

### 3. Genetic Transplantation Requires Adaptation

Tested BTC winner strategy directly on ETH/SOL:

| Asset | Sharpe (direct transplant) |
|-------|---------------------------|
| BTC | 3.29 (original asset) |
| ETH | -1.18 (FAILS) |
| SOL | -2.00 (FAILS) |

**Conclusion**: Strategies are asset-specific. Seeding helps evolution start from a proven structure, but parameters need adaptation per asset.

---

## What Was Accomplished

### Successful Evolutions
- **BTC**: Score 3.0, Sharpe 3.49 (15 generations)
- **SOL**: Score 2.733, Sharpe 2.73 (29 generations)

### Deployed to Production
- Winners added to shadow pool: `crypto/logs/shadow_pool/`
  - `shadow_evo_20251215_SimpleTrendFollower_BTC_Winner.json`
  - `shadow_evo_20251215_MomentumContinuation_SOL_Winner.json`
- Deployed to Fly.io (`crypto-alpha` app)
- Shadow trading running with 7 strategies

### Token Optimization (Recent Work)

**Before → After:**
| Metric | Before | After | Savings |
|--------|--------|-------|---------|
| Model | `gpt-4o` | `gpt-5.2-chat-latest` | Latest & efficient |
| Generation prompt | ~450 tokens | ~157 tokens | 65% |
| Mutation prompt | ~300 tokens | ~114 tokens | 62% |
| Crossover prompt | ~400 tokens | ~100 tokens | 75% |
| max_tokens | 1024 | 300 | 70% |
| Prompt file size | 9357 bytes | 5473 bytes | 42% |

**Files Modified:**
- `shared/evolution/mutator/llm_client.py` - Updated model to `gpt-5.2-chat-latest`, reduced max_tokens
- `shared/evolution/mutator/prompts.py` - Compact prompts

### Genetic Transplantation Feature

Added `--seed` flag to `crypto/evolve.py` for seeding evolutions with a known winner:
```bash
python3 crypto/evolve.py --symbol ETHUSDT --full --seed crypto/logs/shadow_pool/shadow_evo_20251215_SimpleTrendFollower_BTC_Winner.json
```

**Files Modified:**
- `crypto/evolve.py:18-19` - Added `import json`
- `crypto/evolve.py:837-867` - Seed strategy loading logic
- `crypto/evolve.py:950-955` - Added `--seed` argument

### Database Sync
- Synced `candles.db` from Fly.io to local
- Data coverage: BTC (Feb 2024 - Dec 2025), ETH (~83 days), SOL (~1 month)

---

## Current Blockers

### API Quota Exhaustion (ALL PROVIDERS)

| Provider | Status | Error |
|----------|--------|-------|
| OpenAI | EXHAUSTED | "insufficient_quota" |
| Anthropic | EXHAUSTED | "credit balance too low" |
| Gemini | EXHAUSTED | Free tier rate limited |

**To Resume Evolutions:**
1. Add credits to OpenAI: https://platform.openai.com/settings/billing
2. OR add credits to Anthropic: https://console.anthropic.com/
3. OR wait for quota reset

---

## File Changes Summary

### `shared/evolution/mutator/llm_client.py`
- Line 5: Updated docstring
- Line 34: `max_tokens = 300` (was 1024)
- Line 49: `model = "gpt-5.2-chat-latest"` (was gpt-4o)
- Line 289: Same model update in `create_default_client()`
- Lines 208-238: Added `GeminiClient` class
- Line 256: Added Gemini to factory function
- Lines 273-304: Updated `create_default_client()` priority: Anthropic > OpenAI > Gemini

### `shared/evolution/mutator/prompts.py`
- Lines 7-27: Compact `STRATEGY_GENERATION_PROMPT` (~157 tokens)
- Lines 29-41: Compact `MUTATION_PROMPT` (~114 tokens)
- Lines 65-76: Compact `CROSSOVER_PROMPT` (~100 tokens)

### `crypto/evolve.py`
- Line 19: Added `import json`
- Lines 77-99: Updated `get_market_filter_name()` to use `btc_trend` for altcoins
- Lines 837-867: Seed strategy loading in `run_full_evolution()`
- Lines 950-955: Added `--seed` CLI argument

---

## Running Services

### Fly.io (`crypto-alpha`)
- **Shadow Trader**: Running
- **Scheduler**: Running
- **Dashboard**: Running on port 8080
- **Hot Reload**: Running

Check status: `fly logs -a crypto-alpha --no-tail | tail -30`

### Local
- No evolutions currently running (killed due to quota)
- Database: `crypto/data/candles.db` (synced from Fly.io)

---

## Next Steps (Priority Order)

### T0: Restore API Access
1. Add billing to OpenAI or Anthropic
2. Test with: `python3 -c "from shared.evolution.mutator.llm_client import create_default_client; c = create_default_client(); print(c.generate('test'))"`

### T1: Run Seeded Evolutions
Once API works:
```bash
# ETH with BTC winner seed
python3 crypto/evolve.py --symbol ETHUSDT --generations 15 --population 10 --full \
  --seed crypto/logs/shadow_pool/shadow_evo_20251215_SimpleTrendFollower_BTC_Winner.json \
  --checkpoint-dir /tmp/evo_eth_seeded

# SOL with BTC winner seed
python3 crypto/evolve.py --symbol SOLUSDT --generations 12 --population 8 --full \
  --seed crypto/logs/shadow_pool/shadow_evo_20251215_SimpleTrendFollower_BTC_Winner.json \
  --checkpoint-dir /tmp/evo_sol_seeded
```

### T2: Debug Score=0.000 Analysis
Gemini suggested adding debug capability to understand WHY strategies fail (stops hit? no entries? fees?). Not yet implemented.

### T3: More Historical Data
ETH only has ~83 days of data. Consider backfilling more via Fly.io (bypasses geo-blocking).

---

## Useful Commands

```bash
# Check evolution logs
tail -f /tmp/evolution_*.log

# Kill all evolutions
pkill -f "evolve.py"

# Test LLM connection
python3 -c "from shared.evolution.mutator.llm_client import create_default_client; print(create_default_client().config.model)"

# Check Fly.io status
fly status -a crypto-alpha
fly logs -a crypto-alpha --no-tail | tail -50

# Sync DB from Fly.io
fly sftp get /data/candles.db crypto/data/candles_fly.db -a crypto-alpha

# Test strategy transplantation
python3 /tmp/test_transplant.py  # (file exists from this session)
```

---

## Session Insights from Gemini Review

Gemini provided critique on our approach:

1. **Data Island Problem**: We had 90-day data on Fly.io but only 24-day locally. **FIXED** - synced DB.

2. **Blind Debugging**: We saw Score=0.000 for hours without investigating why. **NOT YET FIXED** - need debug mode.

3. **Re-inventing the Wheel**: Found winning BTC structure but kept generating random populations. **FIXED** - added `--seed` flag for genetic transplantation.

---

## Git Status

Uncommitted changes:
- `crypto/evolve.py` (seed feature, btc_trend filter fix)
- `shared/evolution/mutator/llm_client.py` (Gemini support, GPT-5.2, token optimization)
- `shared/evolution/mutator/prompts.py` (compact prompts)

Consider committing with:
```bash
git add -A && git commit -m "feat: Add genetic transplantation, optimize LLM tokens, fix altcoin filters"
```

---

*Document created: 12/14/2025 09:48 PM PST (via pst-timestamp)*
