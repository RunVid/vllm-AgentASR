#!/bin/bash
set -e

echo "Searching for running api.py and VLLM engine processes..."

# Find PIDs for the main application script AND the VLLM engine processes.
# vLLM spawns a child process (e.g., VLLM::EngineCore) that must also be terminated.
# We use '|| true' to prevent 'set -e' from exiting the script if pgrep finds nothing.
PIDS_API=$(pgrep -f "api.py" || true)
PIDS_VLLM=$(pgrep -f "VLLM" || true)

# Combine, sort, and get unique PIDs
ALL_PIDS=$(echo "$PIDS_API $PIDS_VLLM" | tr ' ' '\n' | sort -u | tr '\n' ' ')

if [ -z "$ALL_PIDS" ]; then
    echo "No running api.py servers or VLLM engines found."
    exit 0
fi

echo "Found the following server and engine PIDs to stop:"
echo "$ALL_PIDS"
echo ""
echo "Stopping all related processes..."

# Kill all found processes
# The '--' ensures that if ALL_PIDS is empty or starts with a dash, it's not misinterpreted as an option.
kill -- $ALL_PIDS

# Optional: Add a small delay and check if processes are gone
sleep 1

# Check if any processes are still running
REMAINING_PIDS_API=$(pgrep -f "api.py" || true)
REMAINING_PIDS_VLLM=$(pgrep -f "VLLM" || true)
REMAINING_PIDS=$(echo "$REMAINING_PIDS_API $REMAINING_PIDS_VLLM" | tr ' ' '\n' | sort -u)

if [ -z "$REMAINING_PIDS" ]; then
    echo "All processes stopped successfully."
else
    echo "Warning: The following PIDs could not be stopped gracefully:"
    echo "$REMAINING_PIDS"
    echo "You may need to use 'kill -9' to force stop them."
fi
