# -*- coding: utf-8 -*-
"""v1.2.0 无界面功能测试：用本地 http.server 驱动 visit_one / stream_session /
_page_burst，验证：无子线程 Tk 访问崩溃、DNS 检测正确、页面簇发生效、CSV 写出、无异常。
不创建任何 Tk 窗口。"""
import os
import sys
import time
import threading
import random

# 1) 本地服务器（返回 200 + 少量正文）
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = 18080
BASE = f"http://127.0.0.1:{PORT}"


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"<html><body>hello realsurf test</body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


srv = HTTPServer(("127.0.0.1", PORT), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
time.sleep(0.5)

# 2) 导入被测模块
import realnet_sim as R

# 3) 注入仅本地可达的测试站点（避免依赖外网）
R.WEBSITES["__TEST__"] = [f"{BASE}/", f"{BASE}/a", f"{BASE}/b", f"{BASE}/c"]
R.STREAM_SITES = [{'label': '视频:Local', 'host': '视频:Local', 'url': f"{BASE}/",
                   'mp4': False, 'subs': [f"{BASE}/a", f"{BASE}/b"]}]
R.domain_status["__TEST__"] = {'speed': 0, 'status': 'Idle', 'last_time': 0, 'size': 0}


class FakeApp:
    def __init__(self):
        self.params = {'verify': False, 'stream_dur': 15.0,
                       'stream_prob': 1.0, 'interval': 8.0}
        self.network_down = threading.Event()
        self.conn_lock = threading.Lock()
        self.csv_var = type('B', (), {'get': lambda self: True})()
        self.conn_file = None

        class M:
            def record(self, ok):
                pass
        self.monitor = M()


app = FakeApp()
# 把被测类的实例方法绑定到 FakeApp（避免创建 Tk UI）
app._open_conn_log = R.RealNetSimApp._open_conn_log.__get__(app)
app._record_conn = R.RealNetSimApp._record_conn.__get__(app)
app._page_burst = R.RealNetSimApp._page_burst.__get__(app)
app._open_conn_log()

session = R.requests.Session()
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
ad = HTTPAdapter(max_retries=Retry(total=1), pool_connections=8, pool_maxsize=8)
session.mount('http://', ad)
session.mount('https://', ad)

R.stop_event.clear()
errors = []


def run_visit():
    try:
        for _ in range(20):
            R.RealNetSimApp.visit_one(app, "__TEST__", session)
    except Exception as e:
        errors.append(("visit", repr(e)))


def run_stream():
    try:
        for _ in range(5):
            R.RealNetSimApp.stream_session(app, session)
    except Exception as e:
        errors.append(("stream", repr(e)))


t1 = threading.Thread(target=run_visit, daemon=True)
t2 = threading.Thread(target=run_stream, daemon=True)
t1.start()
t2.start()
t1.join(30)
t2.join(30)

# 4) 单独验证 _page_burst（成功访问后触发）
try:
    R.RealNetSimApp._page_burst(app, "__TEST__", f"{BASE}/", session)
except Exception as e:
    errors.append(("burst", repr(e)))

# 5) 验证 is_dns_error 检测
e_dns = R.requests.exceptions.ConnectionError(
    "Failed to resolve example.invalid: Name or service not known")
e_conn = R.requests.exceptions.ConnectionError("Connection refused")
dns_ok = R.is_dns_error(e_dns) is True and R.is_dns_error(e_conn) is False

# 6) 汇总
print("REQUESTS=%d ERRORS=%d" % (R.request_counter, R.error_counter))
print("DNS_DETECT_OK=%s" % dns_ok)
print("THREAD_ERRORS=%s" % (errors if errors else "none"))

# 7) CSV 检查
csv_rows = 0
try:
    with open('conn_log.csv', 'r', encoding='utf-8') as f:
        csv_rows = sum(1 for _ in f)
except Exception as e:
    print("CSV_READ_ERR", e)
print("CONN_CSV_ROWS=%d (含表头应为 >1)" % csv_rows)

if app.conn_file:
    app.conn_file.close()

ok = (R.request_counter > 0 and not errors and dns_ok and csv_rows > 1)
print("RESULT", "PASS" if ok else "FAIL")
srv.shutdown()
sys.exit(0 if ok else 1)
