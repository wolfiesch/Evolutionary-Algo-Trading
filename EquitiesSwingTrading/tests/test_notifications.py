"""Tests for Discord notification system."""
import pytest
from unittest.mock import Mock, patch, MagicMock
import time

from notifications.discord import DiscordNotifier, RateLimiter
from execution.shadow.models import TradeLog, DailySummary, PortfolioSnapshot


class TestRateLimiter:
    """Tests for RateLimiter."""

    def test_initial_tokens(self):
        limiter = RateLimiter()
        assert limiter.tokens == 25.0
        assert limiter.max_tokens == 25.0

    def test_acquire_success(self):
        limiter = RateLimiter()
        assert limiter.acquire() is True
        assert limiter.tokens == 24.0

    def test_acquire_depletes_tokens(self):
        limiter = RateLimiter(tokens=1.0, max_tokens=1.0)
        assert limiter.acquire() is True
        assert limiter.acquire() is False

    def test_token_refill(self):
        limiter = RateLimiter(tokens=0.0, refill_rate=10.0)  # 10 per second

        # Wait a bit for refill
        time.sleep(0.2)  # Should refill ~2 tokens

        # Should be able to acquire now
        assert limiter.acquire() is True

    def test_wait_for_token(self):
        limiter = RateLimiter(tokens=1.0, refill_rate=50.0)  # Fast refill

        # Use the token
        limiter.acquire()

        # Wait should succeed quickly with fast refill
        assert limiter.wait_for_token(timeout=0.5) is True

    def test_wait_for_token_timeout(self):
        limiter = RateLimiter(tokens=0.0, refill_rate=0.1)  # Slow refill

        # Should timeout
        assert limiter.wait_for_token(timeout=0.1) is False


