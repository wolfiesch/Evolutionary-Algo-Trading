"""
Strategy Lifecycle Management.

Handles the automated "hiring and firing" of strategies in the shadow pool:
1. Retires underperforming strategies (archived to logs/shadow_pool/retired/).
2. Identifies promotion candidates for live trading.
3. Generates daily health reports.
"""
import json
import logging
import shutil
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any

from config import settings
from .pool_manager import ShadowPoolManager, StrategyPerformance

logger = logging.getLogger("trades")

@dataclass
class LifecycleReport:
    """Daily report on strategy lifecycle events."""
    date: str
    pool_size_start: int
    pool_size_end: int
    retired: List[Dict[str, Any]]  # List of {"id": str, "reason": str, "stats": dict}
    promoted_candidates: List[Dict[str, Any]]  # List of {"id": str, "stats": dict}


class StrategyLifecycleManager:
    """
    Manages the lifecycle of strategies in the shadow pool.
    """

    def __init__(self, pool_manager: ShadowPoolManager):
        self.pool = pool_manager
        self.shadow_pool_dir = self.pool.shadow_pool_dir
        self.retired_dir = self.shadow_pool_dir / "retired"
        self.reports_dir = settings.logs_dir / "daily_reports"
        
        # Ensure directories exist
        self.retired_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    def run_review_cycle(self) -> LifecycleReport:
        """
        Run a full review cycle of the shadow pool.
        
        Returns:
            LifecycleReport containing actions taken.
        """
        logger.info("Starting strategy lifecycle review cycle...")
        
        start_count = len(self.pool.strategies)
        retired_list = []
        promoted_list = []
        
        # Snapshot of strategies to iterate over safely
        strategy_ids = list(self.pool.strategies.keys())
        
        for strategy_id in strategy_ids:
            perf = self.pool.state.strategy_performance.get(strategy_id)
            if not perf:
                continue
                
            # 1. Check for Retirement
            retirement_reason = self._check_retirement(perf)
            if retirement_reason:
                self._retire_strategy(strategy_id, retirement_reason, perf)
                retired_list.append({
                    "id": strategy_id,
                    "reason": retirement_reason,
                    "stats": {
                        "sharpe": 0.0, # TODO: Add sharpe calculation to StrategyPerformance if needed, or pass from outside
                        "drawdown": perf.max_drawdown,
                        "trades": perf.trade_count,
                        "pnl": perf.total_pnl
                    }
                })
                continue # Don't check for promotion if retiring
                
            # 2. Check for Promotion
            if self._is_promotion_candidate(perf):
                promoted_list.append({
                    "id": strategy_id,
                    "stats": {
                        "trades": perf.trade_count,
                        "win_rate": perf.win_rate,
                        "pnl": perf.total_pnl
                    }
                })

        # Generate Report
        report = LifecycleReport(
            date=datetime.utcnow().strftime("%Y-%m-%d"),
            pool_size_start=start_count,
            pool_size_end=len(self.pool.strategies),
            retired=retired_list,
            promoted_candidates=promoted_list
        )
        
        self._save_report(report)
        logger.info(f"Lifecycle review complete. Retired: {len(retired_list)}, Promoted Candidates: {len(promoted_list)}")
        return report

    def _check_retirement(self, perf: StrategyPerformance) -> Optional[str]:
        """
        Check if a strategy should be retired.
        
        Criteria:
        1. Max Drawdown > 15% (Hard Stop) - Min 1 trade
        2. Inactivity > 14 days
        3. Win Rate < 30% (Min 50 trades)
        4. Net Loss (PnL < 0) after 50 trades (Proxy for negative Sharpe for now)
        """
        # 1. Max Drawdown (Hard Stop)
        if perf.max_drawdown > 0.15:
            return f"Max Drawdown Violation ({perf.max_drawdown:.1%})"
            
        # 2. Inactivity
        if perf.last_trade_time:
            last_trade = datetime.fromtimestamp(perf.last_trade_time / 1000)
            if datetime.utcnow() - last_trade > timedelta(days=14):
                return "Inactivity (> 14 days)"
        # Note: If no trades ever, we might want to keep it a bit longer or have a separate 'dead on arrival' check. 
        # For now, assuming inactivity applies to strategies that *started* trading then stopped.
        
        # 3. Win Rate (Sample size > 50)
        if perf.trade_count >= 50:
            if perf.win_rate < 0.30:
                return f"Low Win Rate ({perf.win_rate:.1%})"
            
            # 4. Consistent Losses (Simple proxy for Sharpe < 0)
            if perf.total_pnl < 0:
                return f"Negative PnL after 50 trades (${perf.total_pnl:.2f})"
                
        return None

    def _is_promotion_candidate(self, perf: StrategyPerformance) -> bool:
        """
        Check if strategy is a candidate for promotion.
        
        Criteria:
        1. Trades > 100
        2. Win Rate > 45% (Conservative baseline)
        3. Max Drawdown < 10%
        4. Total PnL > 0
        """
        if perf.trade_count < 100:
            return False
            
        if perf.win_rate <= 0.45:
            return False
            
        if perf.max_drawdown >= 0.10:
            return False
            
        if perf.total_pnl <= 0:
            return False
            
        return True

    def _retire_strategy(self, strategy_id: str, reason: str, perf: StrategyPerformance):
        """
        Archive the strategy execution and file.
        """
        logger.info(f"Retiring strategy {strategy_id}: {reason}")
        
        # 1. Unload from Pool Manager
        self.pool.remove_strategy(strategy_id)
        
        # 2. Move file to retired directory
        src_file = self.shadow_pool_dir / f"{strategy_id}.json"
        if src_file.exists():
            dst_file = self.retired_dir / f"{strategy_id}.json"
            
            # If destination exists (re-retired?), append timestamp
            if dst_file.exists():
                timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
                dst_file = self.retired_dir / f"{strategy_id}_{timestamp}.json"
            
            try:
                # Add retirement metadata to the JSON before moving
                with open(src_file, 'r') as f:
                    data = json.load(f)
                
                data["retirement_info"] = {
                    "date": datetime.utcnow().isoformat(),
                    "reason": reason,
                    "final_stats": asdict(perf)
                }
                
                with open(src_file, 'w') as f:
                    json.dump(data, f, indent=2)
                    
                shutil.move(str(src_file), str(dst_file))
                logger.info(f"Archived {strategy_id} to {dst_file}")
            except Exception as e:
                logger.error(f"Failed to archive strategy file {src_file}: {e}")
        else:
            logger.warning(f"Strategy file {src_file} not found for retirement")

    def _save_report(self, report: LifecycleReport):
        """Save report to JSON file."""
        filename = f"lifecycle_{report.date}.json"
        path = self.reports_dir / filename
        
        try:
            with open(path, 'w') as f:
                json.dump(asdict(report), f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save lifecycle report: {e}")
