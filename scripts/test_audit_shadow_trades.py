"""
Test cases for audit_shadow_trades.py

Generates synthetic trade data with known violations to validate
the audit script catches all issues correctly.
"""
import json
import tempfile
import pytest
from pathlib import Path
from audit_shadow_trades import (
    load_trades,
    audit_friction_model,
    audit_candle_bounds,
    audit_pnl_math,
    audit_risk_limits,
    calculate_friction_stats,
    run_audit,
    TradeRecord,
    DEFAULT_FRICTION,
    DEFAULT_MAX_POSITION_PCT,
    DEFAULT_INITIAL_EQUITY,
    DEFAULT_MAX_EXPOSURE,
)


def make_trade(
    timestamp: int = 1702300000000,
    strategy_id: str = "test_strat_1",
    coin: str = "BTCUSDT",
    signal: str = "ENTRY_LONG",
    price_at_signal: float = 42000.0,
    simulated_fill: float = None,  # Will compute if not provided
    position_size_usdt: float = 500.0,
    pnl: float = None,
    pnl_pct: float = None,
    candle_open: float = None,
    candle_high: float = None,
    candle_low: float = None,
    candle_close: float = None,
    friction: float = DEFAULT_FRICTION,
) -> dict:
    """Create a trade record dict, computing fill price if needed."""

    # Default candle data if not provided
    if candle_close is None:
        candle_close = price_at_signal
    if candle_high is None:
        candle_high = price_at_signal * 1.001
    if candle_low is None:
        candle_low = price_at_signal * 0.999
    if candle_open is None:
        candle_open = price_at_signal * 0.9995

    # Compute expected fill if not provided
    if simulated_fill is None:
        if "ENTRY" in signal and "LONG" in signal:
            simulated_fill = price_at_signal * (1 + friction)
        elif "EXIT" in signal and "LONG" in signal:
            simulated_fill = price_at_signal * (1 - friction)
        else:
            simulated_fill = price_at_signal * (1 + friction)

    return {
        "timestamp": timestamp,
        "strategy_id": strategy_id,
        "coin": coin,
        "signal": signal,
        "price_at_signal": price_at_signal,
        "simulated_fill": simulated_fill,
        "position_size_usdt": position_size_usdt,
        "pnl": pnl,
        "pnl_pct": pnl_pct,
        "candle_open": candle_open,
        "candle_high": candle_high,
        "candle_low": candle_low,
        "candle_close": candle_close,
        "gene_expression": "test_gene",
        "btc_trend": 1.0,
        "atr_regime": 0.0,
        "market_regime": "bull_calm",
    }


def write_trades_to_file(trades: list[dict], filepath: Path) -> None:
    """Write trades to JSONL file."""
    with open(filepath, 'w') as f:
        for t in trades:
            f.write(json.dumps(t) + "\n")


class TestFrictionModel:
    """Tests for friction model verification."""

    def test_valid_entry_long_friction(self, tmp_path):
        """Valid ENTRY_LONG should have fill = signal * (1 + friction)."""
        trades_file = tmp_path / "trades.jsonl"
        trades = [
            make_trade(
                signal="ENTRY_LONG",
                price_at_signal=42000.0,
                # simulated_fill computed automatically
            )
        ]
        write_trades_to_file(trades, trades_file)

        loaded = load_trades(trades_file)
        violations = audit_friction_model(loaded)

        assert len(violations) == 0, f"Expected no violations, got: {violations}"

    def test_valid_exit_long_friction(self, tmp_path):
        """Valid EXIT_LONG should have fill = signal * (1 - friction)."""
        trades_file = tmp_path / "trades.jsonl"
        trades = [
            make_trade(
                signal="EXIT_LONG",
                price_at_signal=42500.0,
                pnl=25.0,
                pnl_pct=5.0,
            )
        ]
        write_trades_to_file(trades, trades_file)

        loaded = load_trades(trades_file)
        violations = audit_friction_model(loaded)

        assert len(violations) == 0, f"Expected no violations, got: {violations}"

    def test_wrong_entry_friction_detected(self, tmp_path):
        """Entry with wrong friction should be flagged."""
        trades_file = tmp_path / "trades.jsonl"
        trades = [
            make_trade(
                signal="ENTRY_LONG",
                price_at_signal=42000.0,
                simulated_fill=42000.0,  # Wrong! Should be 42000 * 1.0025
            )
        ]
        write_trades_to_file(trades, trades_file)

        loaded = load_trades(trades_file)
        violations = audit_friction_model(loaded)

        assert len(violations) == 1, f"Expected 1 violation, got: {violations}"
        assert "ENTRY_LONG" in violations[0]

    def test_wrong_exit_friction_detected(self, tmp_path):
        """Exit with wrong friction should be flagged."""
        trades_file = tmp_path / "trades.jsonl"

        # EXIT_LONG should have fill = signal * (1 - friction)
        # = 42500 * 0.9975 = 42393.75
        # But we're providing 42500 (no friction applied)
        trades = [
            make_trade(
                signal="EXIT_LONG",
                price_at_signal=42500.0,
                simulated_fill=42500.0,  # Wrong! Should be 42393.75
                pnl=25.0,
                pnl_pct=5.0,
            )
        ]
        write_trades_to_file(trades, trades_file)

        loaded = load_trades(trades_file)
        violations = audit_friction_model(loaded)

        assert len(violations) == 1, f"Expected 1 violation, got: {violations}"
        assert "EXIT_LONG" in violations[0]


