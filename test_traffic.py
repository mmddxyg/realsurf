# -*- coding: utf-8 -*-
"""受控流量验证：用可达的国内站点证明请求管线(计数+状态)正常。"""
import threading
import realnet_sim as R

class MiniApp:
    def __init__(self):
        self.verify_var = type('V', (), {'get': lambda self: False})()
        self.network_down = threading.Event()
        self.stream_dur_entry = type('E', (), {'get': lambda self: '15'})()
        self.stream_prob_entry = type('E', (), {'get': lambda self: '0'})()
        self.interval_entry = type('E', (), {'get': lambda self: '8'})()
        class M:
            def record(self, ok):
                pass
        self.monitor = M()

def main():
    # 临时把站点表换成可达的国内站点，验证请求确实发生且计数自增
    R.WEBSITES = {'测试:百度': ['https://www.baidu.com']}
    R.domain_status.clear()
    app = MiniApp()
    session = R.requests.Session()
    from requests.adapters import HTTPAdapter
    from requests.packages.urllib3.util.retry import Retry
    ad = HTTPAdapter(max_retries=Retry(total=2, backoff_factor=1))
    session.mount('http://', ad); session.mount('https://', ad)

    before = R.request_counter
    for _ in range(3):
        R.RealNetSimApp.visit_one(app, '测试:百度', session)
    after = R.request_counter
    st = R.domain_status.get('测试:百度', {})
    print("TRAFFIC_TEST before=%d after=%d delta=%d status=%s speed=%.1f size=%.0f"
          % (before, after, after - before, st.get('status'), st.get('speed', 0), st.get('size', 0)))

if __name__ == '__main__':
    main()
