"""
Equities Swing Trading System - Main Orchestrator

Daily workflow orchestration for shadow trading:
1. Fetch market data (SPY, VIX, universe stocks)
2. Get fundamental context from EDGAR
3. Run shadow trader daily scan
4. Send Discord notifications
5. Generate reports

Usage:
    python main.py scan          # Run daily scan now
    python main.py schedule      # Run on scheduler (4:15 PM ET)
    python main.py status        # Show portfolio status
    python main.py evolve        # Run strategy evolution
"""

import argparse
import asyncio
import logging
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional
import json

import pandas as pd

# Configure logging before imports
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('logs/equities.log'),
    ]
)
logger = logging.getLogger(__name__)

# Import system components
from config import config, get_config, PROJECT_ROOT, STRATEGIES_DIR
from data.ingestion.market_data import MarketDataClient
from data.ingestion.universe import UniverseManager, SEED_UNIVERSE
from data.storage.repository import EquitiesRepository
from data.storage.models import DailyCandle
from execution.shadow.trader import EquitiesShadowTrader, ShadowTraderConfig
from execution.shadow.models import DailySummary
from execution.shadow.reporter import ReportGenerator
from evolution.backtester.evaluator import Strategy, FundamentalContext
from engine.gene_pool.fundamental import (
    insider_buy_intensity,
    revenue_cagr,
    earnings_quality,
    insider_cluster_buy,
)
from notifications.discord import DiscordNotifier


