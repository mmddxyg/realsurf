# -*- coding: utf-8 -*-
"""v1.3.x 专项测试（无界面，纯逻辑 + 真网络）。

覆盖：
  C1 上传三档 / C2 大文件下载 / C3 小包高频交互
  A1 品牌档位权重 + 子域角色加权
  B1 _page_burst 真并发
  D1 httpx 通道与接口归一（_get/_iter_chunks/_close_resp）
  E1 CACHE_BUST 开关
  E2 HLS 分片拉取
  R1 无 CSV 残留（v1.3.1 起「记录连接明细(CSV)」功能整体下线）
用法：python tests/test_v13.py            （跑全部）
      python tests/test_v13.py --offline  （跳过真网络）
"""
import os
import re
import sys
import time
import threading
import logging

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)

import realnet_sim as R  # noqa: E402

OFFLINE = '--offline' in sys.argv
PASS, FAIL = [], []

# R1：这些标识符在源码里必须彻底消失（top1m.csv 属 A1-3 榜单，白名单）
RESIDUE_PAT = re.compile(
    r'csv|conn_log|csv_var|csv_check|chk_csv|_record_conn|_open_conn_log'
    r'|_proto_of|_status_code|conn_lock|conn_file')
RESIDUE_ALLOW = ('top1m.csv',)


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
    if _n.startswith('_') or _n in ('visit_one', 'stream_session', 'worker_loop'):
        setattr(Harness, _n, _v)


class _Mon:
    def __init__(self):
        self.n = 0

    def record(self, ok):
        self.n += 1


def make_host(verify=False, hx=False):
    h = Harness()
    h.params = {'verify': verify, 'interval': 8.0, 'stream_prob': 1.0, 'stream_dur': 12.0}
    h.network_down = threading.Event()
    h.monitor = _Mon()
    h.hx = None
    if hx:
        try:
            import httpx
            h.hx = httpx.Client(http1=True, http2=True, timeout=20.0, verify=verify,
                                follow_redirects=True)
        except Exception as e:
            print(f"  (httpx 初始化失败，改用 requests: {e})")
            h.hx = None
    return h


