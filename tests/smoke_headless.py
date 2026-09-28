# -*- coding: utf-8 -*-
"""无界面冒烟测试：直接驱动 realnet_sim 的 stream_session / visit_one，
验证长连接(视频流)与短请求逻辑不崩、且确实在产生流量。
不创建任何 Tk 窗口，纯逻辑验证，便于在自动化环境里跑。
"""
import time
import threading
import logging
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import realnet_sim as R

class FakeApp:
    def __init__(self):
        # verify=False 模拟走代理 TLS 拦截环境（用户通常会勾选跳过证书校验）
        self.verify_var = type('V', (), {'get': lambda self: False})()
        # v1.2.0 起 worker 只读快照参数，不再访问 Tk 控件
        self.params = {'verify': False, 'stream_dur': 15.0,
                       'stream_prob': 1.0, 'interval': 8.0}
        self.network_down = threading.Event()
        self.conn_file = None
        self.conn_lock = threading.Lock()
        self.csv_var = type('B', (), {'get': lambda self: False})()

        class M:
            def record(self, ok):
                pass
        self.monitor = M()

    # 占位：冒烟测试不写 CSV
    def _record_conn(self, *a, **k):
        pass

    def _open_conn_log(self):
        pass

    def _page_burst(self, site_name, base_url, session):
        pass


def main():
    app = FakeApp()
    session = R.requests.Session()
    from requests.adapters import HTTPAdapter
    from requests.packages.urllib3.util.retry import Retry
    retry = Retry(total=2, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    ad = HTTPAdapter(max_retries=retry, pool_connections=8, pool_maxsize=8)
    session.mount('http://', ad)
    session.mount('https://', ad)

    R.stop_event.clear()
    deadline = time.time() + 18
    loops = 0
    while time.time() < deadline:
        try:
            R.RealNetSimApp.stream_session(app, session)   # 长连接(视频流)
        except Exception as e:
            logging.error(f"stream err: {e}")
        try:
            site = list(R.WEBSITES.keys())[loops % len(R.WEBSITES)]
            R.RealNetSimApp.visit_one(app, site, session)  # 短请求浏览
        except Exception as e:
            logging.error(f"visit err: {e}")
        loops += 1

    print("SMOKE_DONE loops=%d req=%d err=%d" % (loops, R.request_counter, R.error_counter))
    # 打印 access_log 尾部供核对
    try:
        with open('access_log.txt', 'r', encoding='utf-8') as f:
            lines = f.readlines()[-25:]
        print("---- access_log tail ----")
        for ln in lines:
            print(ln.rstrip())
    except Exception as e:
        print("read log err:", e)


if __name__ == '__main__':
    main()