class EquitiesOrchestrator:
    """
    Main orchestrator for equities swing trading system.

    Coordinates daily workflow:
    - Market data fetching
    - Fundamental signal updates
    - Strategy evaluation
    - Shadow trading
    - Notifications
    """

    def __init__(
        self,
        environment: str = "development",
        strategies: Optional[list[Strategy]] = None,
    ):
        """
        Initialize orchestrator with all components.

        Args:
            environment: "development", "staging", or "production"
            strategies: List of strategies to trade (loads from disk if None)
        """
        self.environment = environment
        self.cfg = get_config(environment)

        # Initialize components
        self._init_infrastructure()

        # Load or use provided strategies
        if strategies:
            self.strategies = strategies
        else:
            self.strategies = self._load_strategies()

        # Initialize shadow trader
        self._init_shadow_trader()

        # Initialize notifier (if configured)
        self._init_notifier()

        logger.info(
            f"Orchestrator initialized: {environment} mode, "
            f"{len(self.strategies)} strategies"
        )

    def _init_infrastructure(self) -> None:
        """Initialize data infrastructure."""
        # Database
        self.repository = EquitiesRepository(self.cfg.database.db_path)

        # Market data
        self.market_client = MarketDataClient(
            provider=self.cfg.market_data.provider,
        )

        # Universe manager
        self.universe_manager = UniverseManager(
            market_client=self.market_client,
            repository=self.repository,
            config=self.cfg.universe,
        )

        # Reporter
        self.reporter = ReportGenerator(
            output_dir=PROJECT_ROOT / "logs" / "reports",
        )

    def _init_shadow_trader(self) -> None:
        """Initialize shadow trading engine."""
        trader_config = ShadowTraderConfig(
            initial_equity=self.cfg.backtest.initial_equity,
            risk_per_trade=self.cfg.backtest.risk_per_trade,
            max_position_pct=self.cfg.backtest.max_position_pct,
            max_open_positions=self.cfg.backtest.max_open_positions,
            max_exposure_pct=self.cfg.backtest.max_total_exposure,
            default_stop_loss_pct=self.cfg.backtest.stop_loss_pct,
            log_dir=PROJECT_ROOT / "logs",
            state_dir=PROJECT_ROOT / "state",
        )

        self.shadow_trader = EquitiesShadowTrader(
            strategies=self.strategies,
            config=trader_config,
        )

    def _init_notifier(self) -> None:
        """Initialize Discord notifier if configured."""
        webhook_url = self.cfg.notification.discord_webhook_url

        if webhook_url:
            self.notifier = DiscordNotifier(webhook_url=webhook_url)
            logger.info("Discord notifications enabled")
        else:
            self.notifier = None
            logger.warning("Discord webhook not configured - notifications disabled")

    def _load_strategies(self) -> list[Strategy]:
        """Load strategies from disk or return defaults."""
        strategies_file = STRATEGIES_DIR / "active_strategies.json"

        if strategies_file.exists():
            with open(strategies_file) as f:
                data = json.load(f)

            strategies = []
            for s in data.get("strategies", []):
                strategies.append(Strategy(
                    name=s["name"],
                    entry_long=s["entry_long"],
                    exit_long=s["exit_long"],
                    entry_short=s.get("entry_short"),
                    exit_short=s.get("exit_short"),
                ))

            if strategies:
                logger.info(f"Loaded {len(strategies)} strategies from {strategies_file}")
                return strategies

        # Return default strategies for development
        return self._get_default_strategies()

    def _get_default_strategies(self) -> list[Strategy]:
        """Get default development strategies."""
        return [
            Strategy(
                name="Insider_Momentum",
                entry_long="spy_trend(20) >= 0 AND insider_buy_intensity(90) > 0.3 AND ema_trend(9, 21) == 1.0",
                exit_long="norm_rsi(14) > 0.6 OR ema_trend(9, 21) == -1.0",
            ),
            Strategy(
                name="Quality_Pullback",
                entry_long="spy_trend(20) >= 0 AND earnings_quality() > 0.5 AND norm_rsi(14) < -0.4 AND ema_trend(20, 50) == 1.0",
                exit_long="norm_rsi(14) > 0.5",
            ),
            Strategy(
                name="Growth_Breakout",
                entry_long="spy_trend(20) >= 0 AND revenue_cagr(3) > 0.1 AND bb_position(20, 2.0) > 0.8",
                exit_long="bb_position(20, 2.0) < 0.2 OR norm_rsi(14) > 0.7",
            ),
        ]

    def save_strategies(self, strategies: list[Strategy]) -> None:
        """Save strategies to disk."""
        data = {
            "updated": datetime.utcnow().isoformat(),
            "strategies": [
                {
                    "name": s.name,
                    "entry_long": s.entry_long,
                    "exit_long": s.exit_long,
                    "entry_short": s.entry_short,
                    "exit_short": s.exit_short,
                }
                for s in strategies
            ],
        }

        strategies_file = STRATEGIES_DIR / "active_strategies.json"
        STRATEGIES_DIR.mkdir(exist_ok=True)

        with open(strategies_file, "w") as f:
            json.dump(data, f, indent=2)

        logger.info(f"Saved {len(strategies)} strategies to {strategies_file}")

    async def run_daily_scan(
        self,
        trade_date: Optional[date] = None,
        universe_override: Optional[list[str]] = None,
    ) -> DailySummary:
        """
        Run the daily scan workflow.

        Args:
            trade_date: Date to process (defaults to today)
            universe_override: Override universe (for testing)

        Returns:
            DailySummary with results
        """
        if trade_date is None:
            trade_date = date.today()

        logger.info(f"Starting daily scan for {trade_date}")
        start_time = datetime.now()

        try:
            # Step 1: Get universe
            if universe_override:
                universe = universe_override
            else:
                universe = self.universe_manager.get_universe()
                if not universe:
                    # Use seed universe if database is empty
                    universe = SEED_UNIVERSE[:self.cfg.universe.max_symbols]

            logger.info(f"Universe: {len(universe)} symbols")

            # Step 2: Fetch market data
            logger.info("Fetching market data...")
            spy_data = self.market_client.fetch_spy_bars(days=100)
            vix_data = self.market_client.fetch_vix_bars(days=100)

            # Calculate lookback needed for indicators
            lookback_days = 100  # 100 trading days for indicators
            start_date = trade_date - timedelta(days=int(lookback_days * 1.5))

            # Fetch price data for universe
            price_data = await self.market_client.bulk_fetch_async(
                symbols=universe,
                start_date=start_date,
                end_date=trade_date,
                progress_callback=lambda done, total: logger.debug(f"Fetched {done}/{total} symbols"),
            )

            logger.info(f"Fetched price data for {len(price_data)} symbols")

            # Step 3: Build fundamental context
            # [*TO-DO*] - Integrate with EDGAR agent when available
            fundamental_data = self._build_fundamental_context(
                symbols=list(price_data.keys()),
                as_of_date=trade_date,
            )

            # Step 4: Run shadow trader scan
            summary = self.shadow_trader.run_daily_scan(
                trade_date=trade_date,
                universe=list(price_data.keys()),
                price_data=price_data,
                spy_data=spy_data,
                vix_data=vix_data,
                fundamental_data=fundamental_data,
            )

            # Step 5: Send notifications
            await self._send_notifications(summary)

            # Step 6: Generate report
            all_trades = self.shadow_trader.daily_entries + self.shadow_trader.daily_exits
            self.reporter.generate_daily_report(
                summary=summary,
                snapshot=self.shadow_trader.get_portfolio_snapshot(
                    prices={s: price_data[s]["close"].iloc[-1] for s in price_data if len(price_data[s]) > 0},
                    trade_date=trade_date,
                    spy_data=spy_data,
                    vix_data=vix_data,
                ),
                trades=all_trades,
            )

            # Log completion
            elapsed = (datetime.now() - start_time).total_seconds()
            logger.info(
                f"Daily scan completed in {elapsed:.1f}s: "
                f"{summary.entries} entries, {summary.exits} exits, "
                f"equity ${summary.ending_equity:,.2f}"
            )

            return summary

        except Exception as e:
            logger.error(f"Daily scan failed: {e}", exc_info=True)
            if self.notifier:
                self.notifier.send_error(str(e), "Daily scan failed")
            raise

    def _build_fundamental_context(
        self,
        symbols: list[str],
        as_of_date: date,
    ) -> dict[str, FundamentalContext]:
        """
        Build fundamental context for symbols.

        [*INCOMPLETE*] - Currently returns cached data or defaults.
        Full implementation requires EDGAR agent integration.
        """
        # [*TO-DO*] - Replace with real EDGAR data
        contexts = {}

        for symbol in symbols:
            # Check if we have cached fundamental signals
            insider = self.repository.get_fundamental_signal(
                symbol=symbol,
                signal_type="insider_buy_intensity",
                as_of_date=as_of_date,
            )
            insider_cluster = self.repository.get_fundamental_signal(
                symbol=symbol,
                signal_type="insider_cluster",
                as_of_date=as_of_date,
            )
            revenue = self.repository.get_fundamental_signal(
                symbol=symbol,
                signal_type="revenue_cagr_3y",
                as_of_date=as_of_date,
            )
            quality = self.repository.get_fundamental_signal(
                symbol=symbol,
                signal_type="earnings_quality",
                as_of_date=as_of_date,
            )
            risk_change = self.repository.get_fundamental_signal(
                symbol=symbol,
                signal_type="risk_change",
                as_of_date=as_of_date,
            )

            contexts[symbol] = FundamentalContext(
                symbol=symbol,
                as_of_date=as_of_date,
                insider_intensity=insider or 0.0,
                insider_cluster=insider_cluster or 0.0,
                revenue_cagr=revenue or 0.0,
                earnings_quality=quality or 0.0,
                risk_change=risk_change or 0.0,
            )

        return contexts

    async def _send_notifications(self, summary: DailySummary) -> None:
        """Send Discord notifications for daily activity."""
        if not self.notifier:
            return

        # Send individual trade notifications
        for entry in self.shadow_trader.daily_entries:
            self.notifier.send_trade_entry(entry)

        for exit_trade in self.shadow_trader.daily_exits:
            self.notifier.send_trade_exit(exit_trade)

        # Send daily summary
        self.notifier.send_daily_summary(summary)

    def get_status(self) -> dict:
        """Get current portfolio status."""
        # Get latest prices for open positions
        positions = self.shadow_trader.position_tracker.get_all_positions()

        prices = {}
        for pos in positions:
            try:
                df = self.market_client.fetch_daily_bars(
                    pos.symbol,
                    date.today() - timedelta(days=5),
                )
                if not df.empty:
                    prices[pos.symbol] = df["close"].iloc[-1]
            except Exception:
                pass

        # Get market data
        spy_data = self.market_client.fetch_spy_bars(days=30)
        vix_data = self.market_client.fetch_vix_bars(days=30)

        snapshot = self.shadow_trader.get_portfolio_snapshot(
            prices=prices,
            trade_date=date.today(),
            spy_data=spy_data,
            vix_data=vix_data,
        )

        return {
            "equity": snapshot.equity,
            "cash": snapshot.cash,
            "positions_value": snapshot.positions_value,
            "total_pnl": snapshot.total_pnl,
            "total_pnl_pct": snapshot.total_pnl_pct,
            "daily_pnl": snapshot.daily_pnl,
            "daily_pnl_pct": snapshot.daily_pnl_pct,
            "open_positions": snapshot.open_positions,
            "exposure_pct": snapshot.exposure_pct,
            "max_drawdown_pct": snapshot.max_drawdown_pct,
            "total_trades": snapshot.total_trades,
            "win_rate": snapshot.win_rate,
            "market_regime": snapshot.market_regime,
            "spy_trend": snapshot.spy_trend,
            "vix_level": snapshot.vix_level,
            "positions": [
                {
                    "symbol": pos.symbol,
                    "strategy": pos.strategy_id,
                    "entry_date": pos.entry_date.isoformat(),
                    "entry_price": pos.entry_price,
                    "shares": pos.shares,
                    "current_price": prices.get(pos.symbol),
                    "unrealized_pnl": pos.unrealized_pnl(prices.get(pos.symbol, pos.entry_price)),
                    "days_held": pos.days_held(date.today()),
                }
                for pos in positions
            ],
        }

    def startup(self) -> None:
        """Send startup notification."""
        if self.notifier:
            self.notifier.send_startup(
                strategies=[s.name for s in self.strategies],
                equity=self.shadow_trader.equity,
                open_positions=len(self.shadow_trader.position_tracker.positions),
            )

    def shutdown(self, reason: str = "Manual shutdown") -> None:
        """Send shutdown notification."""
        if self.notifier:
            self.notifier.send_shutdown(
                reason=reason,
                equity=self.shadow_trader.equity,
                total_pnl=self.shadow_trader.total_pnl,
            )


