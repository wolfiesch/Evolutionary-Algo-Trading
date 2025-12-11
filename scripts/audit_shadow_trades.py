"""
Audit script for Shadow Trading System (Phase 3).

Analyzes logs/shadow_trades.jsonl to verify:
1. Friction Model: Do fill prices match expected friction calculation?
2. Math Integrity: Does the logged PnL match the calculated PnL from prices?
3. Risk Limits: Did any trade exceed position size or exposure limits?
4. Execution Cost Stats: What is the materialized friction distribution?
"""
import json
import logging
import sys
import numpy as np
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Tuple
from datetime import datetime, timezone

# Setup simple logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger("audit")

# Default paths - can be overridden
LOG_FILE = Path("logs/shadow_trades.jsonl")
REPORT_FILE = Path("docs/audits/shadow_trades_audit.md")

# Risk limits from config (defaults)
DEFAULT_FRICTION = 0.0025  # 0.25% per side
DEFAULT_MAX_POSITION_PCT = 0.10  # 10% max position
DEFAULT_MAX_EXPOSURE = 0.50  # 50% max exposure
DEFAULT_INITIAL_EQUITY = 10000.0


@dataclass
class TradeRecord:
    """Parsed trade record from shadow_trades.jsonl."""
    timestamp: int
    strategy_id: str
    symbol: str
    signal: str
    price_signal: float
    fill_price: float
    size: float
    pnl: Optional[float]
    pnl_pct: Optional[float]  # In percentage (e.g. 5.0 for 5%)
    candle: Dict[str, Optional[float]]  # {open, high, low, close}
    raw_line: int

    @property
    def is_entry(self) -> bool:
        return "ENTRY" in self.signal

    @property
    def is_exit(self) -> bool:
        return "EXIT" in self.signal

    @property
    def is_long(self) -> bool:
        return "LONG" in self.signal


@dataclass
class AuditResult:
    """Aggregated audit results."""
    total_trades: int = 0
    entries: int = 0
    exits: int = 0
    friction_violations: List[str] = field(default_factory=list)
    pnl_mismatches: List[str] = field(default_factory=list)
    risk_violations: List[str] = field(default_factory=list)
    candle_violations: List[str] = field(default_factory=list)
    friction_stats: Dict[str, float] = field(default_factory=dict)

    @property
    def is_passing(self) -> bool:
        return (
            len(self.friction_violations) == 0 and
            len(self.pnl_mismatches) == 0 and
            len(self.risk_violations) == 0 and
            len(self.candle_violations) == 0
        )


def load_trades(filepath: Path) -> List[TradeRecord]:
    """Load trades from JSONL log file."""
    trades = []
    if not filepath.exists():
        logger.error(f"Log file not found: {filepath}")
        return []

    with open(filepath, 'r') as f:
        for i, line in enumerate(f):
            try:
                data = json.loads(line)

                # Extract candle data if available
                candle = {
                    'open': data.get('candle_open'),
                    'high': data.get('candle_high'),
                    'low': data.get('candle_low'),
                    'close': data.get('candle_close')
                }

                record = TradeRecord(
                    timestamp=data['timestamp'],
                    strategy_id=data['strategy_id'],
                    symbol=data['coin'],
                    signal=data['signal'],
                    price_signal=data['price_at_signal'],
                    fill_price=data['simulated_fill'],
                    size=data['position_size_usdt'],
                    pnl=data.get('pnl'),
                    pnl_pct=data.get('pnl_pct'),
                    candle=candle,
                    raw_line=i + 1
                )
                trades.append(record)
            except Exception as e:
                logger.warning(f"Skipping malformed line {i+1}: {e}")

    return trades


