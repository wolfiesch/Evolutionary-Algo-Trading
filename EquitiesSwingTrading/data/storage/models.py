"""
Data models for Equities Swing Trading System.

Pydantic models for type-safe data handling.
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional
import json


@dataclass
class DailyCandle:
    """Daily OHLCV candle for equities."""
    symbol: str
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: int
    adj_close: Optional[float] = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "symbol": self.symbol,
            "date": self.date.isoformat(),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "adj_close": self.adj_close,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "DailyCandle":
        """Create from dictionary."""
        dt = d["date"]
        if isinstance(dt, str):
            dt = date.fromisoformat(dt)
        elif isinstance(dt, datetime):
            dt = dt.date()

        return cls(
            symbol=d["symbol"],
            date=dt,
            open=d["open"],
            high=d["high"],
            low=d["low"],
            close=d["close"],
            volume=int(d["volume"]),
            adj_close=d.get("adj_close"),
        )


@dataclass
class FundamentalSignal:
    """
    Cached fundamental signal from SEC EDGAR.

    Point-in-time data: signal_date is when the signal was computed/available,
    not when the underlying data was generated.
    """
    symbol: str
    signal_type: str  # 'insider_buy_intensity', 'revenue_cagr', etc.
    signal_date: date  # When signal became available (filing date)
    signal_value: float
    raw_data: Optional[str] = None  # JSON string for debugging

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "signal_type": self.signal_type,
            "signal_date": self.signal_date.isoformat(),
            "signal_value": self.signal_value,
            "raw_data": self.raw_data,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "FundamentalSignal":
        dt = d["signal_date"]
        if isinstance(dt, str):
            dt = date.fromisoformat(dt)

        return cls(
            symbol=d["symbol"],
            signal_type=d["signal_type"],
            signal_date=dt,
            signal_value=d["signal_value"],
            raw_data=d.get("raw_data"),
        )


@dataclass
class FilingEvent:
    """
    SEC filing event for event-driven signals.
    """
    symbol: str
    filing_date: date
    form_type: str  # '10-K', '10-Q', '8-K', 'Form 4', '13F'
    accession_number: str
    summary: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "filing_date": self.filing_date.isoformat(),
            "form_type": self.form_type,
            "accession_number": self.accession_number,
            "summary": self.summary,
        }


@dataclass
class UniverseMember:
    """
    Stock in the tradable universe.
    """
    symbol: str
    company_name: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    market_cap: Optional[float] = None
    avg_volume: Optional[float] = None
    exchange: Optional[str] = None
    last_updated: Optional[date] = None

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "company_name": self.company_name,
            "sector": self.sector,
            "industry": self.industry,
            "market_cap": self.market_cap,
            "avg_volume": self.avg_volume,
            "exchange": self.exchange,
            "last_updated": self.last_updated.isoformat() if self.last_updated else None,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "UniverseMember":
        last_updated = d.get("last_updated")
        if isinstance(last_updated, str):
            last_updated = date.fromisoformat(last_updated)

        return cls(
            symbol=d["symbol"],
            company_name=d.get("company_name"),
            sector=d.get("sector"),
            industry=d.get("industry"),
            market_cap=d.get("market_cap"),
            avg_volume=d.get("avg_volume"),
            exchange=d.get("exchange"),
            last_updated=last_updated,
        )


@dataclass
class InsiderTrade:
    """
    Parsed insider trade from Form 4.
    """
    symbol: str
    insider_name: str
    insider_title: Optional[str]
    transaction_date: date
    transaction_type: str  # 'buy' or 'sell'
    shares: int
    price_per_share: Optional[float]
    shares_owned_after: Optional[int]
    filing_date: date

    @property
    def value(self) -> Optional[float]:
        """Total transaction value."""
        if self.price_per_share:
            return self.shares * self.price_per_share
        return None

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "insider_name": self.insider_name,
            "insider_title": self.insider_title,
            "transaction_date": self.transaction_date.isoformat(),
            "transaction_type": self.transaction_type,
            "shares": self.shares,
            "price_per_share": self.price_per_share,
            "shares_owned_after": self.shares_owned_after,
            "filing_date": self.filing_date.isoformat(),
        }
