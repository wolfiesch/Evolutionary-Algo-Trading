# SOL VWAP Reversion V1 - Deployment Summary

**Deployed**: 12/16/2025 02:33 PM PST (via pst-timestamp)
**Status**: READY FOR SHADOW TRADING

---

## Strategy Overview

### Performance (Walk-Forward Backtest)
- **Sharpe Ratio**: 2.52
- **Win Rate**: 100% (9/9 trades)
- **Max Drawdown**: 0.6%
- **Walk-Forward Score**: 1.388
- **Backtest Period**: 180 days (H4 timeframe)

### Strategy Logic
**Entry Conditions**:
```
btc_trend(60) >= 0 AND vwap_distance(20) < -1.0 AND norm_rsi(14) < -0.1
```
- BTC market must be bullish (60-period trend)
- SOL must be significantly oversold vs VWAP (< -1.0 Z-score)
- RSI must be slightly oversold (< -0.1 normalized)

**Exit Conditions**:
```
vwap_distance(20) > -0.2
```
- Exit when price recovers toward VWAP (mean reversion complete)

### Primitives Used
1. **btc_trend(60)** - BTC market filter from `crypto/engine/gene_pool/market_filter.py`
2. **vwap_distance(20)** - VWAP distance Z-score from `shared/engine/gene_pool/volume.py`
3. **norm_rsi(14)** - Normalized RSI from `shared/engine/gene_pool/mean_reversion.py`

### Target Symbol
- **SOLUSDT** (Solana)

---

## Deployment Files

### 1. Winning Strategy Archive
**Location**: `/crypto/winning_strategies/sol_vwap_reversion_v1.json`
**Purpose**: Original validation results and documentation

### 2. Shadow Pool Deployment
**Location**: `/crypto/logs/shadow_pool/sol_vwap_reversion_v1.json`
**Purpose**: Production-ready strategy file (auto-loaded by ShadowPoolManager)
**Status**: ACTIVE

### 3. Deployment Guide
**Location**: `/crypto/winning_strategies/DEPLOYMENT_GUIDE.md`
**Purpose**: Instructions for deploying and monitoring strategies

---

## How to Start Shadow Trading

### Quick Start
```bash
cd /Users/wolfgangschoenberger/Projects/Oil-Stonks/crypto
python3 main.py --shadow-pool
```

This will:
- Load SOL VWAP Reversion V1 + all other strategies from `logs/shadow_pool/`
- Monitor BTCUSDT, ETHUSDT, SOLUSDT (Phase 3 default symbols)
- Start with $10,000 paper equity
- Log trades to `logs/shadow_trades.jsonl`

### Custom Symbol Set (SOL only)
```bash
python3 main.py --shadow-pool --symbols BTCUSDT,SOLUSDT
```

### Monitor Real-time
```bash
# Watch trade logs
tail -f logs/shadow_trades.jsonl | jq

# Watch system logs
tail -f logs/trades.log
```

---

## Risk Controls (Automatic)

### Position Sizing
- **Risk per trade**: 1% of equity
- **Max position size**: 10% of equity
- **Max open positions**: 5 (across ALL strategies)
- **Max total exposure**: 50% of equity

### Stop Loss
- **Stop loss**: 3% below entry price
- **Warning alert**: -1.5% (halfway to stop)

### Kill Switches
| Trigger | Action | Resume |
|---------|--------|--------|
| >5% drawdown in 1 hour | Pause 1 hour | Automatic |
| >15% total drawdown | FULL STOP | Manual restart required |

### Friction Modeling
- **Exchange fee**: 0.1%
- **Estimated slippage**: 0.15%
- **Total per side**: 0.25%

---

## Expected Behavior

### During Bullish BTC Markets
- Strategy will monitor SOL for VWAP dips
- Entry when SOL drops >1.0 Z-scores below VWAP + RSI oversold
- Quick exits when price recovers toward VWAP

### During Bearish/Sideways BTC
- **No entries** (btc_trend filter blocks all trades)
- Strategy remains dormant

### Sample Trade Lifecycle
```
1. BTC trending up (btc_trend >= 0) ✓
2. SOL flash-dips 1.2 Z-scores below VWAP ✓
3. RSI at -0.15 (slightly oversold) ✓
4. → ENTRY LONG at $150.00
5. SOL recovers to -0.15 Z-score vs VWAP
6. → EXIT LONG at $152.00 (+1.3%)
```

