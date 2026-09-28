# -*- coding: utf-8 -*-
"""v1.3.x GUI 可视化回归：主窗口三语言 + 勾选项文案 + 更新通道 + 启停 + 按钮行连续性。

v1.3.1 起「记录连接明细(CSV)」功能已整体下线，按钮行应为
【开始】【停止】【穿透缓存】三件套，且占满 column 0/1/2 无空列。
截图存到 _shots_v13/，用于人工核对（本机有真实 Windows 桌面会话）。
跑法：python tests/gui_v13_test.py
"""
import os
import sys
import time
import threading

import tkinter as tk
import ttkbootstrap as ttkb
from PIL import ImageGrab

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)

import realnet_sim as R  # noqa: E402

SHOT_DIR = os.path.join(_ROOT, '_shots_v13')
os.makedirs(SHOT_DIR, exist_ok=True)

RESULTS = []


def rec(name, cond, detail=''):
    RESULTS.append((name, bool(cond), detail))
    print(('  [OK]   ' if cond else '  [FAIL] ') + name + (('  -> ' + str(detail)) if detail else ''))


def shot(root, tag):
    try:
        root.update_idletasks()
        x, y = root.winfo_rootx(), root.winfo_rooty()
        w, h = root.winfo_width(), root.winfo_height()
        img = ImageGrab.grab(bbox=(x, y, x + w, y + h))
        p = os.path.join(SHOT_DIR, f'{tag}.png')
        img.save(p)
        print('  SHOT:', p)
        return p
    except Exception as e:
        print('  shot err:', e)
        return None


root = ttkb.Window(themename="litera")
root.geometry("1060x860")
app = R.RealNetSimApp(root)
root.update()

lang_texts = {}


def step1():
    print("== 1. 中文主窗口 ==")
    shot(root, '01_zh_main')
    rec('主窗口标题含版本号 v1.3.2', 'v1.3.2' in root.title(), root.title())
    rec('中文界面：开始按钮文案', app.start_button.cget('text') == '开始', app.start_button.cget('text'))
    rec('E1 穿透缓存勾选框存在(中文)', app.cachebust_check.cget('text') == '穿透缓存(?num=)',
        app.cachebust_check.cget('text'))
    rec('R1 CSV 勾选框已下线', not hasattr(app, 'csv_check') and not hasattr(app, 'csv_var'))
    # 按钮行连续性回归：删除 CSV 勾选框后，穿透缓存必须落到 column=2（不留空列）
    rec('按钮行无空列：穿透缓存位于 column=2',
        int(app.cachebust_check.grid_info()['column']) == 2,
        app.cachebust_check.grid_info())
    rec('按钮行 3 个控件全部显示',
        all(w.winfo_ismapped() for w in (app.start_button, app.stop_button, app.cachebust_check)))
    lang_texts['zh'] = (app.start_button.cget('text'), app.cachebust_check.cget('text'))
    # 布局回归：默认窗口下所有输入控件都必须完整可见（原来「单次观看」被右边缘裁掉）
    root.update_idletasks()
    right_edge = root.winfo_rootx() + root.winfo_width()
    for nm, w in (('线程数', app.threads_entry), ('访问间隔', app.interval_entry),
                  ('长连接比例', app.stream_prob_entry), ('单次观看', app.stream_dur_entry)):
        vis = (w.winfo_rootx() + w.winfo_width()) <= right_edge
        rec(f'布局：{nm}输入框完整可见', vis,
            f'right={w.winfo_rootx()+w.winfo_width()} 窗口右边缘={right_edge}')
    root.after(400, step2)


def step2():
    print("== 2. 切英文 ==")
    app.switch_language('en')
    root.update()
    shot(root, '02_en_main')
    rec('英文界面：开始按钮文案', app.start_button.cget('text') == 'Start', app.start_button.cget('text'))
    rec('英文界面：穿透缓存勾选框文案', app.cachebust_check.cget('text') == 'Bust cache (?num=)',
        app.cachebust_check.cget('text'))
    lang_texts['en'] = (app.start_button.cget('text'), app.cachebust_check.cget('text'))
    root.after(400, step3)


def step3():
    print("== 3. 切越南语 ==")
    app.switch_language('vi')
    root.update()
    shot(root, '03_vi_main')
    rec('越南语界面：开始按钮文案', app.start_button.cget('text') == 'Bắt đầu',
        app.start_button.cget('text'))
    rec('越南语界面：穿透缓存勾选框文案',
        app.cachebust_check.cget('text') == 'Phá cache (?num=)', app.cachebust_check.cget('text'))
    lang_texts['vi'] = (app.start_button.cget('text'), app.cachebust_check.cget('text'))
    rec('三语言文案互不相同', len(set(lang_texts.values())) == 3, lang_texts)
    root.after(400, step4)


