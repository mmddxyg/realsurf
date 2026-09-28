# -*- coding: utf-8 -*-
"""无头验证更新下载组件：用本地 http.server 模拟 GitHub asset 下载，
直接驱动真实 _download_worker，确认：带进度回调、完成后写出重启 bat、不崩。
全程用纯对象桩代替 Tk 控件，避免需要显示器。
"""
import os
import sys
import time
import threading
import tempfile
import functools
import http.server
import socketserver

import realnet_sim as R


def main():
    # 准备一个本地待下载文件（约 5MB）
    data = os.urandom(5 * 1024 * 1024)
    serve_dir = tempfile.mkdtemp()
    fpath = os.path.join(serve_dir, "realsurf.exe")
    with open(fpath, "wb") as f:
        f.write(data)

    Handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=serve_dir)
    httpd = socketserver.TCPServer(("127.0.0.1", 0), Handler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{port}/realsurf.exe"

    # ---- 桩：root.after 立即同步执行回调（桩是纯对象，线程安全无所谓） ----
    class FakeRoot:
        def after(self, ms, fn):
            try:
                fn()
            except Exception as e:  # 回调异常应暴露，不应静默
                print("after-cb-error:", e)
                raise

        def destroy(self):
            pass

    class Stub:
        def configure(self, **k):
            pass

        def stop(self):
            pass

    class FakeApp:
        def __init__(self):
            self.root = FakeRoot()
            self.network_down = threading.Event()
            self.last_pct = -1
            self.finished = False
            self.canceled = False
            self.failed = False
            self.bat_content = ""

        # 覆盖掉会 sys.exit 的收尾，仅记录结果
        def _init_bar(self, bar, total):
            self.total = total

        def _upd_progress(self, bar, pct, v, t, el=0.0):
            if t > 0:
                self.last_pct = v * 100 // t

        def _stop_bar(self, bar):
            pass

        def _set_restart_label(self, lbl):
            self.restart_set = True

        def _cancel_update_ui(self, dlg):
            self.canceled = True

        def _update_fail_ui(self, dlg, detail=''):
            self.failed = True

        def _finish_update(self, dlg, bat):
            self.finished = True
            self.bat = bat
            with open(bat, "r", encoding="utf-8") as f:
                self.bat_content = f.read()

    app = FakeApp()
    bar, pct, lbl = Stub(), Stub(), Stub()
    cancel = threading.Event()

    # 真实下载逻辑（后台线程），用 FakeApp 充当 self
    w = threading.Thread(target=R.RealNetSimApp._download_worker,
                         args=(app, url, "9.9.9", None, bar, pct, lbl, cancel),
                         daemon=True)
    w.start()
    w.join(timeout=30)

    ok = (
        app.finished
        and app.last_pct == 100
        and getattr(app, "restart_set", False)
        and "copy /Y" in app.bat_content
        and "taskkill /f /im" in app.bat_content
        and "start \"\"" in app.bat_content
        and not app.failed
        and not app.canceled
    )
    print("FINISHED=%s LAST_PCT=%s TOTAL=%s FAILED=%s CANCELED=%s"
          % (app.finished, app.last_pct, getattr(app, "total", None), app.failed, app.canceled))
    print("UPDATE_DOWNLOAD_TEST", "PASS" if ok else "FAIL")
    httpd.shutdown()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
