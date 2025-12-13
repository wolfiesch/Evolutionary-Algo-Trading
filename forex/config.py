"""Configuration management for forex-alpha system."""
import os
from pydantic_settings import BaseSettings
from pydantic import Field
from pathlib import Path


def _get_default_sqlite_path() -> Path:
    """Get SQLite path - prefer /data volume if it exists (Fly.io), otherwise local."""
    if Path("/data").exists():
        return Path("/data/candles_forex.db")
    return Path(__file__).parent / "data" / "candles_forex.db"


class Settings(BaseSettings):
    """Application settings loaded from environment."""

    # Paths
    base_dir: Path = Field(default=Path(__file__).parent)
    logs_dir: Path = Field(default=Path(__file__).parent / "logs")
    data_dir: Path = Field(default=Path(__file__).parent / "data")

    # Database
    sqlite_path: Path = Field(default_factory=_get_default_sqlite_path)

    # OANDA API
    oanda_access_token: str = Field(default="", description="OANDA V20 API Token")
    oanda_account_id: str = Field(default="", description="OANDA V20 Account ID")
    oanda_env: str = Field(default="practice", description="practice or live")
    
    # Pairs to track
    pairs: list[str] = Field(default=["EUR_USD", "GBP_USD", "USD_JPY", "USD_CHF"], validate_default=False)
    
    # Trading Parameters
    candle_interval: str = Field(default="M1", description="OANDA Candle Granularity")

    # Risk Parameters (Forex Specific)
    risk_per_trade: float = Field(default=0.01, description="1% risk per trade")
    max_position_pct: float = Field(default=0.15, description="15% max position (higher than crypto)")
    max_open_positions: int = Field(default=5)
    max_exposure: float = Field(default=0.50, description="50% max exposure")

    # Reconnection
    reconnect_delay_seconds: int = Field(default=5)
    
    # Shadow Trading
    initial_equity: float = Field(default=10000.0, description="Starting paper equity")
    # Approx 1-2 pips friction
    friction_pips: float = Field(default=1.5, description="Friction in pips per trade side")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
