#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

PY_BIN="${PYTHON3_BIN:-python3}"
if ! command -v "$PY_BIN" >/dev/null 2>&1; then
  osascript -e 'display alert "启动失败" message "未检测到 python3，请先安装 Python 3.10+。" as critical'
  exit 1
fi

if [ ! -d ".venv" ]; then
  "$PY_BIN" -m venv .venv
fi

source .venv/bin/activate
python -m pip install --upgrade pip >/dev/null 2>&1 || true
python apps/desktop/launcher.py
