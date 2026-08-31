"""Gene pool primitives - asset-agnostic building blocks for strategies."""
from shared.engine.gene_pool import trend, mean_reversion, volume, volatility, risk

# === VECTORIZED EXPORTS (for Strategy Templates) ===
# These return pd.Series for efficient backtesting

from shared.engine.gene_pool.trend import (
    ema_trend_series,
    price_position_series,
)

from shared.engine.gene_pool.mean_reversion import (
    norm_rsi_series,
    bb_position_series,
    bb_width_percentile_series,
)

from shared.engine.gene_pool.volatility import (
    atr_regime_series,
    atr_percentile_series,
)

from shared.engine.gene_pool.volume import (
    volume_intensity_series,
    vwap_distance_series,
)

# === SCALAR EXPORTS (for legacy string-based strategies) ===
# These return float for the last bar

from shared.engine.gene_pool.trend import (
    ema_trend,
    price_position,
)

from shared.engine.gene_pool.mean_reversion import (
    norm_rsi,
    bb_position,
    bb_width_percentile,
)

from shared.engine.gene_pool.volatility import (
    atr_regime,
    atr_percentile,
)

from shared.engine.gene_pool.volume import (
    volume_intensity,
    vwap_distance,
)

__all__ = [
    # Modules
    "trend", "mean_reversion", "volume", "volatility", "risk",
    # Vectorized
    "ema_trend_series", "price_position_series",
    "norm_rsi_series", "bb_position_series", "bb_width_percentile_series",
    "atr_regime_series", "atr_percentile_series",
    "volume_intensity_series", "vwap_distance_series",
    # Scalar
    "ema_trend", "price_position",
    "norm_rsi", "bb_position", "bb_width_percentile",
    "atr_regime", "atr_percentile",
    "volume_intensity", "vwap_distance",
]