def run_daily_scan_command(args: argparse.Namespace) -> None:
    """Run daily scan command."""
    orchestrator = EquitiesOrchestrator(environment=args.env)

    # Parse date if provided
    trade_date = None
    if args.date:
        trade_date = date.fromisoformat(args.date)

    # Run scan
    summary = asyncio.run(orchestrator.run_daily_scan(trade_date=trade_date))

    print("\n" + "=" * 60)
    print(f"Daily Scan Complete: {summary.date}")
    print("=" * 60)
    print(f"Starting Equity: ${summary.starting_equity:,.2f}")
    print(f"Ending Equity:   ${summary.ending_equity:,.2f}")
    print(f"Daily P&L:       ${summary.daily_pnl:+,.2f} ({summary.daily_pnl_pct:+.2f}%)")
    print(f"Entries:         {summary.entries}")
    print(f"Exits:           {summary.exits}")
    print(f"Stop Losses:     {summary.stop_losses}")
    print(f"Open Positions:  {summary.open_positions}")
    print(f"Exposure:        {summary.exposure_pct:.1f}%")
    print(f"Market Regime:   {summary.market_regime}")


def run_scheduled_command(args: argparse.Namespace) -> None:
    """Run on schedule (requires APScheduler)."""
    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        print("APScheduler not installed. Install with: pip install apscheduler")
        sys.exit(1)

    orchestrator = EquitiesOrchestrator(environment=args.env)
    orchestrator.startup()

    scheduler = BlockingScheduler()

    # Schedule daily scan at 4:15 PM ET (after market close)
    # Cron: minute=15, hour=16, day_of_week=0-4 (Mon-Fri)
    trigger = CronTrigger(
        hour=16,
        minute=15,
        day_of_week="mon-fri",
        timezone="America/New_York",
    )

    def scheduled_scan():
        asyncio.run(orchestrator.run_daily_scan())

    scheduler.add_job(scheduled_scan, trigger)

    print(f"Scheduler started. Daily scan at 4:15 PM ET (Mon-Fri)")
    print("Press Ctrl+C to stop.")

    try:
        scheduler.start()
    except KeyboardInterrupt:
        orchestrator.shutdown("Scheduler stopped")
        print("\nScheduler stopped.")


