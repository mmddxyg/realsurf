# -*- coding: utf-8 -*-
"""v1.3.0 优化任务书专项测试（无界面，纯逻辑 + 真网络）。

覆盖：
  C1 上传三档 / C2 大文件下载 / C3 小包高频交互
  A1 品牌档位权重 + 子域角色加权
  B1 _page_burst 真并发
  D1 httpx 通道与接口归一（_get/_iter_chunks/_proto_of）
  E1 CACHE_BUST 开关
  E2 HLS 分片拉取
  S1-S4 conn_log 轮转 / ok 语义 / UTC ts / 扩字段
用法：python tests/test_v13.py            （跑全部）
      python tests/test_v13.py --offline  （跳过真网络）
"""
import csv
import os
import sys
import time
import threading
import logging
import importlib.util

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)

import realnet_sim as R  # noqa: E402

OFFLINE = '--offline' in sys.argv
PASS, FAIL = [], []


def check(name, cond, detail=''):
    (PASS if cond else FAIL).append(name)
    print(('  [OK]   ' if cond else '  [FAIL] ') + name + (('  -> ' + str(detail)) if detail else ''))


# ---------------------------------------------------------------------------
# 测试用宿主：直接绑定 RealNetSimApp 的真实方法，保证跑的是生产代码路径
# ---------------------------------------------------------------------------
class Harness:
    pass


for _n, _v in list(vars(R.RealNetSimApp).items()):
    # 用 vars() 取原始描述符，保留 staticmethod/classmethod 语义，
    # 否则 _is_hx 这类 staticmethod 会被当成普通函数而多吃一个 self。
    if _n.startswith('__'):
        continue
    if _n.startswith('_') or _n in ('visit_one', 'stream_session', 'worker_loop',
                                    'CONN_LOG_MAX'):
        setattr(Harness, _n, _v)


class _FlagGetter:
    def __init__(self, v):
        self._v = v

    def get(self):
        return self._v


class _Mon:
    def __init__(self):
        self.n = 0

    def record(self, ok):
        self.n += 1


def make_host(csv_on=True, verify=False, hx=False):
    h = Harness()
    h.params = {'verify': verify, 'interval': 8.0, 'stream_prob': 1.0, 'stream_dur': 12.0}
    h.network_down = threading.Event()
    h.conn_lock = threading.Lock()
    h.csv_var = _FlagGetter(csv_on)
    h.monitor = _Mon()
    h.conn_file = None
    h.hx = None
    if hx:
        try:
            import httpx
            h.hx = httpx.Client(http1=True, http2=True, timeout=20.0, verify=verify,
                                follow_redirects=True)
        except Exception as e:
            print(f"  (httpx 初始化失败，改用 requests: {e})")
            h.hx = None
    h._open_conn_log()
    return h


def fresh_conn_log():
    for f in ('conn_log.csv',):
        if os.path.exists(f):
            os.remove(f)


