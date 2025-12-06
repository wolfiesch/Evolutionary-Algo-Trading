"""Gene expression parser - converts JSON strategies to executable code."""
import re
import operator
from typing import Callable, Optional
from dataclasses import dataclass
from enum import Enum
import pandas as pd

from engine.gene_pool import trend, mean_reversion, volume, volatility, market_filter


class Signal(Enum):
    """Trading signals."""
    HOLD = "HOLD"
    ENTRY_LONG = "ENTRY_LONG"
    EXIT_LONG = "EXIT_LONG"


@dataclass
class Strategy:
    """Parsed strategy with entry/exit conditions."""
    name: str
    entry_long: Optional[str]
    exit_long: Optional[str]
    entry_short: Optional[str] = None  # Disabled Phase 1
    exit_short: Optional[str] = None   # Disabled Phase 1


# Allowed primitives (whitelist for security)
PRIMITIVES = {
    "ema_trend": trend.ema_trend,
    "price_position": trend.price_position,
    "norm_rsi": mean_reversion.norm_rsi,
    "bb_position": mean_reversion.bb_position,
    "bb_width_percentile": mean_reversion.bb_width_percentile,
    "volume_intensity": volume.volume_intensity,
    "vwap_distance": volume.vwap_distance,
    "atr_regime": volatility.atr_regime,
    "atr_percentile": volatility.atr_percentile,
    "btc_trend": market_filter.btc_trend,
}

OPERATORS = {
    "==": operator.eq,
    "!=": operator.ne,
    ">": operator.gt,
    ">=": operator.ge,
    "<": operator.lt,
    "<=": operator.le,
}


