#!/bin/bash
# Tail multistep tool call logs for debugging
# Usage: ./scripts/tail_multistep_logs.sh

LOG_FILE="logs/multistep_tools.log"

if [ ! -f "$LOG_FILE" ]; then
    echo "⚠️  Log file not found: $LOG_FILE"
    echo "   Make sure the application has been started at least once"
    exit 1
fi

echo "📊 Tailing multistep tool logs from: $LOG_FILE"
echo "   Press Ctrl+C to stop"
echo ""

tail -f "$LOG_FILE"