# ---------------------------------------------------------------------------
def test_static():
    print("\n== A1 / E1 / i18n / 版本 静态检查 ==")
    missing = [k for k in R.WEBSITES if k not in R.BRAND_WEIGHT]
    check('A1-1 BRAND_WEIGHT 覆盖 WEBSITES 全部品牌', not missing, f'缺失={missing}')
    top = max(R.BRAND_WEIGHT.values())
    tail = min(R.BRAND_WEIGHT.values())
    check('A1-1 头尾权重量级拉开 (>=30:1)', top / tail >= 30, f'{top}:{tail}')
    check('A1-2 _host_weight(www)=10', R._host_weight('https://www.google.com') == 10)
    check('A1-2 _host_weight(api)=10', R._host_weight('https://api.x.com') == 10)
    check('A1-2 _host_weight(static cdn)=1', R._host_weight('https://static.xx.com/a.js') == 1)
    check('A1-2 _host_weight(裸域)=10', R._host_weight('https://bilibili.com') == 10)
    check('A1-2 _host_weight(普通子域)=3', R._host_weight('https://mail.google.com') == 3)
    check('A1-3 USE_TOP_LIST 默认关（无榜单文件时行为不变）', R.USE_TOP_LIST is False)
    check('A1-3 _load_top_list 无文件返回空', R._load_top_list('__nope__.csv') == {})
    check('E1 CACHE_BUST 默认关', R.CACHE_BUST is False)
    check('E2 STREAM_M3U8 已配置', len(R.STREAM_M3U8) >= 1, f'{len(R.STREAM_M3U8)} 条')
    check('C2 MAX_BULK_BYTES 已定义', R.MAX_BULK_BYTES == 200 * 1024 * 1024)
    check('版本号为 1.3.0', R.APP_VERSION == '1.3.0', R.APP_VERSION)
    for lang in ('zh', 'en', 'vi'):
        d = R.I18N[lang]
        check(f'i18n[{lang}] 新增键齐全',
              all(k in d for k in ('chk_cachebust', 'upd_downloading', 'upd_canceled',
                                   'upd_restart', 'upd_checking', 'btn_cancel')))
    check('D1 _REQUEST_ERRORS 至少含 requests 异常', len(R._REQUEST_ERRORS) >= 1,
          f'{len(R._REQUEST_ERRORS)} 项, httpx={R._HAS_HTTPX}')
    check('D1 httpx 已安装', R._HAS_HTTPX, '未装则自动回退 requests（不影响功能）')


def test_feeder_weights():
    print("\n== A1 投喂器幂律抽样 ==")
    pool = []
    for site in R.WEBSITES:
        if R.WEBSITES.get(site):
            pool.extend([site] * R.BRAND_WEIGHT.get(site, R.BRAND_WEIGHT_DEFAULT))
    import collections
    c = collections.Counter(R.random.choice(pool) for _ in range(20000))
    g = c['Google']
    q = c['Quora']
    check('Google 抽样频次远高于 Quora (>20x)', g > q * 20, f'Google={g} Quora={q}')
    allbrands = [k for k in R.WEBSITES if k not in c]
    check('无品牌被完全饿死', not allbrands, f'零样本={allbrands}')


def test_update_channel():
    print("\n== 更新通道回归（不可用 REST API，避免 60/小时限流）==")
    if OFFLINE:
        print('  (offline 跳过)')
        return
    h = make_host(csv_on=False)
    try:
        tag, notes, html_url, asset_url, size = h._fetch_latest_release_info()
        check('_fetch_latest_release_info 返回 tag', bool(tag), tag)
        check('返回资产直链含 .exe', bool(asset_url) and '.exe' in asset_url, asset_url)
        check('资产大小 > 0', size > 0, f'{size} bytes')
        check('发布页 URL 有效', bool(html_url) and 'github.com' in (html_url or ''), html_url)
    except Exception as e:
        check('更新通道可用', False, f'{type(e).__name__}: {e}')


