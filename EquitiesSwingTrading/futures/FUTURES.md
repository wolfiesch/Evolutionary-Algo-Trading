# Futures Trading Module

Experimental futures trading system using Interactive Brokers TWS API. Separate from equities swing trading but shares core infrastructure (broker abstraction, risk management, watchdog).

## Status: Phase 0 - Setup & Exploration

**Current Focus:** IBKR account setup, API connectivity, paper trading validation

## Broker: Interactive Brokers (IBKR)

### Why IBKR (Not Alpaca)
- Alpaca does **not** support futures trading (on roadmap, no timeline)
- IBKR provides full futures access via TWS API
- Free API included with account
- Paper trading available (requires live account)

### Connection Architecture

```
┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
│  Python Client  │──────│  TWS / Gateway  │──────│  IBKR Servers   │
│  (ibkr_adapter) │ TCP  │  (localhost)    │      │  (Production)   │
└─────────────────┘      └─────────────────┘      └─────────────────┘
                         Port 7497 (paper)
                         Port 7496 (live)
                         Port 4002 (Gateway paper)
                         Port 4001 (Gateway live)
```

### API Requirements
- **Software:** TWS (Trader Workstation) or IB Gateway running locally
- **Python Package:** `ibapi` (official IB package)
- **TWS Config:** Enable "ActiveX and Socket Clients" in API settings
- **Port:** 7497 for paper trading, 7496 for live

## Target Contracts

### Phase 1: Index Futures (Liquid, Lower Margin)

| Symbol | Name | Exchange | Multiplier | Approx Margin | Notes |
|--------|------|----------|------------|---------------|-------|
| **MES** | Micro E-mini S&P 500 | CME | $5 | ~$235 | Best for testing |
| **MNQ** | Micro E-mini Nasdaq | CME | $2 | ~$300 | Tech-heavy |
| **ES** | E-mini S&P 500 | CME | $50 | ~$2,350 | Standard size |
| **NQ** | E-mini Nasdaq 100 | CME | $20 | ~$3,000 | Higher volatility |

### Phase 2: Commodity Futures (Fits Oil-Stonks Theme)

| Symbol | Name | Exchange | Multiplier | Approx Margin | Notes |
|--------|------|----------|------------|---------------|-------|
| **MCL** | Micro WTI Crude | NYMEX | 100 bbl | ~$170 | 1/10th CL |
| **CL** | WTI Crude Oil | NYMEX | 1000 bbl | ~$1,700 | Full size |
| **MNG** | Micro Natural Gas | NYMEX | 1,000 MMBtu | ~$100 | Volatile |

*Note: Margin requirements change daily based on market conditions*

## Market Hours

**Futures trade nearly 24/5** - major difference from equities!

### CME Globex Hours (ES, NQ, MES, MNQ)
- **Sunday 6:00 PM ET** → **Friday 5:00 PM ET**
- Daily maintenance: 5:00 PM - 6:00 PM ET (Mon-Thu)
- Total: ~23 hours/day vs 6.5 hours for equities

### NYMEX Hours (CL, MCL)
- **Sunday 6:00 PM ET** → **Friday 5:00 PM ET**
- Daily settlement: ~2:30 PM ET
- Daily maintenance: 5:00 PM - 6:00 PM ET

### Key Implications
1. **Overnight gap risk is minimal** (unlike equities)
2. **Can react to global events** in real-time
3. **Must handle session boundaries** in code
4. **Weekend risk** still exists (Friday close → Sunday open)

## Futures-Specific Considerations

### 1. Contract Expiry & Rollover
Futures contracts expire! Must handle:
- **Front-month tracking:** Know which contract is active
- **Rollover logic:** Switch to next contract before expiry
- **Volume migration:** Liquidity shifts to next contract ~1 week before expiry
- **Calendar spreads:** Price difference between months

```python
# Example: ES contract months are H, M, U, Z (Mar, Jun, Sep, Dec)
# December 2025 contract: "ESZ5" or lastTradeDateOrContractMonth="202512"
```

### 2. Margin Management
- **Initial margin:** Required to open position
- **Maintenance margin:** Required to hold position
- **Intraday margin:** Often 50% of overnight (broker-specific)
- **Margin calls:** Position liquidated if below maintenance

### 3. Settlement
- **Daily settlement:** Mark-to-market at end of each session
- **Final settlement:** Cash-settled (indexes) or physical delivery (commodities)
- **Never hold to expiry** for physical delivery contracts!

