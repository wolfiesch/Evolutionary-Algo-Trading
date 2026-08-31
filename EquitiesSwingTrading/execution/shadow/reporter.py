"""
Daily summary report generator for equities shadow trading.

Generates markdown reports and logs for end-of-day analysis.
"""
import json
import logging
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from .models import DailySummary, PortfolioSnapshot, TradeLog


logger = logging.getLogger(__name__)


class ReportGenerator:
    """
    Generates daily reports for shadow trading analysis.

    Output formats:
    - Markdown summary for human review
    - JSON log for data analysis
    - Trade log aggregation
    """

    def __init__(
        self,
        output_dir: Path,
    ):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Subdirectories
        self.daily_dir = self.output_dir / "daily"
        self.weekly_dir = self.output_dir / "weekly"
        self.monthly_dir = self.output_dir / "monthly"

        for d in [self.daily_dir, self.weekly_dir, self.monthly_dir]:
            d.mkdir(exist_ok=True)

    def generate_daily_report(
        self,
        summary: DailySummary,
        snapshot: PortfolioSnapshot,
        trades: list[TradeLog],
    ) -> Path:
        """
        Generate daily summary report.

        Args:
            summary: Daily summary data
            snapshot: Portfolio snapshot at end of day
            trades: All trades executed today

        Returns:
            Path to generated report
        """
        report_date = summary.date
        report_path = self.daily_dir / f"{report_date}.md"

        lines = [
            f"# Daily Report: {report_date}",
            "",
            "## Summary",
            "",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Starting Equity | ${summary.starting_equity:,.2f} |",
            f"| Ending Equity | ${summary.ending_equity:,.2f} |",
            f"| Daily P&L | ${summary.daily_pnl:+,.2f} ({summary.daily_pnl_pct:+.2f}%) |",
            f"| Open Positions | {summary.open_positions} |",
            f"| Exposure | {summary.exposure_pct:.1f}% |",
            "",
            "## Market Context",
            "",
            f"- **Regime:** {summary.market_regime}",
            f"- **SPY Change:** {summary.spy_change_pct:+.2f}%",
            f"- **VIX Level:** {summary.vix_level:.1f}",
            "",
            "## Trading Activity",
            "",
            f"- **Entries:** {summary.entries}",
            f"- **Exits:** {summary.exits}",
            f"- **Stop Losses:** {summary.stop_losses}",
            "",
        ]

        # Add entries section if any
        if summary.new_entries:
            lines.extend([
                "### New Positions",
                "",
                "| Symbol | Entry Price | Size |",
                "|--------|-------------|------|",
            ])
            for entry in summary.new_entries:
                lines.append(
                    f"| {entry['symbol']} | ${entry['price']:.2f} | ${entry['size']:,.2f} |"
                )
            lines.append("")

        # Add exits section if any
        if summary.closed_positions:
            lines.extend([
                "### Closed Positions",
                "",
                "| Symbol | P&L | P&L % | Days Held |",
                "|--------|-----|-------|-----------|",
            ])
            for pos in summary.closed_positions:
                pnl = pos.get('pnl', 0) or 0
                pnl_pct = pos.get('pnl_pct', 0) or 0
                days = pos.get('days_held', 0) or 0
                lines.append(
                    f"| {pos['symbol']} | ${pnl:+,.2f} | {pnl_pct:+.1f}% | {days} |"
                )
            lines.append("")

        # Add best/worst if available
        if summary.best_trade or summary.worst_trade:
            lines.extend([
                "### Trade Highlights",
                "",
            ])
            if summary.best_trade:
                lines.append(
                    f"- **Best:** {summary.best_trade['symbol']} "
                    f"(${summary.best_trade['pnl']:+,.2f})"
                )
            if summary.worst_trade:
                lines.append(
                    f"- **Worst:** {summary.worst_trade['symbol']} "
                    f"(${summary.worst_trade['pnl']:+,.2f})"
                )
            lines.append("")

        # Portfolio snapshot
        lines.extend([
            "## Portfolio Snapshot",
            "",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Total P&L | ${snapshot.total_pnl:+,.2f} ({snapshot.total_pnl_pct:+.2f}%) |",
            f"| Max Drawdown | {snapshot.max_drawdown_pct:.2f}% |",
            f"| Total Trades | {snapshot.total_trades} |",
            f"| Win Rate | {snapshot.win_rate:.1%} |",
            "",
        ])

        # Write report
        report_path.write_text("\n".join(lines))
        logger.info(f"Generated daily report: {report_path}")

        # Also save JSON summary
        json_path = self.daily_dir / f"{report_date}.json"
        with open(json_path, "w") as f:
            json.dump({
                "summary": asdict(summary),
                "snapshot": asdict(snapshot),
                "trades_count": len(trades),
            }, f, indent=2)

        return report_path

    def generate_weekly_report(
        self,
        start_date: date,
        end_date: date,
        daily_summaries: list[DailySummary],
        ending_snapshot: PortfolioSnapshot,
    ) -> Path:
        """
        Generate weekly aggregated report.

        Args:
            start_date: Week start date
            end_date: Week end date
            daily_summaries: List of daily summaries for the week
            ending_snapshot: Portfolio snapshot at week end

        Returns:
            Path to generated report
        """
        week_str = start_date.strftime("%Y-W%W")
        report_path = self.weekly_dir / f"{week_str}.md"

        # Aggregate stats
        total_pnl = sum(s.daily_pnl for s in daily_summaries)
        total_entries = sum(s.entries for s in daily_summaries)
        total_exits = sum(s.exits for s in daily_summaries)
        total_stops = sum(s.stop_losses for s in daily_summaries)

        # Calculate win rate from daily P&L
        winning_days = sum(1 for s in daily_summaries if s.daily_pnl > 0)
        trading_days = len(daily_summaries)

        lines = [
            f"# Weekly Report: {week_str}",
            f"",
            f"**Period:** {start_date} to {end_date}",
            "",
            "## Summary",
            "",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Weekly P&L | ${total_pnl:+,.2f} |",
            f"| Trading Days | {trading_days} |",
            f"| Winning Days | {winning_days} ({winning_days/trading_days:.0%} if trading_days else 0) |",
            f"| Total Entries | {total_entries} |",
            f"| Total Exits | {total_exits} |",
            f"| Stop Losses | {total_stops} |",
            "",
            "## Daily Breakdown",
            "",
            "| Date | P&L | P&L % | Entries | Exits | Market |",
            "|------|-----|-------|---------|-------|--------|",
        ]

        for s in daily_summaries:
            lines.append(
                f"| {s.date} | ${s.daily_pnl:+,.2f} | {s.daily_pnl_pct:+.1f}% | "
                f"{s.entries} | {s.exits} | {s.market_regime} |"
            )

        lines.extend([
            "",
            "## Portfolio Status",
            "",
            f"- **Equity:** ${ending_snapshot.equity:,.2f}",
            f"- **Total P&L:** ${ending_snapshot.total_pnl:+,.2f} ({ending_snapshot.total_pnl_pct:+.2f}%)",
            f"- **Max Drawdown:** {ending_snapshot.max_drawdown_pct:.2f}%",
            f"- **Win Rate:** {ending_snapshot.win_rate:.1%}",
            "",
        ])

        report_path.write_text("\n".join(lines))
        logger.info(f"Generated weekly report: {report_path}")

        return report_path

    def load_daily_summaries(
        self,
        start_date: date,
        end_date: date,
    ) -> list[DailySummary]:
        """Load daily summaries for a date range."""
        summaries = []

        current = start_date
        while current <= end_date:
            json_path = self.daily_dir / f"{current.isoformat()}.json"
            if json_path.exists():
                try:
                    with open(json_path, "r") as f:
                        data = json.load(f)
                        summary_data = data.get("summary", {})
                        summary = DailySummary(**summary_data)
                        summaries.append(summary)
                except Exception as e:
                    logger.warning(f"Failed to load summary for {current}: {e}")

            current = date(current.year, current.month, current.day + 1)

        return summaries

    def get_trade_log_path(self, trade_date: date) -> Path:
        """Get path for trade log file."""
        return self.daily_dir / f"{trade_date.isoformat()}_trades.jsonl"

    def save_trade_logs(
        self,
        trade_date: date,
        trades: list[TradeLog],
    ) -> Path:
        """Save trade logs for a specific date."""
        log_path = self.get_trade_log_path(trade_date)

        with open(log_path, "w") as f:
            for trade in trades:
                f.write(trade.to_json() + "\n")

        logger.info(f"Saved {len(trades)} trades to {log_path}")
        return log_path

    def load_trade_logs(self, trade_date: date) -> list[TradeLog]:
        """Load trade logs for a specific date."""
        log_path = self.get_trade_log_path(trade_date)

        if not log_path.exists():
            return []

        trades = []
        with open(log_path, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        trades.append(TradeLog.from_json(line))
                    except Exception as e:
                        logger.warning(f"Failed to parse trade log: {e}")

        return trades
