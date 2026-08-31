"""
Tests for EDGAR HTTP client.

Uses mocks to test without requiring sec-edgar-agent to be running.
"""

import pytest
from datetime import date, datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
import httpx

import sys
sys.path.insert(0, ".")

from data.ingestion.edgar_client import (
    EdgarClient,
    EdgarConfig,
    InsiderTrade,
    InsiderSummary,
    FinancialData,
    RiskFactorChange,
    EdgarConnectionError,
    EdgarAPIError,
)


class TestEdgarClient:
    """Tests for EdgarClient class."""

    def test_init_default_config(self):
        """Client should use default config if not provided."""
        client = EdgarClient()
        assert client.config.base_url == "http://localhost:8000/api/v1"
        assert client.config.timeout == 30.0

    def test_init_custom_config(self):
        """Client should use custom config if provided."""
        config = EdgarConfig(
            base_url="http://custom:9000",
            timeout=60.0,
        )
        client = EdgarClient(config)
        assert client.config.base_url == "http://custom:9000"
        assert client.config.timeout == 60.0


class TestInsiderTrades:
    """Tests for insider trading functionality."""

    @pytest.fixture
    def mock_insider_response(self):
        """Mock response for insider trades."""
        return {
            "success": True,
            "by_insider": [
                {
                    "name": "John CEO",
                    "title": "CEO",
                    "transactions": [
                        {
                            "transaction_date": (date.today() - timedelta(days=5)).isoformat(),
                            "transaction_type": "P",
                            "shares": 10000,
                            "price_per_share": 150.0,
                            "total_value": 1500000,
                            "shares_owned_after": 50000,
                        },
                        {
                            "transaction_date": (date.today() - timedelta(days=10)).isoformat(),
                            "transaction_type": "P",
                            "shares": 5000,
                            "price_per_share": 145.0,
                            "total_value": 725000,
                            "shares_owned_after": 40000,
                        },
                    ]
                },
                {
                    "name": "Jane CFO",
                    "title": "CFO",
                    "transactions": [
                        {
                            "transaction_date": (date.today() - timedelta(days=3)).isoformat(),
                            "transaction_type": "S",
                            "shares": 2000,
                            "price_per_share": 155.0,
                            "total_value": 310000,
                            "shares_owned_after": 20000,
                        },
                    ]
                },
            ]
        }

    def test_parse_insider_response(self, mock_insider_response):
        """Should correctly parse insider response."""
        client = EdgarClient()
        summary = client._parse_insider_response("AAPL", 90, mock_insider_response)

        assert summary.ticker == "AAPL"
        assert summary.period_days == 90
        assert summary.total_buys == 2
        assert summary.total_sells == 1
        assert summary.buy_value == 2225000  # 1500000 + 725000
        assert summary.sell_value == 310000
        assert summary.unique_buyers == 1  # John CEO
        assert summary.unique_sellers == 1  # Jane CFO

    def test_parse_empty_response(self):
        """Should handle empty response."""
        client = EdgarClient()
        summary = client._parse_insider_response("AAPL", 90, {"success": False})

        assert summary.total_buys == 0
        assert summary.total_sells == 0

    def test_insider_summary_net_value(self):
        """InsiderSummary should calculate net value correctly."""
        summary = InsiderSummary(
            ticker="AAPL",
            period_days=90,
            buy_value=1000000,
            sell_value=300000,
        )
        assert summary.net_value == 700000

    def test_insider_summary_buy_sell_ratio(self):
        """InsiderSummary should calculate buy/sell ratio correctly."""
        summary = InsiderSummary(
            ticker="AAPL",
            period_days=90,
            total_buys=10,
            total_sells=5,
        )
        assert summary.buy_sell_ratio == 2.0

    def test_insider_summary_ratio_no_sells(self):
        """Buy/sell ratio should handle zero sells."""
        summary = InsiderSummary(
            ticker="AAPL",
            period_days=90,
            total_buys=10,
            total_sells=0,
        )
        assert summary.buy_sell_ratio == 10.0


class TestInsiderTrade:
    """Tests for InsiderTrade model."""

    def test_is_buy(self):
        """Should correctly identify buy transactions."""
        trade = InsiderTrade(
            insider_name="Test",
            insider_title=None,
            transaction_date=date.today(),
            transaction_type="P",
            shares=100,
            price_per_share=50.0,
            total_value=5000,
            shares_owned_after=1000,
        )
        assert trade.is_buy is True
        assert trade.is_sell is False

    def test_is_sell(self):
        """Should correctly identify sell transactions."""
        trade = InsiderTrade(
            insider_name="Test",
            insider_title=None,
            transaction_date=date.today(),
            transaction_type="S",
            shares=100,
            price_per_share=50.0,
            total_value=5000,
            shares_owned_after=1000,
        )
        assert trade.is_buy is False
        assert trade.is_sell is True


