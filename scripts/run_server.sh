#!/bin/bash
# Run the iOS Simulator MCP Server
#
# Usage: ./run_server.sh
# Usage: WDA_HOST=192.168.1.30 ./run_server.sh
#
# Environment variables:
#   WDA_HOST    - WebDriverAgent host (default: 127.0.0.1)
#   LOG_LEVEL   - Logging level: DEBUG, INFO, WARNING, ERROR (default: DEBUG)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR/src"

# Activate virtual environment if it exists
if [ -d "../venv" ]; then
    source ../venv/bin/activate
fi

# Default log level to DEBUG for verbose output
export LOG_LEVEL="${LOG_LEVEL:-DEBUG}"

# Force unbuffered Python output
export PYTHONUNBUFFERED=1

echo "Starting iOS Simulator MCP Server..."
echo "  WDA_HOST: ${WDA_HOST:-127.0.0.1}"
echo "  LOG_LEVEL: $LOG_LEVEL"
echo ""

# Run the server with unbuffered output
exec python -u -m ios_simulator_mcp.server
