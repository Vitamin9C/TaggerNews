#!/bin/bash
# Run Locust load test for TaggerNews
#
# Usage:
#   ./run_load_test.sh              # Run with defaults (10 users, 60s)
#   ./run_load_test.sh 20 5 120     # 20 users, spawn rate 5, 120 seconds
#
# Prerequisites:
#   uv add --dev locust
#   Start the server: uv run python -m taggernews.main

set -e

# Default parameters
USERS=${1:-10}
SPAWN_RATE=${2:-2}
RUN_TIME=${3:-60}
HOST=${HOST:-http://localhost:8000}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Starting Locust load test..."
echo "  Host: $HOST"
echo "  Users: $USERS"
echo "  Spawn rate: $SPAWN_RATE"
echo "  Run time: ${RUN_TIME}s"
echo ""

cd "$SCRIPT_DIR"

# Run in headless mode with HTML report
uv run locust \
    -f locustfile.py \
    --host="$HOST" \
    --users "$USERS" \
    --spawn-rate "$SPAWN_RATE" \
    --run-time "${RUN_TIME}s" \
    --headless \
    --html="load_test_report.html"

echo ""
echo "Load test complete! Report saved to: $SCRIPT_DIR/load_test_report.html"