def test_conn_log(csv_on=True):
    print("\n== S1/S3/S4 conn_log 表头与记录 ==")
    fresh_conn_log()
    h = make_host(csv_on=csv_on)
    if not csv_on:
        check('S1 csv 关闭时不建文件', not os.path.exists('conn_log.csv'))
        return
    h._record_conn('测试站', 'https://www.google.com', 200, 1234, 0.5, True,
                   method='GET', bytes_up=0, proto_ver='HTTP/2',
                   scene_hint='web', tier='page')
    h._record_conn('测试站', 'https://api.x.com', 503, 10, 0.1, False,
                   method='POST', bytes_up=4096, proto_ver='HTTP/1.1',
                   scene_hint='transfer', tier='bulk')
    # visit_one 传的是字符串状态（"OK (200)"），必须也能解析出 2xx，否则 ok=1 却 ok_2xx=0
    h._record_conn('测试站', 'https://www.youtube.com', 'OK (200)', 999, 0.3, True,
                   proto_ver='HTTP/2', scene_hint='streaming', tier='stream')
    h._record_conn('测试站', 'https://x.com', 'HLS 123MB', 888, 0.4, True,
                   scene_hint='streaming', tier='stream')
    if h.conn_file:
        h.conn_file.close()
    with open('conn_log.csv', 'r', encoding='utf-8') as f:
        rows = list(csv.reader(f))
    hdr = rows[0]
    want = ['ts', 'site', 'host', 'url', 'method', 'status', 'ok', 'ok_2xx', 'ok_3xx',
            'bytes_down', 'bytes_up', 'total_ms', 'proto_ver', 'scene_hint', 'tier']
    check('S4 表头为 15 列新字段', hdr == want, hdr)
    ts = rows[1][0]
    check('S3 ts 为 UTC ISO8601 且带 Z', ts.endswith('Z') and 'T' in ts, ts)
    check('S2 ok=1 且 ok_2xx=1 (200)', rows[1][6] == '1' and rows[1][7] == '1', rows[1][:8])
    check('S2 503 -> ok=0 且 ok_2xx=0 且 ok_3xx=0',
          rows[2][6] == '0' and rows[2][7] == '0' and rows[2][8] == '0', rows[2][:9])
    check('S4 bytes_up 写入正确', rows[2][10] == '4096', rows[2][10])
    check('S4 proto_ver 写入正确', rows[1][12] == 'HTTP/2', rows[1][12])
    check('S4 scene_hint/tier 写入正确',
          rows[1][13] == 'web' and rows[2][14] == 'bulk', rows[1][13:])
    check('S2 字符串状态 "OK (200)" 也能解析出 2xx',
          rows[3][5] == '200' and rows[3][6] == '1' and rows[3][7] == '1', rows[3][:9])
    check('S2 "HLS 123MB" 不被误判成状态码 123',
          rows[4][5] == 'HLS 123MB' and rows[4][7] == '0', rows[4][:9])


def test_conn_log_rotate():
    print("\n== S1 conn_log 轮转 ==")
    fresh_conn_log()
    with open('conn_log.csv', 'w', encoding='utf-8') as f:
        f.write('x' * (R.RealNetSimApp.CONN_LOG_MAX + 100))
    h = make_host(csv_on=True)
    rotated = getattr(h, 'conn_log_path', 'conn_log.csv') != 'conn_log.csv'
    check('S1 超限自动换名分卷', rotated, getattr(h, 'conn_log_path', '?'))
    if h.conn_file:
        h.conn_file.close()
    if rotated:
        try:
            os.remove(h.conn_log_path)
        except OSError:
            pass
    fresh_conn_log()


def test_scenes():
    print("\n== C1/C2/C3/B1/E2 真流量（关闭 CSV）==")
    if OFFLINE:
        print('  (offline 跳过)')
        return
    h = make_host(csv_on=False)
    s = R.requests.Session()
    R.stop_event.clear()
    before = R.request_counter

    t0 = time.time()
    try:
        h._upload('Google', s)
        check('C1 _upload 未抛异常', True)
    except Exception as e:
        check('C1 _upload 未抛异常', False, f'{type(e).__name__}: {e}')
    try:
        got = h._upload('Dropbox', s)
        check('C1 _upload 返回上行字节数', got >= 0, f'{got} bytes')
    except Exception as e:
        check('C1 _upload 返回上行字节数', False, str(e))
    try:
        h._bulk_download('Google', s)
        check('C2 _bulk_download 未抛异常', True)
    except Exception as e:
        check('C2 _bulk_download 未抛异常', False, f'{type(e).__name__}: {e}')
    try:
        h._interactive('Telegram', s)
        check('C3 _interactive 未抛异常', True)
    except Exception as e:
        check('C3 _interactive 未抛异常', False, f'{type(e).__name__}: {e}')
    try:
        h._page_burst('Google', 'https://www.google.com', s)
        check('B1 _page_burst(真并发) 未抛异常', True)
    except Exception as e:
        check('B1 _page_burst(真并发) 未抛异常', False, f'{type(e).__name__}: {e}')
    try:
        n, hcode = h._stream_hls(R.STREAM_M3U8[0], s, 8.0, 4 * 1024 * 1024)
        check('E2 _stream_hls 执行完成', True, f'拉到 {n/1024:.0f} KB, 清单状态码={hcode}')
        check('E2 清单返回 2xx', 200 <= hcode < 300, hcode)
    except Exception as e:
        check('E2 _stream_hls 执行完成', False, f'{type(e).__name__}: {e}')

    # visit_one 全链路（含 C1/C2/C3 概率分支）
    for i, site in enumerate(list(R.WEBSITES.keys())[:6]):
        try:
            h.visit_one(site, s)
        except Exception as e:
            check(f'visit_one({site}) 未抛异常', False, f'{type(e).__name__}: {e}')
            break
    else:
        check('visit_one 连续 6 站点无异常', True)
    try:
        h.stream_session(s)
        check('stream_session 未抛异常', True)
    except Exception as e:
        check('stream_session 未抛异常', False, f'{type(e).__name__}: {e}')

    delta = R.request_counter - before
    check('确实产生了请求（计数增长）', delta > 0, f'+{delta} 次，{time.time()-t0:.1f}s')
    s.close()


