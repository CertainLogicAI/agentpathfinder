#!/bin/bash
# Autonomous Build System — Cron job
# Runs every 30 minutes to auto-build modules with new specs

LOG_DIR="/data/.openclaw/workspace/skills-publish/agentpathfinder/cron_logs"
REPO="/data/.openclaw/workspace/skills-publish/agentpathfinder"
LAST_RUN_FILE="$REPO/.build_data/.last_cron_run"

mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/auto_build_$(date +%Y%m%d_%H%M%S).log"

echo "[$(date -Iseconds)] Starting cron run" >> "$LOG"

# Check for new specs
if [ -f "$LAST_RUN_FILE" ]; then
    NEW_SPECS=$(find "$REPO/.build_data" -name "spec_*.md" -newer "$LAST_RUN_FILE" 2>/dev/null)
else
    NEW_SPECS=$(find "$REPO/.build_data" -name "spec_*.md" 2>/dev/null)
fi

if [ -z "$NEW_SPECS" ]; then
    echo "[$(date -Iseconds)] No new specs, nothing to build" >> "$LOG"
else
    echo "[$(date -Iseconds)] Found new specs:" >> "$LOG"
    echo "$NEW_SPECS" >> "$LOG"
    
    for spec in $NEW_SPECS; do
        name=$(basename "$spec" .md | sed 's/^spec_//')
        echo "[$date -Iseconds)] Building spec: $name" >> "$LOG"
        
        # Find module
        module=$(find "$REPO" -name "$name.py" -not -path "*/build_output/*" -not -path "*/.build_data/*" | head -1)
        if [ -n "$module" ]; then
            rel_mod=$(realpath --relative-to="$REPO" "$module")
            cd "$REPO"
            python3 scripts/auto_build.py --target "$rel_mod" >> "$LOG" 2>&1
            echo "[$date -Iseconds)] Build complete for $rel_mod" >> "$LOG"
        fi
    done
fi

# Log cache metrics
python3 "$REPO/scripts/cache_metrics.py" --report >> "$LOG" 2>&1

# Update last run timestamp
touch "$LAST_RUN_FILE"
echo "[$(date -Iseconds)] Cron run complete" >> "$LOG"
