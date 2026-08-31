"""
Generate synthetic shadow trades for testing the audit script.
"""
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

LOG_FILE = Path("logs/shadow_trades.jsonl")

def generate_data():
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    base_time = datetime.utcnow()
    trades = []
    
    # 1. Valid Trade
    trades.append({
        "timestamp": int(base_time.timestamp() * 1000),
        "strategy_id": "valid_strat",
        "coin": "BTCUSDT",
        "signal": "ENTRY_LONG",
        "price_at_signal": 50000.0,
        "simulated_fill": 50050.0, # 0.1% friction
        "position_size_usdt": 1000.0,
        "candle_open": 49900.0,
        "candle_high": 50100.0,
        "candle_low": 49900.0,
        "candle_close": 50000.0
    })
    
    # Exit for valid trade
    trades.append({
        "timestamp": int((base_time + timedelta(minutes=60)).timestamp() * 1000),
        "strategy_id": "valid_strat",
        "coin": "BTCUSDT",
        "signal": "EXIT_LONG_SIGNAL",
        "gene_expression": "some_logic",
        "price_at_signal": 51000.0,
        "simulated_fill": 50949.0, # 0.1% friction
        "position_size_usdt": 1000.0,
        "pnl": 17.96, # approx calculation
        "pnl_pct": 1.796,
        "candle_open": 50900.0,
        "candle_high": 51100.0,
        "candle_low": 50900.0,
        "candle_close": 51000.0
    })

    # 2. Suspicious Fill (Outside Candle)
    trades.append({
        "timestamp": int((base_time + timedelta(minutes=120)).timestamp() * 1000),
        "strategy_id": "suspicious_strat",
        "coin": "ETHUSDT",
        "signal": "ENTRY_LONG",
        "price_at_signal": 3000.0,
        "simulated_fill": 3003.0,
        "position_size_usdt": 1000.0,
        "candle_open": 2800.0,
        "candle_high": 2900.0, # Max is 2900, but signal was 3000!
        "candle_low": 2800.0,
        "candle_close": 2900.0
    })

    # 3. PnL Mismatch
    trades.append({
        "timestamp": int((base_time + timedelta(minutes=180)).timestamp() * 1000),
        "strategy_id": "math_fail_strat",
        "coin": "SOLUSDT",
        "signal": "EXIT_LONG_SIGNAL",
        "price_at_signal": 100.0,
        "simulated_fill": 99.9,
        "position_size_usdt": 1000.0,
        "pnl": 500.0, # Huge mismatch
        "pnl_pct": 50.0, 
        "candle_open": 90.0,
        "candle_high": 110.0,
        "candle_low": 90.0,
        "candle_close": 100.0
    })

    with open(LOG_FILE, "w") as f:
        for t in trades:
            f.write(json.dumps(t) + "\n")
            
    print(f"Generated {len(trades)} synthetic trades in {LOG_FILE}")

if __name__ == "__main__":
    generate_data()
