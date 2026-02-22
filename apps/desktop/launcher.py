#!/usr/bin/env python3
"""
视频制作助手 — macOS 原生 GUI 入口
使用 pywebview (WKWebView) + Flask，支持 Intel & Silicon Mac

用法:
  python app.py                              # 启动，选择/新建项目
  python app.py --project /path/to/project  # 直接打开已有项目
"""

import time
import socket
import argparse
import threading

import webview
from modules.app_api.server import create_app, set_window

# ── 端口选择（避免冲突）──────────────────────────────────────────────

def _find_free_port(start: int = 9527) -> int:
    for port in range(start, start + 100):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return start


# ── Flask 线程 ────────────────────────────────────────────────────────

def _start_flask(flask_app, port: int):
    import logging
    log = logging.getLogger("werkzeug")
    log.setLevel(logging.ERROR)   # 静音 Flask 请求日志
    flask_app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)


# ── 主入口 ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="视频制作助手 GUI")
    parser.add_argument("--project", help="直接打开的项目目录路径")
    args = parser.parse_args()

    port = _find_free_port(9527)
    flask_app = create_app(project_dir=args.project)

    # Flask 在后台线程运行
    t = threading.Thread(
        target=_start_flask, args=(flask_app, port), daemon=True
    )
    t.start()

    # 等待 Flask 就绪
    url = f"http://127.0.0.1:{port}"
    for _ in range(20):
        try:
            import urllib.request
            urllib.request.urlopen(url, timeout=1)
            break
        except Exception:
            time.sleep(0.2)

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

    # 注入 window 引用供文件对话框使用
    set_window(window)

    # macOS: 隐藏标题栏但保留交通灯按钮（需 pywebview >= 4.x）
    try:
        webview.start(
            debug=False,
            http_server=False,
        )
    except Exception:
        webview.start(debug=False)


if __name__ == "__main__":
    main()