def audit_friction_model(
    trades: List[TradeRecord],
    friction: float = DEFAULT_FRICTION
) -> List[str]:
    """
    Verify fill prices match the friction model.

    For ENTRY_LONG: fill = signal * (1 + friction)  (buy at worse price)
    For EXIT_LONG: fill = signal * (1 - friction)   (sell at worse price)
    """
    violations = []

    for t in trades:
        # Determine expected friction direction
        if t.is_entry and t.is_long:
            # Buying: pay more
            expected_fill = t.price_signal * (1 + friction)
        elif t.is_exit and t.is_long:
            # Selling: receive less
            expected_fill = t.price_signal * (1 - friction)
        else:
            # SHORT trades (if implemented)
            if t.is_entry:
                expected_fill = t.price_signal * (1 - friction)
            else:
                expected_fill = t.price_signal * (1 + friction)

        # Allow small tolerance for floating point rounding
        tolerance = t.price_signal * 0.00001  # 0.001%

        if abs(t.fill_price - expected_fill) > tolerance:
            violations.append(
                f"Line {t.raw_line}: {t.signal} {t.symbol} - "
                f"Fill {t.fill_price:.6f} != expected {expected_fill:.6f} "
                f"(signal={t.price_signal:.6f}, friction={friction*100:.3f}%)"
            )

    return violations


def audit_candle_bounds(trades: List[TradeRecord]) -> List[str]:
    """
    Verify signal prices are within candle bounds.

    The signal price should equal candle close (or at least be within H/L).
    """
    violations = []

    for t in trades:
        # Skip if no candle data recorded
        if t.candle['high'] is None or t.candle['low'] is None:
            continue

        epsilon = t.price_signal * 0.0001  # 0.01% tolerance

        # Signal price should be within candle range
        if not (t.candle['low'] - epsilon <= t.price_signal <= t.candle['high'] + epsilon):
            violations.append(
                f"Line {t.raw_line}: Signal price {t.price_signal:.6f} outside "
                f"candle range [{t.candle['low']:.6f}, {t.candle['high']:.6f}]"
            )

        # Signal price should ideally equal candle close
        if t.candle['close'] is not None:
            if abs(t.price_signal - t.candle['close']) > epsilon:
                violations.append(
                    f"Line {t.raw_line}: Signal price {t.price_signal:.6f} != "
                    f"candle close {t.candle['close']:.6f}"
                )

    return violations


def audit_pnl_math(trades: List[TradeRecord]) -> List[str]:
    """
    Verify PnL calculations are consistent.

    Check: PnL == Size * (PnL_Pct / 100)
    """
    violations = []

    for t in trades:
        if not t.is_exit or t.pnl is None or t.pnl_pct is None:
            continue

        expected_pnl = t.size * (t.pnl_pct / 100.0)

        # Tolerance: 5 cents
        if abs(expected_pnl - t.pnl) > 0.05:
            violations.append(
                f"Line {t.raw_line}: PnL mismatch - "
                f"Logged: ${t.pnl:.2f}, Calculated: ${expected_pnl:.2f} "
                f"(size=${t.size:.2f}, pct={t.pnl_pct:.2f}%)"
            )

    return violations


def audit_risk_limits(
    trades: List[TradeRecord],
    max_position_pct: float = DEFAULT_MAX_POSITION_PCT,
    initial_equity: float = DEFAULT_INITIAL_EQUITY,
    max_exposure: float = DEFAULT_MAX_EXPOSURE
) -> List[str]:
    """
    Verify trades respected risk limits.

    Checks:
    - Position size <= max_position_pct * equity
    - Total exposure at any point <= max_exposure * equity
    """
    violations = []
    max_position_size = initial_equity * max_position_pct

    # Track open positions for exposure calculation
    open_positions: Dict[str, float] = {}  # symbol -> size_usdt

    for t in trades:
        # Check 1: Single position size limit
        if t.is_entry:
            if t.size > max_position_size * 1.01:  # 1% tolerance
                violations.append(
                    f"Line {t.raw_line}: Position size ${t.size:.2f} exceeds "
                    f"limit ${max_position_size:.2f} ({max_position_pct*100:.0f}% of equity)"
                )

            # Track for exposure calculation
            key = f"{t.strategy_id}:{t.symbol}"
            open_positions[key] = t.size

        elif t.is_exit:
            # Remove from tracking
            key = f"{t.strategy_id}:{t.symbol}"
            open_positions.pop(key, None)

        # Check 2: Total exposure limit (after this trade)
        if t.is_entry:
            total_exposure = sum(open_positions.values())
            max_allowed = initial_equity * max_exposure
            if total_exposure > max_allowed * 1.01:  # 1% tolerance
                violations.append(
                    f"Line {t.raw_line}: Total exposure ${total_exposure:.2f} exceeds "
                    f"limit ${max_allowed:.2f} ({max_exposure*100:.0f}% of equity)"
                )

    return violations


