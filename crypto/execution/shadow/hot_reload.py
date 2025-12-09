"""
Hot-reload watcher for shadow pool strategies.

Monitors the shadow pool directory for changes and signals
the main process to reload strategies without restart.

Usage:
    python -m execution.shadow.hot_reload

The watcher uses a simple file-based signaling mechanism:
- Creates a .reload signal file when changes detected
- Main process checks for this file periodically
"""
import logging
import os
import signal
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


class StrategyWatcher:
    """
    Watches shadow pool directory for strategy changes.

    Features:
    - Detects new, modified, and deleted strategy files
    - Debounces rapid changes (waits for stability)
    - Creates signal file for main process
    - Handles graceful shutdown
    """

    def __init__(
        self,
        shadow_pool_dir: Optional[Path] = None,
        signal_file: Optional[Path] = None,
        poll_interval: float = 5.0,
        debounce_seconds: float = 3.0,
    ):
        """
        Initialize watcher.

        Args:
            shadow_pool_dir: Directory to watch
            signal_file: Path for reload signal file
            poll_interval: Seconds between checks
            debounce_seconds: Wait for stability after change
        """
        self.shadow_pool_dir = shadow_pool_dir or (settings.logs_dir / "shadow_pool")
        self.signal_file = signal_file or (settings.logs_dir / ".reload_strategies")
        self.poll_interval = poll_interval
        self.debounce_seconds = debounce_seconds

        self._running = False
        self._file_states: dict[str, tuple[float, int]] = {}  # path -> (mtime, size)
        self._last_change_time: Optional[float] = None

        # Ensure directory exists
        self.shadow_pool_dir.mkdir(parents=True, exist_ok=True)

    def _get_current_states(self) -> dict[str, tuple[float, int]]:
        """Get current file states (mtime, size) for all JSON files."""
        states = {}

        for filepath in self.shadow_pool_dir.glob("*.json"):
            try:
                stat = filepath.stat()
                states[str(filepath)] = (stat.st_mtime, stat.st_size)
            except OSError:
                # File may have been deleted
                pass

        return states

    def _detect_changes(self) -> list[str]:
        """
        Detect changes in shadow pool directory.

        Returns:
            List of change descriptions
        """
        changes = []
        current_states = self._get_current_states()

        # Check for new and modified files
        for path, (mtime, size) in current_states.items():
            if path not in self._file_states:
                changes.append(f"NEW: {Path(path).name}")
            else:
                old_mtime, old_size = self._file_states[path]
                if mtime != old_mtime or size != old_size:
                    changes.append(f"MODIFIED: {Path(path).name}")

        # Check for deleted files
        for path in self._file_states:
            if path not in current_states:
                changes.append(f"DELETED: {Path(path).name}")

        # Update state
        self._file_states = current_states

        return changes

    def _signal_reload(self):
        """Create signal file to trigger reload in main process."""
        try:
            with open(self.signal_file, "w") as f:
                f.write(datetime.utcnow().isoformat())
            logger.info(f"Created reload signal file: {self.signal_file}")
        except OSError as e:
            logger.error(f"Failed to create signal file: {e}")

    def run(self):
        """
        Start the watcher loop.
        """
        self._running = True

        # Set up signal handlers
        def signal_handler(signum, frame):
            logger.info("Shutdown signal received")
            self._running = False

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        logger.info("=" * 50)
        logger.info("STRATEGY HOT-RELOAD WATCHER STARTED")
        logger.info("=" * 50)
        logger.info(f"Watching: {self.shadow_pool_dir}")
        logger.info(f"Poll interval: {self.poll_interval}s")
        logger.info(f"Debounce: {self.debounce_seconds}s")
        logger.info("=" * 50)

        # Initial state scan
        self._file_states = self._get_current_states()
        logger.info(f"Initial scan: {len(self._file_states)} strategy files")

        while self._running:
            try:
                changes = self._detect_changes()

                if changes:
                    logger.info(f"Changes detected: {', '.join(changes)}")
                    self._last_change_time = time.time()

                # Debounce: signal reload after stability period
                if self._last_change_time:
                    elapsed = time.time() - self._last_change_time
                    if elapsed >= self.debounce_seconds:
                        logger.info("Stability reached, signaling reload")
                        self._signal_reload()
                        self._last_change_time = None

                time.sleep(self.poll_interval)

            except Exception as e:
                logger.error(f"Watcher error: {e}")
                time.sleep(self.poll_interval)

        logger.info("Watcher stopped")

    def stop(self):
        """Stop the watcher."""
        self._running = False


def check_reload_signal(signal_file: Optional[Path] = None) -> bool:
    """
    Check if a reload signal exists and consume it.

    Call this periodically from the main process to check
    if strategies should be reloaded.

    Args:
        signal_file: Path to signal file

    Returns:
        True if reload signal was present
    """
    signal_path = signal_file or (settings.logs_dir / ".reload_strategies")

    if signal_path.exists():
        try:
            signal_path.unlink()  # Delete the signal file
            return True
        except OSError:
            pass

    return False


def main():
    """Entry point for hot-reload watcher."""
    watcher = StrategyWatcher()
    watcher.run()


if __name__ == "__main__":
    main()
