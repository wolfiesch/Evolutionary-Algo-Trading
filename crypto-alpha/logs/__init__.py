"""Logging configuration with separate trade and error loggers."""
import logging
import structlog
from pathlib import Path
from datetime import datetime


def setup_logging(logs_dir: Path) -> tuple[structlog.BoundLogger, structlog.BoundLogger]:
    """
    Configure trade logger and error logger.

    Returns:
        Tuple of (trade_logger, error_logger)
    """
    logs_dir.mkdir(parents=True, exist_ok=True)

    # Timestamp for log files
    date_str = datetime.now().strftime("%Y-%m-%d")

    # Trade logger - all trade activity
    trade_handler = logging.FileHandler(logs_dir / f"trades_{date_str}.log")
    trade_handler.setLevel(logging.INFO)
    trade_handler.setFormatter(logging.Formatter("%(message)s"))

    trade_log = logging.getLogger("trades")
    trade_log.setLevel(logging.INFO)
    trade_log.addHandler(trade_handler)

    # Also log to console for visibility
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter("%(asctime)s - %(message)s"))
    trade_log.addHandler(console_handler)

    # Error logger - exceptions only (BLACK SWAN LOG)
    error_handler = logging.FileHandler(logs_dir / f"errors_{date_str}.log")
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(
        logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    )

    error_log = logging.getLogger("errors")
    error_log.setLevel(logging.ERROR)
    error_log.addHandler(error_handler)

    # Also log errors to console
    error_console = logging.StreamHandler()
    error_console.setLevel(logging.ERROR)
    error_console.setFormatter(
        logging.Formatter("%(asctime)s - ERROR - %(message)s")
    )
    error_log.addHandler(error_console)

    # Configure structlog for JSON output
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    return (
        structlog.wrap_logger(trade_log),
        structlog.wrap_logger(error_log),
    )
