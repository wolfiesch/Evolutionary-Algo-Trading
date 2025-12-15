"""
Equities Swing Trading System - Configuration

Configuration for the equities trading system that combines
technical analysis with SEC EDGAR fundamental data.
"""

from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Optional
import os


# =============================================================================
# PATH CONFIGURATION
# =============================================================================

PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"
LOGS_DIR = PROJECT_ROOT / "logs"
STRATEGIES_DIR = PROJECT_ROOT / "strategies"

# Ensure directories exist
DATA_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)
STRATEGIES_DIR.mkdir(exist_ok=True)


# =============================================================================
# DATABASE CONFIGURATION
# =============================================================================

@dataclass
class DatabaseConfig:
    """SQLite database configuration."""
    db_path: Path = DATA_DIR / "equities.db"
    echo_sql: bool = False  # Set True for debugging


# =============================================================================
# MARKET DATA CONFIGURATION
# =============================================================================

@dataclass
class MarketDataConfig:
    """Market data provider configuration."""
    # Provider: "yahoo", "polygon", "alpaca"
    provider: str = "yahoo"

    # Polygon.io settings (if using)
    polygon_api_key: Optional[str] = field(
        default_factory=lambda: os.getenv("POLYGON_API_KEY")
    )

    # Alpaca settings (if using)
    alpaca_api_key: Optional[str] = field(
        default_factory=lambda: os.getenv("ALPACA_API_KEY")
    )
    alpaca_secret_key: Optional[str] = field(
        default_factory=lambda: os.getenv("ALPACA_SECRET_KEY")
    )
    alpaca_base_url: str = "https://paper-api.alpaca.markets"  # Paper trading

    # Rate limiting
    requests_per_second: float = 5.0  # Conservative for Yahoo

    # Data settings
    lookback_days: int = 252 * 5  # 5 years of daily data


# =============================================================================
# SEC EDGAR CONFIGURATION
# =============================================================================

@dataclass
class EdgarConfig:
    """SEC EDGAR agent configuration."""
    # EDGAR agent API endpoint
    base_url: str = "http://localhost:8000/api/v1"
    timeout_seconds: float = 30.0

    # Cache TTLs
    insider_trades_ttl: timedelta = timedelta(hours=24)
    financials_ttl: timedelta = timedelta(days=7)
    risk_changes_ttl: timedelta = timedelta(days=7)
    company_info_ttl: timedelta = timedelta(days=30)

    # Retry settings
    max_retries: int = 3
    retry_backoff_seconds: list = field(default_factory=lambda: [1, 2, 4])


# =============================================================================
# UNIVERSE CONFIGURATION
# =============================================================================

@dataclass
class UniverseConfig:
    """Tradable universe configuration."""
    # Market cap filter (USD)
    min_market_cap: float = 1e9  # $1 billion

    # Liquidity filter (average daily dollar volume)
    min_avg_daily_volume: float = 10e6  # $10 million

    # Price filter
    min_price: float = 10.0  # No penny stocks

    # Exchange filter
    allowed_exchanges: list = field(
        default_factory=lambda: ["NYSE", "NASDAQ", "AMEX"]
    )

    # ETF filter
    exclude_etfs: bool = True

    # EDGAR coverage required
    require_edgar_coverage: bool = True
    min_edgar_filings: int = 4  # At least 4 quarterly filings

    # Target universe size
    max_symbols: int = 500

    # Refresh frequency
    refresh_interval: timedelta = timedelta(days=7)


# =============================================================================
# TRADING CONFIGURATION
# =============================================================================

@dataclass
class TradingConfig:
    """Trading and execution configuration."""
    # Position sizing
    max_position_pct: float = 0.05  # 5% max per position
    max_sector_pct: float = 0.20  # 20% max per sector
    max_total_exposure: float = 0.80  # 80% max invested
    max_positions: int = 20

    # Stop loss
    stop_loss_pct: float = 0.05  # 5% stop loss

    # Market hours (Eastern Time)
    market_open: str = "09:30"
    market_close: str = "16:00"
    entry_window_start: str = "09:35"  # Avoid open volatility
    entry_window_end: str = "15:55"  # Avoid close volatility

    # Order types
    use_limit_orders: bool = True
    limit_order_buffer_pct: float = 0.001  # 0.1% from current price


# =============================================================================
# BACKTEST CONFIGURATION
# =============================================================================

@dataclass
class BacktestConfig:
    """Backtesting engine configuration."""
    # Capital
    initial_equity: float = 100_000.0

    # Friction (equities have lower costs than crypto)
    friction_per_side: float = 0.0003  # 0.03% (slippage + spread)

    # Position sizing
    max_position_pct: float = 0.05  # 5% per position
    risk_per_trade: float = 0.01  # 1% risk per trade
    max_open_positions: int = 20
    max_total_exposure: float = 0.80

    # Stop loss
    stop_loss_pct: float = 0.05

    # Trade frequency limits
    min_position_interval_bars: int = 1  # Can trade daily
    min_trade_value: float = 1000.0  # Minimum position value

    # Warmup period (bars to skip for indicator stability)
    warmup_bars: int = 60


# =============================================================================
# EVOLUTION CONFIGURATION
# =============================================================================

@dataclass
class EvolutionConfig:
    """Evolutionary algorithm configuration."""
    # Population
    population_size: int = 20
    generations: int = 50
    elite_count: int = 3

    # Reproduction
    mutation_rate: float = 0.6
    crossover_rate: float = 0.4
    tournament_size: int = 4

    # Stagnation
    max_stagnation: int = 10

    # Checkpointing
    checkpoint_interval: int = 5
    checkpoint_dir: Path = STRATEGIES_DIR / "checkpoints"

    # Trade requirements
    min_trades: int = 20
    target_trades: int = 60

    # Fitness thresholds
    min_sharpe_for_shadow: float = 0.8
    min_regime_passes: int = 4  # Out of 5 regimes


