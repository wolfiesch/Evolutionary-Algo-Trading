# Shadow Trading Deployment Guide

## Overview

This guide explains how to deploy winning strategies to shadow trading (paper trading on live data).

## Current Winning Strategies

### 1. SOL VWAP Reversion V1
**Status**: DEPLOYED to shadow pool (12/16/2025 02:33 PM PST via pst-timestamp)

**Performance** (Walk-Forward Backtest on H4, 180 days):
- Sharpe Ratio: 2.52
- Win Rate: 100% (9/9 trades)
- Max Drawdown: 0.6%
- Walk-Forward Score: 1.388

**Strategy Logic**:
```
Entry:  btc_trend(60) >= 0 AND vwap_distance(20) < -1.0 AND norm_rsi(14) < -0.1
Exit:   vwap_distance(20) > -0.2
```

**Deployment File**: `/crypto/logs/shadow_pool/sol_vwap_reversion_v1.json`

---

## Deployment Process

### Step 1: Verify Strategy File Format

Ensure your strategy JSON has the required fields:
```json
{
  "strategy_name": "Strategy_Name",
  "strategy_id": "unique_strategy_id",
  "entry_long": "condition_expression",
  "exit_long": "condition_expression",
  "entry_short": null,
  "exit_short": null,
  "target_symbols": ["SYMBOL"],
  "backtest_sharpe": 0.0,
  "deployment_status": "shadow_trading_active"
}
```

### Step 2: Deploy to Shadow Pool

Copy the strategy file to the shadow pool directory:
```bash
cp crypto/winning_strategies/your_strategy.json crypto/logs/shadow_pool/your_strategy.json
```

The `ShadowPoolManager` automatically loads all JSON files from this directory on startup.

### Step 3: Launch Shadow Trading

#### Option A: Shadow Pool Mode (Recommended - runs ALL strategies)
```bash
cd crypto
python main.py --shadow-pool
```

This will:
- Load all strategies from `logs/shadow_pool/`
- Monitor BTC, ETH, and SOL by default (Phase 3 symbols)
- Paper trade with $10,000 initial equity
- Apply realistic friction (0.25% per side)
- Log all trades to `logs/shadow_trades.jsonl`

#### Option B: Shadow Pool with Custom Symbols
```bash
python main.py --shadow-pool --symbols BTCUSDT,ETHUSDT,SOLUSDT,XRPUSDT
```

#### Option C: Shadow Pool with All 29 Symbols
```bash
python main.py --shadow-pool --all-symbols
```

### Step 4: Monitor Performance

**Real-time logs**:
```bash
tail -f crypto/logs/shadow_trades.jsonl | jq
```

**Check pool stats** (via Python REPL while running):
```python
from execution.shadow.pool_manager import ShadowPoolManager
pool = ShadowPoolManager()
stats = pool.get_stats()
print(stats)
```

**Discord notifications** (if configured):
- Set `DISCORD_WEBHOOK_URL` in `.env`
- Receive trade entries/exits, P&L updates, and kill switch alerts

### Step 5: Hot Reload (Add/Remove Strategies Without Restart)

To add a new strategy while system is running:
```bash
# Add new strategy file to shadow_pool/
cp new_strategy.json crypto/logs/shadow_pool/

# Trigger reload (create signal file)
touch crypto/logs/RELOAD_STRATEGIES
```

The system checks for this file every candle and reloads strategies automatically.

---

## Risk Controls (Automatic)

### Position Limits (Per Strategy)
- Max 1% risk per trade
- Max 10% position size
- Max 5 open positions across all strategies
- Max 50% total exposure

### Stop Loss
- 3% stop loss on all long positions
- Force close if position hits stop
- Warning alert at -1.5%

### Kill Switches
| Trigger | Action |
|---------|--------|
| >5% drawdown in 1 hour | Pause 1 hour |
| >15% total drawdown | FULL STOP (manual restart required) |

### Early Warning Alerts (Discord)
- 3% hourly/total drawdown: Initial warning
- 5% hourly/total drawdown: Elevated warning
- 10% total drawdown: Critical warning

---

## Strategy Lifecycle Management

### Automatic Retirement (Daily Review)

Run the lifecycle manager to check for underperformers:
```bash
python main.py --run-lifecycle
```

**Retirement Criteria**:
- Max Drawdown > 15%
- Win Rate < 30% (min 50 trades)
- Negative P&L after 50 trades
- Inactivity > 14 days

Retired strategies are moved to `logs/shadow_pool/retired/` with metadata.

### Promotion to Live Trading

**Promotion Criteria** (not automated - manual review required):
- Trades > 100
- Win Rate > 45%
- Max Drawdown < 10%
- Positive P&L
- **Manual verification of regime robustness**

---

## Troubleshooting

### Strategy Not Trading

1. **Check if strategy is loaded**:
```bash
cat crypto/logs/trades.log | grep "Loaded strategy"
```

2. **Check for parsing errors**:
```bash
cat crypto/logs/errors.log
```

3. **Verify primitives exist**:
- `btc_trend()` - in `crypto/engine/gene_pool/market_filter.py`
- `vwap_distance()` - in `shared/engine/gene_pool/volume.py`
- `norm_rsi()` - in `shared/engine/gene_pool/mean_reversion.py`

### Position Not Entered

Check logs for limit violations:
```bash
cat crypto/logs/trades.log | grep "Max positions"
cat crypto/logs/trades.log | grep "Max exposure"
```

### Kill Switch Triggered

Check for drawdown events:
```bash
cat crypto/logs/trades.log | grep "KILL SWITCH"
```

To resume after temporary pause:
- 1-hour pause: System auto-resumes
- 15% drawdown: Manual restart required (review strategy performance first)

---

## Files and Directories

```
crypto/
├── logs/
│   ├── shadow_pool/              # Active strategies (auto-loaded)
│   │   ├── sol_vwap_reversion_v1.json
│   │   └── retired/              # Retired strategies
│   ├── shadow_trades.jsonl       # Trade log (JSON lines)
│   ├── trades.log                # Human-readable log
│   ├── errors.log                # Errors only
│   └── daily_reports/            # Lifecycle reports
├── winning_strategies/           # Documentation & archive
│   ├── sol_vwap_reversion_v1.json
│   └── DEPLOYMENT_GUIDE.md (this file)
└── execution/shadow/
    ├── trader.py                 # Single-strategy shadow trader
    ├── pool_manager.py           # Multi-strategy manager
    ├── lifecycle.py              # Retirement/promotion logic
    └── hot_reload.py             # Dynamic strategy loading
```

---

## Next Steps After Deployment

1. **Monitor for 7 days minimum** - Incubation purgatory before promoting
2. **Verify friction assumptions** - Check `implied_slippage_pct` in trade logs
3. **Regime validation** - Ensure strategy trades in different market conditions
4. **Compare to backtest** - Sharpe should be similar (allow 20% variance)

---

**Last Updated**: 12/16/2025 02:33 PM PST (via pst-timestamp)
