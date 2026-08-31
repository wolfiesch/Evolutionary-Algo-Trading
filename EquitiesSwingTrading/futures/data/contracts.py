"""
Futures contract definitions and rollover logic.

Handles the complexity of futures contract expiration and rollover.
"""
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional, List, Tuple
from enum import Enum


class ContractMonth(Enum):
    """CME contract month codes."""
    F = 1   # January
    G = 2   # February
    H = 3   # March
    J = 4   # April
    K = 5   # May
    M = 6   # June
    N = 7   # July
    Q = 8   # August
    U = 9   # September
    V = 10  # October
    X = 11  # November
    Z = 12  # December

    @classmethod
    def from_month(cls, month: int) -> "ContractMonth":
        """Get contract month code from month number."""
        for cm in cls:
            if cm.value == month:
                return cm
        raise ValueError(f"Invalid month: {month}")

    @classmethod
    def from_code(cls, code: str) -> "ContractMonth":
        """Get contract month from single-letter code."""
        return cls[code.upper()]


# Quarterly contract months (ES, NQ, MES, MNQ)
QUARTERLY_MONTHS = [ContractMonth.H, ContractMonth.M, ContractMonth.U, ContractMonth.Z]

# Monthly contract months (CL, MCL)
MONTHLY_MONTHS = list(ContractMonth)


@dataclass
class FuturesContract:
    """
    Represents a specific futures contract instance.

    Example: ESZ24 = E-mini S&P 500 December 2024
    """
    symbol: str              # Root symbol (ES, NQ, CL, etc.)
    month: ContractMonth     # Contract month
    year: int                # Full year (2024, not 24)

    @property
    def local_symbol(self) -> str:
        """
        Get the local symbol format used by exchanges.

        Example: ESZ4 or ESZ24 depending on context
        """
        year_suffix = str(self.year)[-1]  # Last digit for short form
        return f"{self.symbol}{self.month.name}{year_suffix}"

    @property
    def full_symbol(self) -> str:
        """
        Get full symbol with 2-digit year.

        Example: ESZ24
        """
        year_suffix = str(self.year)[-2:]
        return f"{self.symbol}{self.month.name}{year_suffix}"

    @property
    def expiry_month_str(self) -> str:
        """
        Get expiry in YYYYMM format for IBKR API.

        Example: "202412" for December 2024
        """
        return f"{self.year}{self.month.value:02d}"

    def __str__(self) -> str:
        return self.full_symbol

    def __repr__(self) -> str:
        return f"FuturesContract({self.full_symbol})"


def get_quarterly_expiry_date(month: ContractMonth, year: int) -> date:
    """
    Calculate the expiry date for quarterly index futures.

    ES/NQ expire on the 3rd Friday of the contract month.
    """
    # Find first day of expiry month
    first_day = date(year, month.value, 1)

    # Find first Friday
    days_until_friday = (4 - first_day.weekday()) % 7
    first_friday = first_day + timedelta(days=days_until_friday)

    # Third Friday is 14 days after first Friday
    third_friday = first_friday + timedelta(days=14)

    return third_friday


def get_crude_expiry_date(month: ContractMonth, year: int) -> date:
    """
    Calculate the expiry date for crude oil futures.

    CL expires on the 3rd business day before the 25th of the month
    PRIOR to the contract month.
    """
    # Contract month - 1 for the expiry calculation month
    if month.value == 1:
        expiry_month = 12
        expiry_year = year - 1
    else:
        expiry_month = month.value - 1
        expiry_year = year

    # Start from the 25th
    target = date(expiry_year, expiry_month, 25)

    # Count back 3 business days
    business_days = 0
    current = target
    while business_days < 3:
        current -= timedelta(days=1)
        # Skip weekends (crude doesn't trade on holidays either, but this is approximate)
        if current.weekday() < 5:
            business_days += 1

    return current


def get_front_month(
    symbol: str,
    reference_date: Optional[date] = None,
    rollover_days_before_expiry: int = 5
) -> FuturesContract:
    """
    Get the current front-month contract.

    Accounts for rollover: switches to next month when close to expiry.

    Args:
        symbol: Root symbol (ES, NQ, CL, etc.)
        reference_date: Date to calculate from (default: today)
        rollover_days_before_expiry: Days before expiry to roll to next month

    Returns:
        FuturesContract for the front month
    """
    if reference_date is None:
        reference_date = date.today()

    # Determine if quarterly or monthly contract
    is_quarterly = symbol.upper() in ("ES", "NQ", "MES", "MNQ", "RTY", "YM")
    contract_months = QUARTERLY_MONTHS if is_quarterly else MONTHLY_MONTHS

    # Find the next valid contract month
    current_year = reference_date.year
    current_month = reference_date.month

    # Look ahead up to 14 months to find the front month
    for _ in range(14):
        for cm in contract_months:
            if cm.value < current_month:
                continue

            # Calculate expiry for this contract
            if is_quarterly:
                expiry = get_quarterly_expiry_date(cm, current_year)
            else:
                expiry = get_crude_expiry_date(cm, current_year)

            # Check if we should use this contract or roll to next
            days_to_expiry = (expiry - reference_date).days

            if days_to_expiry > rollover_days_before_expiry:
                return FuturesContract(
                    symbol=symbol.upper(),
                    month=cm,
                    year=current_year
                )

        # Move to next year
        current_year += 1
        current_month = 1

    # Fallback (shouldn't reach here)
    raise ValueError(f"Could not determine front month for {symbol}")


