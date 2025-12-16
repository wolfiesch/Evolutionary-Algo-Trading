"""
Strategy Templates - Fixed Logic, Evolvable Parameters.

The strategy logic is FIXED in these templates; only parameters evolve.
This dramatically reduces the search space compared to evolving logic strings.

Key features:
1. VECTORIZED: All signals return pd.Series for fast backtesting
2. REGIME-SWITCHED: Two weight sets selected by regime indicator
3. BIDIRECTIONAL: Native support for long AND short positions

Usage:
    from shared.evolution.templates import (
        StrategyTemplate,
        CryptoStrategyTemplate,
    )
    from shared.evolution.parameters import CryptoParameters

    # Create parameters (the DNA)
    params = CryptoParameters(
        weights_A=WeightVector(trend=0.2, mean_reversion=0.8),
        weights_B=WeightVector(trend=0.8, mean_reversion=0.2),
        entry_threshold_long=0.4,
    )

    # Create template with parameters
    template = CryptoStrategyTemplate(params)

    # Generate signals for entire candle history (vectorized)
    signals = template.generate_signals(candles)
"""

from shared.evolution.templates.base import StrategyTemplate
from shared.evolution.templates.crypto import CryptoStrategyTemplate

__all__ = [
    "StrategyTemplate",
    "CryptoStrategyTemplate",
]