class TestCandleBounds:
    """Tests for candle bounds verification."""

    def test_valid_signal_within_candle(self, tmp_path):
        """Signal price within candle range should pass."""
        trades_file = tmp_path / "trades.jsonl"
        trades = [
            make_trade(
                price_at_signal=42000.0,
                candle_open=41990.0,
                candle_high=42050.0,
                candle_low=41980.0,
                candle_close=42000.0,
            )
        ]
        write_trades_to_file(trades, trades_file)

        loaded = load_trades(trades_file)
        violations = audit_candle_bounds(loaded)

        assert len(violations) == 0, f"Expected no violations, got: {violations}"

    def test_signal_outside_candle_detected(self, tmp_path):
        """Signal price outside candle range should be flagged."""
        trades_file = tmp_path / "trades.jsonl"
        trades = [
            make_trade(
                price_at_signal=43000.0,  # Way outside!
                candle_open=41990.0,
                candle_high=42050.0,
                candle_low=41980.0,
                candle_close=42000.0,
            )
        ]
        write_trades_to_file(trades, trades_file)

        loaded = load_trades(trades_file)
        violations = audit_candle_bounds(loaded)

        assert len(violations) >= 1, f"Expected violations, got: {violations}"
        assert "outside" in violations[0].lower() or "!=" in violations[0]

    def test_signal_not_equal_close_detected(self, tmp_path):
        """Signal price different from candle close should be flagged."""
        trades_file = tmp_path / "trades.jsonl"
        trades = [
            make_trade(
                price_at_signal=42020.0,  # Within range but != close
                candle_open=41990.0,
                candle_high=42050.0,
                candle_low=41980.0,
                candle_close=42000.0,  # Different from signal
            )
        ]
        write_trades_to_file(trades, trades_file)

        loaded = load_trades(trades_file)
        violations = audit_candle_bounds(loaded)

        # Should flag that signal != close
        assert len(violations) >= 1, f"Expected violations for signal != close"


class TestPnLMath:
    """Tests for PnL math verification."""

    def test_valid_pnl_calculation(self, tmp_path):
        """Correct PnL calculation should pass."""
        trades_file = tmp_path / "trades.jsonl"

        # PnL should equal size * (pnl_pct / 100)
        # 500 * (5.0 / 100) = 25.0
        trades = [
            make_trade(
                signal="EXIT_LONG",
                position_size_usdt=500.0,
                pnl=25.0,
                pnl_pct=5.0,
            )
        ]
        write_trades_to_file(trades, trades_file)

        loaded = load_trades(trades_file)
        violations = audit_pnl_math(loaded)

        assert len(violations) == 0, f"Expected no violations, got: {violations}"

    def test_pnl_mismatch_detected(self, tmp_path):
        """Incorrect PnL calculation should be flagged."""
        trades_file = tmp_path / "trades.jsonl"

        # PnL should be 500 * (5.0 / 100) = 25.0
        # But we're providing 50.0 (wrong!)
        trades = [
            make_trade(
                signal="EXIT_LONG",
                position_size_usdt=500.0,
                pnl=50.0,  # Wrong! Should be 25.0
                pnl_pct=5.0,
            )
        ]
        write_trades_to_file(trades, trades_file)

        loaded = load_trades(trades_file)
        violations = audit_pnl_math(loaded)

        assert len(violations) == 1, f"Expected 1 violation, got: {violations}"
        assert "mismatch" in violations[0].lower()


