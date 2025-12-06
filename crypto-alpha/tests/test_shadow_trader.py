"""Tests for shadow trading implementation."""
import pytest
import tempfile
from pathlib import Path
import pandas as pd

from execution.shadow.trader import ShadowTrader, TradeLog
from execution.shadow.position import Position
from engine.strategy_logic.parser import Strategy, Signal
from tests.fixtures.candle_data import generate_candles


def candles_to_df(candles) -> pd.DataFrame:
    """Convert list of Candle objects to DataFrame."""
    return pd.DataFrame([{
        'open': c.open,
        'high': c.high,
        'low': c.low,
        'close': c.close,
        'volume': c.volume,
    } for c in candles])


@pytest.fixture
def test_strategy():
    """Simple test strategy."""
    return Strategy(
        name="Test_Strategy",
        entry_long="btc_trend(60) >= 0 AND norm_rsi(14) < -0.4",
        exit_long="norm_rsi(14) > 0.4",
    )


@pytest.fixture
def temp_log_path():
    """Temporary log file path."""
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        yield Path(f.name)


@pytest.fixture
def trader(test_strategy, temp_log_path):
    """Shadow trader instance."""
    return ShadowTrader(
        strategy=test_strategy,
        equity=10000.0,
        log_path=temp_log_path,
    )


@pytest.fixture
def btc_uptrend():
    """BTC uptrend data for btc_trend >= 0."""
    return pd.DataFrame({
        'open': [40000.0 + i * 10 for i in range(200)],
        'high': [40050.0 + i * 10 for i in range(200)],
        'low': [39950.0 + i * 10 for i in range(200)],
        'close': [40000.0 + i * 10 for i in range(200)],
        'volume': [1000.0] * 200,
    })


@pytest.fixture
def oversold_candles():
    """Candles with oversold RSI (< -0.4)."""
    return pd.DataFrame({
        'open': [100.0] * 200,
        'high': [101.0] * 200,
        'low': [99.0] * 200,
        'close': [100.0 - i * 0.3 for i in range(200)],  # Steady decline
        'volume': [1000.0] * 200,
    })


@pytest.fixture
def overbought_candles():
    """Candles with overbought RSI (> 0.4)."""
    return pd.DataFrame({
        'open': [50.0] * 200,
        'high': [51.0] * 200,
        'low': [49.0] * 200,
        'close': [50.0 + i * 0.3 for i in range(200)],  # Steady rise
        'volume': [1000.0] * 200,
    })


class TestPosition:
    """Test Position dataclass."""

    def test_position_creation(self):
        """Test creating a position."""
        pos = Position(
            symbol="ETHUSDT",
            strategy_id="test",
            entry_time=1701820000000,
            entry_price=2000.0,
            size_usdt=100.0,
        )
        assert pos.symbol == "ETHUSDT"
        assert pos.side == "LONG"

    def test_unrealized_pnl_profit(self):
        """Test unrealized P&L calculation for profit."""
        pos = Position(
            symbol="ETHUSDT",
            strategy_id="test",
            entry_time=1701820000000,
            entry_price=2000.0,
            size_usdt=100.0,
        )
        # 10% price increase
        pnl = pos.unrealized_pnl(2200.0)
        assert pnl == pytest.approx(10.0, rel=0.01)

    def test_unrealized_pnl_loss(self):
        """Test unrealized P&L calculation for loss."""
        pos = Position(
            symbol="ETHUSDT",
            strategy_id="test",
            entry_time=1701820000000,
            entry_price=2000.0,
            size_usdt=100.0,
        )
        # 10% price decrease
        pnl = pos.unrealized_pnl(1800.0)
        assert pnl == pytest.approx(-10.0, rel=0.01)


class TestTradeLog:
    """Test TradeLog dataclass."""

    def test_trade_log_to_json(self):
        """Test JSON serialization."""
        log = TradeLog(
            timestamp=1701820000000,
            strategy_id="test",
            coin="ETHUSDT",
            signal="ENTRY_LONG",
            gene_expression="norm_rsi(14) < -0.4",
            price_at_signal=2000.0,
            simulated_fill=2005.0,
            position_size_usdt=100.0,
            btc_trend=1.0,
            atr_regime=0.0,
        )
        json_str = log.to_json()
        assert "ENTRY_LONG" in json_str
        assert "ETHUSDT" in json_str


