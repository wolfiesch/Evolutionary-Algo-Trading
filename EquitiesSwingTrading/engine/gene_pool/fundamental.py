"""
Fundamental Primitives for Equities Swing Trading.

These primitives provide alpha signals from SEC EDGAR data:
- Insider trading activity (Form 4)
- Financial trajectory (10-K, 10-Q)
- Risk factor changes
- Earnings quality

All primitives return normalized values suitable for strategy expressions.
These signals have longer decay periods (weeks to months) compared to
technical signals (days), making them ideal for stock selection filters
rather than entry/exit timing.

Usage:
    entry_long: insider_buy_intensity("AAPL", 90) > 0.3 AND ...
"""

import logging
from datetime import date, timedelta
from typing import Optional
from functools import lru_cache

from data.ingestion.edgar_client import (
    EdgarClient,
    EdgarConfig,
    InsiderSummary,
    FinancialData,
)

logger = logging.getLogger(__name__)

# Module-level client for reuse (created lazily)
_edgar_client: Optional[EdgarClient] = None


def _get_client() -> EdgarClient:
    """Get or create the EDGAR client."""
    global _edgar_client
    if _edgar_client is None:
        _edgar_client = EdgarClient()
    return _edgar_client


def set_edgar_client(client: EdgarClient) -> None:
    """
    Set a custom EDGAR client (useful for testing or custom config).

    Args:
        client: Configured EdgarClient instance
    """
    global _edgar_client
    _edgar_client = client


# =============================================================================
# INSIDER TRADING SIGNALS
# =============================================================================

def insider_buy_intensity(
    symbol: str,
    period_days: int = 90,
    min_value_threshold: float = 100_000,
) -> float:
    """
    Insider buy intensity - measures conviction of insider buying.

    Strong signal when multiple insiders buy with significant value.
    Normalized based on:
    - Number of unique buyers (cluster buying = stronger signal)
    - Net value (buys - sells)
    - Buy/sell ratio

    Args:
        symbol: Stock symbol
        period_days: Lookback period (default 90 days)
        min_value_threshold: Minimum transaction value to consider

    Returns:
        -1.0 to +1.0
        +1.0 = Strong insider buying (multiple buyers, high value)
        0.0 = No significant activity or balanced
        -1.0 = Strong insider selling

    Example usage:
        entry_long: insider_buy_intensity("AAPL", 90) > 0.3 AND ...
    """
    try:
        client = _get_client()
        summary = client.get_insider_trades(symbol, days=period_days)

        return _calculate_insider_intensity(summary, min_value_threshold)

    except Exception as e:
        logger.warning(f"Error calculating insider intensity for {symbol}: {e}")
        return 0.0  # Neutral on error


def _calculate_insider_intensity(
    summary: InsiderSummary,
    min_value_threshold: float,
) -> float:
    """
    Calculate insider intensity score from summary data.

    Scoring components (each 0-1):
    1. Buyer count score: More unique buyers = stronger signal
    2. Net value score: Net buying value normalized
    3. Buy/sell ratio score: Ratio of buy to sell transactions

    Final score is weighted average, then scaled to -1 to +1.
    """
    if summary.total_buys == 0 and summary.total_sells == 0:
        return 0.0

    # Component 1: Buyer count score
    # 3+ unique buyers is very bullish
    buyer_score = min(summary.unique_buyers / 3.0, 1.0)
    seller_score = min(summary.unique_sellers / 3.0, 1.0)
    count_score = buyer_score - seller_score  # -1 to +1

    # Component 2: Net value score
    # $1M+ net buying is very bullish
    net_value = summary.buy_value - summary.sell_value
    if abs(net_value) < min_value_threshold:
        value_score = 0.0
    else:
        # Scale: $1M = 1.0, cap at ±1.0
        value_score = max(-1.0, min(1.0, net_value / 1_000_000))

    # Component 3: Buy/sell ratio score
    total_txns = summary.total_buys + summary.total_sells
    if total_txns == 0:
        ratio_score = 0.0
    else:
        # Ratio of buys to total transactions, scaled to -1 to +1
        buy_ratio = summary.total_buys / total_txns
        ratio_score = 2 * buy_ratio - 1  # 0.5 -> 0, 1.0 -> 1, 0.0 -> -1

    # Weighted average
    # Buyer count is most important (cluster buying), then value, then ratio
    intensity = (
        0.4 * count_score +
        0.4 * value_score +
        0.2 * ratio_score
    )

    return float(max(-1.0, min(1.0, intensity)))