def calculate_friction_stats(
    trades: List[TradeRecord],
    expected_friction: float = DEFAULT_FRICTION
) -> Dict[str, float]:
    """
    Calculate realized friction statistics.

    Compares actual fill price difference vs signal price.
    """
    realized_frictions = []

    for t in trades:
        # Realized friction = |fill - signal| / signal
        realized = abs(t.fill_price - t.price_signal) / t.price_signal
        realized_frictions.append(realized)

    if not realized_frictions:
        return {}

    f = np.array(realized_frictions)
    return {
        "count": len(f),
        "expected_bp": expected_friction * 10000,  # basis points
        "mean_bp": float(np.mean(f) * 10000),
        "max_bp": float(np.max(f) * 10000),
        "min_bp": float(np.min(f) * 10000),
        "std_bp": float(np.std(f) * 10000)
    }


def format_report(result: AuditResult, report_time: str) -> str:
    """Generate markdown report content."""
    lines = [
        "# Shadow Trading Audit Report\n",
        f"**Date:** {report_time}",
        f"**Trades Analyzed:** {result.total_trades} ({result.entries} entries, {result.exits} exits)\n",
        f"**Overall Status:** {'✅ PASSED' if result.is_passing else '❌ FAILED'}\n",
        "---\n",
    ]

    # Section 1: Friction Model
    lines.append("## 1. Friction Model Verification\n")
    if not result.friction_violations:
        lines.append("✅ **PASSED** - All fill prices match the friction model.\n")
    else:
        lines.append(f"❌ **FAILED** - {len(result.friction_violations)} violations detected.\n")
        lines.append("| Line | Details |")
        lines.append("|------|---------|")
        for v in result.friction_violations[:10]:
            lines.append(f"| {v} |")
        if len(result.friction_violations) > 10:
            lines.append(f"\n*...and {len(result.friction_violations) - 10} more*\n")

    # Section 2: Candle Bounds
    lines.append("\n## 2. Candle Bounds Verification\n")
    if not result.candle_violations:
        lines.append("✅ **PASSED** - All signal prices within candle bounds.\n")
    else:
        lines.append(f"❌ **FAILED** - {len(result.candle_violations)} violations detected.\n")
        for v in result.candle_violations[:5]:
            lines.append(f"- {v}")
        if len(result.candle_violations) > 5:
            lines.append(f"\n*...and {len(result.candle_violations) - 5} more*\n")

    # Section 3: PnL Integrity
    lines.append("\n## 3. PnL Math Integrity\n")
    if not result.pnl_mismatches:
        lines.append("✅ **PASSED** - All PnL calculations are consistent.\n")
    else:
        lines.append(f"❌ **FAILED** - {len(result.pnl_mismatches)} mismatches detected.\n")
        for v in result.pnl_mismatches[:5]:
            lines.append(f"- {v}")
        if len(result.pnl_mismatches) > 5:
            lines.append(f"\n*...and {len(result.pnl_mismatches) - 5} more*\n")

    # Section 4: Risk Limits
    lines.append("\n## 4. Risk Limit Compliance\n")
    if not result.risk_violations:
        lines.append("✅ **PASSED** - All trades within risk limits.\n")
    else:
        lines.append(f"❌ **FAILED** - {len(result.risk_violations)} violations detected.\n")
        for v in result.risk_violations[:5]:
            lines.append(f"- {v}")
        if len(result.risk_violations) > 5:
            lines.append(f"\n*...and {len(result.risk_violations) - 5} more*\n")

    # Section 5: Friction Stats
    lines.append("\n## 5. Execution Cost Statistics\n")
    stats = result.friction_stats
    if stats:
        lines.append(f"- **Expected Friction:** {stats['expected_bp']:.2f} bps")
        lines.append(f"- **Mean Realized:** {stats['mean_bp']:.2f} bps")
        lines.append(f"- **Min Realized:** {stats['min_bp']:.2f} bps")
        lines.append(f"- **Max Realized:** {stats['max_bp']:.2f} bps")
        lines.append(f"- **Std Dev:** {stats['std_bp']:.2f} bps")

        # Check if realized matches expected
        if abs(stats['mean_bp'] - stats['expected_bp']) < 0.5:
            lines.append("\n✅ Realized friction matches expected friction model.")
        else:
            lines.append(f"\n⚠️ Realized friction ({stats['mean_bp']:.2f} bps) differs from expected ({stats['expected_bp']:.2f} bps).")
    else:
        lines.append("No data available.\n")

    return "\n".join(lines)


