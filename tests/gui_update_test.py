# -*- coding: utf-8 -*-
"""端到端 GUI 测试：走真实 check_update(manual=True) → 进度条对话框 → 截图验证。
用本地限速 asset 服务模拟 30MB 下载，并 patch _fetch_latest_release_info 返回「有 v9.9.9」。
只在有桌面会话的机器上跑（本机 = 用户 Windows 桌面）。
"""
import os
import time
import threading
import tempfile
import functools
import http.server
import socketserver

import tkinter as tk
import ttkbootstrap as ttkb
from PIL import ImageGrab

import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import realnet_sim as R

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
SHOT = os.path.join(ROOT_DIR, "gui_update_shot.png")

# ---- 待下载文件（30MB）+ 限速 HTTP 服务（便于截到中间进度） ----
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

# 让本地版本「低于」远端，触发更新流程
R.APP_VERSION = "1.0.0"

# ---- 自动点「是」 ----
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
        self._cb_error_shown = False

    # 直接给出「有更新」，跳过网络检查（检查逻辑已单独实测）
    def _fetch_latest_release_info(self):
        return ("v9.9.9", "fake notes", "http://example.invalid",
                asset_url, 30 * 1024 * 1024)

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