def run_status_command(args: argparse.Namespace) -> None:
    """Show portfolio status."""
    orchestrator = EquitiesOrchestrator(environment=args.env)
    status = orchestrator.get_status()

    print("\n" + "=" * 60)
    print("Portfolio Status")
    print("=" * 60)
    print(f"Equity:          ${status['equity']:,.2f}")
    print(f"Cash:            ${status['cash']:,.2f}")
    print(f"Positions Value: ${status['positions_value']:,.2f}")
    print(f"Total P&L:       ${status['total_pnl']:+,.2f} ({status['total_pnl_pct']:+.2f}%)")
    print(f"Daily P&L:       ${status['daily_pnl']:+,.2f} ({status['daily_pnl_pct']:+.2f}%)")
    print(f"Open Positions:  {status['open_positions']}")
    print(f"Exposure:        {status['exposure_pct']:.1f}%")
    print(f"Max Drawdown:    {status['max_drawdown_pct']:.1f}%")
    print(f"Total Trades:    {status['total_trades']}")
    print(f"Win Rate:        {status['win_rate']:.1%}")
    print(f"Market Regime:   {status['market_regime']}")
    print(f"SPY Trend:       {status['spy_trend']:+.1f}")
    print(f"VIX Level:       {status['vix_level']:.1f}")

    if status['positions']:
        print("\n" + "-" * 60)
        print("Open Positions:")
        print("-" * 60)
        for pos in status['positions']:
            pnl = pos['unrealized_pnl']
            print(
                f"  {pos['symbol']:6} | {pos['strategy']:20} | "
                f"${pos['entry_price']:>8.2f} | {pos['shares']:>6.1f} sh | "
                f"${pnl:>+8.2f} | {pos['days_held']:>2}d"
            )