def get_next_contract(contract: FuturesContract) -> FuturesContract:
    """
    Get the next contract after the given one.

    For quarterly contracts, jumps to next quarter.
    For monthly contracts, goes to next month.
    """
    is_quarterly = contract.symbol in ("ES", "NQ", "MES", "MNQ", "RTY", "YM")
    contract_months = QUARTERLY_MONTHS if is_quarterly else MONTHLY_MONTHS

    # Find current position in contract months
    try:
        current_idx = contract_months.index(contract.month)
    except ValueError:
        # If not in list, find next valid month
        current_idx = -1
        for i, cm in enumerate(contract_months):
            if cm.value > contract.month.value:
                current_idx = i - 1
                break

    # Get next month
    next_idx = (current_idx + 1) % len(contract_months)
    next_month = contract_months[next_idx]

    # Determine year
    if next_month.value <= contract.month.value:
        next_year = contract.year + 1
    else:
        next_year = contract.year

    return FuturesContract(
        symbol=contract.symbol,
        month=next_month,
        year=next_year
    )


def get_contract_chain(
    symbol: str,
    num_contracts: int = 4,
    reference_date: Optional[date] = None
) -> List[FuturesContract]:
    """
    Get a chain of upcoming contracts.

    Useful for analyzing term structure / contango / backwardation.

    Args:
        symbol: Root symbol
        num_contracts: Number of contracts to return
        reference_date: Starting reference date

    Returns:
        List of FuturesContracts starting with front month
    """
    chain = []
    current = get_front_month(symbol, reference_date)

    for _ in range(num_contracts):
        chain.append(current)
        current = get_next_contract(current)

    return chain


def should_rollover(
    contract: FuturesContract,
    reference_date: Optional[date] = None,
    days_before_expiry: int = 5
) -> Tuple[bool, Optional[FuturesContract]]:
    """
    Check if a contract should be rolled over.

    Args:
        contract: Current contract
        reference_date: Date to check against
        days_before_expiry: Days before expiry to trigger rollover

    Returns:
        Tuple of (should_roll, next_contract or None)
    """
    if reference_date is None:
        reference_date = date.today()

    # Calculate expiry
    is_quarterly = contract.symbol in ("ES", "NQ", "MES", "MNQ", "RTY", "YM")
    if is_quarterly:
        expiry = get_quarterly_expiry_date(contract.month, contract.year)
    else:
        expiry = get_crude_expiry_date(contract.month, contract.year)

    days_to_expiry = (expiry - reference_date).days

    if days_to_expiry <= days_before_expiry:
        return True, get_next_contract(contract)

    return False, None


def create_ibkr_contract_params(contract: FuturesContract) -> dict:
    """
    Create parameters dict for IBKR Contract object.

    Returns dict that can be used with ibapi.contract.Contract
    """
    # Map symbols to exchanges
    exchange_map = {
        "ES": "CME",
        "NQ": "CME",
        "MES": "CME",
        "MNQ": "CME",
        "RTY": "CME",
        "YM": "CBOT",
        "CL": "NYMEX",
        "MCL": "NYMEX",
        "NG": "NYMEX",
        "MNG": "NYMEX",
        "GC": "COMEX",
        "MGC": "COMEX",
    }

    exchange = exchange_map.get(contract.symbol, "CME")

    return {
        "symbol": contract.symbol,
        "secType": "FUT",
        "exchange": exchange,
        "currency": "USD",
        "lastTradeDateOrContractMonth": contract.expiry_month_str,
    }


# Convenience functions for common contracts
def es_front_month(reference_date: Optional[date] = None) -> FuturesContract:
    """Get front month ES contract."""
    return get_front_month("ES", reference_date)


def mes_front_month(reference_date: Optional[date] = None) -> FuturesContract:
    """Get front month MES (micro) contract."""
    return get_front_month("MES", reference_date)


def nq_front_month(reference_date: Optional[date] = None) -> FuturesContract:
    """Get front month NQ contract."""
    return get_front_month("NQ", reference_date)


def cl_front_month(reference_date: Optional[date] = None) -> FuturesContract:
    """Get front month CL (crude) contract."""
    return get_front_month("CL", reference_date)