### 4. Tick Values

| Contract | Tick Size | Tick Value |
|----------|-----------|------------|
| ES | 0.25 | $12.50 |
| MES | 0.25 | $1.25 |
| NQ | 0.25 | $5.00 |
| MNQ | 0.25 | $0.50 |
| CL | 0.01 | $10.00 |
| MCL | 0.01 | $1.00 |

## Risk Parameters (Futures-Specific)

### Position Sizing
```python
FUTURES_RISK_CONFIG = {
    # Per-trade risk
    "max_risk_per_trade_pct": 1.0,      # 1% of equity per trade

    # Position limits
    "max_contracts_per_symbol": 5,       # Per-symbol limit
    "max_total_contracts": 10,           # Total open contracts
    "max_notional_exposure_pct": 50.0,   # % of equity in notional value

    # Correlation limits
    "max_correlated_positions": 3,       # E.g., ES + NQ + MES = 3
}
```

### Kill Switches (Adapted for Futures)
| Trigger | Action |
|---------|--------|
| Drawdown > 3% in 1 hour | Close all, pause 1 hour |
| Drawdown > 7% in 24 hours | Close all, pause 24 hours |
| Drawdown > 15% from peak | **Full shutdown** |
| Single position loss > 2% equity | Force close |
| Margin utilization > 80% | No new positions |
| Approaching expiry (< 3 days) | Close position |

*Note: Tighter thresholds than equities due to leverage*

## Directory Structure

```
futures/
├── FUTURES.md              # This file
├── __init__.py
├── config.py               # Futures-specific configuration
├── main.py                 # Futures trading entry point [*TO-DO*]
│
├── data/
│   ├── __init__.py
│   ├── contracts.py        # Contract definitions & rollover logic
│   └── ibkr_data.py        # Historical/streaming data [*TO-DO*]
│
├── strategies/
│   ├── __init__.py
│   └── futures_strategies.py  # [*TO-DO*]
│
└── tests/
    ├── __init__.py
    └── test_contracts.py   # [*TO-DO*]
```

## Shared Infrastructure

These components are shared with equities (in `/execution/live/`):

| Component | File | Futures Notes |
|-----------|------|---------------|
| Broker Interface | `broker.py` | Used as-is |
| IBKR Adapter | `ibkr_adapter.py` | **NEW** - implements BrokerAdapter |
| Watchdog | `watchdog.py` | May need futures-specific thresholds |

## Phase Roadmap

### Phase 0: Setup (Current)
- [x] Research IBKR API capabilities
- [x] Create directory structure
- [x] Document futures-specific requirements
- [ ] IBKR account setup (user action)
- [ ] TWS/Gateway installation
- [ ] Paper trading API connection test

### Phase 1: Plumbing
- [ ] Implement `ibkr_adapter.py` (BrokerAdapter for IBKR)
- [ ] Contract definition & rollover logic
- [ ] Historical data fetching
- [ ] Real-time data streaming
- [ ] Order execution on paper account
- [ ] Run 48 hours without crashes

### Phase 2: Strategies
- [ ] Port applicable strategies from equities
- [ ] Futures-specific strategies (spread trading, etc.)
- [ ] Backtest with futures data

### Phase 3: Live Trading
- [ ] Shadow trading validation
- [ ] Live deployment with micro contracts
- [ ] Scale to full-size contracts

## Development Log

| Date | Action |
|------|--------|
| 12/16/2024 | Initial research and directory setup |

## Resources

### Official Documentation
- [IBKR TWS API Docs](https://interactivebrokers.github.io/tws-api/)
- [IBKR Python API Guide](https://algotrading101.com/learn/interactive-brokers-python-api-native-guide/)
- [Futures Margin Requirements](https://www.interactivebrokers.com/en/trading/margin-futures-fops.php)

### ibapi Installation
```bash
# Option 1: PyPI (may have version issues)
pip install ibapi

# Option 2: From TWS API download (recommended)
# Download from: https://interactivebrokers.github.io/
# Navigate to TWS API/source/pythonclient
python setup.py install
```

### TWS Configuration for API
1. File → Global Configuration → API → Settings
2. Enable "ActiveX and Socket Clients"
3. Note Socket port (7497 for paper, 7496 for live)
4. Add trusted IPs if needed
5. Uncheck "Read-Only API" for order execution
