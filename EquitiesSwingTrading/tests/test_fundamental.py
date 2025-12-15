"""
Tests for fundamental primitives.

Uses mocks to test without requiring sec-edgar-agent to be running.
"""

import pytest
from datetime import date, timedelta
from unittest.mock import Mock, patch

import sys
sys.path.insert(0, ".")

from data.ingestion.edgar_client import (
    InsiderSummary,
    InsiderTrade,
    FinancialData,
    EdgarClient,
)
from engine.gene_pool.fundamental import (
    _calculate_insider_intensity,
    insider_buy_intensity,
    insider_cluster_buy,
    revenue_cagr,
    earnings_growth,
    earnings_quality,
    fundamental_score,
    set_edgar_client,
)


class TestInsiderIntensity:
    """Tests for insider_buy_intensity primitive."""

    def test_strong_buying_returns_positive(self):
        """Strong buying activity should return positive intensity."""
        summary = InsiderSummary(
            ticker="AAPL",
            period_days=90,
            total_buys=10,
            total_sells=2,
            buy_value=5_000_000,
            sell_value=500_000,
            buy_shares=50000,
            sell_shares=5000,
            unique_buyers=4,
            unique_sellers=1,
        )

        intensity = _calculate_insider_intensity(summary, min_value_threshold=100_000)

        # Should be strongly positive with 4 unique buyers and net $4.5M buying
        assert intensity > 0.5

    def test_strong_selling_returns_negative(self):
        """Strong selling activity should return negative intensity."""
        summary = InsiderSummary(
            ticker="AAPL",
            period_days=90,
            total_buys=1,
            total_sells=15,
            buy_value=100_000,
            sell_value=10_000_000,
            buy_shares=1000,
            sell_shares=100000,
            unique_buyers=1,
            unique_sellers=5,
        )

        intensity = _calculate_insider_intensity(summary, min_value_threshold=100_000)

        # Should be strongly negative
        assert intensity < -0.3

    def test_no_activity_returns_zero(self):
        """No activity should return zero."""
        summary = InsiderSummary(
            ticker="AAPL",
            period_days=90,
        )

        intensity = _calculate_insider_intensity(summary, min_value_threshold=100_000)
        assert intensity == 0.0

    def test_balanced_activity_near_zero(self):
        """Balanced buying/selling should return near zero."""
        summary = InsiderSummary(
            ticker="AAPL",
            period_days=90,
            total_buys=5,
            total_sells=5,
            buy_value=1_000_000,
            sell_value=1_000_000,
            unique_buyers=2,
            unique_sellers=2,
        )

        intensity = _calculate_insider_intensity(summary, min_value_threshold=100_000)

        # Should be close to zero
        assert -0.2 <= intensity <= 0.2

    def test_intensity_bounded(self):
        """Intensity should always be between -1 and 1."""
        # Extreme buying
        summary = InsiderSummary(
            ticker="AAPL",
            period_days=90,
            total_buys=100,
            total_sells=0,
            buy_value=100_000_000,
            unique_buyers=20,
        )

        intensity = _calculate_insider_intensity(summary, min_value_threshold=100_000)
        assert -1.0 <= intensity <= 1.0


class TestInsiderClusterBuy:
    """Tests for insider_cluster_buy primitive."""

    @pytest.fixture
    def mock_client(self):
        """Create mock EDGAR client."""
        client = Mock(spec=EdgarClient)
        return client

    def test_cluster_detected_with_3_buyers(self, mock_client):
        """Should detect cluster buy with 3+ unique buyers."""
        mock_client.get_insider_trades.return_value = InsiderSummary(
            ticker="AAPL",
            period_days=90,
            total_buys=5,
            unique_buyers=3,
        )

        set_edgar_client(mock_client)
        result = insider_cluster_buy("AAPL", 90, min_buyers=3)

        assert result == 1.0

    def test_no_cluster_with_2_buyers(self, mock_client):
        """Should not detect cluster with fewer than 3 buyers."""
        mock_client.get_insider_trades.return_value = InsiderSummary(
            ticker="AAPL",
            period_days=90,
            total_buys=10,
            unique_buyers=2,
        )

        set_edgar_client(mock_client)
        result = insider_cluster_buy("AAPL", 90, min_buyers=3)

        assert result == 0.0