class TestDiscordNotifier:
    """Tests for DiscordNotifier."""

    @pytest.fixture
    def mock_notifier(self):
        with patch("requests.Session") as mock_session:
            notifier = DiscordNotifier(
                webhook_url="https://discord.com/api/webhooks/test",
            )
            notifier.session = MagicMock()
            yield notifier

    @pytest.fixture
    def sample_entry_trade(self):
        return TradeLog(
            timestamp="2024-01-15T14:30:00",
            trade_date="2024-01-15",
            strategy_id="Test_Strategy",
            symbol="AAPL",
            signal="ENTRY_LONG",
            price_at_signal=185.00,
            simulated_fill=185.10,
            shares=27.0,
            notional_value=5000.00,
            spy_trend=1.0,
            vix_regime=1.0,
            market_regime="bull_calm",
            insider_intensity=0.5,
            revenue_cagr=0.15,
        )

    @pytest.fixture
    def sample_exit_trade(self):
        return TradeLog(
            timestamp="2024-01-20T14:30:00",
            trade_date="2024-01-20",
            strategy_id="Test_Strategy",
            symbol="AAPL",
            signal="EXIT_LONG",
            price_at_signal=195.00,
            simulated_fill=194.90,
            shares=27.0,
            notional_value=5268.00,
            spy_trend=1.0,
            vix_regime=1.0,
            market_regime="bull_calm",
            pnl=268.00,
            pnl_pct=5.36,
            days_held=5,
            exit_reason="signal",
        )

    @pytest.fixture
    def sample_summary(self):
        return DailySummary(
            date="2024-01-15",
            starting_equity=100000.00,
            ending_equity=101500.00,
            daily_pnl=1500.00,
            daily_pnl_pct=1.5,
            entries=3,
            exits=2,
            stop_losses=0,
            open_positions=6,
            exposure_pct=55.0,
            spy_change_pct=0.75,
            vix_level=15.0,
            market_regime="bull_calm",
        )

    @pytest.fixture
    def sample_snapshot(self):
        return PortfolioSnapshot(
            timestamp="2024-01-15T16:00:00",
            trade_date="2024-01-15",
            equity=102500.00,
            cash=50000.00,
            positions_value=52500.00,
            total_pnl=2500.00,
            total_pnl_pct=2.5,
            daily_pnl=500.00,
            daily_pnl_pct=0.49,
            open_positions=5,
            exposure_pct=51.2,
            max_drawdown_pct=1.5,
            total_trades=25,
            winning_trades=15,
            losing_trades=10,
            win_rate=0.6,
            spy_trend=1.0,
            vix_level=15.5,
            market_regime="bull_calm",
        )

    def test_notifier_initialization(self, mock_notifier):
        assert mock_notifier.webhook_url == "https://discord.com/api/webhooks/test"
        assert mock_notifier.bot_name == "Equities Shadow Trader"

    def test_send_trade_entry_success(self, mock_notifier, sample_entry_trade):
        mock_notifier.session.post.return_value = Mock(status_code=204)

        result = mock_notifier.send_trade_entry(sample_entry_trade)

        assert result is True
        mock_notifier.session.post.assert_called_once()

    def test_send_trade_entry_embeds(self, mock_notifier, sample_entry_trade):
        mock_notifier.session.post.return_value = Mock(status_code=204)

        mock_notifier.send_trade_entry(sample_entry_trade)

        call_args = mock_notifier.session.post.call_args
        payload = call_args[1]["json"]

        assert "embeds" in payload
        assert len(payload["embeds"]) == 1
        embed = payload["embeds"][0]
        assert "ENTRY" in embed["title"]
        assert "AAPL" in embed["title"]

    def test_send_trade_exit_success(self, mock_notifier, sample_exit_trade):
        mock_notifier.session.post.return_value = Mock(status_code=204)

        result = mock_notifier.send_trade_exit(sample_exit_trade)

        assert result is True

    def test_send_trade_exit_embeds(self, mock_notifier, sample_exit_trade):
        mock_notifier.session.post.return_value = Mock(status_code=204)

        mock_notifier.send_trade_exit(sample_exit_trade)

        call_args = mock_notifier.session.post.call_args
        payload = call_args[1]["json"]
        embed = payload["embeds"][0]

        assert "EXIT" in embed["title"]
        # Should be green for profit
        assert embed["color"] == 0x00FF00

    def test_send_trade_exit_loss_color(self, mock_notifier):
        trade = TradeLog(
            timestamp="2024-01-20T14:30:00",
            trade_date="2024-01-20",
            strategy_id="Test_Strategy",
            symbol="AAPL",
            signal="EXIT_LONG",
            price_at_signal=175.00,
            simulated_fill=174.90,
            shares=27.0,
            notional_value=4722.00,
            spy_trend=1.0,
            vix_regime=1.0,
            market_regime="bull_calm",
            pnl=-278.00,
            pnl_pct=-5.56,
            days_held=5,
            exit_reason="stop_loss",
        )

        mock_notifier.session.post.return_value = Mock(status_code=204)
        mock_notifier.send_trade_exit(trade)

        call_args = mock_notifier.session.post.call_args
        payload = call_args[1]["json"]
        embed = payload["embeds"][0]

        # Should be red for loss
        assert embed["color"] == 0xFF0000

    def test_send_daily_summary_success(self, mock_notifier, sample_summary):
        mock_notifier.session.post.return_value = Mock(status_code=204)

        result = mock_notifier.send_daily_summary(sample_summary)

        assert result is True

    def test_send_kill_switch(self, mock_notifier):
        mock_notifier.session.post.return_value = Mock(status_code=204)

        result = mock_notifier.send_kill_switch(
            trigger="Daily drawdown exceeded 5%",
            drawdown_pct=5.5,
            equity=95000.00,
            positions_closed=3,
        )

        assert result is True

        call_args = mock_notifier.session.post.call_args
        payload = call_args[1]["json"]

        assert "@here" in payload["content"]
        assert "KILL SWITCH" in payload["embeds"][0]["title"]

    def test_send_drawdown_warning(self, mock_notifier):
        mock_notifier.session.post.return_value = Mock(status_code=204)

        result = mock_notifier.send_drawdown_warning(
            level="warning",
            drawdown_pct=3.5,
            equity=96500.00,
        )

        assert result is True

    def test_send_startup(self, mock_notifier):
        mock_notifier.session.post.return_value = Mock(status_code=204)

        result = mock_notifier.send_startup(
            strategies=["Momentum_Pullback", "Insider_Momentum"],
            equity=100000.00,
            open_positions=0,
        )

        assert result is True

    def test_send_shutdown(self, mock_notifier):
        mock_notifier.session.post.return_value = Mock(status_code=204)

        result = mock_notifier.send_shutdown(
            reason="Scheduled maintenance",
            equity=102500.00,
            total_pnl=2500.00,
        )

        assert result is True

    def test_send_error(self, mock_notifier):
        mock_notifier.session.post.return_value = Mock(status_code=204)

        result = mock_notifier.send_error(
            error="Connection timeout",
            context="Fetching market data",
        )

        assert result is True

    def test_send_portfolio_snapshot(self, mock_notifier, sample_snapshot):
        mock_notifier.session.post.return_value = Mock(status_code=204)

        result = mock_notifier.send_portfolio_snapshot(sample_snapshot)

        assert result is True

    def test_rate_limit_handling(self, mock_notifier):
        # Simulate rate limit response
        rate_limit_response = Mock(
            status_code=429,
            json=lambda: {"retry_after": 0.1},
        )
        success_response = Mock(status_code=204)

        mock_notifier.session.post.side_effect = [rate_limit_response, success_response]

        result = mock_notifier.send_startup(
            strategies=["Test"],
            equity=100000.00,
            open_positions=0,
        )

        # Should succeed after retry
        assert result is True
        assert mock_notifier.session.post.call_count == 2

    def test_webhook_failure(self, mock_notifier, sample_entry_trade):
        mock_notifier.session.post.return_value = Mock(status_code=500, text="Server error")

        result = mock_notifier.send_trade_entry(sample_entry_trade)

        assert result is False