---

## Validation Checklist

### Pre-Deployment (COMPLETE)
- [x] Strategy validated on 180 days of H4 data
- [x] Walk-forward testing passed (Sharpe 2.52)
- [x] Win rate acceptable (100% on 9 trades)
- [x] Max drawdown acceptable (0.6% < 10%)
- [x] Strategy file created in shadow pool directory
- [x] All primitives exist and tested

### Post-Deployment (TO-DO)
- [ ] Run shadow trading for minimum 7 days
- [ ] Verify trades occur in expected market conditions
- [ ] Compare live Sharpe to backtest (allow ±20% variance)
- [ ] Validate friction assumptions (check `implied_slippage_pct` in logs)
- [ ] Monitor across different market regimes
- [ ] Accumulate >100 trades before considering live promotion

---

## Monitoring & Alerts

### Discord Notifications (Optional)
To enable:
```bash
# Add to .env file
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

You'll receive:
- Trade entry/exit notifications
- P&L updates
- Kill switch alerts
- Position warnings
- Drawdown warnings

### Key Metrics to Track
1. **Sharpe Ratio** - Should remain near 2.5 (±20%)
2. **Win Rate** - May normalize from 100% (small sample)
3. **Max Drawdown** - Should stay < 10%
4. **Trade Frequency** - Expect trades during BTC bull phases
5. **Slippage** - Monitor `implied_slippage_pct` in trade logs

### Daily Review
```bash
# Check if strategy traded today
cat logs/shadow_trades.jsonl | grep sol_vwap_reversion_v1 | tail -20 | jq

# Run lifecycle review (retirement check)
python3 main.py --run-lifecycle
```

---

## Troubleshooting

### Strategy Not Trading
1. **Check if loaded**:
   ```bash
   cat logs/trades.log | grep "sol_vwap_reversion_v1"
   ```

2. **Verify BTC is bullish**:
   - Strategy ONLY trades when `btc_trend(60) >= 0`
   - Check recent BTC price action

3. **Check for limit violations**:
   ```bash
   cat logs/trades.log | grep "Max positions"
   cat logs/trades.log | grep "Max exposure"
   ```

### Unexpected Exit
- Check if kill switch triggered:
  ```bash
  cat logs/trades.log | grep "KILL SWITCH"
  ```

### Performance Degradation
- Compare live Sharpe to backtest after 30+ trades
- If Sharpe drops >50% → Consider retiring strategy
- Run: `python3 main.py --run-lifecycle`

---

## Next Steps

### Week 1 (Incubation)
- Monitor for 7 days minimum
- Validate trade execution quality
- Verify regime behavior

### Week 2-4 (Validation)
- Accumulate 30+ trades
- Calculate live Sharpe ratio
- Compare to backtest metrics
- Check regime robustness

### After 100 Trades (Promotion Consideration)
- **Required metrics**:
  - Win Rate > 45%
  - Sharpe > 1.0
  - Max Drawdown < 10%
  - Positive P&L
- **Manual review required** before live trading

---

## Files Reference

```
crypto/
├── logs/
│   ├── shadow_pool/
│   │   └── sol_vwap_reversion_v1.json      # DEPLOYMENT FILE (active)
│   ├── shadow_trades.jsonl                  # Trade logs
│   └── trades.log                           # System logs
├── winning_strategies/
│   ├── sol_vwap_reversion_v1.json          # Archive/documentation
│   ├── DEPLOYMENT_GUIDE.md                  # General deployment guide
│   └── SOL_VWAP_REVERSION_V1_DEPLOYMENT.md # This file
└── execution/shadow/
    ├── pool_manager.py                      # Loads strategies from shadow_pool/
    ├── trader.py                            # Executes paper trades
    └── lifecycle.py                         # Auto-retirement logic
```

---

## Strategy Metadata

```json
{
  "strategy_id": "sol_vwap_reversion_v1",
  "strategy_name": "SOL_VWAP_Reversion_V1",
  "validation_date": "2025-12-15",
  "deployed_date": "2025-12-16",
  "backtest_sharpe": 2.52,
  "backtest_trades": 9,
  "backtest_win_rate": 1.0,
  "target_symbols": ["SOLUSDT"],
  "deployment_status": "shadow_trading_active"
}
```

---

**Deployment completed**: 12/16/2025 02:33 PM PST (via pst-timestamp)
**Next review**: 12/23/2025 (7 days)
