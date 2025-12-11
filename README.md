# Oil-Stonks: Systematic Alpha Generation Platform

An LLM-driven evolutionary trading system that discovers and optimizes trading strategies across multiple asset classes. The system uses AI to generate trading strategies from pre-validated building blocks ("genes"), then tests them rigorously before deploying real capital.

## 🎯 Current Focus: **Crypto Trading System** (Active Development)

We're currently building out the **crypto trading infrastructure** in Phase 1 (plumbing). The forex system is planned for future expansion once the crypto system is proven and profitable.

### What We're Working On Now

**Crypto System (Phase 1 - Infrastructure)**
- Real-time data pipeline from Bybit exchange
- Technical indicator calculation and validation
- Shadow trading (paper trading with live data)
- Risk management and kill switches
- Data quality monitoring

📖 **See [crypto/CRYPTO.md](crypto/CRYPTO.md) for detailed crypto system documentation**

### Future Plans

**Forex Trading System** (Planning Phase)
- Currency pair trading with similar evolutionary approach
- Will leverage shared infrastructure once crypto is proven
- Design docs coming once crypto Phase 1 is complete

📖 **See [forex/FOREX.md](forex/FOREX.md) for forex roadmap**

## 🏗️ Project Structure

```
/Oil-Stonks/
├── crypto/              # 🔥 ACTIVE: Crypto trading system
│   ├── CRYPTO.md       # Main crypto documentation (READ THIS!)
│   ├── data/           # Bybit WebSocket feeds, SQLite storage
│   ├── execution/      # Shadow and live trading
│   ├── engine/         # Strategy parsing and gene pool
│   └── logs/           # Trade and error logs
│
├── forex/              # 📋 PLANNED: Forex system (future)
│   └── FOREX.md        # Design notes
│
├── shared/             # Cross-asset infrastructure
│   ├── engine/         # Universal primitives (indicators)
│   ├── evolution/      # Backtesting, fitness calculations
│   └── risk/           # Kill switches, risk management
│
├── docs/plans/         # Design documents and research
├── CLAUDE.md           # Universal system principles
└── README.md           # You are here!
```

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- Bybit API credentials (for crypto)
- Git

### Installation

```bash
# Clone the repository
git clone <your-repo-url>
cd Oil-Stonks

# Install dependencies
pip install -r requirements.txt

# Set up Bybit API credentials (crypto)
# Create crypto/config.py with your API keys
# See crypto/CRYPTO.md for configuration details
```

### Running the Crypto System

```bash
# Start the crypto data pipeline
python crypto/main.py
```

**⚠️ Important:** We're still in Phase 1 (infrastructure). The system currently:
- Collects live market data
- Calculates technical indicators
- Runs shadow trading (paper trading)
- Does NOT place real trades yet

## 🧬 How It Works

### The Core Idea

Instead of hand-coding strategies, we let an LLM generate them from pre-validated building blocks:

1. **Gene Pool**: Library of proven technical indicators (EMA, RSI, ATR, etc.)
2. **LLM Generation**: AI combines genes into trading strategies
3. **Rigorous Testing**: Backtest across different market conditions (bull, bear, sideways)
4. **Shadow Trading**: Paper trade with live data for 7+ days
5. **Live Trading**: Deploy only proven strategies with strict risk controls

### Design Philosophy

- **Robustness over returns** — Survive black swans first, profit second
- **Conservative risk** — 1% per trade, 10% max position size, aggressive kill switches
- **Prove it first** — Minimum 7 days paper trading before real capital
- **Simplicity constraint** — Max 5 indicators per strategy (prevents overfitting)

## 📊 Development Phases (Per Asset Class)

Each asset class (crypto, forex) progresses independently:

### Phase 1: Plumbing (Crypto - IN PROGRESS)
✅ Data pipeline stability (48+ hours uptime)
✅ Indicator accuracy validation
🔄 Shadow trading implementation
⏳ Reconnect protocol testing
⏳ 48-hour stability test

### Phase 2: Evolution (Not Started)
- LLM strategy generation
- Automated backtesting
- Gene pool expansion
- Fitness optimization

### Phase 3: Live Trading (Not Started)
- Real capital deployment
- Performance monitoring
- Strategy rotation
- Risk management validation

**Status**: Crypto is in Phase 1. Forex is in planning (Phase 0).

## 📚 Key Documentation

Start here to understand the system:

1. **[CLAUDE.md](CLAUDE.md)** - Universal principles, shared infrastructure, philosophy
2. **[crypto/CRYPTO.md](crypto/CRYPTO.md)** - Crypto-specific implementation (ACTIVE WORK)
3. **[forex/FOREX.md](forex/FOREX.md)** - Forex plans (future)
4. **[docs/plans/](docs/plans/)** - Detailed design documents and research

### Recommended Reading Order

For new collaborators:
1. This README (overview)
2. `CLAUDE.md` (understand the philosophy)
3. `crypto/CRYPTO.md` (current implementation)
4. `docs/plans/2025-12-04-crypto-alpha-system-design.md` (detailed crypto design)

## 🛡️ Risk Management

Safety is paramount. The system includes:

- **Kill Switches**: Auto-shutdown on drawdowns (5%/1hr, 10%/24hr, 20%/all-time)
- **Position Limits**: 1% risk per trade, max 10% position size
- **Exposure Caps**: Max 5 open positions, 50% total exposure
- **Rate Limiting**: 1 new position per 5 minutes (prevent correlation)
- **Shadow Trading**: Mandatory 7+ day paper trading before live capital

## 🤝 Contributing

We're currently focused on completing **Crypto Phase 1** before expanding to other systems.

### Current Priorities

1. ✅ Complete crypto data pipeline stability testing
2. 🔄 Implement shadow trading system
3. ⏳ Validate reconnect protocols
4. ⏳ Achieve 48-hour uptime milestone

### Workflow

- Check `crypto/CRYPTO.md` for current phase goals
- Use `git commit` conventions for clean history
- Test changes thoroughly before committing
- Log any anomalies in `/crypto/logs/`

## 🔧 Tech Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.11+ |
| Exchange API | Bybit (crypto) |
| Data Storage | SQLite → PostgreSQL (planned) |
| Technical Analysis | `pandas-ta` |
| Backtesting | Custom lightweight engine |
| LLM | Anthropic Claude / OpenAI |
| Process Management | supervisor / systemd |

## 📈 Current Status

**Crypto System**: Phase 1 (Infrastructure) - ~80% complete
- ✅ Data pipeline implemented
- ✅ Real-time monitoring dashboard
- 🔄 Shadow trading in progress
- ⏳ Stability testing pending

**Forex System**: Planning phase
- 📋 Architecture design in progress
- ⏳ Waiting for crypto Phase 1 completion

## ⚠️ Important Notes

- **Not trading live yet**: System is in development/testing mode
- **No real funds at risk**: Currently shadow trading only
- **Crypto is priority**: Focus all efforts here before forex expansion
- **Phase gates are strict**: Must pass all Phase 1 criteria before Phase 2

## 📞 Questions?

- Check the documentation in `/docs/plans/`
- Review `CLAUDE.md` for universal principles
- See `crypto/CRYPTO.md` for crypto-specific details
- Check commit history for recent changes

---

**Last Updated**: 2025-12-11
**Active Development**: Crypto Phase 1
**Next Milestone**: 48-hour stability test