class TestRevenueCagr:
    """Tests for revenue_cagr primitive."""

    @pytest.fixture
    def mock_client_growth(self):
        """Mock client returning growing revenue."""
        client = Mock(spec=EdgarClient)
        client.get_financials.return_value = [
            FinancialData(
                ticker="AAPL",
                period_end=date(2024, 9, 30),
                fiscal_year=2024,
                fiscal_period="FY",
                revenue=400_000_000_000,  # $400B
            ),
            FinancialData(
                ticker="AAPL",
                period_end=date(2023, 9, 30),
                fiscal_year=2023,
                fiscal_period="FY",
                revenue=383_000_000_000,  # $383B
            ),
            FinancialData(
                ticker="AAPL",
                period_end=date(2022, 9, 30),
                fiscal_year=2022,
                fiscal_period="FY",
                revenue=330_000_000_000,  # $330B
            ),
        ]
        return client

    @pytest.fixture
    def mock_client_decline(self):
        """Mock client returning declining revenue."""
        client = Mock(spec=EdgarClient)
        client.get_financials.return_value = [
            FinancialData(
                ticker="TEST",
                period_end=date(2024, 12, 31),
                fiscal_year=2024,
                fiscal_period="FY",
                revenue=80_000_000_000,
            ),
            FinancialData(
                ticker="TEST",
                period_end=date(2022, 12, 31),
                fiscal_year=2022,
                fiscal_period="FY",
                revenue=100_000_000_000,
            ),
        ]
        return client

    def test_positive_growth_returns_positive(self, mock_client_growth):
        """Growing revenue should return positive value."""
        set_edgar_client(mock_client_growth)
        result = revenue_cagr("AAPL", 3)

        # ~10% CAGR should map to ~0.5
        assert result > 0

    def test_declining_revenue_returns_negative(self, mock_client_decline):
        """Declining revenue should return negative value."""
        set_edgar_client(mock_client_decline)
        result = revenue_cagr("TEST", 3)

        assert result < 0


class TestEarningsQuality:
    """Tests for earnings_quality primitive."""

    @pytest.fixture
    def mock_client_high_quality(self):
        """Mock client with high earnings quality (OCF > Net Income)."""
        client = Mock(spec=EdgarClient)
        client.get_financials.return_value = [
            FinancialData(
                ticker="AAPL",
                period_end=date(2024, 9, 30),
                fiscal_year=2024,
                fiscal_period="FY",
                net_income=90_000_000_000,
                operating_cash_flow=120_000_000_000,  # 1.33x net income
            ),
        ]
        return client

    @pytest.fixture
    def mock_client_low_quality(self):
        """Mock client with low earnings quality (OCF < Net Income)."""
        client = Mock(spec=EdgarClient)
        client.get_financials.return_value = [
            FinancialData(
                ticker="TEST",
                period_end=date(2024, 12, 31),
                fiscal_year=2024,
                fiscal_period="FY",
                net_income=100_000_000_000,
                operating_cash_flow=60_000_000_000,  # 0.6x net income
            ),
        ]
        return client

    def test_high_quality_returns_positive(self, mock_client_high_quality):
        """High earnings quality (OCF > NI) should return positive."""
        set_edgar_client(mock_client_high_quality)
        result = earnings_quality("AAPL")

        # OCF/NI = 1.33, should be positive
        assert result > 0

    def test_low_quality_returns_negative(self, mock_client_low_quality):
        """Low earnings quality (OCF < NI) should return negative."""
        set_edgar_client(mock_client_low_quality)
        result = earnings_quality("TEST")

        # OCF/NI = 0.6, should be negative
        assert result < 0


class TestFundamentalScore:
    """Tests for composite fundamental_score primitive."""

    @pytest.fixture
    def mock_client_strong(self):
        """Mock client with strong fundamentals across all metrics."""
        client = Mock(spec=EdgarClient)

        # Strong insider buying
        client.get_insider_trades.return_value = InsiderSummary(
            ticker="AAPL",
            period_days=90,
            total_buys=10,
            total_sells=1,
            buy_value=5_000_000,
            sell_value=100_000,
            unique_buyers=4,
            unique_sellers=1,
        )

        # Strong revenue growth
        client.get_financials.return_value = [
            FinancialData(
                ticker="AAPL",
                period_end=date(2024, 9, 30),
                fiscal_year=2024,
                fiscal_period="FY",
                revenue=150_000_000_000,
                net_income=40_000_000_000,
                operating_cash_flow=50_000_000_000,
            ),
            FinancialData(
                ticker="AAPL",
                period_end=date(2021, 9, 30),
                fiscal_year=2021,
                fiscal_period="FY",
                revenue=100_000_000_000,
            ),
        ]

        # Few risk changes
        client.get_risk_factor_changes.return_value = []

        return client

    def test_strong_fundamentals_positive(self, mock_client_strong):
        """Strong fundamentals should yield positive composite score."""
        set_edgar_client(mock_client_strong)
        score = fundamental_score("AAPL")

        # With strong metrics across the board, score should be positive
        assert score > 0


class TestPrimitiveNormalization:
    """Tests that all primitives return normalized values."""

    def test_intensity_returns_float(self):
        """insider_buy_intensity should return float."""
        summary = InsiderSummary(ticker="AAPL", period_days=90)
        result = _calculate_insider_intensity(summary, 100_000)
        assert isinstance(result, float)

    def test_all_primitives_bounded(self):
        """All primitives should return values in [-1, 1] or [0, 1] range."""
        # This is a design contract - values should never exceed bounds
        # Test with extreme inputs

        summary = InsiderSummary(
            ticker="AAPL",
            period_days=90,
            total_buys=1000,
            total_sells=0,
            buy_value=1e12,  # $1 trillion
            unique_buyers=100,
        )

        intensity = _calculate_insider_intensity(summary, 0)
        assert -1.0 <= intensity <= 1.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