def insider_cluster_buy(
    symbol: str,
    period_days: int = 90,
    min_buyers: int = 3,
) -> float:
    """
    Insider cluster buy - binary signal for coordinated insider buying.

    A "cluster buy" is when 3+ insiders buy within a short period.
    This is a stronger signal than scattered individual purchases.

    Args:
        symbol: Stock symbol
        period_days: Lookback period
        min_buyers: Minimum unique buyers to trigger signal

    Returns:
        +1.0 = Cluster buy detected (3+ unique buyers)
        0.0 = No cluster buy

    Example usage:
        entry_long: insider_cluster_buy("AAPL", 90, 3) == 1.0 AND ...
    """
    try:
        client = _get_client()
        summary = client.get_insider_trades(symbol, days=period_days)

        if summary.unique_buyers >= min_buyers:
            return 1.0
        return 0.0

    except Exception as e:
        logger.warning(f"Error calculating cluster buy for {symbol}: {e}")
        return 0.0


# =============================================================================
# FINANCIAL TRAJECTORY SIGNALS
# =============================================================================

def revenue_cagr(
    symbol: str,
    years: int = 3,
) -> float:
    """
    Revenue CAGR - compound annual growth rate of revenue.

    Measures the company's top-line growth trajectory.
    Useful for identifying growth stocks vs value/mature companies.

    Args:
        symbol: Stock symbol
        years: Number of years for CAGR calculation

    Returns:
        -1.0 to +1.0
        +1.0 = High growth (>20% CAGR)
        0.0 = Flat (~0% CAGR)
        -1.0 = Strong decline (<-20% CAGR)

    Example usage:
        entry_long: revenue_cagr("AAPL", 3) > 0.2 AND ...
    """
    try:
        client = _get_client()
        financials = client.get_financials(symbol, years=years + 1)

        # Filter to annual data only
        annual = [f for f in financials if f.fiscal_period == "FY"]

        if len(annual) < 2:
            logger.debug(f"Insufficient annual data for {symbol} CAGR")
            return 0.0

        # Get oldest and newest annual revenue
        annual.sort(key=lambda x: x.fiscal_year)
        old_revenue = annual[0].revenue
        new_revenue = annual[-1].revenue
        actual_years = annual[-1].fiscal_year - annual[0].fiscal_year

        if not old_revenue or not new_revenue or actual_years < 1:
            return 0.0

        if old_revenue <= 0:
            return 0.0 if new_revenue <= 0 else 1.0

        # Calculate CAGR
        cagr = (new_revenue / old_revenue) ** (1 / actual_years) - 1

        # Scale: 20% CAGR = 1.0
        scaled = cagr / 0.20

        return float(max(-1.0, min(1.0, scaled)))

    except Exception as e:
        logger.warning(f"Error calculating revenue CAGR for {symbol}: {e}")
        return 0.0


