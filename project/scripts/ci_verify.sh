#!/usr/bin/env bash
# ════════════════════════════════════════════════════════════════════
# ci_verify.sh — Part A 自动化门禁脚本
# ════════════════════════════════════════════════════════════════════
#
# 用法:
#   ./scripts/ci_verify.sh          # 运行全部检查
#   ./scripts/ci_verify.sh --quick  # 只运行语法检查 + 单元测试
#
# 退出码:
#   0 = 全部通过
#   1 = 有失败项
#
# 本脚本作为 dev-governance.md §12.2 Part A 门禁的自动化入口。
# ════════════════════════════════════════════════════════════════════

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

# ── 颜色 ──
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
NC='\033[0m'

PASSED=0
FAILED=0
SKIPPED=0
RESULTS=()

# ── 工具函数 ──
run_check() {
    local name="$1"
    shift
    printf "${CYAN}▶ %-40s${NC}" "$name"
    if "$@" > /tmp/ci_verify_output.txt 2>&1; then
        printf "${GREEN}PASS${NC}\n"
        PASSED=$((PASSED + 1))
        RESULTS+=("✅ $name")
    else
        printf "${RED}FAIL${NC}\n"
        FAILED=$((FAILED + 1))
        RESULTS+=("❌ $name")
        # 显示失败输出的最后 20 行
        tail -20 /tmp/ci_verify_output.txt | sed 's/^/   /'
    fi
}

skip_check() {
    local name="$1"
    local reason="$2"
    printf "${YELLOW}▶ %-40s SKIP (%s)${NC}\n" "$name" "$reason"
    SKIPPED=$((SKIPPED + 1))
    RESULTS+=("⏭️  $name (skipped: $reason)")
}

# ── 模式判断 ──
QUICK=false
if [[ "${1:-}" == "--quick" ]]; then
    QUICK=true
fi

echo ""
echo "════════════════════════════════════════════════════"
echo "  VideoEditor — Part A Gate Verification"
echo "════════════════════════════════════════════════════"
echo "  Project: $PROJECT_DIR"
echo "  Mode:    $([ "$QUICK" = true ] && echo 'Quick' || echo 'Full')"
echo "  Time:    $(date '+%Y-%m-%d %H:%M:%S')"
echo "════════════════════════════════════════════════════"
echo ""

# ═══════════════════════════════════════════════════════
# Gate 1: Python 语法检查
# ═══════════════════════════════════════════════════════
check_python_syntax() {
    # 排除 legacy_lab（已知有语法问题的历史代码）
    python3 -c "
import py_compile, sys, os
errors = []
for root_dir in ['modules', 'apps', 'tests']:
    for dirpath, dirnames, filenames in os.walk(root_dir):
        # 跳过 legacy_lab 和 __pycache__
        dirnames[:] = [d for d in dirnames if d not in ('legacy_lab', '__pycache__')]
        for f in filenames:
            if f.endswith('.py'):
                path = os.path.join(dirpath, f)
                try:
                    py_compile.compile(path, doraise=True)
                except py_compile.PyCompileError as e:
                    errors.append(str(e))
if errors:
    print('\n'.join(errors))
    sys.exit(1)
"
}
run_check "Python syntax (excl. legacy_lab)" check_python_syntax

# ═══════════════════════════════════════════════════════
# Gate 2: 关键文件存在性
# ═══════════════════════════════════════════════════════
check_files() {
    local missing=0
    for f in VERSION CHANGELOG.md requirements.txt; do
        if [[ ! -f "$f" ]]; then
            echo "MISSING: $f"
            missing=1
        fi
    done
    return $missing
}
run_check "Critical files exist" check_files

