"""
EDGAR Client for Equities Swing Trading.

HTTP client that connects to the sec-edgar-agent API to fetch:
- Insider trading data (Form 4)
- Financial statements (10-K, 10-Q)
- Risk factor changes
- Company information

All data is returned in normalized formats suitable for signal calculation.
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Optional
from urllib.parse import urljoin

import httpx

logger = logging.getLogger(__name__)


@dataclass
class EdgarConfig:
    """Configuration for EDGAR API client."""
    base_url: str = "http://localhost:8000/api/v1"
    timeout: float = 30.0
    max_retries: int = 3
    retry_delay: float = 1.0
    rate_limit_rps: float = 5.0  # Requests per second


@dataclass
class InsiderTrade:
    """Normalized insider trade data."""
    insider_name: str
    insider_title: Optional[str]
    transaction_date: date
    transaction_type: str  # "P" = purchase, "S" = sale
    shares: float
    price_per_share: Optional[float]
    total_value: Optional[float]
    shares_owned_after: Optional[float]

    @property
    def is_buy(self) -> bool:
        return self.transaction_type == "P"

    @property
    def is_sell(self) -> bool:
        return self.transaction_type == "S"


@dataclass
class FinancialData:
    """Normalized financial statement data."""
    ticker: str
    period_end: date
    fiscal_year: int
    fiscal_period: str  # "FY", "Q1", "Q2", "Q3", "Q4"

    # Income statement
    revenue: Optional[float] = None
    net_income: Optional[float] = None
    operating_income: Optional[float] = None
    gross_profit: Optional[float] = None
    eps: Optional[float] = None

    # Balance sheet
    total_assets: Optional[float] = None
    total_liabilities: Optional[float] = None
    total_equity: Optional[float] = None
    cash_and_equivalents: Optional[float] = None
    total_debt: Optional[float] = None

    # Cash flow
    operating_cash_flow: Optional[float] = None
    free_cash_flow: Optional[float] = None
    capital_expenditures: Optional[float] = None


@dataclass
class RiskFactorChange:
    """Risk factor change between filings."""
    change_type: str  # "new", "removed", "modified"
    risk_summary: str
    similarity_score: Optional[float] = None  # For modified risks


@dataclass
class InsiderSummary:
    """Aggregated insider activity for a stock."""
    ticker: str
    period_days: int
    total_buys: int = 0
    total_sells: int = 0
    buy_value: float = 0.0
    sell_value: float = 0.0
    buy_shares: float = 0.0
    sell_shares: float = 0.0
    unique_buyers: int = 0
    unique_sellers: int = 0
    trades: list[InsiderTrade] = field(default_factory=list)

    @property
    def net_value(self) -> float:
        """Net value of insider activity (positive = net buying)."""
        return self.buy_value - self.sell_value

    @property
    def buy_sell_ratio(self) -> float:
        """Ratio of buys to sells (by count). >1 = more buying."""
        if self.total_sells == 0:
            return float(self.total_buys) if self.total_buys > 0 else 0.0
        return self.total_buys / self.total_sells


class EdgarClientError(Exception):
    """Base exception for EDGAR client errors."""
    pass


class EdgarConnectionError(EdgarClientError):
    """Connection error to EDGAR API."""
    pass


class EdgarAPIError(EdgarClientError):
    """API returned an error response."""
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        super().__init__(f"API error {status_code}: {message}")


class EdgarClient:
    """
    HTTP client for sec-edgar-agent API.

    Provides methods to fetch insider trades, financials, and risk factors
    in normalized formats suitable for signal calculation.
    """

    def __init__(self, config: Optional[EdgarConfig] = None):
        """
        Initialize EDGAR client.

        Args:
            config: Client configuration. Uses defaults if not provided.
        """
        self.config = config or EdgarConfig()
        self._client: Optional[httpx.Client] = None
        self._last_request_time: float = 0.0

    def _get_client(self) -> httpx.Client:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.Client(
                base_url=self.config.base_url,
                timeout=self.config.timeout,
            )
        return self._client

    def _rate_limit(self) -> None:
        """Enforce rate limiting."""
        if self.config.rate_limit_rps <= 0:
            return

        min_interval = 1.0 / self.config.rate_limit_rps
        elapsed = time.time() - self._last_request_time

        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)

        self._last_request_time = time.time()

    def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[dict] = None,
        json_data: Optional[dict] = None,
    ) -> dict:
        """
        Make HTTP request with retries and rate limiting.

        Args:
            method: HTTP method (GET, POST)
            endpoint: API endpoint (e.g., "/filings/AAPL/10-K")
            params: Query parameters
            json_data: JSON body for POST requests

        Returns:
            JSON response data

        Raises:
            EdgarConnectionError: Connection failed
            EdgarAPIError: API returned error
        """
        client = self._get_client()
        url = endpoint if endpoint.startswith("/") else f"/{endpoint}"

        last_error = None

        for attempt in range(self.config.max_retries):
            try:
                self._rate_limit()

                if method.upper() == "GET":
                    response = client.get(url, params=params)
                elif method.upper() == "POST":
                    response = client.post(url, params=params, json=json_data)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")

                if response.status_code >= 400:
                    raise EdgarAPIError(
                        response.status_code,
                        response.text[:200]
                    )

                return response.json()

            except httpx.ConnectError as e:
                last_error = EdgarConnectionError(
                    f"Failed to connect to EDGAR API at {self.config.base_url}: {e}"
                )
                logger.warning(
                    f"Connection attempt {attempt + 1}/{self.config.max_retries} "
                    f"failed: {e}"
                )

            except httpx.TimeoutException as e:
                last_error = EdgarConnectionError(f"Request timed out: {e}")
                logger.warning(
                    f"Timeout on attempt {attempt + 1}/{self.config.max_retries}"
                )

            if attempt < self.config.max_retries - 1:
                time.sleep(self.config.retry_delay * (attempt + 1))

        raise last_error or EdgarConnectionError("Unknown connection error")

    def health_check(self) -> bool:
        """
        Check if EDGAR API is reachable.

        Returns:
            True if API is healthy, False otherwise
        """
        try:
            # Try a lightweight endpoint
            self._request("GET", "/")
            return True
        except EdgarClientError:
            return False

    # =========================================================================
    # INSIDER TRADING (Form 4)
    # =========================================================================

    def get_insider_trades(
        self,
        ticker: str,
        days: int = 90,
        limit: int = 100,
    ) -> InsiderSummary:
        """
        Get insider trading data for a stock.

        Args:
            ticker: Stock symbol
            days: Lookback period in days
            limit: Maximum trades to fetch

        Returns:
            InsiderSummary with aggregated insider activity
        """
        try:
            # Call sec-edgar-agent insider trades endpoint
            # The endpoint is accessed via tools, so we use the search/tools pattern
            response = self._request(
                "POST",
                "/tools/execute",
                json_data={
                    "tool": "get_insider_trades",
                    "args": {
                        "ticker": ticker,
                        "limit": limit,
                    }
                }
            )

            return self._parse_insider_response(ticker, days, response)

        except EdgarAPIError as e:
            if e.status_code == 404:
                logger.warning(f"No insider data found for {ticker}")
                return InsiderSummary(ticker=ticker, period_days=days)
            raise
        except Exception as e:
            logger.error(f"Error fetching insider trades for {ticker}: {e}")
            return InsiderSummary(ticker=ticker, period_days=days)

    def _parse_insider_response(
        self,
        ticker: str,
        days: int,
        response: dict,
    ) -> InsiderSummary:
        """Parse insider trades response into InsiderSummary."""
        summary = InsiderSummary(ticker=ticker, period_days=days)

        if not response.get("success"):
            logger.warning(f"Insider query unsuccessful for {ticker}")
            return summary

        cutoff_date = date.today() - timedelta(days=days)
        buyers = set()
        sellers = set()

        # Response structure: by_insider -> list of insiders with transactions
        for insider_data in response.get("by_insider", []):
            insider_name = insider_data.get("name", "Unknown")
            insider_title = insider_data.get("title")

            for txn in insider_data.get("transactions", []):
                # Parse transaction date
                txn_date_str = txn.get("transaction_date")
                if not txn_date_str:
                    continue

                try:
                    txn_date = datetime.fromisoformat(txn_date_str).date()
                except ValueError:
                    continue

                # Filter by date
                if txn_date < cutoff_date:
                    continue

                txn_type = txn.get("transaction_type", "")
                shares = float(txn.get("shares", 0))
                price = txn.get("price_per_share")
                total_value = txn.get("total_value")

                if price is not None:
                    price = float(price)
                if total_value is not None:
                    total_value = float(total_value)
                elif price and shares:
                    total_value = price * shares

                trade = InsiderTrade(
                    insider_name=insider_name,
                    insider_title=insider_title,
                    transaction_date=txn_date,
                    transaction_type=txn_type,
                    shares=shares,
                    price_per_share=price,
                    total_value=total_value,
                    shares_owned_after=txn.get("shares_owned_after"),
                )

                summary.trades.append(trade)

                if trade.is_buy:
                    summary.total_buys += 1
                    summary.buy_shares += shares
                    if total_value:
                        summary.buy_value += total_value
                    buyers.add(insider_name)
                elif trade.is_sell:
                    summary.total_sells += 1
                    summary.sell_shares += shares
                    if total_value:
                        summary.sell_value += total_value
                    sellers.add(insider_name)

        summary.unique_buyers = len(buyers)
        summary.unique_sellers = len(sellers)

        return summary

    # =========================================================================
    # FINANCIAL STATEMENTS (10-K, 10-Q)
    # =========================================================================

    def get_financials(
        self,
        ticker: str,
        years: int = 3,
        include_quarterly: bool = True,
    ) -> list[FinancialData]:
        """
        Get financial statement data for a stock.

        Args:
            ticker: Stock symbol
            years: Number of years of data to fetch
            include_quarterly: Include quarterly (10-Q) data

        Returns:
            List of FinancialData objects sorted by period (newest first)
        """
        financials = []

        try:
            # Fetch income statement
            income_response = self._request(
                "POST",
                "/tools/execute",
                json_data={
                    "tool": "get_income_statement",
                    "args": {
                        "ticker": ticker,
                        "years": years,
                    }
                }
            )

            # Fetch balance sheet
            balance_response = self._request(
                "POST",
                "/tools/execute",
                json_data={
                    "tool": "get_balance_sheet",
                    "args": {
                        "ticker": ticker,
                        "years": years,
                    }
                }
            )

            # Fetch cash flow
            cashflow_response = self._request(
                "POST",
                "/tools/execute",
                json_data={
                    "tool": "get_cash_flow",
                    "args": {
                        "ticker": ticker,
                        "years": years,
                    }
                }
            )

            # Merge the three statements by period
            financials = self._merge_financials(
                ticker,
                income_response,
                balance_response,
                cashflow_response,
            )

        except Exception as e:
            logger.error(f"Error fetching financials for {ticker}: {e}")

        return financials

    def _merge_financials(
        self,
        ticker: str,
        income: dict,
        balance: dict,
        cashflow: dict,
    ) -> list[FinancialData]:
        """Merge income, balance, and cash flow data by period."""
        # Create lookup by fiscal period key
        periods: dict[str, FinancialData] = {}

        # Helper to extract period key
        def get_period_key(item: dict) -> Optional[str]:
            fy = item.get("fiscal_year")
            fp = item.get("fiscal_period", "FY")
            if fy:
                return f"{fy}-{fp}"
            return None

        # Process income statement
        for item in income.get("data", []):
            key = get_period_key(item)
            if not key:
                continue

            period_end = item.get("period_end")
            if period_end and isinstance(period_end, str):
                try:
                    period_end = datetime.fromisoformat(period_end).date()
                except ValueError:
                    period_end = None

            periods[key] = FinancialData(
                ticker=ticker,
                period_end=period_end or date.today(),
                fiscal_year=item.get("fiscal_year", 0),
                fiscal_period=item.get("fiscal_period", "FY"),
                revenue=item.get("revenue"),
                net_income=item.get("net_income"),
                operating_income=item.get("operating_income"),
                gross_profit=item.get("gross_profit"),
                eps=item.get("eps") or item.get("earnings_per_share"),
            )

        # Add balance sheet data
        for item in balance.get("data", []):
            key = get_period_key(item)
            if not key or key not in periods:
                continue

            periods[key].total_assets = item.get("total_assets")
            periods[key].total_liabilities = item.get("total_liabilities")
            periods[key].total_equity = item.get("total_equity") or item.get("stockholders_equity")
            periods[key].cash_and_equivalents = item.get("cash") or item.get("cash_and_equivalents")
            periods[key].total_debt = item.get("total_debt") or item.get("long_term_debt")

        # Add cash flow data
        for item in cashflow.get("data", []):
            key = get_period_key(item)
            if not key or key not in periods:
                continue

            periods[key].operating_cash_flow = item.get("operating_cash_flow") or item.get("cash_from_operations")
            periods[key].free_cash_flow = item.get("free_cash_flow")
            periods[key].capital_expenditures = item.get("capital_expenditures") or item.get("capex")

        # Sort by period (newest first)
        result = list(periods.values())
        result.sort(key=lambda x: (x.fiscal_year, x.fiscal_period), reverse=True)

        return result

    # =========================================================================
    # RISK FACTOR ANALYSIS
    # =========================================================================

    def get_risk_factor_changes(
        self,
        ticker: str,
        year1: int,
        year2: Optional[int] = None,
    ) -> list[RiskFactorChange]:
        """
        Get risk factor changes between two years.

        Args:
            ticker: Stock symbol
            year1: Earlier year
            year2: Later year (defaults to year1 + 1)

        Returns:
            List of RiskFactorChange objects
        """
        if year2 is None:
            year2 = year1 + 1

        try:
            response = self._request(
                "POST",
                "/filings/diff",
                json_data={
                    "ticker": ticker,
                    "form_type": "10-K",
                    "year1": year1,
                    "year2": year2,
                    "section": "risk_factors",
                }
            )

            return self._parse_risk_changes(response)

        except Exception as e:
            logger.error(f"Error fetching risk changes for {ticker}: {e}")
            return []

    def _parse_risk_changes(self, response: dict) -> list[RiskFactorChange]:
        """Parse risk factor diff response."""
        changes = []

        for item in response.get("new_risks", []):
            changes.append(RiskFactorChange(
                change_type="new",
                risk_summary=item.get("summary", ""),
            ))

        for item in response.get("removed_risks", []):
            changes.append(RiskFactorChange(
                change_type="removed",
                risk_summary=item.get("summary", ""),
            ))

        for item in response.get("modified_risks", []):
            changes.append(RiskFactorChange(
                change_type="modified",
                risk_summary=item.get("summary", ""),
                similarity_score=item.get("similarity"),
            ))

        return changes

    # =========================================================================
    # COMPANY INFO
    # =========================================================================

    def get_company_info(self, ticker: str) -> dict:
        """
        Get basic company information.

        Returns dict with: name, cik, sic, sic_description, exchange
        """
        try:
            response = self._request(
                "POST",
                "/tools/execute",
                json_data={
                    "tool": "get_company_info",
                    "args": {"ticker": ticker}
                }
            )
            return response.get("data", {})

        except Exception as e:
            logger.error(f"Error fetching company info for {ticker}: {e}")
            return {}

    # =========================================================================
    # CLEANUP
    # =========================================================================

    def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            self._client.close()
            self._client = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False


# =============================================================================
# QUICK TEST
# =============================================================================

def quick_test():
    """Test EDGAR client connectivity."""
    import sys

    print("Testing EDGAR client...")

    client = EdgarClient()

    # Health check
    if client.health_check():
        print("✓ EDGAR API is reachable")
    else:
        print("✗ EDGAR API is NOT reachable")
        print("  Make sure sec-edgar-agent is running on localhost:8000")
        sys.exit(1)

    # Test insider trades
    print("\nFetching AAPL insider trades (90 days)...")
    summary = client.get_insider_trades("AAPL", days=90)
    print(f"  Total buys: {summary.total_buys}")
    print(f"  Total sells: {summary.total_sells}")
    print(f"  Buy value: ${summary.buy_value:,.0f}")
    print(f"  Sell value: ${summary.sell_value:,.0f}")
    print(f"  Net value: ${summary.net_value:,.0f}")

    # Test financials
    print("\nFetching AAPL financials (3 years)...")
    financials = client.get_financials("AAPL", years=3)
    for fin in financials[:3]:
        print(f"  {fin.fiscal_year} {fin.fiscal_period}: Revenue ${fin.revenue/1e9:.1f}B")

    client.close()
    print("\n✓ All tests completed")


if __name__ == "__main__":
    quick_test()