def earnings_growth(
    symbol: str,
    years: int = 3,
) -> float:
    """
    Earnings growth - compound growth of net income.

    Similar to revenue CAGR but for the bottom line.

    Args:
        symbol: Stock symbol
        years: Number of years for calculation

    Returns:
        -1.0 to +1.0
        Scaled where 25% annual growth = 1.0

    Example usage:
        entry_long: earnings_growth("AAPL", 3) > 0.0 AND ...
    """
    try:
        client = _get_client()
        financials = client.get_financials(symbol, years=years + 1)

        annual = [f for f in financials if f.fiscal_period == "FY"]

        if len(annual) < 2:
            return 0.0

        annual.sort(key=lambda x: x.fiscal_year)
        old_earnings = annual[0].net_income
        new_earnings = annual[-1].net_income
        actual_years = annual[-1].fiscal_year - annual[0].fiscal_year

        if not old_earnings or not new_earnings or actual_years < 1:
            return 0.0

        # Handle sign changes
        if old_earnings < 0 and new_earnings > 0:
            return 1.0  # Turnaround
        if old_earnings > 0 and new_earnings < 0:
            return -1.0  # Deterioration
        if old_earnings < 0:
            return 0.0  # Both negative, can't calculate meaningful growth

        # Calculate growth
        cagr = (new_earnings / old_earnings) ** (1 / actual_years) - 1

        # Scale: 25% growth = 1.0
        scaled = cagr / 0.25

        return float(max(-1.0, min(1.0, scaled)))

    except Exception as e:
        logger.warning(f"Error calculating earnings growth for {symbol}: {e}")
        return 0.0


# =============================================================================
# EARNINGS QUALITY SIGNALS
# =============================================================================

def earnings_quality(
    symbol: str,
) -> float:
    """
    Earnings quality - operating cash flow vs net income ratio.

    High-quality earnings are backed by actual cash flow.
    Low quality (accrual-heavy) earnings may not be sustainable.

    The ratio OCF/NetIncome ideally should be >= 1.0.
    - >1.0: Cash flow exceeds earnings (high quality)
    - <1.0: Earnings exceed cash flow (potential accounting issues)

    Args:
        symbol: Stock symbol

    Returns:
        -1.0 to +1.0
        +1.0 = OCF >= 1.5x Net Income (very high quality)
        0.0 = OCF = Net Income (neutral)
        -1.0 = OCF <= 0.5x Net Income (low quality)

    Example usage:
        entry_long: earnings_quality("AAPL") > 0.0 AND ...
    """
    try:
        client = _get_client()
        financials = client.get_financials(symbol, years=1)

        # Get most recent annual data
        annual = [f for f in financials if f.fiscal_period == "FY"]

        if not annual:
            return 0.0

        most_recent = annual[0]  # Already sorted newest first

        ocf = most_recent.operating_cash_flow
        net_income = most_recent.net_income

        if not ocf or not net_income:
            return 0.0

        # Handle edge cases
        if net_income <= 0:
            # Losing money - positive OCF is good, negative is bad
            if ocf > 0:
                return 0.5
            return -0.5

        # Calculate quality ratio
        quality_ratio = ocf / net_income

        # Scale: ratio of 1.0 = 0, 1.5 = +1, 0.5 = -1
        scaled = (quality_ratio - 1.0) * 2

        return float(max(-1.0, min(1.0, scaled)))

    except Exception as e:
        logger.warning(f"Error calculating earnings quality for {symbol}: {e}")
        return 0.0


def free_cash_flow_yield(
    symbol: str,
    market_cap: Optional[float] = None,
) -> float:
    """
    Free cash flow yield - FCF / Market Cap.

    High FCF yield indicates potential undervaluation.
    Low or negative FCF yield may indicate overvaluation.

    Args:
        symbol: Stock symbol
        market_cap: Market cap (will fetch if not provided)

    Returns:
        -1.0 to +1.0
        +1.0 = FCF yield >= 10% (potentially undervalued)
        0.0 = FCF yield ~5% (typical)
        -1.0 = Negative FCF or very low yield

    Example usage:
        entry_long: free_cash_flow_yield("AAPL") > 0.0 AND ...
    """
    try:
        client = _get_client()
        financials = client.get_financials(symbol, years=1)

        annual = [f for f in financials if f.fiscal_period == "FY"]

        if not annual:
            return 0.0

        fcf = annual[0].free_cash_flow

        if not fcf:
            return 0.0

        # Get market cap if not provided
        if market_cap is None:
            company_info = client.get_company_info(symbol)
            market_cap = company_info.get("market_cap")

        if not market_cap or market_cap <= 0:
            return 0.0

        # Calculate FCF yield
        fcf_yield = fcf / market_cap

        # Scale: 5% yield = 0, 10% yield = +1, 0% = -1
        scaled = (fcf_yield - 0.05) * 20

        return float(max(-1.0, min(1.0, scaled)))

    except Exception as e:
        logger.warning(f"Error calculating FCF yield for {symbol}: {e}")
        return 0.0