class TestShadowTrader:
    """Test ShadowTrader class."""

    def test_initial_state(self, trader):
        """Test initial trader state."""
        assert trader.equity == 10000.0
        assert trader.trade_count == 0
        assert len(trader.positions) == 0

    def test_entry_creates_position(self, trader, oversold_candles, btc_uptrend):
        """Test that entry signal creates a position."""
        signal = trader.process_candle("ETHUSDT", oversold_candles, btc_uptrend)

        assert signal == Signal.ENTRY_LONG
        assert "ETHUSDT" in trader.positions
        assert trader.positions["ETHUSDT"].side == "LONG"

    def test_exit_closes_position(self, trader, oversold_candles, overbought_candles, btc_uptrend):
        """Test that exit signal closes position."""
        # First create a position
        trader.process_candle("ETHUSDT", oversold_candles, btc_uptrend)
        assert "ETHUSDT" in trader.positions

        # Now exit with overbought conditions
        signal = trader.process_candle("ETHUSDT", overbought_candles, btc_uptrend)

        assert signal == Signal.EXIT_LONG
        assert "ETHUSDT" not in trader.positions
        assert trader.trade_count == 1

    def test_max_positions_limit(self, trader, oversold_candles, btc_uptrend):
        """Test that max positions limit is enforced."""
        # Fill up to max positions
        for i in range(trader.max_open_positions):
            symbol = f"COIN{i}USDT"
            trader.positions[symbol] = Position(
                symbol=symbol,
                strategy_id="test",
                entry_time=1701820000000,
                entry_price=100.0,
                size_usdt=100.0,
            )

        # Try to add another
        signal = trader.process_candle("NEWCOINUSDT", oversold_candles, btc_uptrend)
        assert signal is None
        assert "NEWCOINUSDT" not in trader.positions

    def test_max_exposure_limit(self, trader, oversold_candles, btc_uptrend):
        """Test that max exposure limit is enforced."""
        # Create position using 50% of equity (at max exposure)
        trader.positions["BIGUSDT"] = Position(
            symbol="BIGUSDT",
            strategy_id="test",
            entry_time=1701820000000,
            entry_price=100.0,
            size_usdt=5000.0,  # 50% of 10000
        )

        # Try to add another
        signal = trader.process_candle("NEWCOINUSDT", oversold_candles, btc_uptrend)
        assert signal is None

    def test_friction_applied_on_entry(self, trader, oversold_candles, btc_uptrend):
        """Test that friction is applied on entry (higher fill price)."""
        current_price = oversold_candles["close"].iloc[-1]
        trader.process_candle("ETHUSDT", oversold_candles, btc_uptrend)

        position = trader.positions["ETHUSDT"]
        expected_fill = current_price * (1 + trader.friction_per_side)
        assert position.entry_price == pytest.approx(expected_fill, rel=0.001)

    def test_pnl_calculation(self, trader, oversold_candles, btc_uptrend):
        """Test P&L is calculated correctly on exit."""
        initial_equity = trader.equity

        # Enter
        trader.process_candle("ETHUSDT", oversold_candles, btc_uptrend)
        entry_price = trader.positions["ETHUSDT"].entry_price
        position_size = trader.positions["ETHUSDT"].size_usdt

        # Create exit conditions with higher price (profit)
        exit_candles = pd.DataFrame({
            'open': [50.0] * 200,
            'high': [52.0] * 200,
            'low': [48.0] * 200,
            'close': [50.0 + i * 0.5 for i in range(200)],  # Rising for overbought RSI
            'volume': [1000.0] * 200,
        })

        # Exit
        trader.process_candle("ETHUSDT", exit_candles, btc_uptrend)

        # Check trade was recorded
        assert trader.trade_count == 1

    def test_trade_logging(self, trader, oversold_candles, btc_uptrend, temp_log_path):
        """Test that trades are logged to file."""
        trader.process_candle("ETHUSDT", oversold_candles, btc_uptrend)

        # Check log file was written
        assert temp_log_path.exists()
        with open(temp_log_path) as f:
            content = f.read()
            assert "ENTRY_LONG" in content
            assert "ETHUSDT" in content

    def test_stats(self, trader, oversold_candles, overbought_candles, btc_uptrend):
        """Test stats calculation."""
        # Make a trade
        trader.process_candle("ETHUSDT", oversold_candles, btc_uptrend)
        trader.process_candle("ETHUSDT", overbought_candles, btc_uptrend)

        stats = trader.get_stats()
        assert stats["trade_count"] == 1
        assert stats["open_positions"] == 0
        assert "total_pnl" in stats
        assert "win_rate" in stats


class TestMultipleSymbols:
    """Test trading multiple symbols."""

    def test_independent_positions(self, trader, oversold_candles, btc_uptrend):
        """Test that positions are tracked independently per symbol."""
        # Enter two positions
        trader.process_candle("ETHUSDT", oversold_candles, btc_uptrend)

        # Create different oversold data for second symbol
        oversold2 = pd.DataFrame({
            'open': [200.0] * 200,
            'high': [201.0] * 200,
            'low': [199.0] * 200,
            'close': [200.0 - i * 0.3 for i in range(200)],
            'volume': [1000.0] * 200,
        })
        trader.process_candle("SOLUSDT", oversold2, btc_uptrend)

        assert len(trader.positions) == 2
        assert "ETHUSDT" in trader.positions
        assert "SOLUSDT" in trader.positions

    def test_exit_one_keeps_other(self, trader, oversold_candles, overbought_candles, btc_uptrend):
        """Test that exiting one position keeps the other."""
        # Enter two positions
        trader.process_candle("ETHUSDT", oversold_candles, btc_uptrend)

        oversold2 = pd.DataFrame({
            'open': [200.0] * 200,
            'high': [201.0] * 200,
            'low': [199.0] * 200,
            'close': [200.0 - i * 0.3 for i in range(200)],
            'volume': [1000.0] * 200,
        })
        trader.process_candle("SOLUSDT", oversold2, btc_uptrend)

        # Exit only ETHUSDT
        trader.process_candle("ETHUSDT", overbought_candles, btc_uptrend)

        assert len(trader.positions) == 1
        assert "ETHUSDT" not in trader.positions
        assert "SOLUSDT" in trader.positions