def print_console_report(result: AuditResult) -> None:
    """Print summary to console."""
    print("\n" + "=" * 50)
    print("SHADOW TRADING AUDIT REPORT")
    print("=" * 50)
    print(f"\nTotal Trades: {result.total_trades} ({result.entries} entries, {result.exits} exits)")
    print(f"Overall Status: {'PASSED' if result.is_passing else 'FAILED'}")

    print(f"\n[1] FRICTION MODEL")
    if result.friction_violations:
        print(f"    ❌ FAILED - {len(result.friction_violations)} violations")
        for v in result.friction_violations[:3]:
            print(f"       {v}")
        if len(result.friction_violations) > 3:
            print(f"       ... and {len(result.friction_violations) - 3} more")
    else:
        print("    ✅ PASSED")

    print(f"\n[2] CANDLE BOUNDS")
    if result.candle_violations:
        print(f"    ❌ FAILED - {len(result.candle_violations)} violations")
    else:
        print("    ✅ PASSED")

    print(f"\n[3] PnL INTEGRITY")
    if result.pnl_mismatches:
        print(f"    ❌ FAILED - {len(result.pnl_mismatches)} mismatches")
    else:
        print("    ✅ PASSED")

    print(f"\n[4] RISK LIMITS")
    if result.risk_violations:
        print(f"    ❌ FAILED - {len(result.risk_violations)} violations")
    else:
        print("    ✅ PASSED")

    print(f"\n[5] EXECUTION COST STATS")
    stats = result.friction_stats
    if stats:
        print(f"    Expected: {stats['expected_bp']:.2f} bps")
        print(f"    Mean:     {stats['mean_bp']:.2f} bps")
        print(f"    Max:      {stats['max_bp']:.2f} bps")
    else:
        print("    No data")

    print("\n" + "=" * 50)


def run_audit(
    log_file: Path = LOG_FILE,
    report_file: Path = REPORT_FILE,
    friction: float = DEFAULT_FRICTION,
    max_position_pct: float = DEFAULT_MAX_POSITION_PCT,
    initial_equity: float = DEFAULT_INITIAL_EQUITY,
    max_exposure: float = DEFAULT_MAX_EXPOSURE
) -> AuditResult:
    """Run full audit and generate report."""
    print(f"Loading logs from {log_file}...")
    trades = load_trades(log_file)
    print(f"Loaded {len(trades)} records.")

    if not trades:
        print("No trades found to audit.")
        return AuditResult()

    # Count entries/exits
    entries = sum(1 for t in trades if t.is_entry)
    exits = sum(1 for t in trades if t.is_exit)

    # Run all checks
    friction_violations = audit_friction_model(trades, friction)
    candle_violations = audit_candle_bounds(trades)
    pnl_errors = audit_pnl_math(trades)
    risk_violations = audit_risk_limits(
        trades, max_position_pct, initial_equity, max_exposure
    )
    friction_stats = calculate_friction_stats(trades, friction)

    result = AuditResult(
        total_trades=len(trades),
        entries=entries,
        exits=exits,
        friction_violations=friction_violations,
        candle_violations=candle_violations,
        pnl_mismatches=pnl_errors,
        risk_violations=risk_violations,
        friction_stats=friction_stats
    )

    # Print to console
    print_console_report(result)

    # Save to file
    report_file.parent.mkdir(parents=True, exist_ok=True)
    report_time = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
    report_content = format_report(result, report_time)
    with open(report_file, "w") as f:
        f.write(report_content)
    print(f"\nReport saved to: {report_file}")

    return result


def main():
    """CLI entry point."""
    # Allow override via command line args
    log_file = Path(sys.argv[1]) if len(sys.argv) > 1 else LOG_FILE
    report_file = Path(sys.argv[2]) if len(sys.argv) > 2 else REPORT_FILE

    result = run_audit(log_file, report_file)

    # Exit with error code if audit failed
    sys.exit(0 if result.is_passing else 1)


if __name__ == "__main__":
    main()
