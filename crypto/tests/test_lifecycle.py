"""
Unit tests for StrategyLifecycleManager.
"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta
from pathlib import Path

from execution.shadow.lifecycle import StrategyLifecycleManager, LifecycleReport
from execution.shadow.pool_manager import ShadowPoolManager, StrategyPerformance, ShadowPoolState
from config import settings

@pytest.fixture
def mock_pool_manager(tmp_path):
    """Create a mock ShadowPoolManager."""
    pool = MagicMock(spec=ShadowPoolManager)
    pool.shadow_pool_dir = tmp_path / "shadow_pool"
    pool.shadow_pool_dir.mkdir()
    pool.state = ShadowPoolState(paper_equity=10000, initial_equity=10000)
    pool.strategies = {}
    return pool

@pytest.fixture
def lifecycle_manager(mock_pool_manager):
    """Create a StrategyLifecycleManager instance."""
    return StrategyLifecycleManager(mock_pool_manager)

def test_retirement_max_drawdown(lifecycle_manager):
    """Test retirement due to max drawdown."""
    perf = StrategyPerformance(
        strategy_id="strat_dd",
        strategy_name="DrawdownMaster",
        max_drawdown=0.16, # > 15%
        trade_count=5
    )
    
    reason = lifecycle_manager._check_retirement(perf)
    assert reason is not None
    assert "Max Drawdown" in reason

def test_retirement_inactivity(lifecycle_manager):
    """Test retirement due to inactivity."""
    last_trade = (datetime.utcnow() - timedelta(days=15)).timestamp() * 1000
    perf = StrategyPerformance(
        strategy_id="strat_inactive",
        strategy_name="LazyStrat",
        last_trade_time=int(last_trade),
        trade_count=10
    )
    
    reason = lifecycle_manager._check_retirement(perf)
    assert reason is not None
    assert "Inactivity" in reason

def test_retirement_low_win_rate(lifecycle_manager):
    """Test retirement due to low win rate (with enough trades)."""
    perf = StrategyPerformance(
        strategy_id="strat_loser",
        strategy_name="LoserStrat",
        trade_count=55,
        winning_trades=10, # < 20% win rate
        total_pnl=-50
    )
    
    reason = lifecycle_manager._check_retirement(perf)
    assert reason is not None
    assert "Low Win Rate" in reason

def test_no_retirement_good_strat(lifecycle_manager):
    """Test a good strategy is not retired."""
    perf = StrategyPerformance(
        strategy_id="strat_good",
        strategy_name="GoodStrat",
        trade_count=60,
        winning_trades=40,
        total_pnl=100,
        max_drawdown=0.05
    )
    
    reason = lifecycle_manager._check_retirement(perf)
    assert reason is None

def test_promotion_candidate(lifecycle_manager):
    """Test promotion candidacy."""
    perf = StrategyPerformance(
        strategy_id="strat_promo",
        strategy_name="PromoStrat",
        trade_count=105, # > 100
        winning_trades=60, # > 45% (approx 57%)
        total_pnl=500, # > 0
        max_drawdown=0.05 # < 10%
    )
    
    assert lifecycle_manager._is_promotion_candidate(perf)

def test_promotion_fail_trades(lifecycle_manager):
    """Test promotion fails if not enough trades."""
    perf = StrategyPerformance(
        strategy_id="strat_new",
        strategy_name="NewStrat",
        trade_count=50, 
        winning_trades=40,
        total_pnl=500,
        max_drawdown=0.05
    )
    
    assert not lifecycle_manager._is_promotion_candidate(perf)

def test_full_cycle(lifecycle_manager, mock_pool_manager):
    """Test the full run_review_cycle flow."""
    # Setup strategies in pool
    mock_pool_manager.strategies = {
        "strat_retire": MagicMock(),
        "strat_promote": MagicMock(),
        "strat_keep": MagicMock()
    }
    
    mock_pool_manager.state.strategy_performance = {
        "strat_retire": StrategyPerformance(
            strategy_id="strat_retire", 
            strategy_name="RetireMe", 
            max_drawdown=0.20
        ),
        "strat_promote": StrategyPerformance(
            strategy_id="strat_promote", 
            strategy_name="PromoteMe", 
            trade_count=120, 
            winning_trades=80, 
            total_pnl=1000, 
            max_drawdown=0.05
        ),
        "strat_keep": StrategyPerformance(
            strategy_id="strat_keep", 
            strategy_name="KeepMe", 
            trade_count=10, 
            total_pnl=50, 
            max_drawdown=0.01
        )
    }
    
    # Create fake strategy files
    (mock_pool_manager.shadow_pool_dir / "strat_retire.json").touch()
    (mock_pool_manager.shadow_pool_dir / "strat_promote.json").touch()
    (mock_pool_manager.shadow_pool_dir / "strat_keep.json").touch()
    
    # Write valid json to files
    import json
    for name in ["strat_retire", "strat_promote", "strat_keep"]:
         with open(mock_pool_manager.shadow_pool_dir / f"{name}.json", "w") as f:
             json.dump({"strategy_id": name}, f)

    # Run cycle
    report = lifecycle_manager.run_review_cycle()
    
    # Verify retired
    assert len(report.retired) == 1
    assert report.retired[0]["id"] == "strat_retire"
    assert (lifecycle_manager.retired_dir / "strat_retire.json").exists()
    assert not (mock_pool_manager.shadow_pool_dir / "strat_retire.json").exists()
    
    # Verify promoted
    assert len(report.promoted_candidates) == 1
    assert report.promoted_candidates[0]["id"] == "strat_promote"
    
    # Verify keep
    assert (mock_pool_manager.shadow_pool_dir / "strat_keep.json").exists()
    
    # Verify removal called
    mock_pool_manager.remove_strategy.assert_called_with("strat_retire")

