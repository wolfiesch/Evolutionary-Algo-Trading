# Phase 3E: Strategy Lifecycle Management - Implementation Plan

**Created:** 2025-12-11
**Status:** Planning
**Prerequisites:** Phase 3A-3D Complete

## Overview

Complete the "Gauntlet" by implementing the automated "Hiring and Firing" of strategies. This system ensures that the shadow pool remains high-quality by ruthlessly culling underperformers and identifying top performers for potential live trading.

## 1. Objectives

1.  **Automated Retirement**: Remove strategies that hit "kill" criteria (Deep DD, consistent losses, inactivity).
2.  **Promotion Candidate Identification**: Highlight strategies that meet "Live Ready" criteria.
3.  **Reporting**: Generate daily summaries of pool health, retirements, and top performers.
4.  **Archival**: Move retired strategies to `logs/shadow_pool/retired/` to preserve history without cluttering the active pool.

## 2. Retirement Criteria (The "Firing" Squad)

A strategy is **Retired** (archived) if it meets ANY of these conditions:

| Metric           | Threshold | Minimum Sample | Rationale                                |
| ---------------- | --------- | -------------- | ---------------------------------------- |
| **Max Drawdown** | > 15%     | 1 trade        | Safety cutoff (hard stop)                |
| **Sharpe Ratio** | < 0.0     | 50 trades      | Consistently losing money                |
| **Win Rate**     | < 30%     | 50 trades      | Broken logic or bad fit                  |
| **Inactivity**   | No trades | 14 days        | Dead strategy (market changed or broken) |

_Note: "Minimum Sample" ensures we don't fire a strategy for one bad trade (unless it hits the hard DD limit)._

## 3. Promotion Criteria (The "Hiring" List)

A strategy is marked as a **Live Candidate** if it meets ALL conditions:

| Metric            | Threshold | Minimum Sample     |
| ----------------- | --------- | ------------------ |
| **Sharpe Ratio**  | > 1.0     | 100 trades         |
| **Profit Factor** | > 1.5     | 100 trades         |
| **Max Drawdown**  | < 10%     | Throughout history |
| **Returns**       | Positive  | 4 weeks            |

_Note: Promotion doesn't automatically start live trading. It puts the strategy on a "Shortlist" for human review._

## 4. Implementation Details

### 4.1 New Component: `StrategyLifecycleManager`

**Location:** `crypto/execution/shadow/lifecycle.py`

```python
class StrategyLifecycleManager:
    def __init__(self, pool_manager: ShadowPoolManager):
        self.pool = pool_manager
        self.retired_dir = settings.logs_dir / "shadow_pool" / "retired"

    def run_review_cycle(self) -> LifecycleReport:
        """
        Run a full review of the pool.
        1. Check all strategies against Retirement Criteria.
        2. Archive retired strategies.
        3. Identify Promotion Candidates.
        4. Generate Report.
        """

    def _check_retirement(self, stats: StrategyPerformance) -> Optional[str]:
        """Return reason if should retire, else None."""

    def _archive_strategy(self, strategy_id: str, reason: str):
        """Move JSON file to retired/ folder and log event."""
```

### 4.2 Updates to `ShadowPoolManager`

**Location:** `crypto/execution/shadow/pool_manager.py`

- Add `remove_strategy(strategy_id)` method to cleanly unload a strategy from memory.

### 4.3 Integration in `main.py`

- Run `lifecycle_manager.run_review_cycle()` once per day (e.g., at 00:00 UTC) or via a new CLI flag `--run-lifecycle`.

### 4.4 Reporting

**Report File:** `logs/daily_reports/lifecycle_YYYY-MM-DD.json`

Structure:

```json
{
  "date": "2025-12-11",
  "pool_size_start": 20,
  "pool_size_end": 18,
  "retired": [{ "id": "strat_123", "reason": "Max Drawdown > 15% (-16.2%)" }],
  "promoted_candidates": [{ "id": "strat_999", "sharpe": 1.4, "trades": 120 }]
}
```

## 5. Task Breakdown

| Task                       | Description                                                                    | Effort |
| -------------------------- | ------------------------------------------------------------------------------ | ------ |
| **1. Lifecycle Manager**   | Create `crypto/execution/shadow/lifecycle.py` with retirement/promotion logic. | Medium |
| **2. Pool Manager Update** | Add `remove_strategy` to `ShadowPoolManager`.                                  | Low    |
| **3. Integration**         | Add lifecycle check to `main.py` loop (or scheduler).                          | Low    |
| **4. CLI Tool**            | Add `--lifecycle-check` flag to `main.py` for manual runs.                     | Low    |
| **5. Testing**             | Unit tests for retirement logic and file archival.                             | Medium |

## 6. Verification

1.  **Unit Test**: Create synthetic `StrategyPerformance` objects (one good, one bad). Verify "bad" one triggers retirement and "good" one triggers promotion candidate.
2.  **Integration Test**: Create a dummy strategy file, simulate poor performance in `ShadowPoolManager`, run lifecycle check, verify file moves to `retired/`.