class GeneExpressionParser:
    """
    Parses and evaluates gene expression strings.

    Example expression:
        "btc_trend(60) >= 0 AND ema_trend(9,21) == 1.0 AND norm_rsi(14) < -0.4"
    """

    FUNC_PATTERN = re.compile(r"(\w+)\(([^)]*)\)")
    COMPARISON_PATTERN = re.compile(r"(.+?)\s*(==|!=|>=|<=|>|<)\s*([\d\.\-]+)")

    def parse(self, strategy_json: dict) -> Strategy:
        """
        Parse a JSON strategy definition and validate allowed primitives.

        Args:
            strategy_json: Dictionary with keys:
                - strategy_name (str)
                - entry_long (str or None)
                - exit_long (str or None)
                - entry_short (str or None, optional)
                - exit_short (str or None, optional)

        Returns:
            Strategy dataclass

        Raises:
            ValueError: If unknown primitive found in expression
        """
        # Validate expressions contain only allowed primitives
        if strategy_json.get("entry_long"):
            self._validate_expression(strategy_json["entry_long"])
        if strategy_json.get("exit_long"):
            self._validate_expression(strategy_json["exit_long"])
        if strategy_json.get("entry_short"):
            self._validate_expression(strategy_json["entry_short"])
        if strategy_json.get("exit_short"):
            self._validate_expression(strategy_json["exit_short"])

        return Strategy(
            name=strategy_json["strategy_name"],
            entry_long=strategy_json.get("entry_long"),
            exit_long=strategy_json.get("exit_long"),
            entry_short=strategy_json.get("entry_short"),
            exit_short=strategy_json.get("exit_short"),
        )

    def _validate_expression(self, expression: str) -> None:
        """
        Validate that expression only uses allowed primitives.

        Args:
            expression: Gene expression string

        Raises:
            ValueError: If unknown primitive found
        """
        # Find all function calls in the expression
        for match in self.FUNC_PATTERN.finditer(expression):
            func_name = match.group(1)
            if func_name not in PRIMITIVES:
                raise ValueError(
                    f"Unknown primitive '{func_name}'. "
                    f"Allowed primitives: {', '.join(sorted(PRIMITIVES.keys()))}"
                )

    def evaluate(
        self,
        expression: str,
        candles: pd.DataFrame,
        btc_candles: Optional[pd.DataFrame] = None,
    ) -> bool:
        """
        Evaluate a gene expression against current data.

        Args:
            expression: Gene expression string (e.g., "norm_rsi(14) < -0.4 AND ema_trend(9,21) == 1.0")
            candles: OHLCV DataFrame for the asset
            btc_candles: OHLCV DataFrame for BTC (required if expression uses btc_trend)

        Returns:
            True if ALL conditions are met, False otherwise
        """
        if not expression:
            return False

        # Split by AND and evaluate each condition
        conditions = [c.strip() for c in expression.split(" AND ")]

        for condition in conditions:
            if not self._evaluate_condition(condition, candles, btc_candles):
                return False

        return True

    def _evaluate_condition(
        self,
        condition: str,
        candles: pd.DataFrame,
        btc_candles: Optional[pd.DataFrame]
    ) -> bool:
        """
        Evaluate a single condition like 'ema_trend(9,21) == 1.0'.

        Args:
            condition: Single comparison condition
            candles: OHLCV DataFrame for the asset
            btc_candles: OHLCV DataFrame for BTC

        Returns:
            True if condition is met, False otherwise
        """
        # Parse the condition using the comparison pattern
        match = self.COMPARISON_PATTERN.match(condition)
        if not match:
            raise ValueError(f"Invalid condition format: '{condition}'")

        left_expr = match.group(1).strip()
        operator_str = match.group(2)
        right_value = float(match.group(3))

        # Get the comparison operator
        op_func = OPERATORS.get(operator_str)
        if not op_func:
            raise ValueError(f"Invalid operator: '{operator_str}'")

        # Evaluate the left side (function call)
        left_value = self._evaluate_term(left_expr, candles, btc_candles)

        # Perform the comparison
        return op_func(left_value, right_value)

    def _evaluate_term(
        self,
        term: str,
        candles: pd.DataFrame,
        btc_candles: Optional[pd.DataFrame]
    ) -> float:
        """
        Evaluate a term (function call or constant).

        Args:
            term: Function call string (e.g., "ema_trend(9,21)") or numeric constant
            candles: OHLCV DataFrame for the asset
            btc_candles: OHLCV DataFrame for BTC

        Returns:
            Evaluated float value
        """
        # Check if it's a numeric constant
        try:
            return float(term)
        except ValueError:
            pass

        # Parse as function call
        match = self.FUNC_PATTERN.match(term)
        if not match:
            raise ValueError(f"Invalid term: '{term}'")

        func_name = match.group(1)
        args_str = match.group(2)

        # Get the primitive function
        func = PRIMITIVES.get(func_name)
        if not func:
            raise ValueError(f"Unknown primitive: '{func_name}'")

        # Parse arguments
        if args_str:
            args = [arg.strip() for arg in args_str.split(",")]
            # Convert to appropriate types (int or float)
            parsed_args = []
            for arg in args:
                try:
                    # Try integer first
                    if "." not in arg:
                        parsed_args.append(int(arg))
                    else:
                        parsed_args.append(float(arg))
                except ValueError:
                    raise ValueError(f"Invalid argument '{arg}' in {func_name}")
        else:
            parsed_args = []

        # Special handling for btc_trend - needs btc_candles
        if func_name == "btc_trend":
            if btc_candles is None:
                raise ValueError("btc_trend requires btc_candles parameter")
            return func(btc_candles, *parsed_args)
        else:
            return func(candles, *parsed_args)

    def get_signal(
        self,
        strategy: Strategy,
        candles: pd.DataFrame,
        btc_candles: pd.DataFrame,
        has_position: bool,
    ) -> Signal:
        """
        Determine trading signal for current state.

        Args:
            strategy: Parsed Strategy object
            candles: OHLCV DataFrame for the asset
            btc_candles: OHLCV DataFrame for BTC
            has_position: Whether currently holding a position

        Returns:
            Signal enum (ENTRY_LONG, EXIT_LONG, or HOLD)
        """
        if has_position:
            # Check exit condition
            if strategy.exit_long and self.evaluate(strategy.exit_long, candles, btc_candles):
                return Signal.EXIT_LONG
            return Signal.HOLD
        else:
            # Check entry condition
            if strategy.entry_long and self.evaluate(strategy.entry_long, candles, btc_candles):
                return Signal.ENTRY_LONG
            return Signal.HOLD