# ═══════════════════════════════════════════════════════
# Gate 3: 技术规范四件套存在
# ═══════════════════════════════════════════════════════
check_tech_specs() {
    local missing=0
    for f in docs/tech-specs/architecture.md \
             docs/tech-specs/dev-governance.md \
             docs/tech-specs/coding-standards.md \
             docs/tech-specs/testing-strategy.md; do
        if [[ ! -f "$f" ]]; then
            echo "MISSING: $f"
            missing=1
        fi
    done
    return $missing
}
run_check "Tech specs (4-piece set)" check_tech_specs

# ═══════════════════════════════════════════════════════
# Gate 4: requirements.txt 格式校验
# ═══════════════════════════════════════════════════════
check_requirements() {
    python3 -c "
import re, sys
with open('requirements.txt') as f:
    for i, line in enumerate(f, 1):
        line = line.strip()
        if not line or line.startswith('#') or line.startswith('-'):
            continue
        if not re.match(r'^[a-zA-Z0-9_\-\[\]\.]+', line):
            print(f'Line {i}: suspicious format: {line}')
            sys.exit(1)
"
}
run_check "requirements.txt format" check_requirements

# ═══════════════════════════════════════════════════════
# Gate 5: 单元测试（pytest）
# ═══════════════════════════════════════════════════════
if command -v pytest &>/dev/null; then
    if [[ "$QUICK" == true ]]; then
        run_check "Unit tests (pytest -x --tb=short)" \
            python3 -m pytest tests/ -x --tb=short -q --no-header 2>&1
    else
        run_check "Full test suite (pytest -v)" \
            python3 -m pytest tests/ -v --tb=short 2>&1
    fi
else
    skip_check "Unit tests" "pytest not installed"
fi

# ═══════════════════════════════════════════════════════
# 以下检查在 --quick 模式下跳过
# ═══════════════════════════════════════════════════════
if [[ "$QUICK" == false ]]; then

    # Gate 6: 导入检查（确保模块可被导入）
    check_imports() {
        python3 -c "
import sys, importlib
sys.path.insert(0, '.')
errors = []
for mod in ['modules', 'modules.library', 'modules.app_api']:
    try:
        importlib.import_module(mod)
    except Exception as e:
        errors.append(f'{mod}: {e}')
if errors:
    print('\\n'.join(errors))
    sys.exit(1)
"
    }
    run_check "Module imports" check_imports

    # Gate 7: TODO/FIXME/HACK 统计（不阻塞，仅报告）
    check_todo_count() {
        local count
        count=$(grep -rn 'TODO\|FIXME\|HACK\|XXX' modules/ apps/ --include='*.py' 2>/dev/null | wc -l | tr -d ' ')
        echo "Found $count TODO/FIXME/HACK/XXX markers"
        return 0
    }
    run_check "TODO/FIXME markers (info)" check_todo_count

    # Gate 8: 大文件检查（>1MB 的 Python 文件）
    check_large_files() {
        local found=0
        while IFS= read -r f; do
            local size
            size=$(wc -c < "$f" | tr -d ' ')
            if [[ $size -gt 1048576 ]]; then
                echo "LARGE: $f ($((size / 1024))KB)"
                found=1
            fi
        done < <(find modules/ apps/ -name '*.py' 2>/dev/null)
        return $found
    }
    run_check "No oversized Python files (>1MB)" check_large_files

fi

# ═══════════════════════════════════════════════════════
# 报告
# ═══════════════════════════════════════════════════════
echo ""
echo "════════════════════════════════════════════════════"
echo "  Results"
echo "════════════════════════════════════════════════════"
for r in "${RESULTS[@]}"; do
    echo "  $r"
done
echo ""
echo "  Passed: $PASSED  Failed: $FAILED  Skipped: $SKIPPED"
echo "════════════════════════════════════════════════════"

if [[ $FAILED -gt 0 ]]; then
    echo ""
    printf "  ${RED}❌ Part A Gate: FAILED${NC}\n"
    echo ""
    exit 1
else
    echo ""
    printf "  ${GREEN}✅ Part A Gate: PASSED${NC}\n"
    echo ""
    exit 0
fi
