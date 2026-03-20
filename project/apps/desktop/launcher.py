#!/usr/bin/env python3
"""
视频制作助手 — macOS 原生 GUI 入口
使用 pywebview (WKWebView) + Flask，支持 Intel & Silicon Mac

用法:
  python apps/desktop/launcher.py                              # 启动，选择/新建项目
  python apps/desktop/launcher.py --project /path/to/project  # 直接打开已有项目
"""

import argparse
import importlib.util
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _module_available(module_name: str) -> bool:
    try:
        return importlib.util.find_spec(module_name) is not None
    except Exception:
        return False


def _ensure_runtime_dependencies(auto_install: bool = True):
    required = [
        ("flask", "Flask"),
        ("webview", "pywebview"),
    ]
    missing = [pkg for module_name, pkg in required if not _module_available(module_name)]
    if not missing:
        return

    if not auto_install:
        miss = ", ".join(missing)
        raise RuntimeError(f"缺少依赖: {miss}。请先安装 requirements.txt")

    req = REPO_ROOT / "requirements.txt"
    if not req.exists():
        raise RuntimeError(f"缺少依赖清单文件: {req}")

    print(f"[launcher] 检测到缺少依赖: {', '.join(missing)}，正在自动安装...")
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "-r", str(req)],
            cwd=str(REPO_ROOT),
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"自动安装依赖失败（exit={exc.returncode}），请检查网络或 Python 环境后重试"
        ) from exc

    still_missing = [pkg for module_name, pkg in required if not _module_available(module_name)]
    if still_missing:
        raise RuntimeError(f"依赖安装后仍缺失: {', '.join(still_missing)}")

# ── 端口选择（避免冲突）──────────────────────────────────────────────

def _find_free_port(start: int = 9527) -> int:
    for port in range(start, start + 100):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return start


# ── Flask 线程 ────────────────────────────────────────────────────────

def _start_flask(flask_app, port: int, debug: bool = False):
    import logging
    log = logging.getLogger("werkzeug")
    if not debug:
        log.setLevel(logging.ERROR)   # 静音 Flask 请求日志
    flask_app.run(host="127.0.0.1", port=port, debug=debug, use_reloader=False)


# ── 主入口 ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="视频制作助手 GUI")
    parser.add_argument("--project", help="直接打开的项目目录路径")
    parser.add_argument(
        "--skip-bootstrap",
        action="store_true",
        help="跳过依赖自动检测与安装（调试模式）",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="启用 Flask 与 pywebview 调试模式（显示开发者工具）",
    )
    args = parser.parse_args()

    _ensure_runtime_dependencies(auto_install=not bool(args.skip_bootstrap))

    from modules.app_api.services.startup_timing import mark  # noqa: WPS433
    mark("launcher_start")

    from modules.app_api.services.logging_service import init_logging  # noqa: WPS433
    log_dir = init_logging()
    print(f"[launcher] log file: {log_dir / 'videoeditor.log'}")

    mark("deps_checked")

    # 桌面运行默认开启本地 API token 防护；测试/CLI 可用环境变量覆盖。
    os.environ.setdefault("VIDEOEDITOR_REQUIRE_LOCAL_TOKEN", "1")

    import webview  # noqa: WPS433
    from modules.app_api.server import create_app, set_window  # noqa: WPS433

    debug_mode = bool(args.debug)

    port = _find_free_port(9527)
    flask_app = create_app(project_dir=args.project)
    mark("flask_app_created")

    # Flask 在后台线程运行
    t = threading.Thread(
        target=_start_flask, args=(flask_app, port, debug_mode), daemon=True
    )
    t.start()
    mark("flask_thread_started")

    # 等待 Flask 就绪
    url = f"http://127.0.0.1:{port}"
    print(f"[launcher] serving UI at {url}")
    for _ in range(20):
        try:
            import urllib.request
            urllib.request.urlopen(url, timeout=1)
            break
        except Exception:
            time.sleep(0.2)
    mark("flask_ready")

    # 创建 pywebview 窗口
    window = webview.create_window(
        title="视频制作助手",
        url=url,
        width=1280,
        height=820,
        min_size=(960, 640),
        resizable=True,
        background_color="#0f0f0f",
    )

    mark("ui_window_created")

    # 注入 window 引用供文件对话框使用
    set_window(window)

    # macOS: 隐藏标题栏但保留交通灯按钮（需 pywebview >= 4.x）
    try:
        webview.start(
            debug=debug_mode,
            http_server=False,
        )
    except Exception:
        webview.start(debug=debug_mode)


if __name__ == "__main__":
    main()
