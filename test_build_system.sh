#!/bin/bash
# test_suite.sh - Run all build system tests

echo "============================================"
echo "CertainLogic Build System Test Suite"
echo "============================================"
echo ""

REPO_ROOT="/data/.openclaw/workspace"
SKILL_DIR="$REPO_ROOT/skills-publish/agentpathfinder"
cd "$SKILL_DIR"

PASS=0
FAIL=0

# Test 1: GBrain connectivity
echo "[1/5] GBrain health check..."
if curl -s http://127.0.0.1:8000/health > /dev/null; then
    echo "  PASS"
    PASS=$((PASS+1))
else
    echo "  FAIL"
    FAIL=$((FAIL+1))
fi

# Test 2: GBrain fact count
echo "[2/5] GBrain facts loaded..."
FACTS=$(curl -s http://127.0.0.1:8000/facts?page_size=1 | python3 -c "import sys,json; print(json.load(sys.stdin).get('count',0))" 2>/dev/null)
if [ "$FACTS" -gt 400 ]; then
    echo "  PASS ($FACTS facts)"
    PASS=$((PASS+1))
else
    echo "  FAIL ($FACTS facts)"
    FAIL=$((FAIL+1))
fi

# Test 3: Spec generator
echo "[3/5] Spec generator..."
SPEC=$(python3 scripts/spec_generator.py --feature "Test Feature" --type api 2>&1)
if echo "$SPEC" | grep -q "Build Spec: Test Feature"; then
    echo "  PASS"
    PASS=$((PASS+1))
else
    echo "  FAIL"
    FAIL=$((FAIL+1))
fi

# Test 4: Auto builder dry run
echo "[4/5] Auto builder dry run..."
RESULT=$(python3 /tmp/test_auto_build.py 2>&1)
if echo "$RESULT" | grep -q "Result: OK"; then
    echo "  PASS"
    PASS=$((PASS+1))
else
    echo "  FAIL"
    FAIL=$((FAIL+1))
fi

# Test 5: Build orchestrator (existing)
echo "[5/5] Build orchestrator (existing)..."
if [ -f "scripts/build_orchestrator.py" ]; then
    echo "  PASS (exists)"
    PASS=$((PASS+1))
else
    echo "  FAIL (missing)"
    FAIL=$((FAIL+1))
fi

echo ""
echo "============================================"
echo "Results: $PASS passed, $FAIL failed"
echo "============================================"

if [ $FAIL -eq 0 ]; then
    echo "All tests passed. Build system ready."
    exit 0
else
    echo "Some tests failed. Review output above."
    exit 1
fi
