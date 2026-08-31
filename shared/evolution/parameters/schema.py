"""
Parameter schema for Strategy Templates.

This module defines the DNA that gets evolved:
- WeightVector: Signal weights for a single regime
- UniversalParameters: Base parameters for all asset classes
- CryptoParameters: Crypto-specific extensions
- ForexParameters: Forex-specific extensions

The strategy LOGIC is fixed in the templates; only these parameters evolve.
"""
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Literal, Optional
import json


@dataclass
class WeightVector:
    """
    A set of signal weights used for regime-switched strategies.

    Each weight controls how much a signal contributes to the composite.
    - Positive weight: use signal normally
    - Negative weight: use signal in reverse (contrarian)
    - Zero weight: signal disabled

    All weights bounded to [-1.0, +1.0].
    """
    trend: float = 0.0           # EMA crossover signal
    momentum: float = 0.0        # RSI-based momentum
    mean_reversion: float = 0.0  # Bollinger Band position
    volatility: float = 0.0      # ATR regime signal
    volume: float = 0.0          # Volume intensity signal

    def to_dict(self) -> Dict[str, float]:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, float]) -> "WeightVector":
        """Create from dictionary."""
        return cls(
            trend=data.get("trend", 0.0),
            momentum=data.get("momentum", 0.0),
            mean_reversion=data.get("mean_reversion", 0.0),
            volatility=data.get("volatility", 0.0),
            volume=data.get("volume", 0.0),
        )

    def validate(self) -> List[str]:
        """
        Validate weight vector bounds.

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []
        for field_name in ["trend", "momentum", "mean_reversion", "volatility", "volume"]:
            val = getattr(self, field_name)
            if not isinstance(val, (int, float)):
                errors.append(f"weight_{field_name} must be numeric, got {type(val).__name__}")
            elif not -1.0 <= val <= 1.0:
                errors.append(f"weight_{field_name} must be in [-1.0, 1.0], got {val}")
        return errors

    def total_weight(self) -> float:
        """Sum of absolute weights (for normalization)."""
        return sum(abs(getattr(self, f)) for f in ["trend", "momentum", "mean_reversion", "volatility", "volume"])

    def is_empty(self) -> bool:
        """Check if all weights are effectively zero."""
        return self.total_weight() < 0.01


@dataclass
class UniversalParameters:
    """
    Parameters that apply to all asset classes.

    This is the DNA that gets evolved. The strategy template logic is FIXED;
    only these parameters change during evolution.

    Architecture features:
    1. VECTORIZED: Designed for pd.Series signal calculations
    2. REGIME-SWITCHED: Two weight sets selected by regime indicator
    3. BIDIRECTIONAL: Native support for long AND short positions
    """

    # === REGIME SELECTOR (for regime-switched weights) ===
    regime_indicator: Literal["adx", "atr_percentile", "bb_width"] = "adx"
    regime_period: int = 14             # Period for regime indicator (range: 5-50)
    regime_threshold: float = 25.0      # Above = Regime B (trending), Below = Regime A (ranging)

    # === SIGNAL WEIGHTS - REGIME A (Low Vol / Ranging Market) ===
    # Used when regime_indicator < regime_threshold
    weights_A: WeightVector = field(default_factory=lambda: WeightVector(
        trend=0.1,
        momentum=0.3,
        mean_reversion=0.8,  # Favor mean reversion in ranges
        volatility=0.2,
        volume=0.1,
    ))

    # === SIGNAL WEIGHTS - REGIME B (High Vol / Trending Market) ===
    # Used when regime_indicator >= regime_threshold
    weights_B: WeightVector = field(default_factory=lambda: WeightVector(
        trend=0.8,           # Favor trend following in trends
        momentum=0.5,
        mean_reversion=0.1,
        volatility=0.3,
        volume=0.2,
    ))

    # === SIGNAL PERIODS (Integers Only) ===
    # Trend
    trend_fast_period: int = 9          # Range: 3-50
    trend_slow_period: int = 21         # Range: 10-200

    # Momentum
    momentum_period: int = 14           # Range: 5-50

    # Mean Reversion
    reversion_period: int = 20          # Range: 10-100
    reversion_std_dev: int = 2          # Range: 1-3 (Bollinger std)

    # Volatility
    volatility_period: int = 14         # Range: 5-50

    # Volume
    volume_period: int = 20             # Range: 10-100

    # === DECISION THRESHOLDS (Bidirectional) ===
    # Long entries/exits
    entry_threshold_long: float = 0.3    # Range: 0.1-0.8 (composite > this -> LONG)
    exit_threshold_long: float = -0.1    # Range: -0.5 to 0.2 (composite < this -> EXIT LONG)

    # Short entries/exits (set entry_threshold_short > 0 to disable shorts)
    entry_threshold_short: float = -0.3  # Range: -0.8 to -0.1 (composite < this -> SHORT)
    exit_threshold_short: float = 0.1    # Range: -0.2 to 0.5 (composite > this -> EXIT SHORT)

    # === RISK PARAMETERS ===
    stop_loss_atr_mult: float = 2.0     # Range: 1.0-5.0
    take_profit_atr_mult: float = 3.0   # Range: 1.5-8.0

    # === TIMING PARAMETERS ===
    min_bars_between_trades: int = 5    # Range: 1-50
    max_position_bars: int = 100        # Range: 20-500 (0 = unlimited)

    # === MARKET FILTER (Required) ===
    market_filter_period: int = 60      # Range: 20-200
    market_filter_threshold: float = 0.0  # Range: -1.0 to 1.0

    # === DIRECTION CONTROL ===
    allow_long: bool = True             # Enable long positions
    allow_short: bool = False           # Enable short positions (default: long-only)

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        data = asdict(self)
        # WeightVector is nested, so asdict handles it
        return data

    @classmethod
    def from_dict(cls, data: Dict) -> "UniversalParameters":
        """Create from dictionary."""
        # Handle nested WeightVector objects
        weights_a_data = data.get("weights_A", {})
        weights_b_data = data.get("weights_B", {})

        if isinstance(weights_a_data, dict):
            weights_A = WeightVector.from_dict(weights_a_data)
        else:
            weights_A = weights_a_data

        if isinstance(weights_b_data, dict):
            weights_B = WeightVector.from_dict(weights_b_data)
        else:
            weights_B = weights_b_data

        return cls(
            regime_indicator=data.get("regime_indicator", "adx"),
            regime_period=data.get("regime_period", 14),
            regime_threshold=data.get("regime_threshold", 25.0),
            weights_A=weights_A,
            weights_B=weights_B,
            trend_fast_period=data.get("trend_fast_period", 9),
            trend_slow_period=data.get("trend_slow_period", 21),
            momentum_period=data.get("momentum_period", 14),
            reversion_period=data.get("reversion_period", 20),
            reversion_std_dev=data.get("reversion_std_dev", 2),
            volatility_period=data.get("volatility_period", 14),
            volume_period=data.get("volume_period", 20),
            entry_threshold_long=data.get("entry_threshold_long", 0.3),
            exit_threshold_long=data.get("exit_threshold_long", -0.1),
            entry_threshold_short=data.get("entry_threshold_short", -0.3),
            exit_threshold_short=data.get("exit_threshold_short", 0.1),
            stop_loss_atr_mult=data.get("stop_loss_atr_mult", 2.0),
            take_profit_atr_mult=data.get("take_profit_atr_mult", 3.0),
            min_bars_between_trades=data.get("min_bars_between_trades", 5),
            max_position_bars=data.get("max_position_bars", 100),
            market_filter_period=data.get("market_filter_period", 60),
            market_filter_threshold=data.get("market_filter_threshold", 0.0),
            allow_long=data.get("allow_long", True),
            allow_short=data.get("allow_short", False),
        )

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> "UniversalParameters":
        """Deserialize from JSON string."""
        return cls.from_dict(json.loads(json_str))


@dataclass
class CryptoParameters(UniversalParameters):
    """
    Crypto-specific parameter extensions.

    Extends UniversalParameters with signals specific to crypto markets:
    - BTC correlation (altcoins follow BTC)
    - Funding rate (perpetuals-specific)
    - BTC dominance (altcoin timing)
    """

    # BTC correlation (crypto trades with BTC)
    weight_btc_correlation: float = 0.0  # How much to weight BTC trend [-1.0, 1.0]
    btc_trend_period: int = 60           # Period for BTC trend calc (20-200)

    # Funding rate (perps-specific)
    weight_funding_rate: float = 0.0     # Contrarian funding signal [-1.0, 1.0]
    funding_rate_threshold: float = 0.01 # Extreme funding level (0.001-0.05)

    # Altcoin-specific
    weight_btc_dominance: float = 0.0    # BTC.D trend for alt timing [-1.0, 1.0]
    btc_dominance_period: int = 30       # Period for BTC.D calc (10-100)

    def to_dict(self) -> Dict:
        """Convert to dictionary including crypto-specific fields."""
        data = super().to_dict()
        data.update({
            "weight_btc_correlation": self.weight_btc_correlation,
            "btc_trend_period": self.btc_trend_period,
            "weight_funding_rate": self.weight_funding_rate,
            "funding_rate_threshold": self.funding_rate_threshold,
            "weight_btc_dominance": self.weight_btc_dominance,
            "btc_dominance_period": self.btc_dominance_period,
        })
        return data

    @classmethod
    def from_dict(cls, data: Dict) -> "CryptoParameters":
        """Create from dictionary."""
        # Get base parameters
        base = UniversalParameters.from_dict(data)

        return cls(
            # Base parameters
            regime_indicator=base.regime_indicator,
            regime_period=base.regime_period,
            regime_threshold=base.regime_threshold,
            weights_A=base.weights_A,
            weights_B=base.weights_B,
            trend_fast_period=base.trend_fast_period,
            trend_slow_period=base.trend_slow_period,
            momentum_period=base.momentum_period,
            reversion_period=base.reversion_period,
            reversion_std_dev=base.reversion_std_dev,
            volatility_period=base.volatility_period,
            volume_period=base.volume_period,
            entry_threshold_long=base.entry_threshold_long,
            exit_threshold_long=base.exit_threshold_long,
            entry_threshold_short=base.entry_threshold_short,
            exit_threshold_short=base.exit_threshold_short,
            stop_loss_atr_mult=base.stop_loss_atr_mult,
            take_profit_atr_mult=base.take_profit_atr_mult,
            min_bars_between_trades=base.min_bars_between_trades,
            max_position_bars=base.max_position_bars,
            market_filter_period=base.market_filter_period,
            market_filter_threshold=base.market_filter_threshold,
            allow_long=base.allow_long,
            allow_short=base.allow_short,
            # Crypto-specific
            weight_btc_correlation=data.get("weight_btc_correlation", 0.0),
            btc_trend_period=data.get("btc_trend_period", 60),
            weight_funding_rate=data.get("weight_funding_rate", 0.0),
            funding_rate_threshold=data.get("funding_rate_threshold", 0.01),
            weight_btc_dominance=data.get("weight_btc_dominance", 0.0),
            btc_dominance_period=data.get("btc_dominance_period", 30),
        )


@dataclass
class ForexParameters(UniversalParameters):
    """
    Forex-specific parameter extensions.

    Extends UniversalParameters with signals specific to forex markets:
    - Session timing (forex has distinct session behaviors)
    - Dollar index correlation
    - Interest rate differential (carry trade)
    - Risk sentiment (risk-on/risk-off)
    """

    # Session timing (forex has distinct session behaviors)
    weight_session: float = 0.0          # Session-aware trading [-1.0, 1.0]
    preferred_session: Literal["asian", "london", "newyork", "overlap"] = "london"

    # Dollar index correlation
    weight_dxy: float = 0.0              # DXY trend correlation [-1.0, 1.0]
    dxy_trend_period: int = 60           # Period for DXY trend (20-200)

    # Interest rate differential
    weight_rate_diff: float = 0.0        # Carry trade signal [-1.0, 1.0]

    # Risk sentiment
    weight_risk_sentiment: float = 0.0   # Risk-on/risk-off [-1.0, 1.0]

    def to_dict(self) -> Dict:
        """Convert to dictionary including forex-specific fields."""
        data = super().to_dict()
        data.update({
            "weight_session": self.weight_session,
            "preferred_session": self.preferred_session,
            "weight_dxy": self.weight_dxy,
            "dxy_trend_period": self.dxy_trend_period,
            "weight_rate_diff": self.weight_rate_diff,
            "weight_risk_sentiment": self.weight_risk_sentiment,
        })
        return data

    @classmethod
    def from_dict(cls, data: Dict) -> "ForexParameters":
        """Create from dictionary."""
        # Get base parameters
        base = UniversalParameters.from_dict(data)

        return cls(
            # Base parameters
            regime_indicator=base.regime_indicator,
            regime_period=base.regime_period,
            regime_threshold=base.regime_threshold,
            weights_A=base.weights_A,
            weights_B=base.weights_B,
            trend_fast_period=base.trend_fast_period,
            trend_slow_period=base.trend_slow_period,
            momentum_period=base.momentum_period,
            reversion_period=base.reversion_period,
            reversion_std_dev=base.reversion_std_dev,
            volatility_period=base.volatility_period,
            volume_period=base.volume_period,
            entry_threshold_long=base.entry_threshold_long,
            exit_threshold_long=base.exit_threshold_long,
            entry_threshold_short=base.entry_threshold_short,
            exit_threshold_short=base.exit_threshold_short,
            stop_loss_atr_mult=base.stop_loss_atr_mult,
            take_profit_atr_mult=base.take_profit_atr_mult,
            min_bars_between_trades=base.min_bars_between_trades,
            max_position_bars=base.max_position_bars,
            market_filter_period=base.market_filter_period,
            market_filter_threshold=base.market_filter_threshold,
            allow_long=base.allow_long,
            allow_short=base.allow_short,
            # Forex-specific
            weight_session=data.get("weight_session", 0.0),
            preferred_session=data.get("preferred_session", "london"),
            weight_dxy=data.get("weight_dxy", 0.0),
            dxy_trend_period=data.get("dxy_trend_period", 60),
            weight_rate_diff=data.get("weight_rate_diff", 0.0),
            weight_risk_sentiment=data.get("weight_risk_sentiment", 0.0),
        )
