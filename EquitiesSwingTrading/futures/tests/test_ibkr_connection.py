"""
IBKR Connection Test Script

Run this to verify TWS/Gateway API connection is working.

Prerequisites:
1. TWS or IB Gateway must be running
2. API must be enabled in TWS settings (Edit -> Global Configuration -> API -> Settings)
3. Socket port must match (default: 7497 for paper, 7496 for live)

Usage:
    python -m futures.tests.test_ibkr_connection

Or with pytest:
    pytest futures/tests/test_ibkr_connection.py -v
"""
import asyncio
import sys
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Check ibapi availability first
try:
    import ibapi
    IBAPI_AVAILABLE = True
    print(f"[OK] ibapi version: {ibapi.__version__ if hasattr(ibapi, '__version__') else 'installed'}")
except ImportError:
    IBAPI_AVAILABLE = False
    print("[ERROR] ibapi not installed. Install via: pip install ibapi")
    print("        Or download from: https://interactivebrokers.github.io/")


async def test_connection():
    """Test basic IBKR connection."""
    if not IBAPI_AVAILABLE:
        print("\n[SKIP] Cannot test connection - ibapi not installed")
        return False

    from execution.live.ibkr_adapter import IBKRAdapter, IBKRConfig

    print("\n" + "=" * 60)
    print("IBKR Connection Test")
    print("=" * 60)

    # Configuration - paper trading by default
    # Try paper port first, fall back to live if needed
    import os
    port = int(os.environ.get("IBKR_PORT", "7497"))

    config = IBKRConfig(
        host="127.0.0.1",
        port=port,  # 7497=paper, 7496=live
        client_id=999,  # Use unique client ID for testing
        timeout=15.0,
    )

    print(f"\nConnecting to {config.host}:{config.port} (client_id={config.client_id})...")
    print("Make sure TWS/Gateway is running with API enabled!")
    print("Set IBKR_PORT env var to override (7497=paper, 7496=live)\n")

    adapter = IBKRAdapter(config)

    try:
        connected = await adapter.connect()

        if connected:
            print("[OK] Connected to IBKR!")

            # Test account data
            print("\n--- Account Info ---")
            try:
                account = await adapter.get_account()
                print(f"  Equity:       ${account.equity:,.2f}")
                print(f"  Cash:         ${account.cash:,.2f}")
                print(f"  Buying Power: ${account.buying_power:,.2f}")
                print(f"  Portfolio:    ${account.portfolio_value:,.2f}")
            except Exception as e:
                print(f"  [ERROR] Failed to get account: {e}")

            # Test positions
            print("\n--- Positions ---")
            try:
                positions = await adapter.get_positions()
                if positions:
                    for pos in positions:
                        print(f"  {pos.symbol}: {pos.quantity} @ ${pos.avg_entry_price:.2f}")
                else:
                    print("  No open positions")
            except Exception as e:
                print(f"  [ERROR] Failed to get positions: {e}")

            # Test open orders
            print("\n--- Open Orders ---")
            try:
                orders = await adapter.get_open_orders()
                if orders:
                    for order in orders:
                        print(f"  {order.order_id}: {order.side.value} {order.quantity} {order.symbol}")
                else:
                    print("  No open orders")
            except Exception as e:
                print(f"  [ERROR] Failed to get orders: {e}")

            print("\n" + "=" * 60)
            print("Connection Test: PASSED")
            print("=" * 60)
            return True

    except Exception as e:
        print(f"\n[ERROR] Connection failed: {e}")
        print("\nTroubleshooting:")
        print("  1. Is TWS or IB Gateway running?")
        print("  2. Is API enabled? (TWS: Edit -> Global Configuration -> API -> Settings)")
        print("  3. Is 'Enable ActiveX and Socket Clients' checked?")
        print("  4. Is the socket port correct? (Default: 7497 for paper)")
        print("  5. Is 'Read-Only API' unchecked? (for order execution)")
        print("\n" + "=" * 60)
        print("Connection Test: FAILED")
        print("=" * 60)
        return False

    finally:
        await adapter.disconnect()


async def test_contract_definitions():
    """Test futures contract definition logic."""
    print("\n" + "=" * 60)
    print("Contract Definition Test")
    print("=" * 60)

    from futures.data.contracts import (
        get_front_month,
        get_contract_chain,
        should_rollover,
        create_ibkr_contract_params,
    )
    from datetime import date

    # Test front month calculation
    print("\n--- Front Month Contracts ---")
    symbols = ["ES", "MES", "NQ", "CL"]
    for symbol in symbols:
        contract = get_front_month(symbol)
        params = create_ibkr_contract_params(contract)
        print(f"  {symbol}: {contract.full_symbol} ({params['exchange']}, expiry={params['lastTradeDateOrContractMonth']})")

    # Test contract chain
    print("\n--- ES Contract Chain (next 4) ---")
    chain = get_contract_chain("ES", num_contracts=4)
    for i, contract in enumerate(chain):
        marker = "(front)" if i == 0 else ""
        print(f"  {contract.full_symbol} {marker}")

    # Test rollover check
    print("\n--- Rollover Check ---")
    front = get_front_month("ES")
    should_roll, next_contract = should_rollover(front)
    if should_roll:
        print(f"  {front.full_symbol} should roll to {next_contract.full_symbol}")
    else:
        print(f"  {front.full_symbol} - no rollover needed yet")

    print("\n" + "=" * 60)
    print("Contract Test: PASSED")
    print("=" * 60)
    return True


async def main():
    """Run all tests."""
    print("\n" + "#" * 60)
    print("# IBKR Futures Trading - Connection & Setup Tests")
    print("#" * 60)

    # Always run contract tests (no connection needed)
    await test_contract_definitions()

    # Run connection test
    print("\n")
    result = await test_connection()

    return result


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
