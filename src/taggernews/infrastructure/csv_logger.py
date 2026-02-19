"""CSV Logger for benchmarking metrics."""

import csv
import threading
from datetime import UTC, datetime
from pathlib import Path


class CSVLogger:
    """Thread-safe CSV logger for appending timing metrics."""

    def __init__(self, filepath: str | Path) -> None:
        """Initialize CSV logger.

        Args:
            filepath: Path to CSV file (will be created if doesn't exist)
        """
        self.filepath = Path(filepath)
        self._lock = threading.Lock()
        self._ensure_directory()

    def _ensure_directory(self) -> None:
        """Ensure the parent directory exists."""
        self.filepath.parent.mkdir(parents=True, exist_ok=True)

    def _write_header_if_needed(self) -> None:
        """Write CSV header if file doesn't exist or is empty."""
        if not self.filepath.exists() or self.filepath.stat().st_size == 0:
            with open(self.filepath, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["timestamp", "operation", "duration_ms", "item_count", "tokens"])

    def log(
        self,
        operation: str,
        duration_ms: float,
        item_count: int = 0,
        tokens: int = 0,
    ) -> None:
        """Log a timing metric to CSV.

        Args:
            operation: Name of the operation (e.g., "scrape_top_stories")
            duration_ms: Duration in milliseconds
            item_count: Number of items processed (optional)
            tokens: Number of tokens used (optional)
        """
        with self._lock:
            self._write_header_if_needed()
            with open(self.filepath, "a", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([
                    datetime.now(UTC).isoformat(),
                    operation,
                    f"{duration_ms:.2f}",
                    item_count,
                    tokens,
                ])


# Default logger instance for scraping benchmarks
_scraping_logger: CSVLogger | None = None


def get_scraping_logger() -> CSVLogger:
    """Get or create the scraping metrics logger."""
    global _scraping_logger
    if _scraping_logger is None:
        _scraping_logger = CSVLogger("benchmarking/scraping.csv")
    return _scraping_logger
