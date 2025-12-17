"""
Futures trading configuration.

Separate from equities config but follows same patterns.
"""
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from decimal import Decimal


@dataclass
class IBKRConfig:
    """Interactive Brokers connection configuration."""

    # Connection settings
    host: str = "127.0.0.1"
    paper_port: int = 7497       # TWS paper trading
    live_port: int = 7496        # TWS live trading
    gateway_paper_port: int = 4002  # IB Gateway paper
    gateway_live_port: int = 4001   # IB Gateway live
    client_id: int = 1           # Unique client ID for this connection

    # Use paper trading by default
    use_paper: bool = True

    # Connection behavior
    readonly: bool = False       # Set True for data-only (no orders)
    connection_timeout: int = 30  # Seconds to wait for connection

    @property
    def port(self) -> int:
        """Get the appropriate port based on paper/live mode."""
        return self.paper_port if self.use_paper else self.live_port

    @classmethod
    def from_env(cls) -> "IBKRConfig":
        """Load configuration from environment variables."""
        return cls(
            host=os.getenv("IBKR_HOST", "127.0.0.1"),
            paper_port=int(os.getenv("IBKR_PAPER_PORT", "7497")),
            live_port=int(os.getenv("IBKR_LIVE_PORT", "7496")),
            client_id=int(os.getenv("IBKR_CLIENT_ID", "1")),
            use_paper=os.getenv("IBKR_USE_PAPER", "true").lower() == "true",
            readonly=os.getenv("IBKR_READONLY", "false").lower() == "true",
        )


@dataclass
class FuturesRiskConfig:
    """Risk management settings for futures trading."""

    # Per-trade risk
    max_risk_per_trade_pct: float = 1.0  # 1% of equity per trade

    # Position limits
    max_contracts_per_symbol: int = 5    # Per-symbol limit
    max_total_contracts: int = 10        # Total open contracts
    max_notional_exposure_pct: float = 50.0  # % of equity in notional

    # Margin management
    max_margin_utilization_pct: float = 80.0  # Don't exceed this
    min_free_margin_pct: float = 30.0         # Always keep this free

    # Kill switch thresholds (tighter than equities due to leverage)
    hourly_drawdown_limit_pct: float = 3.0    # Close all if exceeded
    daily_drawdown_limit_pct: float = 7.0     # Close all if exceeded
    max_drawdown_limit_pct: float = 15.0      # Full shutdown
    single_position_loss_limit_pct: float = 2.0  # Force close

    # Expiry management
    days_before_expiry_close: int = 3  # Close positions this many days before expiry

    # Throttling
    min_seconds_between_orders: int = 5  # Rate limiting


@dataclass
class ContractSpec:
    """Specification for a futures contract."""

    symbol: str                    # e.g., "ES", "MES", "CL"
    name: str                      # Human-readable name
    exchange: str                  # e.g., "CME", "NYMEX"
    currency: str = "USD"
    multiplier: int = 1            # Point value multiplier
    tick_size: Decimal = Decimal("0.25")
    tick_value: Decimal = Decimal("12.50")  # Value of one tick
    trading_class: Optional[str] = None     # For disambiguation
    contract_months: List[str] = field(default_factory=list)  # e.g., ["H", "M", "U", "Z"]

    # Session times (ET)
    session_start: str = "18:00"   # 6 PM ET Sunday
    session_end: str = "17:00"     # 5 PM ET Friday
    maintenance_start: str = "17:00"  # Daily maintenance
    maintenance_end: str = "18:00"

    # Risk characteristics
    is_micro: bool = False         # Micro contract (1/10th size)
    typical_daily_range_points: float = 0.0  # For position sizing


# Pre-defined contract specifications
CONTRACT_SPECS: Dict[str, ContractSpec] = {
    # Index Futures - Micro (for testing/small accounts)
    "MES": ContractSpec(
        symbol="MES",
        name="Micro E-mini S&P 500",
        exchange="CME",
        multiplier=5,
        tick_size=Decimal("0.25"),
        tick_value=Decimal("1.25"),
        contract_months=["H", "M", "U", "Z"],  # Mar, Jun, Sep, Dec
        is_micro=True,
        typical_daily_range_points=50.0,
    ),
    "MNQ": ContractSpec(
        symbol="MNQ",
        name="Micro E-mini Nasdaq 100",
        exchange="CME",
        multiplier=2,
        tick_size=Decimal("0.25"),
        tick_value=Decimal("0.50"),
        contract_months=["H", "M", "U", "Z"],
        is_micro=True,
        typical_daily_range_points=200.0,
    ),

    # Index Futures - Standard
    "ES": ContractSpec(
        symbol="ES",
        name="E-mini S&P 500",
        exchange="CME",
        multiplier=50,
        tick_size=Decimal("0.25"),
        tick_value=Decimal("12.50"),
        contract_months=["H", "M", "U", "Z"],
        typical_daily_range_points=50.0,
    ),
    "NQ": ContractSpec(
        symbol="NQ",
        name="E-mini Nasdaq 100",
        exchange="CME",
        multiplier=20,
        tick_size=Decimal("0.25"),
        tick_value=Decimal("5.00"),
        contract_months=["H", "M", "U", "Z"],
        typical_daily_range_points=200.0,
    ),

    # Commodity Futures - Micro
    "MCL": ContractSpec(
        symbol="MCL",
        name="Micro WTI Crude Oil",
        exchange="NYMEX",
        multiplier=100,  # 100 barrels
        tick_size=Decimal("0.01"),
        tick_value=Decimal("1.00"),
        contract_months=["F", "G", "H", "J", "K", "M", "N", "Q", "U", "V", "X", "Z"],
        is_micro=True,
        typical_daily_range_points=2.0,  # $2 range typical
    ),

    # Commodity Futures - Standard
    "CL": ContractSpec(
        symbol="CL",
        name="WTI Crude Oil",
        exchange="NYMEX",
        multiplier=1000,  # 1000 barrels
        tick_size=Decimal("0.01"),
        tick_value=Decimal("10.00"),
        contract_months=["F", "G", "H", "J", "K", "M", "N", "Q", "U", "V", "X", "Z"],
        typical_daily_range_points=2.0,
    ),
}


@dataclass
class FuturesConfig:
    """Main configuration for futures trading module."""

    # IBKR connection
    ibkr: IBKRConfig = field(default_factory=IBKRConfig)

    # Risk management
    risk: FuturesRiskConfig = field(default_factory=FuturesRiskConfig)

    # Trading parameters
    enabled_symbols: List[str] = field(
        default_factory=lambda: ["MES", "MNQ"]  # Start with micros
    )
    default_timeframe: str = "5min"  # Default candle timeframe

    # Logging
    log_dir: str = "futures/logs"
    trade_log_file: str = "futures_trades.jsonl"
    error_log_file: str = "futures_errors.log"

    # State persistence
    state_dir: str = "futures/state"

    @classmethod
    def from_env(cls) -> "FuturesConfig":
        """Load configuration from environment."""
        return cls(
            ibkr=IBKRConfig.from_env(),
            enabled_symbols=os.getenv(
                "FUTURES_SYMBOLS", "MES,MNQ"
            ).split(","),
        )

    def get_contract_spec(self, symbol: str) -> Optional[ContractSpec]:
        """Get contract specification for a symbol."""
        return CONTRACT_SPECS.get(symbol.upper())


# Default configuration instance
default_config = FuturesConfig()