def run_evolve_command(args: argparse.Namespace) -> None:
    """Run strategy evolution."""
    print("Evolution not yet implemented. See Phase 3 in implementation plan.")
    print("Coming soon: LLM-driven strategy generation and optimization.")


def run_download_command(args: argparse.Namespace) -> None:
    """Download historical market data."""
    from scripts.download_historical import HistoricalDataDownloader
    from data.ingestion.universe import SEED_UNIVERSE

    cfg = get_config(args.env)
    repository = EquitiesRepository(cfg.database.db_path)
    market_client = MarketDataClient(provider=cfg.market_data.provider)

    # Parse years
    years = args.years if hasattr(args, 'years') and args.years else 5
    if args.quick:
        years = 1

    downloader = HistoricalDataDownloader(
        repository=repository,
        market_client=market_client,
        years=years,
    )

    # Stats only
    if args.stats:
        stats = downloader.get_database_stats()
        print("\n" + "=" * 60)
        print("Database Statistics")
        print("=" * 60)
        print(f"Total symbols: {stats['total_symbols']}")
        print(f"Total candles: {stats['total_candles']:,}")
        print(f"SPY bars:      {stats['spy_bars']}")
        print(f"VIX bars:      {stats['vix_bars']}")
        return

    # Determine symbols
    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",")]
    else:
        symbols = SEED_UNIVERSE.copy()
        if args.quick:
            symbols = symbols[:50]
        elif args.max_symbols:
            symbols = symbols[:args.max_symbols]

    print(f"\nDownloading {years} years of data...")
    print(f"Database: {cfg.database.db_path}")

    # Download SPY/VIX
    if not args.universe_only:
        print("\n--- Market Indices ---")
        downloader.download_spy_vix()

    # Download universe
    if not args.spy_vix_only:
        print(f"\n--- Universe ({len(symbols)} symbols) ---")
        asyncio.run(downloader.download_universe(symbols=symbols))

    # Final stats
    stats = downloader.get_database_stats()
    print("\n" + "=" * 60)
    print("Download Complete")
    print("=" * 60)
    print(f"Total symbols: {stats['total_symbols']}")
    print(f"Total candles: {stats['total_candles']:,}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Equities Swing Trading System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  scan      Run daily scan immediately
  schedule  Run on daily schedule (4:15 PM ET)
  status    Show portfolio status
  download  Download historical market data
  evolve    Run strategy evolution (coming soon)

Examples:
  python main.py scan                  # Run today's scan
  python main.py scan --date 2024-01-15  # Run for specific date
  python main.py status                # Show portfolio
  python main.py schedule              # Start scheduler
  python main.py download --quick      # Quick download (1 year, 50 symbols)
  python main.py download --stats      # Show database stats
        """,
    )

    parser.add_argument(
        "command",
        choices=["scan", "schedule", "status", "download", "evolve"],
        help="Command to run",
    )
    parser.add_argument(
        "--env",
        choices=["development", "staging", "production"],
        default="development",
        help="Environment (default: development)",
    )
    parser.add_argument(
        "--date",
        help="Trade date (YYYY-MM-DD) for scan command",
    )

    # Download command options
    parser.add_argument(
        "--years",
        type=int,
        default=5,
        help="Years of historical data (download command)",
    )
    parser.add_argument(
        "--symbols",
        help="Comma-separated symbols (download command)",
    )
    parser.add_argument(
        "--max-symbols",
        type=int,
        help="Maximum symbols from universe (download command)",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Quick mode: 1 year, 50 symbols (download command)",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show database statistics only (download command)",
    )
    parser.add_argument(
        "--spy-vix-only",
        action="store_true",
        help="Only download SPY and VIX (download command)",
    )
    parser.add_argument(
        "--universe-only",
        action="store_true",
        help="Only download universe, skip SPY/VIX (download command)",
    )

    args = parser.parse_args()

    # Ensure log directory exists
    (PROJECT_ROOT / "logs").mkdir(exist_ok=True)
    (PROJECT_ROOT / "state").mkdir(exist_ok=True)

    # Route to command
    commands = {
        "scan": run_daily_scan_command,
        "schedule": run_scheduled_command,
        "status": run_status_command,
        "download": run_download_command,
        "evolve": run_evolve_command,
    }

    commands[args.command](args)


if __name__ == "__main__":
    main()