class TestRiskLimits:
    """Tests for risk limit verification."""

    def test_valid_position_size(self, tmp_path):
        """Position within limits should pass."""
        trades_file = tmp_path / "trades.jsonl"

        # Max position = 10000 * 0.10 = 1000
        # 500 is within limit
        trades = [
            make_trade(
                signal="ENTRY_LONG",
                position_size_usdt=500.0,
            )
        ]
        write_trades_to_file(trades, trades_file)

        loaded = load_trades(trades_file)
        violations = audit_risk_limits(loaded)

        assert len(violations) == 0, f"Expected no violations, got: {violations}"

    def test_position_exceeds_limit_detected(self, tmp_path):
        """Position exceeding limit should be flagged."""
        trades_file = tmp_path / "trades.jsonl"

        # Max position = 10000 * 0.10 = 1000
        # 1500 exceeds limit
        trades = [
            make_trade(
                signal="ENTRY_LONG",
                position_size_usdt=1500.0,  # Exceeds 1000 limit
            )
        ]
        write_trades_to_file(trades, trades_file)

        loaded = load_trades(trades_file)
        violations = audit_risk_limits(loaded)

        assert len(violations) >= 1, f"Expected violations, got: {violations}"
        assert "exceeds" in violations[0].lower()

    def test_exposure_exceeds_limit_detected(self, tmp_path):
        """Total exposure exceeding limit should be flagged."""
        trades_file = tmp_path / "trades.jsonl"

        # Max exposure = 10000 * 0.50 = 5000
        # 6 positions of 900 each = 5400, exceeds limit
        trades = [
            make_trade(
                timestamp=1702300000000 + i * 60000,
                strategy_id=f"strat_{i}",
                signal="ENTRY_LONG",
                position_size_usdt=900.0,
            )
            for i in range(6)
        ]
        write_trades_to_file(trades, trades_file)

        loaded = load_trades(trades_file)
        violations = audit_risk_limits(loaded)

        # Should flag the 6th trade (total 5400 > 5000)
        assert len(violations) >= 1, f"Expected exposure violations"
        assert "exposure" in violations[0].lower()


class TestFrictionStats:
    """Tests for friction statistics calculation."""

    def test_friction_stats_calculated(self, tmp_path):
        """Stats should reflect actual friction values."""
        trades_file = tmp_path / "trades.jsonl"
        trades = [
            make_trade(signal="ENTRY_LONG", price_at_signal=42000.0),
            make_trade(signal="EXIT_LONG", price_at_signal=42500.0, pnl=25.0, pnl_pct=5.0),
        ]
        write_trades_to_file(trades, trades_file)

        loaded = load_trades(trades_file)
        stats = calculate_friction_stats(loaded)

        assert stats["count"] == 2
        assert abs(stats["mean_bp"] - 25.0) < 0.5  # Should be ~25 bps (0.25%)
        assert stats["expected_bp"] == 25.0


class TestFullAudit:
    """Integration tests for full audit run."""

    def test_clean_audit_passes(self, tmp_path):
        """Audit with valid trades should pass."""
        trades_file = tmp_path / "trades.jsonl"
        report_file = tmp_path / "report.md"

        trades = [
            make_trade(
                timestamp=1702300000000,
                signal="ENTRY_LONG",
                price_at_signal=42000.0,
                position_size_usdt=500.0,
            ),
            make_trade(
                timestamp=1702300060000,
                signal="EXIT_LONG",
                price_at_signal=42500.0,
                position_size_usdt=500.0,
                pnl=25.0,  # 500 * 5% = 25
                pnl_pct=5.0,
            ),
        ]
        write_trades_to_file(trades, trades_file)

        result = run_audit(trades_file, report_file)

        assert result.is_passing, f"Expected passing audit: {result}"
        assert result.total_trades == 2
        assert result.entries == 1
        assert result.exits == 1

    def test_audit_catches_multiple_violations(self, tmp_path):
        """Audit should catch all types of violations."""
        trades_file = tmp_path / "trades.jsonl"
        report_file = tmp_path / "report.md"

        trades = [
            # Violation 1: Wrong friction
            make_trade(
                timestamp=1702300000000,
                signal="ENTRY_LONG",
                price_at_signal=42000.0,
                simulated_fill=42000.0,  # Wrong - no friction
                position_size_usdt=500.0,
            ),
            # Violation 2: Position too large
            make_trade(
                timestamp=1702300060000,
                signal="ENTRY_LONG",
                price_at_signal=42100.0,
                position_size_usdt=1500.0,  # Exceeds 1000 limit
            ),
            # Violation 3: PnL mismatch
            make_trade(
                timestamp=1702300120000,
                signal="EXIT_LONG",
                price_at_signal=42500.0,
                position_size_usdt=500.0,
                pnl=100.0,  # Wrong! Should be 500 * 5% = 25
                pnl_pct=5.0,
            ),
        ]
        write_trades_to_file(trades, trades_file)

        result = run_audit(trades_file, report_file)

        assert not result.is_passing
        assert len(result.friction_violations) >= 1
        assert len(result.risk_violations) >= 1
        assert len(result.pnl_mismatches) >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
