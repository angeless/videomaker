#!/bin/bash
# 无头模式启动 Flask 后端（不启动 pywebview）
export VIDEOEDITOR_REQUIRE_LOCAL_TOKEN=0
cd "$(dirname "$0")/../project"
exec python3 -c "
import sys, os
sys.path.insert(0, '.')
from modules.app_api.server import create_app
app = create_app()
app.run(host='127.0.0.1', port=9527, debug=False, use_reloader=False)
"
