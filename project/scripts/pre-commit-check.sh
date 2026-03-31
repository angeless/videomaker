#!/bin/bash
# Pre-commit check script (v1.18)
# Runs before git commit to catch issues early

set -e

echo "=== Pre-commit Checks ==="

# 1. Check not committing to main/master directly
BRANCH=$(git branch --show-current)
if [ "$BRANCH" = "main" ] || [ "$BRANCH" = "master" ]; then
    echo "⚠️  Warning: Committing directly to $BRANCH branch"
fi

# 2. Python compile check (if .py files staged)
STAGED_PY=$(git diff --cached --name-only --diff-filter=ACM | grep '\.py$' || true)
if [ -n "$STAGED_PY" ]; then
    echo "--- Python compile check ---"
    for f in $STAGED_PY; do
        if [ -f "$f" ]; then
            python3 -c "import py_compile; py_compile.compile('$f', doraise=True)" 2>&1 || {
                echo "❌ Compile error in $f"
                exit 1
            }
        fi
    done
    echo "✅ Python compile: OK"
fi

# 3. Placeholder scan in tech-specs
PLACEHOLDERS=$(grep -r '{{' project/docs/tech-specs/ 2>/dev/null | grep -v '^\s*#' | grep -v '<!--' | grep -v '.json' || true)
if [ -n "$PLACEHOLDERS" ]; then
    echo "⚠️  Unreplaced placeholders found:"
    echo "$PLACEHOLDERS"
fi

# 4. Gate failures check
if [ -f "project/docs/.gate-failures.json" ]; then
    FAILURES=$(python3 -c "import json; d=json.load(open('project/docs/.gate-failures.json')); print(len(d.get('failures',[])))" 2>/dev/null || echo "0")
    if [ "$FAILURES" != "0" ]; then
        echo "⚠️  Gate failures not cleared: $FAILURES pending"
    fi
fi

echo "=== Pre-commit Checks Done ==="
