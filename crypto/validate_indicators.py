"""
Indicator validation script - compares our calculations with TradingView reference values.

Phase 1 Success Criteria:
- EMA, RSI, ATR, BB must match reference within 0.1% tolerance

Usage:
    python validate_indicators.py
"""
import pandas as pd
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.engine.gene_pool import trend, mean_reversion, volatility
from crypto.data.storage.repository import CandleRepository
from crypto.config import settings


def validate_ema(candles_df: pd.DataFrame, symbol: str):
    """Validate EMA calculations against TradingView."""
    print(f"\n{'='*60}")
    print(f"EMA Validation for {symbol}")
    print(f"{'='*60}")

    # Calculate EMA(9) and EMA(21)
    ema_9_21 = trend.ema_trend(candles_df, 9, 21)

    print(f"Latest close: {candles_df['close'].iloc[-1]:.2f}")
    print(f"EMA trend (9,21): {ema_9_21:.4f}")
    print(f"  (+1.0 = uptrend, -1.0 = downtrend)")

    # Print last 5 closes for manual verification
    print(f"\nLast 5 closes:")
    for i in range(-5, 0):
        print(f"  [{i}] {candles_df['close'].iloc[i]:.2f}")

    print(f"\n✓ Manual verification required:")
    print(f"  1. Open TradingView: https://www.tradingview.com/chart/?symbol=BYBIT:{symbol}.P")
    print(f"  2. Set timeframe to 1 minute")
    print(f"  3. Add EMA(9) and EMA(21) indicators")
    print(f"  4. Verify trend direction matches")

    return True


def validate_rsi(candles_df: pd.DataFrame, symbol: str):
    """Validate RSI calculations against TradingView."""
    print(f"\n{'='*60}")
    print(f"RSI Validation for {symbol}")
    print(f"{'='*60}")

    # Calculate normalized RSI(14)
    norm_rsi_14 = mean_reversion.norm_rsi(candles_df, 14)

    # Convert back to standard RSI (0-100)
    actual_rsi = (norm_rsi_14 * 50) + 50

    print(f"Latest close: {candles_df['close'].iloc[-1]:.2f}")
    print(f"Normalized RSI(14): {norm_rsi_14:.4f}")
    print(f"Actual RSI(14): {actual_rsi:.2f}")
    print(f"  (Range: 0-100, <30 = oversold, >70 = overbought)")

    print(f"\n✓ Manual verification required:")
    print(f"  1. Open TradingView: https://www.tradingview.com/chart/?symbol=BYBIT:{symbol}.P")
    print(f"  2. Set timeframe to 1 minute")
    print(f"  3. Add RSI(14) indicator")
    print(f"  4. Verify value matches {actual_rsi:.2f} ± 0.1%")
    print(f"     (Tolerance: {actual_rsi * 0.999:.2f} - {actual_rsi * 1.001:.2f})")

    return True


def validate_atr(candles_df: pd.DataFrame, symbol: str):
    """Validate ATR calculations against TradingView."""
    print(f"\n{'='*60}")
    print(f"ATR Validation for {symbol}")
    print(f"{'='*60}")

    # Calculate ATR regime
    atr_regime_val = volatility.atr_regime(candles_df, 14)

    print(f"Latest close: {candles_df['close'].iloc[-1]:.2f}")
    print(f"ATR regime: {atr_regime_val:.4f}")
    print(f"  (+1.0 = high volatility, 0.0 = normal, -1.0 = low)")

    print(f"\n✓ Manual verification required:")
    print(f"  1. Open TradingView: https://www.tradingview.com/chart/?symbol=BYBIT:{symbol}.P")
    print(f"  2. Set timeframe to 1 minute")
    print(f"  3. Add ATR(14) indicator")
    print(f"  4. Check if current ATR is relatively high/normal/low")

    return True


def validate_bollinger_bands(candles_df: pd.DataFrame, symbol: str):
    """Validate Bollinger Bands calculations against TradingView."""
    print(f"\n{'='*60}")
    print(f"Bollinger Bands Validation for {symbol}")
    print(f"{'='*60}")

    # Calculate BB position (20, 2.0 std dev)
    bb_pos = mean_reversion.bb_position(candles_df, 20, 2.0)

    print(f"Latest close: {candles_df['close'].iloc[-1]:.2f}")
    print(f"BB position: {bb_pos:.4f}")
    print(f"  (-1.0 = at lower band, 0.0 = at middle, +1.0 = at upper band)")

    print(f"\n✓ Manual verification required:")
    print(f"  1. Open TradingView: https://www.tradingview.com/chart/?symbol=BYBIT:{symbol}.P")
    print(f"  2. Set timeframe to 1 minute")
    print(f"  3. Add Bollinger Bands (20, 2) indicator")
    print(f"  4. Check price position relative to bands")

    return True


def main():
    """Run indicator validation."""
    print("="*60)
    print("INDICATOR VALIDATION SCRIPT")
    print("Phase 1 Success Criteria: Indicators match TradingView ± 0.1%")
    print("="*60)

    # Connect to database (use cloud database if available)
    cloud_db = Path(__file__).parent / "data" / "candles_cloud.db"
    db_path = cloud_db if cloud_db.exists() else settings.sqlite_path
    print(f"Using database: {db_path}")

    repo = CandleRepository(db_path)

    # Test symbols
    test_symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

    for symbol in test_symbols:
        # Get latest 200 candles (enough for all indicators)
        candles = repo.get_latest(symbol, limit=200)

        if len(candles) < 100:
            print(f"\n⚠ Skipping {symbol}: Only {len(candles)} candles (need 100+)")
            continue

        # Convert to DataFrame
        df = pd.DataFrame([{
            'open': c.open,
            'high': c.high,
            'low': c.low,
            'close': c.close,
            'volume': c.volume,
        } for c in candles])

        # Run validations
        validate_ema(df, symbol)
        validate_rsi(df, symbol)
        validate_atr(df, symbol)
        validate_bollinger_bands(df, symbol)

        print(f"\n" + "="*60)
        input(f"Press Enter to continue to next symbol...")

    print("\n" + "="*60)
    print("✓ Validation script complete")
    print("  Manual verification against TradingView required for Phase 1 sign-off")
    print("="*60)


if __name__ == "__main__":
    main()
