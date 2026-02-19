"""Tests for CSVLogger: thread safety, file creation, edge cases."""

import csv
import os
import tempfile
from pathlib import Path

from taggernews.infrastructure.csv_logger import CSVLogger


class TestCSVLogger:
    """Tests for CSVLogger file operations."""

    def test_creates_directory_on_init(self):
        """Logger creates parent directories if they don't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "nested" / "deep" / "metrics.csv"
            logger = CSVLogger(filepath)
            assert filepath.parent.exists()

    def test_writes_header_on_first_log(self):
        """First log call writes CSV header."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "test.csv"
            logger = CSVLogger(filepath)

            logger.log("test_op", 100.0, 5, 0)

            with open(filepath) as f:
                reader = csv.reader(f)
                header = next(reader)
                assert header == ["timestamp", "operation", "duration_ms", "item_count", "tokens"]

    def test_appends_data_rows(self):
        """Multiple log calls append data rows."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "test.csv"
            logger = CSVLogger(filepath)

            logger.log("op1", 100.0, 5, 10)
            logger.log("op2", 200.0, 10, 20)

            with open(filepath) as f:
                reader = csv.reader(f)
                rows = list(reader)

            assert len(rows) == 3  # header + 2 data rows
            assert rows[1][1] == "op1"
            assert rows[2][1] == "op2"

    def test_formats_duration_to_two_decimals(self):
        """Duration is formatted to 2 decimal places."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "test.csv"
            logger = CSVLogger(filepath)

            logger.log("op", 123.456789)

            with open(filepath) as f:
                reader = csv.reader(f)
                next(reader)  # skip header
                row = next(reader)
                assert row[2] == "123.46"

    def test_zero_item_count_and_tokens(self):
        """Default zero values for item_count and tokens."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "test.csv"
            logger = CSVLogger(filepath)

            logger.log("op", 50.0)

            with open(filepath) as f:
                reader = csv.reader(f)
                next(reader)
                row = next(reader)
                assert row[3] == "0"
                assert row[4] == "0"

    def test_existing_file_not_overwritten(self):
        """Existing file is appended to, not overwritten."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "test.csv"
            logger = CSVLogger(filepath)

            logger.log("op1", 100.0)
            logger.log("op2", 200.0)

            # Create a new logger instance pointing to same file
            logger2 = CSVLogger(filepath)
            logger2.log("op3", 300.0)

            with open(filepath) as f:
                reader = csv.reader(f)
                rows = list(reader)

            # Header + op1 + op2 + op3
            assert len(rows) == 4