# =============================================================================
# FITNESS CONFIGURATION
# =============================================================================

@dataclass
class FitnessConfig:
    """Fitness calculation configuration."""
    # Sharpe ratio bounds
    sharpe_min_clamp: float = -5.0
    sharpe_max_clamp: float = 5.0

    # Penalties
    drawdown_penalty_multiplier: float = 2.0
    trade_count_target: int = 60  # Target trades per backtest

    # Disqualification thresholds
    min_trades_required: int = 5
    max_drawdown_allowed: float = 0.50  # 50%

    # Regime testing
    min_regime_sharpe: float = 0.5  # Pass threshold per regime


# =============================================================================
# REGIME CLASSIFICATION
# =============================================================================

@dataclass
class RegimeConfig:
    """Market regime classification configuration."""
    # SPY trend thresholds
    bull_return_min: float = 0.02  # +2% over window
    bear_return_max: float = -0.02  # -2% over window

    # VIX thresholds
    vix_low: float = 15.0  # Below = low volatility
    vix_high: float = 25.0  # Above = high volatility

    # Classification window
    window_days: int = 20


# =============================================================================
# RISK MANAGEMENT (KILL SWITCHES)
# =============================================================================

@dataclass
class RiskConfig:
    """Risk management and kill switch configuration."""
    # Drawdown triggers
    daily_drawdown_limit: float = 0.03  # 3% daily max loss
    weekly_drawdown_limit: float = 0.07  # 7% weekly max loss
    peak_drawdown_limit: float = 0.15  # 15% from peak

    # Position limits
    single_position_loss_limit: float = 0.05  # 5% per position

    # Pause durations
    daily_pause_hours: int = 24
    weekly_pause_hours: int = 168  # 1 week

    # Recovery
    require_manual_restart_on_peak_breach: bool = True


# =============================================================================
# NOTIFICATION CONFIGURATION
# =============================================================================

@dataclass
class NotificationConfig:
    """Notification and alerting configuration."""
    # Discord webhook
    discord_webhook_url: Optional[str] = field(
        default_factory=lambda: os.getenv("DISCORD_WEBHOOK_URL")
    )

    # Alert types
    alert_on_signal: bool = True
    alert_on_trade: bool = True
    alert_on_error: bool = True
    alert_on_kill_switch: bool = True

    # Daily summary
    daily_summary_time: str = "16:30"  # After market close


# =============================================================================
# LOGGING CONFIGURATION
# =============================================================================

@dataclass
class LoggingConfig:
    """Logging configuration."""
    # Log files
    trade_log: Path = LOGS_DIR / "trades.log"
    error_log: Path = LOGS_DIR / "errors.log"
    signal_log: Path = LOGS_DIR / "signals.log"

    # Log levels
    console_level: str = "INFO"
    file_level: str = "DEBUG"

    # Rotation
    max_log_size_mb: int = 100
    backup_count: int = 5


# =============================================================================
# GENE POOL CONFIGURATION
# =============================================================================

# Allowed primitive parameters (integer only per design)
ALLOWED_PERIODS = [5, 9, 14, 20, 21, 50, 60, 100, 200]
ALLOWED_THRESHOLDS = [-0.8, -0.6, -0.4, -0.2, 0.0, 0.2, 0.4, 0.6, 0.8]
ALLOWED_STD_DEVS = [1.5, 2.0, 2.5, 3.0]

# Maximum primitives per strategy (complexity limit)
MAX_PRIMITIVES_PER_STRATEGY = 5


# =============================================================================
# MASTER CONFIGURATION
# =============================================================================

@dataclass
class Config:
    """Master configuration container."""
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    market_data: MarketDataConfig = field(default_factory=MarketDataConfig)
    edgar: EdgarConfig = field(default_factory=EdgarConfig)
    universe: UniverseConfig = field(default_factory=UniverseConfig)
    trading: TradingConfig = field(default_factory=TradingConfig)
    backtest: BacktestConfig = field(default_factory=BacktestConfig)
    evolution: EvolutionConfig = field(default_factory=EvolutionConfig)
    fitness: FitnessConfig = field(default_factory=FitnessConfig)
    regime: RegimeConfig = field(default_factory=RegimeConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    notification: NotificationConfig = field(default_factory=NotificationConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)


# Default configuration instance
config = Config()


# =============================================================================
# ENVIRONMENT-SPECIFIC OVERRIDES
# =============================================================================

def get_config(environment: str = "development") -> Config:
    """
    Get configuration for specific environment.

    Args:
        environment: "development", "staging", or "production"

    Returns:
        Config instance with environment-specific overrides
    """
    cfg = Config()

    if environment == "production":
        # Production overrides
        cfg.market_data.provider = "polygon"
        cfg.trading.use_limit_orders = True
        cfg.risk.require_manual_restart_on_peak_breach = True

    elif environment == "staging":
        # Staging/paper trading overrides
        cfg.market_data.provider = "alpaca"
        cfg.trading.max_positions = 10  # Reduced for testing
        cfg.backtest.initial_equity = 50_000.0

    else:  # development
        # Development defaults (use Yahoo, smaller scale)
        cfg.market_data.provider = "yahoo"
        cfg.universe.max_symbols = 100
        cfg.evolution.population_size = 10
        cfg.evolution.generations = 10

    return cfg
