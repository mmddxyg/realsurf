# -*- coding: utf-8 -*-
"""端到端 GUI 测试：假 GitHub API 报告新版本 + 限速本地 asset 服务，
走真实 check_update(manual=True) 路径，自动点「是」，截图验证进度条对话框真的出现。
只在有桌面会话的机器上跑（本机 = 用户 Windows 桌面）。
"""
import os
import json
import time
import threading
import tempfile
import functools
import http.server
import socketserver

import tkinter as tk
import ttkbootstrap as ttkb
from PIL import ImageGrab

import realnet_sim as R

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
SHOT = os.path.join(ROOT_DIR, "gui_update_shot.png")

# ---- 1) 待下载文件（30MB）+ 限速 HTTP 服务（便于截到中间进度） ----
serve = tempfile.mkdtemp()
with open(os.path.join(serve, "realsurf.exe"), "wb") as f:
    for _ in range(30):
        f.write(os.urandom(1024 * 1024))


class SlowHandler(http.server.SimpleHTTPRequestHandler):
    def copyfile(self, source, out):
        while True:
            buf = source.read(64 * 1024)
            if not buf:
                break
            out.write(buf)
            out.flush()
            time.sleep(0.05)          # ~1.25 MB/s

    def log_message(self, *a):
        pass


asset_srv = socketserver.TCPServer(
    ("127.0.0.1", 0), functools.partial(SlowHandler, directory=serve))
asset_port = asset_srv.server_address[1]
threading.Thread(target=asset_srv.serve_forever, daemon=True).start()
asset_url = f"http://127.0.0.1:{asset_port}/realsurf.exe"

# ---- 2) 假 GitHub API：返回「有 v9.9.9」 ----
RELEASE = {
    "tag_name": "v9.9.9",
    "body": "fake release for GUI test",
    "html_url": "http://example.invalid",
    "assets": [{"name": "realsurf.exe", "browser_download_url": asset_url,
                "size": 30 * 1024 * 1024}],
}


class ApiHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps(RELEASE).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


api_srv = socketserver.TCPServer(("127.0.0.1", 0), ApiHandler)
R.GITHUB_API = f"http://127.0.0.1:{api_srv.server_address[1]}"
threading.Thread(target=api_srv.serve_forever, daemon=True).start()

# ---- 3) 自动点「是」 ----
R.messagebox.askyesno = lambda *a, **k: True

root = ttkb.Window(themename="litera")
root.geometry("420x110")
root.title("RealSurf GUI update test")


class TestApp(R.RealNetSimApp):
    def __init__(self):
        self.root = root
        self.about_window = None
        self.update_status_var = tk.StringVar()
        self.update_status_label = None
        self.finished = False
        self.failed = False

    def _finish_update(self, dlg, bat):
        self.finished = True
        print("FINISH_DOWNLOAD (would restart)")

    def _update_fail_ui(self, dlg, detail=''):
        self.failed = True
        print("FAIL_UI", detail)


app = TestApp()


def shot():
    try:
        ImageGrab.grab().save(SHOT)
        print("SHOT:", SHOT)
    except Exception as e:
        print("shot err:", e)
    root.destroy()


root.after(300, lambda: app.check_update(manual=True))
root.after(2500, shot)
root.after(15000, lambda: (print("TIMEOUT"), root.destroy()))
root.mainloop()
print("DONE finished=%s failed=%s" % (app.finished, app.failed))