def step4():
    print("== 4. 关于窗口 + 更新通道（真网络）==")
    app.switch_language('zh')
    app.show_about()
    root.update()
    # 更新检查受网络影响可能较慢，轮询等待而不是死等固定秒数
    root.after(1000, lambda: poll_update(0))


def poll_update(n):
    st = ''
    try:
        st = app.update_status_var.get()
    except Exception as e:
        st = f'(读取失败 {e})'
    # 进行中的文案（三语言）：更新状态：正在检查… / Checking for update… / Đang kiểm tra…
    pending = (('正在检查' in st) or ('checking for update' in st.lower())
               or ('đang kiểm tra' in st.lower()) or (st.strip() == ''))
    if pending and n < 40:
        root.after(1000, lambda: poll_update(n + 1))
        return
    shot(root, '04_about_update_channel')
    rec('更新状态非「请求过于频繁」', '频繁' not in st and 'rate limited' not in st.lower(), st)
    rec('更新状态为「已是/发现新版本」之一',
        ('已是最新' in st) or ('发现新版本' in st) or ('no release' in st.lower()),
        f'{st}（等待 {n}s）')
    try:
        app.about_window.destroy()
    except Exception:
        pass
    root.after(500, step6)


def step6():
    print("== 5. 启停回归（真实跑 6 秒）==")
    try:
        app.start_test()
        root.update()
        rec('start_test() 未抛异常', True)
        rec('线程数默认 8 -> 站点数 > 0', len(R.WEBSITES) > 0, f'{len(R.WEBSITES)} 品牌')
        rec('D1 httpx 通道状态', True,
            '已启用' if getattr(app, 'hx', None) is not None else '未启用(httpx 缺失, 已回退)')
        root.after(6000, step7)
    except Exception as e:
        rec('start_test() 未抛异常', False, f'{type(e).__name__}: {e}')
        root.after(200, step8)


def step7():
    shot(root, '05_running')
    n1 = R.request_counter
    rec('运行中确实产生请求', n1 > 0, f'request_counter={n1}')

    # M1：图表指标回归 —— 必须是「真实访问次数」，不能再是网速 KB/s
    try:
        app.update_chart()
        root.update()
    except Exception as e:
        rec('update_chart() 未抛异常', False, f'{type(e).__name__}: {e}')
    ylab = app.ax.get_ylabel()
    rec('图表 y 轴 = 访问次数（不再是网速）', ylab == R.I18N['zh']['chart_ylabel'], repr(ylab))
    rec('图表标题不再含 KB/s', 'KB/s' not in app.ax.get_title(), app.ax.get_title())
    bars = app.ax.patches
    heights = [b.get_height() for b in bars]
    rec('图表有柱子', len(bars) > 0, f'{len(bars)} 根')
    rec('柱子高度 > 0（网速版这里全是 0）', bool(heights) and max(heights) > 0,
        f'max={max(heights) if heights else 0}')
    rec('图例已渲染（成功/部分/全败）', app.ax.get_legend() is not None)
    with R.status_lock:
        visited = {k: v['visits'] for k, v in R.domain_status.items() if v['visits'] > 0}
    rec('有站点记到真实访问次数', bool(visited),
        f'{len(visited)} 个站点, 前 3: {sorted(visited.items(), key=lambda kv: -kv[1])[:3]}')
    rec('柱子数 = 有访问的站点数（未访问不画）',
        len(bars) == min(len(visited), R.CHART_MAX_SITES),
        f'bars={len(bars)} visited={len(visited)} cap={R.CHART_MAX_SITES}')
    shot(root, '09_chart_visits')

    app.stop_test()
    root.update()
    shot(root, '06_stopped')
    rec('stop_test() 后按钮状态复原', str(app.stop_button['state']) == 'disabled',
        app.stop_button['state'])
    leftovers = [f for f in os.listdir(_ROOT) if f.startswith('conn_log')]
    rec('R1 运行后未生成任何 conn_log*.csv', not leftovers, leftovers)
    root.after(300, step8)


def step8():
    print("\n" + "=" * 62)
    ok = sum(1 for _, c, _ in RESULTS if c)
    print(f"GUI 回归：通过 {ok}/{len(RESULTS)}")
    for n, c, d in RESULTS:
        if not c:
            print("  失败:", n, '->', d)
    print("=" * 62)
    root.destroy()


root.after(1000, step1)
root.after(150000, lambda: (print("TIMEOUT"), root.destroy()))
root.mainloop()
