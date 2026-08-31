"""
Equities Backtester Configuration.

Adapts the shared backtester for equities swing trading:
- Lower friction (0.03% vs crypto's 0.25%)
- More positions (up to 20)
- Daily bars (not 1-minute)
- Wider stops (5% vs 3%)
"""

from dataclasses import dataclass
from typing import Optional

import sys
sys.path.insert(0, "/Users/wolfgangschoenberger/Projects/Oil-Stonks")

from shared.evolution.backtester import BacktestConfig


@dataclass
class EquitiesBacktestConfig(BacktestConfig):
    """
    Equities-specific backtest configuration.

    Key differences from crypto:
    - Lower friction (stock commissions ~0.03% vs crypto 0.25%)
    - More diversified positions (20 vs 5)
    - Wider stops (daily volatility)
    - Higher exposure limits (80% vs 50%)
    """

    # Override defaults for equities
    initial_equity: float = 100_000       # Typical equity account
    friction_per_side: float = 0.0003     # 0.03% per side (~$3 per $10k trade)
    max_position_pct: float = 0.05        # 5% max per position (more diversified)
    risk_per_trade: float = 0.01          # 1% risk per trade
    max_open_positions: int = 20          # Up to 20 concurrent positions
    max_total_exposure: float = 0.80      # 80% max total exposure
    stop_loss_pct: float = 0.05           # 5% stop (wider for daily volatility)
    min_position_interval_bars: int = 1   # 1 day between entries (daily bars)

    # Equities-specific
    warmup_bars: int = 60                 # 60 trading days warmup (~3 months)
    benchmark_symbol: str = "SPY"         # Default benchmark
    allow_shorting: bool = False          # Start long-only


# Pre-configured configs for different use cases
CONSERVATIVE_CONFIG = EquitiesBacktestConfig(
    max_position_pct=0.03,
    max_open_positions=10,
    max_total_exposure=0.50,
    stop_loss_pct=0.03,
)

AGGRESSIVE_CONFIG = EquitiesBacktestConfig(
    max_position_pct=0.08,
    max_open_positions=15,
    max_total_exposure=0.90,
    stop_loss_pct=0.07,
)

DEVELOPMENT_CONFIG = EquitiesBacktestConfig(
    initial_equity=50_000,
    max_position_pct=0.10,
    max_open_positions=5,
    warmup_bars=30,
)


def get_config(profile: str = "default") -> EquitiesBacktestConfig:
    """
    Get backtest config by profile name.

    Args:
        profile: "default", "conservative", "aggressive", or "development"

    Returns:
        EquitiesBacktestConfig instance
    """
    configs = {
        "default": EquitiesBacktestConfig(),
        "conservative": CONSERVATIVE_CONFIG,
        "aggressive": AGGRESSIVE_CONFIG,
        "development": DEVELOPMENT_CONFIG,
    }
    return configs.get(profile, EquitiesBacktestConfig())


__all__ = [
    "EquitiesBacktestConfig",
    "CONSERVATIVE_CONFIG",
    "AGGRESSIVE_CONFIG",
    "DEVELOPMENT_CONFIG",
    "get_config",
]
