"""Configuration management for crypto-alpha system."""
import os
from pydantic_settings import BaseSettings
from pydantic import Field, field_validator
from pathlib import Path


def _get_default_sqlite_path() -> Path:
    """Get SQLite path - prefer /data volume if it exists (Fly.io), otherwise local."""
    if Path("/data").exists():
        return Path("/data/candles.db")
    return Path(__file__).parent / "data" / "candles.db"


class Settings(BaseSettings):
    """Application settings loaded from environment."""

    # Paths
    base_dir: Path = Field(default=Path(__file__).parent)
    logs_dir: Path = Field(default=Path(__file__).parent / "logs")
    data_dir: Path = Field(default=Path(__file__).parent / "data")

    # Database - use /data for persistent volume on Fly.io, fallback to local
    sqlite_path: Path = Field(default_factory=_get_default_sqlite_path)

    # Bybit API (read-only for Phase 1)
    bybit_ws_url: str = Field(default="wss://stream.bybit.com/v5/public/linear")
    bybit_rest_url: str = Field(default="https://api.bybit.com")

    # Trading Parameters
    universe_size: int = Field(default=30, description="Number of coins to track")
    candle_interval: str = Field(default="1", description="Candle interval in minutes")

    # Risk Parameters (Phase 1 defaults)
    risk_per_trade: float = Field(default=0.01, description="1% risk per trade")
    max_position_pct: float = Field(default=0.10, description="10% max position")
    max_open_positions: int = Field(default=5)
    max_exposure: float = Field(default=0.50, description="50% max exposure")

    # Reconnection
    reconnect_delay_seconds: int = Field(default=5)
    warmup_candles: int = Field(default=100, description="Candles to fetch on reconnect")

    # Shadow Trading
    initial_equity: float = Field(default=10000.0, description="Starting paper equity")
    friction_per_side: float = Field(default=0.0025, description="0.25% per trade side")

    # Discord Notifications
    discord_webhook_url: str = Field(default="", description="Discord webhook URL for notifications")
    discord_batch_trades: bool = Field(default=False, description="Batch trade notifications (opt-in)")
    discord_batch_interval: int = Field(default=300, description="Batch interval in seconds (5 min default)")

    # Warning Thresholds (for early warning alerts before kill switches)
    drawdown_warning_pct: float = Field(default=0.03, description="3% - send warning")
    drawdown_elevated_pct: float = Field(default=0.05, description="5% - elevated warning")
    drawdown_critical_pct: float = Field(default=0.10, description="10% - critical warning")
    position_warning_pct: float = Field(default=0.015, description="1.5% - position warning threshold")

    @property
    def discord_enabled(self) -> bool:
        """Check if Discord notifications are enabled."""
        return bool(self.discord_webhook_url)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