# ---------------------------------------------------------------------------
def test_residue():
    print("\n== R1 CSV 功能下线残留检查（必须 0 命中）==")
    src_path = os.path.join(_ROOT, 'realnet_sim.py')
    with open(src_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    hits = []
    for i, ln in enumerate(lines, 1):
        if RESIDUE_PAT.search(ln) and not any(a in ln for a in RESIDUE_ALLOW):
            hits.append(f'{i}: {ln.rstrip()}')
    check('R1 源码无 CSV/conn_log 残留', not hits, ' | '.join(hits[:5]))
    for name in ('_record_conn', '_open_conn_log', '_proto_of', '_status_code',
                 'CONN_LOG_MAX'):
        check(f'R1 类属性 {name} 已删除', not hasattr(R.RealNetSimApp, name))
    check('R1 模块不再导入 csv', not hasattr(R, 'csv'))
    check('R1 模块不再导入 datetime', not hasattr(R, 'datetime'))
    for lang in ('zh', 'en', 'vi'):
        check(f'R1 i18n[{lang}] 已移除 chk_csv', 'chk_csv' not in R.I18N[lang])


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
    check('版本号为 1.3.2', R.APP_VERSION == '1.3.2', R.APP_VERSION)
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
    h = make_host()
    try:
        tag, notes, html_url, asset_url, size = h._fetch_latest_release_info()
        check('_fetch_latest_release_info 返回 tag', bool(tag), tag)
        check('返回资产直链含 .exe', bool(asset_url) and '.exe' in asset_url, asset_url)
        check('资产大小 > 0', size > 0, f'{size} bytes')
        check('发布页 URL 有效', bool(html_url) and 'github.com' in (html_url or ''), html_url)
    except Exception as e:
        check('更新通道可用', False, f'{type(e).__name__}: {e}')


def test_scenes():
    print("\n== C1/C2/C3/B1/E2 真流量 ==")
    if OFFLINE:
        print('  (offline 跳过)')
        return
    h = make_host()
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


def test_no_conn_log_file():
    print("\n== R1 实跑后不得生成 conn_log.csv ==")
    if OFFLINE:
        print('  (offline 跳过)')
        return
    h = make_host()
    s = R.requests.Session()
    R.stop_event.clear()
    for site in list(R.WEBSITES.keys())[:8]:
        try:
            h.visit_one(site, s)
        except Exception:
            pass
    try:
        h.stream_session(s)
    except Exception:
        pass
    s.close()
    leftovers = [f for f in os.listdir(_ROOT) if f.startswith('conn_log')]
    check('R1 目录内无 conn_log*.csv', not leftovers, leftovers)


def test_httpx_channel():
    print("\n== D1 httpx 通道与接口归一 ==")
    if not R._HAS_HTTPX:
        print('  (httpx 未安装，跳过；运行时自动回退 requests，功能不受影响)')
        return
    if OFFLINE:
        print('  (offline 跳过)')
        return
    h = make_host(hx=True)
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
        proto = str(getattr(resp, 'http_version', '?'))   # httpx 已返回 "HTTP/2" 形式
        check('httpx.Response.http_version 可用', 'HTTP/' in proto, proto)
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
    check('UI 变量存在且默认 False',
          hasattr(R.RealNetSimApp, '_upload') and R.CACHE_BUST is False)


def test_site_stats():
    print("\n== M1 站点真实访问统计（图表指标不再是网速）==")
    blank = R._blank_site_stat()
    check('统计单元字段齐全',
          set(blank) == {'visits', 'ok', 'ms', 'size', 'speed', 'status', 'last_time'}, sorted(blank))
    site = '__M1_test__'
    R.domain_status.pop(site, None)
    R.bump_site_stat(site, True, 0.40, 2048, 'OK (200)')
    R.bump_site_stat(site, False, 1.60, 0, 'Timeout')
    st = R.domain_status[site]
    check('visits 累加到 2', st['visits'] == 2, st['visits'])
    check('ok 只计成功那次', st['ok'] == 1, st['ok'])
    check('ms 累加 400+1600=2000', abs(st['ms'] - 2000.0) < 0.01, st['ms'])
    check('size 累加 2048', st['size'] == 2048, st['size'])
    check('平均耗时可算出 1000ms', abs(st['ms'] / st['visits'] - 1000.0) < 0.01)
    check('status 记录最后一次', st['status'] == 'Timeout', st['status'])
    c = R.RealNetSimApp._chart_color
    check('配色：全成功=绿', c({'visits': 3, 'ok': 3}) == '#2e7d32')
    check('配色：部分失败=橙', c({'visits': 3, 'ok': 1}) == '#ef6c00')
    check('配色：全失败=红', c({'visits': 3, 'ok': 0}) == '#c62828')
    check('配色：未访问=灰', c({'visits': 0, 'ok': 0}) == '#9e9e9e')
    check('CHART_MAX_SITES 已定义且合理', 5 <= R.CHART_MAX_SITES <= 60, R.CHART_MAX_SITES)
    R.domain_status.pop(site, None)
    for lang in ('zh', 'en', 'vi'):
        d = R.I18N[lang]
        check(f'i18n[{lang}] 图表新键齐全',
              all(k in d for k in ('chart_title', 'chart_title_idle', 'chart_ylabel',
                                   'leg_ok', 'leg_part', 'leg_fail')))
        check(f'i18n[{lang}] 图表文案已去网速',
              'KB/s' not in d['chart_title'] and 'KB/s' not in d['chart_ylabel']
              and 'kb/s' not in d['chart_title'].lower(),
              f"{d['chart_title']} / {d['chart_ylabel']}")


def test_domains():
    print("\n== M3 域名池 ==")
    check('站点数 >= 60', len(R.WEBSITES) >= 60, f'{len(R.WEBSITES)} 个品牌')
    total = sum(len(v) for v in R.WEBSITES.values())
    check('域名总数 >= 300', total >= 300, f'{total} 条')
    dup = {s: [d for d in set(v) if v.count(d) > 1] for s, v in R.WEBSITES.items()
           if len(set(v)) != len(v)}
    check('无同站重复域名', not dup, dup)
    bad = [(s, d) for s, v in R.WEBSITES.items() for d in v
           if not d.startswith('https://')]
    check('全部为 https:// 开头', not bad, bad[:3])
    check('每个品牌至少 2 个域名', all(len(v) >= 2 for v in R.WEBSITES.values()),
          [s for s, v in R.WEBSITES.items() if len(v) < 2])
    check('BRAND_WEIGHT 覆盖全部品牌（含新增）',
          not [s for s in R.WEBSITES if s not in R.BRAND_WEIGHT],
          [s for s in R.WEBSITES if s not in R.BRAND_WEIGHT])
    # 新增品牌抽样实测：每个都要至少被抽到一次，否则等于没加
    import collections
    pool = []
    for site in R.WEBSITES:
        if R.WEBSITES.get(site):
            pool.extend([site] * R.BRAND_WEIGHT.get(site, R.BRAND_WEIGHT_DEFAULT))
    c = collections.Counter(R.random.choice(pool) for _ in range(60000))
    starved = [s for s in R.WEBSITES if s not in c]
    check('60k 抽样无品牌被饿死', not starved, starved)


def test_chart_render():
    """离线渲染图表：不依赖 GUI 后端（纯 Figure），但调用的是生产代码 update_chart()。
    这一条能抓住 update_chart 内部被 try/except 吞掉的错误——例如把模块级翻译函数
    `_()` 误用成 for 循环变量（普通 for 会把 `_` 变成函数局部变量，导致后续
    `_('chart_ylabel')` 直接 TypeError，而 GUI 上只表现为「图表不刷新」）。
    """
    print("\n== M1 图表渲染（离线，纯 Figure）==")
    from matplotlib.figure import Figure
    h = R.RealNetSimApp.__new__(R.RealNetSimApp)
    fig = Figure(figsize=(9, 3.2))
    h.fig = fig
    h.ax = fig.add_subplot(111)
    h.canvas = type('C', (), {'draw': lambda self: None})()
    h.root = type('Rt', (), {'after': lambda self, *a, **kw: None})()

    saved_stop = R.stop_event.is_set()
    R.stop_event.set()                      # 阻止 update_chart 递归排期
    with R.status_lock:
        saved = dict(R.domain_status)
        R.domain_status.clear()
    try:
        L = R.I18N[R.CURRENT_LANG]
        h.update_chart()                    # 无任何访问 → idle 分支
        check('idle 分支标题正确且不崩',
              h.ax.get_title() == L['chart_title_idle'], repr(h.ax.get_title()))

        with R.status_lock:
            R.domain_status['__M1_ok__'] = {'visits': 5, 'ok': 5, 'ms': 750.0, 'size': 0.0,
                                            'speed': 0.0, 'status': 'OK (200)', 'last_time': 0.0}
            R.domain_status['__M1_bad__'] = {'visits': 2, 'ok': 0, 'ms': 300.0, 'size': 0.0,
                                             'speed': 0.0, 'status': 'Timeout', 'last_time': 0.0}
        h.update_chart()
        check('y 轴 = 访问次数（不再是网速）', h.ax.get_ylabel() == L['chart_ylabel'],
              repr(h.ax.get_ylabel()))
        check('标题 = 真实访问', h.ax.get_title() == L['chart_title'], repr(h.ax.get_title()))
        heights = sorted(b.get_height() for b in h.ax.patches)
        check('柱高取自 visits（2 与 5）', heights == [2.0, 5.0], heights)
        check('图例已渲染', h.ax.get_legend() is not None)
        check('标注 = 全成功站点标耗时 / 有失败站点标状态',
              {t.get_text() for t in h.ax.texts} == {'150ms', 'Timeout'},
              sorted(t.get_text() for t in h.ax.texts))

        with R.status_lock:
            for i in range(40):
                R.domain_status[f'__M1_fill_{i:02d}'] = {
                    'visits': 1, 'ok': 1, 'ms': 10.0, 'size': 0.0, 'speed': 0.0,
                    'status': 'OK (200)', 'last_time': 0.0}
        h.update_chart()
        check('超过上限只画 Top N 根柱', len(h.ax.patches) == R.CHART_MAX_SITES,
              len(h.ax.patches))
        check('标题标注 Top N/总数', f'Top {R.CHART_MAX_SITES}/42' in h.ax.get_title(),
              repr(h.ax.get_title()))
    finally:
        with R.status_lock:
            R.domain_status.clear()
            R.domain_status.update(saved)
        if not saved_stop:
            R.stop_event.clear()


def main():
    logging.basicConfig(level=logging.CRITICAL)
    print("RealSurf v1.3.2 专项测试" + ("  [OFFLINE]" if OFFLINE else ""))
    test_residue()
    test_static()
    test_site_stats()
    test_domains()
    test_chart_render()
    test_feeder_weights()
    test_update_channel()
    test_cache_bust()
    test_scenes()
    test_no_conn_log_file()
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
