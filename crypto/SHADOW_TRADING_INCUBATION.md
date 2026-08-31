# Shadow Trading Incubation Tracker

## Current Status: ACTIVE

**Started**: 12/16/2025 03:10 PM PST (via pst-timestamp)
**Target End**: 12/23/2025 03:10 PM PST (7 days)
**Purpose**: Validate winning strategies on live data before real capital deployment

---

## Why We're Doing This

We ran LLM-driven evolutionary strategy search and found winning strategies:

1. **SOL VWAP Reversion V1** (Sharpe 2.52) - Gene Expression
   - Mean reversion on VWAP dips in BTC uptrend
   - 100% win rate on backtest (9 trades)
   - Works because SOL had +54% period return

2. **Momentum Continuation V1** (Sharpe 2.73) - Gene Expression
   - Buy pullbacks in confirmed uptrends with volume
   - 47.8% win rate, 69 trades
   - Trend-following approach

3. **ETH H1 Evolved V1** (Sharpe 1.32) - **NEW** Template Strategy
   - Template-based evolution (parameters evolved, not gene expressions)
   - 76.2% win rate on backtest (21 trades)
   - Entry threshold evolved to 0.60 (LLM found more selective = better)
   - H1 timeframe (60-minute candles)
   - Contrarian volume signal (negative weight in trending regime)
   - File: `winning_strategies/eth_h1_evolved_v1.json`
   - Runner: `python3 run_template_shadow.py --strategy=winning_strategies/eth_h1_evolved_v1.json`

The 7-day incubation validates these strategies work on LIVE data before risking real money.

---

## Daily Progress Log

### Day 1 (12/16/2025) ✅ ACTIVE
- [x] System launched at 03:14 PM PST
- [x] Discord notifications verified and working
- [x] Initial strategy signals observed
- Start time: 03:14 PM PST
- Notes:
  - Screen session `crypto_shadow` running
  - 10 strategies loaded (including SOL_VWAP_Reversion_V1, BTC_Momentum_Continuation_V1)
  - First trades generated within 1 minute of launch
  - Market regime: bear_calm
  - REST API 403 errors (geo-blocked) but WebSocket working fine
  - Initial trades:
    - ENTRY_LONG SOLUSDT @ $128.82 (evo_20251214_winner_btc)
    - ENTRY_LONG ETHUSDT @ $2,958.34 (sol_vwap_reversion_v1)

### Day 2 (12/17/2025)
- [x] ETH H1 Template Strategy added to incubation
- [x] Template shadow trader infrastructure created
- [ ] ETH strategy running in shadow mode (PENDING SCREEN SETUP)
- Notes:
  - Created `execution/shadow/template_trader.py` for template-based strategies
  - Created `run_template_shadow.py` for standalone template validation
  - ETH strategy successfully loads and connects to WebSocket
  - H1 timeframe aggregation implemented (60 1m candles -> 1 H1 candle)
  - Strategy parameters validated: entry_threshold=0.60, Sharpe=1.32, WR=76.2%

**To start ETH template shadow trading:**
```bash
screen -S eth_shadow
cd /Users/wolfgangschoenberger/Projects/Oil-Stonks
python3 crypto/run_template_shadow.py --strategy=winning_strategies/eth_h1_evolved_v1.json
# Ctrl+A, D to detach
```

### Day 3
- [ ] Mid-week checkpoint
- Trades:
- P&L:
- Win rate:
- Notes:

### Day 4
- [ ] Continued monitoring
- Trades:
- P&L:
- Notes:

### Day 5
- [ ] Strategy behavior check
- Trades:
- P&L:
- Notes:

### Day 6
- [ ] Pre-final review
- Trades:
- P&L:
- Notes:

### Day 7 - FINAL
- [ ] Incubation complete
- [ ] Review all metrics
- [ ] Decision: Promote to live or extend incubation
- Total trades:
- Total P&L:
- Final win rate:
- Max drawdown observed:
- Decision:

---

## Success Criteria (Must Pass ALL)

| Metric | Target | Day 7 Actual |
|--------|--------|--------------|
| Trades | > 5 | |
| Sharpe (live) | > 0.3 | |
| Win Rate | > 40% | |
| Max Drawdown | < 10% | |
| No kill switch triggers | 0 | |
| System uptime | > 95% | |

---

## Key Commands

### Gene Expression Pool (Original)
**Check status:**
```bash
tail -f crypto/logs/shadow_trades.jsonl | jq
```

**View pool stats:**
```bash
python3 -c "
from crypto.execution.shadow.pool_manager import ShadowPoolManager
pool = ShadowPoolManager()
import json
print(json.dumps(pool.get_stats(), indent=2))
"
```

**Stop gracefully:**
```bash
# Ctrl+C in terminal running main.py
# Or: pkill -f "python.*main.py.*shadow-pool"
```

### Template Shadow Trading (ETH H1 Strategy)
**Start ETH template shadow:**
```bash
screen -S eth_shadow
python3 crypto/run_template_shadow.py --strategy=winning_strategies/eth_h1_evolved_v1.json
# Ctrl+A, D to detach
```

**Check ETH trades:**
```bash
tail -f crypto/logs/shadow_trades.jsonl | jq 'select(.strategy_type == "template")'
```

**Stop ETH shadow:**
```bash
pkill -f "run_template_shadow"
```

---

## What To Do If Something Goes Wrong

### Kill Switch Triggered
1. Check Discord for alert details
2. Review logs: `cat crypto/logs/errors.log`
3. Wait for automatic resume (1 hour) or restart manually

### System Crashed
1. Check error logs
2. Restart: `python3 crypto/main.py --shadow-pool`
3. System will resume from last state

### Discord Not Working
1. Verify webhook URL in `.env`
2. Test: `python3 -c "from crypto.notifications import DiscordNotifier; d=DiscordNotifier('YOUR_URL'); d._send_sync([{'title':'Test'}])"`

---

## Post-Incubation Decision Tree

```
7 days complete?
├── YES: Check success criteria
│   ├── ALL PASS → Promote to live trading (Phase 2)
│   ├── PARTIAL → Extend incubation 7 more days
│   └── FAIL → Retire strategy, run new evolution
└── NO: Continue monitoring
```

---

## Context for Future Self

**Date Created**: 12/16/2025
**Created By**: Claude Code session
**Project**: Oil-Stonks Crypto Alpha System

This is Phase 1 validation. We're NOT trading real money yet - this is paper trading on live market data. The goal is to verify that strategies that worked in backtesting also work in real-time before deploying capital.

The two winning strategies came from:
- ~40 generations of LLM-driven evolution
- Walk-forward validation on 180 days of H4 data
- Multiple seed approaches tested (mean reversion, momentum, breakout)

SOL mean reversion worked because SOL was in a strong uptrend (+54%).
BTC mean reversion failed because BTC was in a downtrend (-50%).

---

**Last Updated**: 12/17/2025 09:22 AM PST (via pst-timestamp) - Day 2 - ETH Template Strategy Added