# =============================================================================
# RISK FACTOR SIGNALS
# =============================================================================

def risk_change_intensity(
    symbol: str,
    year: Optional[int] = None,
) -> float:
    """
    Risk change intensity - measures significance of risk factor changes.

    Large changes in risk factors may signal material changes in business.
    New risks are weighted more heavily than removed risks.

    Args:
        symbol: Stock symbol
        year: Year to compare (compares year to year-1)

    Returns:
        -1.0 to +1.0
        +1.0 = Many new risks added (potential concerns)
        0.0 = Few/no changes
        -1.0 = Many risks removed (improving situation)

    Example usage:
        entry_long: risk_change_intensity("AAPL") < 0.3 AND ...
    """
    if year is None:
        year = date.today().year - 1  # Compare most recent filings

    try:
        client = _get_client()
        changes = client.get_risk_factor_changes(symbol, year - 1, year)

        if not changes:
            return 0.0

        # Count by type
        new_risks = sum(1 for c in changes if c.change_type == "new")
        removed_risks = sum(1 for c in changes if c.change_type == "removed")
        modified_risks = sum(1 for c in changes if c.change_type == "modified")

        # Score: new risks are concerning, removed risks are positive
        # Modified risks are weighted at 0.5
        net_score = new_risks - removed_risks + 0.5 * modified_risks

        # Scale: 5 net new risks = 1.0
        scaled = net_score / 5.0

        return float(max(-1.0, min(1.0, scaled)))

    except Exception as e:
        logger.warning(f"Error calculating risk change for {symbol}: {e}")
        return 0.0


# =============================================================================
# COMPOSITE SIGNALS
# =============================================================================

def fundamental_score(
    symbol: str,
) -> float:
    """
    Composite fundamental score - combines multiple fundamental signals.

    A convenience function that aggregates:
    - Insider activity (25%)
    - Revenue growth (25%)
    - Earnings quality (25%)
    - Risk factors (25%)

    Args:
        symbol: Stock symbol

    Returns:
        -1.0 to +1.0 composite score

    Example usage:
        entry_long: fundamental_score("AAPL") > 0.3 AND spy_trend(20) >= 0 AND ...
    """
    try:
        insider = insider_buy_intensity(symbol, 90)
        revenue = revenue_cagr(symbol, 3)
        quality = earnings_quality(symbol)
        risk = -risk_change_intensity(symbol)  # Negate so positive = good

        # Equal weighting
        composite = 0.25 * (insider + revenue + quality + risk)

        return float(max(-1.0, min(1.0, composite)))

    except Exception as e:
        logger.warning(f"Error calculating fundamental score for {symbol}: {e}")
        return 0.0


# =============================================================================
# QUICK TEST
# =============================================================================

def quick_test():
    """Test fundamental primitives."""
    print("Testing fundamental primitives...")
    print("(Requires sec-edgar-agent running on localhost:8000)")
    print()

    test_symbols = ["AAPL", "MSFT", "NVDA"]

    for symbol in test_symbols:
        print(f"=== {symbol} ===")

        try:
            print(f"  insider_buy_intensity(90): {insider_buy_intensity(symbol, 90):.2f}")
            print(f"  insider_cluster_buy(90, 3): {insider_cluster_buy(symbol, 90, 3):.2f}")
            print(f"  revenue_cagr(3): {revenue_cagr(symbol, 3):.2f}")
            print(f"  earnings_growth(3): {earnings_growth(symbol, 3):.2f}")
            print(f"  earnings_quality(): {earnings_quality(symbol):.2f}")
            print(f"  risk_change_intensity(): {risk_change_intensity(symbol):.2f}")
            print(f"  fundamental_score(): {fundamental_score(symbol):.2f}")
        except Exception as e:
            print(f"  Error: {e}")

        print()


if __name__ == "__main__":
    quick_test()
