#!/bin/bash
# Auto-build cron — checks for new/updated specs every 30 minutes
# Run from repo root

REPO="/data/.openclaw/workspace/skills-publish/agentpathfinder"
SPEC_DIR="$REPO/.build_data"
LAST_RUN_FILE="$REPO/.build_data/.last_auto_run"

# Ensure spec dir exists
[ -d "$SPEC_DIR" ] || exit 0

# Find specs modified since last run
if [ -f "$LAST_RUN_FILE" ]; then
    NEW_SPECS=$(find "$SPEC_DIR" -name "spec_*.md" -newer "$LAST_RUN_FILE" 2>/dev/null)
else
    NEW_SPECS=$(find "$SPEC_DIR" -name "spec_*.md" 2>/dev/null)
fi

if [ -z "$NEW_SPECS" ]; then
    exit 0  # Nothing new
fi

# Run auto_build.py for each new spec
echo "[$(date -Iseconds)] Found new/updated specs:"
echo "$NEW_SPECS"

for spec in $NEW_SPECS; do
    # Extract module name from spec filename (spec_<name>.md -> <name>.py)
    name=$(basename "$spec" .md | sed 's/^spec_//')
    
    # Find the actual module path
    module=$(find "$REPO" -name "$name.py" -not -path "*/build_output/*" -not -path "*/.build_data/*" | head -1)
    
    if [ -n "$module" ]; then
        # Get relative path from repo root
        rel_mod=$(realpath --relative-to="$REPO" "$module")
        echo "  -> Building $rel_mod (from spec: $spec)"
        cd "$REPO"
        python3 scripts/auto_build.py --target "$rel_mod" 2>&1 | tee -a "$REPO/.build_data/auto_build.log"
    else
        echo "  -> WARNING: No module found for spec $spec"
    fi
done

# Update last run timestamp
touch "$LAST_RUN_FILE"
echo "[$(date -Iseconds)] Cron run complete"