class TestFinancials:
    """Tests for financial data functionality."""

    @pytest.fixture
    def mock_income_response(self):
        """Mock income statement response."""
        return {
            "data": [
                {
                    "fiscal_year": 2024,
                    "fiscal_period": "FY",
                    "period_end": "2024-09-30",
                    "revenue": 383285000000,
                    "net_income": 93736000000,
                    "operating_income": 114301000000,
                    "gross_profit": 169148000000,
                    "eps": 6.08,
                },
                {
                    "fiscal_year": 2023,
                    "fiscal_period": "FY",
                    "period_end": "2023-09-30",
                    "revenue": 383933000000,
                    "net_income": 96995000000,
                    "operating_income": 118658000000,
                    "gross_profit": 169148000000,
                    "eps": 6.16,
                },
            ]
        }

    @pytest.fixture
    def mock_balance_response(self):
        """Mock balance sheet response."""
        return {
            "data": [
                {
                    "fiscal_year": 2024,
                    "fiscal_period": "FY",
                    "total_assets": 352583000000,
                    "total_liabilities": 308030000000,
                    "total_equity": 74000000000,
                    "cash": 29965000000,
                },
            ]
        }

    @pytest.fixture
    def mock_cashflow_response(self):
        """Mock cash flow response."""
        return {
            "data": [
                {
                    "fiscal_year": 2024,
                    "fiscal_period": "FY",
                    "operating_cash_flow": 118254000000,
                    "free_cash_flow": 108807000000,
                    "capital_expenditures": -9447000000,
                },
            ]
        }

    def test_merge_financials(
        self,
        mock_income_response,
        mock_balance_response,
        mock_cashflow_response,
    ):
        """Should correctly merge financial statements."""
        client = EdgarClient()
        financials = client._merge_financials(
            "AAPL",
            mock_income_response,
            mock_balance_response,
            mock_cashflow_response,
        )

        assert len(financials) >= 1

        # Check 2024 data
        fy2024 = next(
            (f for f in financials if f.fiscal_year == 2024 and f.fiscal_period == "FY"),
            None
        )
        assert fy2024 is not None
        assert fy2024.revenue == 383285000000
        assert fy2024.operating_cash_flow == 118254000000


class TestRiskFactors:
    """Tests for risk factor functionality."""

    def test_parse_risk_changes(self):
        """Should correctly parse risk factor changes."""
        response = {
            "new_risks": [
                {"summary": "AI competition risk"},
                {"summary": "Supply chain disruption"},
            ],
            "removed_risks": [
                {"summary": "COVID-19 impact"},
            ],
            "modified_risks": [
                {"summary": "Regulatory compliance", "similarity": 0.7},
            ],
        }

        client = EdgarClient()
        changes = client._parse_risk_changes(response)

        new_risks = [c for c in changes if c.change_type == "new"]
        removed_risks = [c for c in changes if c.change_type == "removed"]
        modified_risks = [c for c in changes if c.change_type == "modified"]

        assert len(new_risks) == 2
        assert len(removed_risks) == 1
        assert len(modified_risks) == 1
        assert modified_risks[0].similarity_score == 0.7


class TestConnectionHandling:
    """Tests for connection error handling."""

    def test_retry_on_connection_error(self):
        """Should retry on connection errors."""
        client = EdgarClient(EdgarConfig(max_retries=2, retry_delay=0.1))

        with patch.object(client, '_get_client') as mock_get_client:
            mock_http = MagicMock()
            mock_http.get.side_effect = httpx.ConnectError("Connection refused")
            mock_get_client.return_value = mock_http

            with pytest.raises(EdgarConnectionError):
                client._request("GET", "/test")

            # Should have tried multiple times
            assert mock_http.get.call_count == 2


class TestHealthCheck:
    """Tests for health check functionality."""

    def test_health_check_success(self):
        """Health check should return True when API is reachable."""
        client = EdgarClient()

        with patch.object(client, '_request') as mock_request:
            mock_request.return_value = {"status": "ok"}
            assert client.health_check() is True

    def test_health_check_failure(self):
        """Health check should return False when API is unreachable."""
        client = EdgarClient()

        with patch.object(client, '_request') as mock_request:
            mock_request.side_effect = EdgarConnectionError("Connection failed")
            assert client.health_check() is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
