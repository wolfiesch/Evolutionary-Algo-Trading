"""Data models for candle storage."""
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime


class Candle(BaseModel):
    """OHLCV candle data."""
    model_config = ConfigDict(frozen=True)  # Immutable

    symbol: str = Field(..., description="Trading pair, e.g., BTCUSDT")
    timestamp: int = Field(..., description="Unix timestamp in milliseconds")
    open: float
    high: float
    low: float
    close: float
    volume: float
    turnover: float = Field(default=0.0, description="Quote volume")

    @property
    def datetime(self) -> datetime:
        """Convert timestamp to datetime."""
        return datetime.fromtimestamp(self.timestamp / 1000)