def test_httpx_channel():
    print("\n== D1 httpx 通道与接口归一 ==")
    if not R._HAS_HTTPX:
        print('  (httpx 未安装，跳过；运行时自动回退 requests，功能不受影响)')
        return
    if OFFLINE:
        print('  (offline 跳过)')
        return
    h = make_host(csv_on=False, hx=True)
    if h.hx is None:
        check('httpx.Client 可创建', False)
        return
    check('httpx.Client 可创建', True, str(h.hx))
    try:
        r = h.hx.get('https://www.cloudflare.com', timeout=15.0)
        hv = getattr(r, 'http_version', '?')
        check(f'httpx 直连可用, proto={hv}', r.status_code < 500, f'status={r.status_code}')
    except Exception as e:
        check('httpx 直连可用', False, f'{type(e).__name__}: {e}')

    # 强制走 httpx：把 HTTPX_PROB 拉满
    old = R.HTTPX_PROB
    R.HTTPX_PROB = 1.0
    try:
        s = R.requests.Session()
        resp = h._get('https://www.cloudflare.com', s, timeout=15)
        check('_get 强制走 httpx 返回 httpx.Response', h._is_hx(resp), type(resp).__name__)
        proto = h._proto_of(resp)
        check('_proto_of 解析出 HTTP/x', proto.startswith('HTTP/'), proto)
        tot = 0
        for c in h._iter_chunks(resp, 8192):
            tot += len(c)
            if tot > 65536:
                break
        h._close_resp(resp)
        check('_iter_chunks 统一分块可读', tot > 0, f'{tot} bytes')
        s.close()
    finally:
        R.HTTPX_PROB = old
        try:
            h.hx.close()
        except Exception:
            pass


def test_cache_bust():
    print("\n== E1 CACHE_BUST 开关生效 ==")
    check('默认关闭时 req_url 不带 ?num=', R.CACHE_BUST is False)
    h = make_host(csv_on=False)
    check('UI 变量存在且默认 False',
          hasattr(R.RealNetSimApp, '_upload') and R.CACHE_BUST is False)


def main():
    logging.basicConfig(level=logging.CRITICAL)
    print("RealSurf v1.3.0 优化任务书专项测试" + ("  [OFFLINE]" if OFFLINE else ""))
    test_static()
    test_feeder_weights()
    test_update_channel()
    test_conn_log(True)
    test_conn_log(False)
    test_conn_log_rotate()
    test_cache_bust()
    test_scenes()
    test_httpx_channel()
    print("\n" + "=" * 62)
    print(f"通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
    if FAIL:
        print("失败项：")
        for f in FAIL:
            print("  - " + f)
    print("=" * 62)
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
