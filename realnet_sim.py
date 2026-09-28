# -*- coding: utf-8 -*-
"""
拟真冲浪 RealSurf  (RealNet Simulator)
============================================
用途：模拟真人电脑对主流站点（含大量子域名）的访问行为，
      用于检验 OpenClash / 代理链路连通性、保活与网速监测。

相比旧版「网络压力测试工具」的改进：
  1. 真实浏览器模拟：使用完整的浏览器请求头档案（Chrome / Edge / Firefox，
     Windows + macOS），带 Referer、Sec-Fetch-*、Accept-Language 等字段，
     并随机切换 UA，行为更贴近真实上网，而非裸 requests。
  2. 断联自动恢复：内置 NetMonitor 网络监控线程。worker 持续上报每次访问
     成败；当窗口内（约 15s）全部失败即判定「网络断联」，暂停发流并进入
     恢复等待；监控线程独立对若干探针站点探测，一旦恢复即自动清除暂停、
     worker 自动续上访问，无需人工重启。
  3. 安全默认：默认开启 SSL 证书校验（verify=True），仅在代理做 TLS 拦截
     的环境下才勾选「跳过证书校验」。
  4. 长连接(视频流)模拟：按可配比例把部分 worker 切换为"看视频"会话——
     Range 分段拉取公开测试视频（像 DASH/HLS 自适应码率）或打开视频平台
     观看页并伴随零星子资源请求，带真实缓冲间隙与观看时长。让出口流量同时
     具备"短请求浏览"与"长连接流式"两种形态，更贴近真人，也补足 Smart 组
     训练所需的"持续吞吐量/长连接稳定性"类特征。

注意：本工具仅用于个人代理连通性验证/训练数据采集目的，请遵守目标站点
      服务条款，勿用于高强度打流或攻击。
"""

import threading
import requests
import time
import sys
import os
import json
import logging
import re
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, Toplevel
import ttkbootstrap as ttkb
from ttkbootstrap.constants import *
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from concurrent.futures import ThreadPoolExecutor
import random
from collections import deque
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from queue import Queue, Empty
import traceback
import webbrowser
from logging.handlers import RotatingFileHandler
from urllib.parse import urlparse

# D1：可选 HTTP/2 + HTTP/3 通道（装不上就自动回退 requests，不影响任何功能）
try:
    import httpx
    _HAS_HTTPX = True
except ImportError:
    httpx = None
    _HAS_HTTPX = False

# 统一可捕获的请求异常：httpx 异常不是 requests 异常的子类，
# 走 httpx 通道时必须一并捕获，否则错误会冒泡成 "worker 异常"。
_REQUEST_ERRORS = ((requests.exceptions.RequestException,) + ((httpx.HTTPError,) if _HAS_HTTPX else ()))

# urllib3 的 DNS 解析失败异常类（requests 本身没有 NameResolutionError，
# 实际以 ConnectionError 形态出现，__cause__ 指向 urllib3 的该类）
try:
    from requests.packages.urllib3.exceptions import NameResolutionError as Urllib3NameResolutionError
except Exception:
    try:
        from urllib3.exceptions import NameResolutionError as Urllib3NameResolutionError
    except Exception:
        Urllib3NameResolutionError = None


def is_dns_error(e):
    """判断异常是否为 DNS 解析失败（域名已死）。

    requests 没有 requests.exceptions.NameResolutionError 这个类，
    DNS 失败实际以 ConnectionError 出现：其 __cause__ 是 urllib3 的
    NameResolutionError，或异常消息含解析失败关键字。
    """
    if Urllib3NameResolutionError is not None:
        cause = getattr(e, '__cause__', None)
        if isinstance(cause, Urllib3NameResolutionError):
            return True
    msg = ' '.join(str(x) for x in (
        getattr(e, 'args', ()), str(e), str(getattr(e, '__cause__', '')))).lower()
    keys = ('name or service not known', 'failed to resolve', 'getaddrinfo',
            'nodename nor servname', 'nameresolutionerror',
            'no address associated with hostname', 'could not resolve host',
            'dns', 'name or service not known')
    return any(k in msg for k in keys)


def resource_path(rel):
    """取打包后资源文件路径，兼容 PyInstaller onefile（_MEIPASS）。"""
    try:
        base = sys._MEIPASS
    except Exception:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, rel)


ICON_FILE = 'realsurf.ico'


def apply_app_icon(window):
    """给窗口设置任务栏/标题栏图标；文件缺失时静默忽略。"""
    try:
        window.iconbitmap(resource_path(ICON_FILE))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 多语言 / i18n（中文 / English / Tiếng Việt）
# ---------------------------------------------------------------------------
import ctypes  # 仅用于读取 Windows 默认 UI 语言；失败时回退英文

# 各语言字体：UI 用 UI_FONT，matplotlib 图表用 CHART_FONT
LANG_FONTS = {
    'zh': ('SimHei', 'SimHei'),
    'en': ('Segoe UI', 'DejaVu Sans'),
    'vi': ('Segoe UI', 'DejaVu Sans'),
}

I18N = {
    'zh': {
        'menu_file': '文件', 'menu_sites': '站点列表', 'menu_export': '导出站点列表(JSON)',
        'menu_check_update': '检查更新', 'menu_about': '关于', 'menu_exit': '退出',
        'menu_language': '语言', 'menu_help': '帮助', 'lang_zh': '中文', 'lang_en': 'English', 'lang_vi': 'Tiếng Việt',
        'about_title': '关于 {name}', 'about_ver': '当前版本  v{ver}', 'about_lang_label': '界面语言:',
        'lbl_threads': '最大并发线程 (1-20):', 'lbl_interval': '访问间隔 (秒, 5-30):',
        'chk_verify': '跳过证书校验(代理环境)', 'lbl_stream_prob': '长连接比例(0-50):',
        'chk_cachebust': '穿透缓存(?num=)',
        'lbl_stream_dur': '单次观看(秒,20-120):', 'btn_start': '开始', 'btn_stop': '停止',
        'lbl_requests': '请求总数: {n}', 'lbl_errors': '错误总数: {n}',
        'net_ok': '网络状态: 正常', 'net_down': '网络状态: 断联恢复中…',
        'editor_title': '站点列表编辑',
        'editor_tip': '选中行后可批量删除 · 右键菜单 · Delete 键删除 · Ctrl+A 全选 · 域名框回车即添加',
        'col_site': '网站名称', 'col_domain': '域名',
        'btn_del_sel': '删除选中', 'btn_select_all': '全选', 'btn_deselect': '取消选择',
        'btn_export': '导出 JSON', 'btn_refresh': '刷新列表', 'btn_close': '关闭',
        'lbl_site_name': '网站名称:', 'lbl_domains': '域名(逗号分隔,可带http):',
        'btn_add': '添加网站', 'ctx_del': '删除选中域名',
        'err_title': '错误', 'warn_title': '警告',
        'warn_select': '请至少选择一个域名',
        'confirm_del_title': '确认删除',
        'confirm_del': '即将删除选中的 {n} 个域名，确定继续？',
        'err_site_name': '请输入网站名称和至少一个域名',
        'err_del_fail': '删除域名失败: {e}', 'err_add_fail': '添加域名失败: {e}\n请检查 access_log.txt',
        'export_ok_title': '导出成功', 'export_ok': '已导出到 sites_export.json',
        'err_export': '导出失败: {e}',
        'init_fail': '初始化失败: {e}\n请检查 access_log.txt',
        'err_threads': '并发线程数必须在 1-20 之间，使用默认值 8',
        'exit_title': '退出', 'exit_confirm': '确定要退出吗？',
        'chart_title': '各站点实时网速与状态', 'chart_title_idle': '各站点实时网速与状态（暂无活动）',
        'chart_ylabel': '网速 (KB/s)',
        'about_intro': '模拟真人上网行为：短请求浏览 + 长连接视频流 + 上传/大文件下载\n'
                       '+ 小包高频交互，用于 OpenClash / 代理链路连通性验证、Smart 策略组\n'
                       '训练数据采集，以及 AdGuardHome(ADG) DNS 缓存预热与命中测试。\n\n'
                       '使用：设好并发数与访问间隔 → 走代理时勾选「跳过\n'
                       '证书校验」→ 点「开始」。运行日志见程序同目录的\n'
                       'access_log.txt。',
        'about_repo_label': '更新仓库：', 'about_status_checking': '更新状态：正在检查…',
        'about_autoshow': '启动时自动显示本窗口',
        'btn_check_update': '检查更新', 'btn_open_repo': '打开仓库',
        'upd_no_release': '更新状态：仓库尚未发布版本',
        'upd_no_release_msg': '还没发布任何版本，暂时无需更新。',
        'upd_rate_limit': '更新状态：请求过于频繁，请稍后再试',
        'upd_rate_limit_msg': 'GitHub 请求过于频繁，请过几分钟再试。',
        'upd_latest': '更新状态：已是最新版本（v{ver}）',
        'upd_latest_msg': '已是最新版本 v{ver}，无需更新。',
        'upd_found_status': '更新状态：发现新版本 {tag}，可点「检查更新」升级',
        'upd_found_msg': '发现新版本 {tag}（当前 v{ver}）\n\n{notes}\n\n是否下载并自动替换？',
        'upd_found_quiet': '发现新版本 {tag}（当前 v{ver}）。\n请用菜单「帮助 → 检查更新」升级。',
        'upd_conn_fail': '更新状态：无法连接更新服务器（请检查网络/代理）',
        'upd_conn_fail_msg': '无法连接更新服务器。\n请检查网络或代理设置后再试。',
        'upd_fail_status': '更新状态：检查更新失败',
        'upd_fail_msg': '检查更新时出现问题，请稍后再试。',
        'upd_apply_fail_title': '更新失败',
        'upd_apply_fail_msg': '自动更新未能完成，已为你打开发布页，\n请手动下载最新版 realsurf<版本号>.exe 覆盖即可。',
        'upd_downloading': '正在下载更新 {ver}…',
        'upd_canceled': '已取消更新',
        'upd_restart': '下载完成，即将重启以完成更新…',
        'upd_checking': '正在检查更新…',
        'btn_cancel': '取消',
    },
    'en': {
        'menu_file': 'File', 'menu_sites': 'Site List', 'menu_export': 'Export Site List (JSON)',
        'menu_check_update': 'Check for Update', 'menu_about': 'About', 'menu_exit': 'Exit',
        'menu_language': 'Language', 'menu_help': 'Help', 'lang_zh': '中文', 'lang_en': 'English', 'lang_vi': 'Tiếng Việt',
        'about_title': 'About {name}', 'about_ver': 'Version  v{ver}', 'about_lang_label': 'Interface language:',
        'lbl_threads': 'Max Threads (1-20):', 'lbl_interval': 'Visit Interval (s, 5-30):',
        'chk_verify': 'Skip Cert Verify (proxy)', 'lbl_stream_prob': 'Stream Ratio (0-50):',
        'chk_cachebust': 'Bust cache (?num=)',
        'lbl_stream_dur': 'Watch Duration (s, 20-120):', 'btn_start': 'Start', 'btn_stop': 'Stop',
        'lbl_requests': 'Total Requests: {n}', 'lbl_errors': 'Total Errors: {n}',
        'net_ok': 'Network: OK', 'net_down': 'Network: Reconnecting…',
        'editor_title': 'Site List Editor',
        'editor_tip': 'Select rows to batch-delete · Right-click menu · Delete key · Ctrl+A select all · Enter in domain box to add',
        'col_site': 'Site Name', 'col_domain': 'Domain',
        'btn_del_sel': 'Delete Selected', 'btn_select_all': 'Select All', 'btn_deselect': 'Deselect',
        'btn_export': 'Export JSON', 'btn_refresh': 'Refresh', 'btn_close': 'Close',
        'lbl_site_name': 'Site Name:', 'lbl_domains': 'Domains (comma-separated, with http):',
        'btn_add': 'Add Site', 'ctx_del': 'Delete Selected Domain',
        'err_title': 'Error', 'warn_title': 'Warning',
        'warn_select': 'Please select at least one domain',
        'confirm_del_title': 'Confirm Delete',
        'confirm_del': 'About to delete {n} selected domain(s). Continue?',
        'err_site_name': 'Enter a site name and at least one domain',
        'err_del_fail': 'Failed to delete domain: {e}', 'err_add_fail': 'Failed to add domain: {e}\nCheck access_log.txt',
        'export_ok_title': 'Exported', 'export_ok': 'Exported to sites_export.json',
        'err_export': 'Export failed: {e}',
        'init_fail': 'Init failed: {e}\nCheck access_log.txt',
        'err_threads': 'Thread count must be 1-20; using default 8',
        'exit_title': 'Exit', 'exit_confirm': 'Exit the application?',
        'chart_title': 'Real-time Speed & Status per Site', 'chart_title_idle': 'Real-time Speed & Status (no activity yet)',
        'chart_ylabel': 'Speed (KB/s)',
        'about_intro': 'Simulates realistic human traffic: short browsing + long video streams\n'
                       '+ uploads / bulk downloads + high-frequency small packets.\n'
                       'For OpenClash / proxy link checks, Smart group training data\n'
                       'collection, and AdGuardHome (ADG) DNS cache warm-up / hit tests.\n\n'
                       'Usage: set threads & interval → check "Skip Cert Verify" when behind a\n'
                       'proxy → click Start. Logs are in access_log.txt next to the app.',
        'about_repo_label': 'Update Repo:', 'about_status_checking': 'Update: checking…',
        'about_autoshow': 'Show this window on startup',
        'btn_check_update': 'Check Update', 'btn_open_repo': 'Open Repo',
        'upd_no_release': 'Update: no release published',
        'upd_no_release_msg': 'No release yet; nothing to update.',
        'upd_rate_limit': 'Update: rate limited, retry later',
        'upd_rate_limit_msg': 'GitHub rate limit; retry in a few minutes.',
        'upd_latest': 'Update: already latest (v{ver})',
        'upd_latest_msg': 'Already latest v{ver}; no update needed.',
        'upd_found_status': 'Update: new version {tag} found',
        'upd_found_msg': 'New version {tag} (current v{ver})\n\n{notes}\n\nDownload and auto-replace?',
        'upd_found_quiet': 'New version {tag} (current v{ver}).\nUse menu "Help → Check for Update" to upgrade.',
        'upd_conn_fail': 'Update: cannot reach server (check network/proxy)',
        'upd_conn_fail_msg': 'Cannot reach update server.\nCheck network or proxy settings.',
        'upd_fail_status': 'Update: check failed',
        'upd_fail_msg': 'Problem during update check; retry later.',
        'upd_apply_fail_title': 'Update Failed',
        'upd_apply_fail_msg': 'Auto-update incomplete; release page opened.\nDownload the latest realsurf<ver>.exe manually.',
        'upd_downloading': 'Downloading update {ver}…',
        'upd_canceled': 'Update canceled',
        'upd_restart': 'Download complete; restarting to finish update…',
        'upd_checking': 'Checking for update…',
        'btn_cancel': 'Cancel',
    },
    'vi': {
        'menu_file': 'Tập tin', 'menu_sites': 'Danh sách trang', 'menu_export': 'Xuất danh sách (JSON)',
        'menu_check_update': 'Kiểm tra cập nhật', 'menu_about': 'Giới thiệu', 'menu_exit': 'Thoát',
        'menu_language': 'Ngôn ngữ', 'menu_help': 'Trợ giúp', 'lang_zh': '中文', 'lang_en': 'English', 'lang_vi': 'Tiếng Việt',
        'about_title': 'Giới thiệu {name}', 'about_ver': 'Phiên bản  v{ver}', 'about_lang_label': 'Ngôn ngữ giao diện:',
        'lbl_threads': 'Số luồng tối đa (1-20):', 'lbl_interval': 'Khoảng cách truy cập (giây, 5-30):',
        'chk_verify': 'Bỏ xác thực chứng chỉ (proxy)', 'lbl_stream_prob': 'Tỉ lệ luồng (0-50):',
        'chk_cachebust': 'Phá cache (?num=)',
        'lbl_stream_dur': 'Thời gian xem (giây, 20-120):', 'btn_start': 'Bắt đầu', 'btn_stop': 'Dừng',
        'lbl_requests': 'Tổng yêu cầu: {n}', 'lbl_errors': 'Tổng lỗi: {n}',
        'net_ok': 'Mạng: Bình thường', 'net_down': 'Mạng: Đang kết nối lại…',
        'editor_title': 'Trình biên tập danh sách',
        'editor_tip': 'Chọn dòng để xóa hàng loạt · Menu chuột phải · Phím Delete · Ctrl+A chọn tất cả · Enter trong ô tên miền để thêm',
        'col_site': 'Tên trang', 'col_domain': 'Tên miền',
        'btn_del_sel': 'Xóa đã chọn', 'btn_select_all': 'Chọn tất cả', 'btn_deselect': 'Bỏ chọn',
        'btn_export': 'Xuất JSON', 'btn_refresh': 'Làm mới', 'btn_close': 'Đóng',
        'lbl_site_name': 'Tên trang:', 'lbl_domains': 'Tên miền (cách nhau bằng dấu phẩy, có http):',
        'btn_add': 'Thêm trang', 'ctx_del': 'Xóa tên miền đã chọn',
        'err_title': 'Lỗi', 'warn_title': 'Cảnh báo',
        'warn_select': 'Vui lòng chọn ít nhất một tên miền',
        'confirm_del_title': 'Xác nhận xóa',
        'confirm_del': 'Sắp xóa {n} tên miền đã chọn. Tiếp tục?',
        'err_site_name': 'Nhập tên trang và ít nhất một tên miền',
        'err_del_fail': 'Lỗi xóa tên miền: {e}', 'err_add_fail': 'Lỗi thêm tên miền: {e}\nKiểm tra access_log.txt',
        'export_ok_title': 'Đã xuất', 'export_ok': 'Đã xuất ra sites_export.json',
        'err_export': 'Lỗi xuất: {e}',
        'init_fail': 'Lỗi khởi tạo: {e}\nKiểm tra access_log.txt',
        'err_threads': 'Số luồng phải từ 1-20; dùng mặc định 8',
        'exit_title': 'Thoát', 'exit_confirm': 'Thoát ứng dụng?',
        'chart_title': 'Tốc độ & trạng thái theo trang', 'chart_title_idle': 'Tốc độ & trạng thái (chưa có hoạt động)',
        'chart_ylabel': 'Tốc độ (KB/s)',
        'about_intro': 'Mô phỏng lướt web thật của con người: truy cập ngắn + luồng video dài.\n'
                       'Dùng để kiểm tra OpenClash / proxy, thu thập dữ liệu huấn luyện\n'
                       'nhóm Smart, và làm nóng / kiểm tra cache DNS của AdGuardHome (ADG).\n\n'
                       'Cách dùng: chỉnh luồng & khoảng cách → khi qua proxy hãy tích\n'
                       '"Bỏ xác thực chứng chỉ" → bấm Bắt đầu. Nhật ký ở access_log.txt.',
        'about_repo_label': 'Kho cập nhật:', 'about_status_checking': 'Cập nhật: đang kiểm tra…',
        'about_autoshow': 'Hiện cửa sổ này khi khởi động',
        'btn_check_update': 'Kiểm tra cập nhật', 'btn_open_repo': 'Mở kho',
        'upd_no_release': 'Cập nhật: chưa có bản phát hành',
        'upd_no_release_msg': 'Chưa có bản phát hành nào.',
        'upd_rate_limit': 'Cập nhật: bị giới hạn, thử lại sau',
        'upd_rate_limit_msg': 'GitHub giới hạn; thử lại sau vài phút.',
        'upd_latest': 'Cập nhật: đã là mới nhất (v{ver})',
        'upd_latest_msg': 'Đã là mới nhất v{ver}; không cần cập nhật.',
        'upd_found_status': 'Cập nhật: tìm thấy phiên bản mới {tag}',
        'upd_found_msg': 'Phiên bản mới {tag} (hiện tại v{ver})\n\n{notes}\n\nTải và tự thay thế?',
        'upd_found_quiet': 'Phiên bản mới {tag} (hiện tại v{ver}).\nDùng menu "Trợ giúp → Kiểm tra cập nhật" để nâng cấp.',
        'upd_conn_fail': 'Cập nhật: không thể kết nối (kiểm tra mạng/proxy)',
        'upd_conn_fail_msg': 'Không thể kết nối máy chủ cập nhật.\nKiểm tra mạng hoặc proxy.',
        'upd_fail_status': 'Cập nhật: kiểm tra thất bại',
        'upd_fail_msg': 'Lỗi khi kiểm tra cập nhật; thử lại sau.',
        'upd_apply_fail_title': 'Cập nhật thất bại',
        'upd_apply_fail_msg': 'Tự cập nhật chưa xong; đã mở trang phát hành.\nTải realsurf<phiên bản>.exe mới nhất thủ công.',
        'upd_downloading': 'Đang tải cập nhật {ver}…',
        'upd_canceled': 'Đã hủy cập nhật',
        'upd_restart': 'Tải xong; sắp khởi động lại để hoàn tất…',
        'upd_checking': 'Đang kiểm tra cập nhật…',
        'btn_cancel': 'Hủy',
    },
}


def detect_windows_language():
    """根据 Windows 默认 UI 语言自动选择：中文系列→zh，越南语→vi，其余→en。"""
    try:
        lid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
        prim = lid & 0x3FF
        if prim == 0x04:
            return 'zh'
        if prim == 0x2A:
            return 'vi'
        return 'en'
    except Exception:
        return 'en'


CURRENT_LANG = detect_windows_language()
UI_FONT = 'SimHei'
CHART_FONT = 'SimHei'


def set_lang_fonts():
    global UI_FONT, CHART_FONT
    uf, cf = LANG_FONTS.get(CURRENT_LANG, LANG_FONTS['en'])
    UI_FONT, CHART_FONT = uf, cf
    plt.rcParams['font.sans-serif'] = [cf]
    plt.rcParams['axes.unicode_minus'] = False


def set_language(code):
    global CURRENT_LANG
    if code in I18N:
        CURRENT_LANG = code
        set_lang_fonts()


def _(key, **kw):
    d = I18N.get(CURRENT_LANG) or I18N['en']
    s = d.get(key, I18N['en'].get(key, key))
    if kw:
        try:
            return s.format(**kw)
        except Exception:
            return s
    return s


# 立即按当前语言设置字体（图表用）
set_lang_fonts()

# ---------------------------------------------------------------------------
# 日志
# ---------------------------------------------------------------------------
try:
    # 启动前若旧日志过大（多为重复冒烟错误），先归档，避免无限膨胀
    _log_path = 'access_log.txt'
    try:
        if os.path.exists(_log_path) and os.path.getsize(_log_path) > 15 * 1024 * 1024:
            _old = 'access_log.old.txt'
            if os.path.exists(_old):
                os.remove(_old)
            os.rename(_log_path, _old)
    except Exception:
        pass
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(threadName)s - %(levelname)s - %(message)s',
        handlers=[
            # 轮转：单文件上限 5MB，保留 2 个备份（access_log.txt.1/.2），防止日志无限膨胀
            RotatingFileHandler(_log_path, maxBytes=5 * 1024 * 1024, backupCount=2,
                                encoding='utf-8'),
            logging.StreamHandler(sys.stdout),
        ],
    )
except PermissionError as e:
    print(f"无法写入日志文件: {e}. 请检查 access_log.txt 权限")
    sys.exit(1)
logger = logging.getLogger()

# 把日志推到 UI 的队列处理器
class QueueHandler(logging.Handler):
    def __init__(self, queue):
        super().__init__()
        self.queue = queue

    def emit(self, record):
        try:
            self.queue.put(self.format(record))
        except Exception:
            self.handleError(record)


# ---------------------------------------------------------------------------
# 真实浏览器请求头档案（模拟真人电脑）
# ---------------------------------------------------------------------------
BROWSER_PROFILES = [
    {   # Chrome / Windows
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                      '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,'
                  'image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
    },
    {   # Edge / Windows
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                      '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,'
                  'image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
    },
    {   # Firefox / Windows
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) '
                      'Gecko/20100101 Firefox/125.0',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,'
                  'image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
    },
    {   # Chrome / macOS
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
                      '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,'
                  'image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
    },
]

# 站点列表（原 OpenClash 规则集补充，覆盖主流站点及其子域名）
WEBSITES = {
    "TikTok": [
        "https://www.tiktok.com", "https://m.tiktok.com", "https://api.tiktok.com",
        "https://ads.tiktok.com", "https://business.tiktok.com", "https://creators.tiktok.com",
        "https://shop.tiktok.com", "https://live.tiktok.com", "https://analytics.tiktok.com",
        "https://developer.tiktok.com", "https://link.tiktok.com", "https://us.tiktok.com",
        "https://v.tiktok.com", "https://vm.tiktok.com", "https://vt.tiktok.com",
        "https://support.tiktok.com", "https://careers.tiktok.com", "https://newsroom.tiktok.com",
        "https://effecthouse.tiktok.com", "https://tiktokcdn.com", "https://api-h2.tiktokv.com",
        "https://webcast.tiktok.com",
    ],
    "YouTube": [
        "https://www.youtube.com", "https://m.youtube.com", "https://music.youtube.com",
        "https://tv.youtube.com", "https://studio.youtube.com", "https://kids.youtube.com",
        "https://accounts.youtube.com", "https://ads.youtube.com", "https://support.youtube.com",
        "https://about.youtube.com", "https://blog.youtube.com", "https://developers.youtube.com",
        "https://ytimg.com", "https://creatoracademy.youtube.com", "https://gaming.youtube.com",
        "https://apis.youtube.com", "https://youtube.googleapis.com", "https://upload.youtube.com",
        "https://redirect.youtube.com", "https://search.youtube.com", "https://myaccount.youtube.com",
        "https://creators.youtube.com", "https://shopping.youtube.com", "https://shorts.youtube.com",
        "https://live.youtube.com", "https://yt.be", "https://m.youtube.googleapis.com",
        "https://youtubekids.com", "https://analytics.youtube.com", "https://notifications.youtube.com",
        "https://embed.youtube.com", "https://youtu.be",
    ],
    "Netflix": [
        "https://www.netflix.com", "https://account.netflix.com", "https://media.netflix.com",
        "https://app.netflix.com", "https://help.netflix.com", "https://blog.netflix.com",
        "https://jobs.netflix.com", "https://ir.netflix.com", "https://partner.netflix.com",
        "https://devices.netflix.com", "https://investor.netflix.com", "https://signup.netflix.com",
        "https://api.netflix.com", "https://developer.netflix.com", "https://support.netflix.com",
        "https://netflix.net", "https://nflxvideo.net", "https://fast.com", "https://about.netflix.com",
        "https://openconnect.netflix.com", "https://api-global.netflix.com", "https://cdn.netflix.com",
        "https://nflximg.com", "https://netflixcdn.com",
    ],
    "Reddit": [
        "https://www.reddit.com", "https://m.reddit.com", "https://oauth.reddit.com",
        "https://old.reddit.com", "https://np.reddit.com", "https://mod.reddit.com",
        "https://ads.reddit.com", "https://about.reddit.com", "https://blog.reddit.com",
        "https://api.reddit.com", "https://i.reddit.com", "https://ssl.reddit.com",
        "https://developer.reddit.com", "https://support.reddit.com", "https://careers.reddit.com",
        "https://store.reddit.com", "https://redditinc.com", "https://accounts.reddit.com",
        "https://gateway.reddit.com", "https://events.reddit.com", "https://help.reddit.com",
    ],
    "X": [
        "https://www.x.com", "https://mobile.x.com", "https://api.x.com", "https://ads.x.com",
        "https://developer.x.com", "https://blog.x.com", "https://about.x.com", "https://support.x.com",
        "https://business.x.com", "https://cards.x.com", "https://media.x.com", "https://help.x.com",
        "https://careers.x.com", "https://status.x.com", "https://analytics.x.com", "https://pay.x.com",
        "https://m.x.com", "https://syndication.x.com", "https://upload.x.com", "https://video.x.com",
        "https://abs.twimg.com", "https://pbs.twimg.com", "https://t.co",
    ],
    "Instagram": [
        "https://www.instagram.com", "https://i.instagram.com", "https://api.instagram.com",
        "https://business.instagram.com", "https://help.instagram.com", "https://about.instagram.com",
        "https://developers.instagram.com", "https://blog.instagram.com", "https://ads.instagram.com",
        "https://careers.instagram.com", "https://creator.instagram.com", "https://support.instagram.com",
        "https://privacy.instagram.com", "https://graph.instagram.com", "https://m.instagram.com",
        "https://l.instagram.com", "https://accountscenter.instagram.com", "https://direct.instagram.com",
    ],
    "Facebook": [
        "https://www.facebook.com", "https://m.facebook.com", "https://graph.facebook.com",
        "https://business.facebook.com", "https://developers.facebook.com", "https://about.facebook.com",
        "https://help.facebook.com", "https://ads.facebook.com", "https://careers.facebook.com",
        "https://blog.facebook.com", "https://investor.facebook.com", "https://privacy.facebook.com",
        "https://messenger.facebook.com", "https://api.facebook.com", "https://l.facebook.com",
        "https://connect.facebook.com", "https://pay.facebook.com", "https://api.messenger.com",
        "https://accountscenter.facebook.com", "https://web.facebook.com", "https://touch.facebook.com",
        "https://static.facebook.com", "https://upload.facebook.com",
    ],
    "Twitch": [
        "https://www.twitch.tv", "https://m.twitch.tv", "https://api.twitch.tv", "https://blog.twitch.tv",
        "https://help.twitch.tv", "https://developer.twitch.tv", "https://ads.twitch.tv",
        "https://partners.twitch.tv", "https://about.twitch.tv", "https://status.twitch.tv",
        "https://affiliate.twitch.tv", "https://dashboard.twitch.tv", "https://link.twitch.tv",
        "https://music.twitch.tv", "https://prime.twitch.tv", "https://clips.twitch.tv",
        "https://player.twitch.tv", "https://spade.twitch.tv", "https://gql.twitch.tv",
        "https://passport.twitch.tv", "https://usher.twitch.tv",
    ],
    "Hulu": [
        "https://www.hulu.com", "https://secure.hulu.com", "https://play.hulu.com", "https://help.hulu.com",
        "https://blog.hulu.com", "https://ads.hulu.com", "https://developer.hulu.com", "https://about.hulu.com",
        "https://press.hulu.com", "https://careers.hulu.com", "https://support.hulu.com", "https://m.hulu.com",
        "https://api.hulu.com", "https://content.hulu.com", "https://live.hulu.com", "https://auth.hulu.com",
        "https://activate.hulu.com", "https://account.hulu.com",
    ],
    "BBC": [
        "https://www.bbc.co.uk", "https://news.bbc.co.uk", "https://iplayer.bbc.co.uk",
        "https://sport.bbc.co.uk", "https://weather.bbc.co.uk", "https://shop.bbc.co.uk",
        "https://careers.bbc.co.uk", "https://about.bbc.co.uk", "https://help.bbc.co.uk",
        "https://api.bbc.co.uk", "https://developer.bbc.co.uk", "https://blog.bbc.co.uk",
        "https://support.bbc.co.uk", "https://m.bbc.co.uk", "https://feeds.bbc.co.uk",
        "https://education.bbc.co.uk", "https://music.bbc.co.uk", "https://www.bbc.com",
    ],
    "CNN": [
        "https://www.cnn.com", "https://edition.cnn.com", "https://m.cnn.com", "https://money.cnn.com",
        "https://politics.cnn.com", "https://travel.cnn.com", "https://health.cnn.com", "https://ads.cnn.com",
        "https://api.cnn.com", "https://blog.cnn.com", "https://about.cnn.com", "https://developer.cnn.com",
        "https://support.cnn.com", "https://careers.cnn.com", "https://video.cnn.com", "https://weather.cnn.com",
    ],
    "Amazon": [
        "https://www.amazon.com", "https://aws.amazon.com", "https://smile.amazon.com",
        "https://seller.amazon.com", "https://developer.amazon.com", "https://advertising.amazon.com",
        "https://affiliates.amazon.com", "https://about.amazon.com", "https://help.amazon.com",
        "https://blog.amazon.com", "https://careers.amazon.com", "https://api.amazon.com",
        "https://music.amazon.com", "https://video.amazon.com", "https://prime.amazon.com",
        "https://m.amazon.com", "https://kindle.amazon.com", "https://pay.amazon.com", "https://a.co",
    ],
    "eBay": [
        "https://www.ebay.com", "https://m.ebay.com", "https://signin.ebay.com", "https://seller.ebay.com",
        "https://developer.ebay.com", "https://about.ebay.com", "https://help.ebay.com",
        "https://www.ebay.com/sch/", "https://www.ebay.com/myebay", "https://www.ebay.com/deals",
        "https://auth.ebay.com", "https://cart.ebay.com", "https://pay.ebay.com",
    ],
    "Ubisoft": [
        "https://status.ubisoft.com", "https://shop.ubisoft.com", "https://redirection.ubisoft.com",
        "https://www.ubisoft.com", "https://account.ubisoft.com", "https://support.ubisoft.com",
        "https://forums.ubisoft.com", "https://connect.ubisoft.com", "https://uplay.ubi.com",
    ],
    "Dropbox": [
        "https://about.dropbox.com", "https://www.dropbox.com", "https://www.dropboxforum.com",
        "https://help.dropbox.com", "https://www.dropbox.com/login", "https://www.dropbox.com/home",
        "https://api.dropbox.com", "https://content.dropbox.com",
    ],
    "Telegram": [
        "https://core.telegram.org", "https://telegram.org", "https://t.me", "https://status.telegram.org",
        "https://desktop.telegram.org", "https://web.telegram.org", "https://api.telegram.org",
        "https://my.telegram.org",
    ],
    "Discord": [
        "https://careers.discord.com", "https://community.discord.com", "https://about.discord.com",
        "https://discord.com", "https://safety.discord.com", "https://support.discord.com",
        "https://status.discord.com", "https://discord.com/invite", "https://cdn.discordapp.com",
        "https://gateway.discord.gg",
    ],
    "EpicGames": [
        "https://community.epicgames.com", "https://launcher.epicgames.com", "https://support.epicgames.com",
        "https://www.epicgames.com", "https://store.epicgames.com", "https://account.epicgames.com",
        "https://unrealengine.com", "https://api.epicgames.com",
    ],
    "GitHub": [
        "https://about.github.com", "https://actions.github.com", "https://www.github.com",
        "https://docs.github.com", "https://support.github.com", "https://status.github.com",
        "https://api.github.com", "https://raw.githubusercontent.com", "https://gist.github.com",
    ],
    "HumbleBundle": [
        "https://store.humblebundle.com", "https://www.humblebundle.com", "https://support.humblebundle.com",
        "https://blog.humblebundle.com", "https://account.humblebundle.com",
    ],
    "PlayStation": [
        "https://psnprofiles.com", "https://store.playstation.com", "https://www.playstation.com",
        "https://my.playstation.com", "https://support.playstation.com",
        "https://account.sonyentertainmentnetwork.com", "https://direct.playstation.com",
    ],
    "Itch": [
        "https://account.itch.io", "https://itch.io", "https://api.itch.io", "https://itch.io/login",
        "https://itch.io/docs", "https://itch.io/jam", "https://itch.io/community",
    ],
    "Nintendo": [
        "https://www.nintendo.co.jp", "https://support.nintendo.com", "https://www.nintendo.com",
        "https://accounts.nintendo.com", "https://store.nintendo.com", "https://my.nintendo.com",
        "https://ec.nintendo.com", "https://api.accounts.nintendo.com",
    ],
    "GOG": [
        "https://cdn.gog.com", "https://shop.gog.com", "https://developer.gog.com", "https://status.gog.com",
        "https://blog.gog.com", "https://www.gog.com", "https://support.gog.com", "https://auth.gog.com",
    ],
    "Xbox": [
        "https://events.xbox.com", "https://www.xbox.com", "https://account.xbox.com",
        "https://support.xbox.com", "https://store.xbox.com", "https://gamepass.xbox.com",
        "https://rewards.xbox.com",
    ],
    "NexusMods": [
        "https://community.nexusmods.com", "https://support.nexusmods.com", "https://www.nexusmods.com",
        "https://users.nexusmods.com", "https://forums.nexusmods.com", "https://api.nexusmods.com",
    ],
    "EA": [
        "https://eaapp.com", "https://account.ea.com", "https://www.ea.com", "https://help.ea.com",
        "https://www.origin.com", "https://api.ea.com", "https://signin.ea.com",
    ],
    "RockstarGames": [
        "https://careers.rockstargames.com", "https://store.rockstargames.com",
        "https://www.rockstargames.com", "https://support.rockstargames.com",
        "https://socialclub.rockstargames.com", "https://media.rockstargames.com",
    ],
    "TGC": [
        "https://cdn.tgcofficial.games", "https://store.tgcofficial.games", "https://community.tgcofficial.games",
        "https://thatgamecompany.com", "https://sky.thatgamecompany.com", "https://api.thatgamecompany.com",
        "https://support.thatgamecompany.com", "https://blog.thatgamecompany.com",
        "https://sky-api.thatgamecompany.com", "https://account.thatgamecompany.com",
        "https://live.thatgamecompany.com",
    ],
    "Bilibili": [
        "https://www.bilibili.tv", "https://www.bilibili.com", "https://m.bilibili.com",
        "https://api.bilibili.com", "https://live.bilibili.com", "https://space.bilibili.com",
        "https://search.bilibili.com", "https://account.bilibili.com", "https://app.bilibili.com",
        "https://passport.bilibili.com", "https://pay.bilibili.com", "https://cm.bilibili.com",
        "https://message.bilibili.com", "https://member.bilibili.com", "https://comic.bilibili.com",
        "https://h.bilibili.com", "https://link.bilibili.com", "https://game.bilibili.com",
        "https://shop.bilibili.com",
    ],
    # ---- 以下为补充的主流站点（含子域名），让训练样本更杂更贴近真人 ----
    "Google": [
        "https://www.google.com", "https://www.google.co.uk", "https://maps.google.com",
        "https://mail.google.com", "https://drive.google.com", "https://docs.google.com",
        "https://photos.google.com", "https://play.google.com", "https://accounts.google.com",
        "https://myaccount.google.com", "https://support.google.com", "https://developers.google.com",
        "https://scholar.google.com", "https://news.google.com", "https://www.google.com.hk",
    ],
    "Microsoft": [
        "https://www.microsoft.com", "https://login.microsoftonline.com", "https://outlook.live.com",
        "https://office.com", "https://onedrive.live.com", "https://azure.microsoft.com",
        "https://learn.microsoft.com", "https://support.microsoft.com", "https://account.microsoft.com",
        "https://www.bing.com",
    ],
    "Apple": [
        "https://www.apple.com", "https://www.icloud.com", "https://appleid.apple.com",
        "https://support.apple.com", "https://music.apple.com", "https://tv.apple.com",
        "https://developer.apple.com", "https://apps.apple.com", "https://www.apple.com.cn",
    ],
    "Spotify": [
        "https://www.spotify.com", "https://open.spotify.com", "https://accounts.spotify.com",
        "https://support.spotify.com", "https://developer.spotify.com", "https://podcasters.spotify.com",
    ],
    "DisneyPlus": [
        "https://www.disneyplus.com", "https://www.disney.com", "https://www.starplus.com",
        "https://www.hotstar.com", "https://support.disneyplus.com",
    ],
    "PrimeVideo": [
        "https://www.primevideo.com", "https://www.amazon.com/gp/video", "https://watch.amazon.com",
        "https://www.amazon.com/music", "https://music.amazon.com",
    ],
    "HBOMax": [
        "https://www.max.com", "https://www.hbomax.com", "https://help.max.com",
        "https://www.hbo.com",
    ],
    "Vimeo": [
        "https://vimeo.com", "https://player.vimeo.com", "https://vimeo.com/log_in",
        "https://developer.vimeo.com", "https://vimeo.com/help",
    ],
    "Pinterest": [
        "https://www.pinterest.com", "https://www.pinterest.co.uk", "https://help.pinterest.com",
        "https://business.pinterest.com", "https://developers.pinterest.com",
    ],
    "LinkedIn": [
        "https://www.linkedin.com", "https://www.linkedin.co.uk", "https://learning.linkedin.com",
        "https://developer.linkedin.com", "https://www.linkedin.com/login",
    ],
    "Wikipedia": [
        "https://www.wikipedia.org", "https://en.wikipedia.org", "https://zh.wikipedia.org",
        "https://commons.wikimedia.org", "https://meta.wikimedia.org", "https://www.mediawiki.org",
    ],
    "Cloudflare": [
        "https://www.cloudflare.com", "https://dash.cloudflare.com", "https://developers.cloudflare.com",
        "https://blog.cloudflare.com", "https://www.cloudflare.com/zh-cn/",
    ],
    "Quora": [
        "https://www.quora.com", "https://www.quora.com/login", "https://business.quora.com",
    ],
    "StackOverflow": [
        "https://stackoverflow.com", "https://meta.stackoverflow.com", "https://stackoverflow.blog",
        "https://api.stackexchange.com",
    ],
    "Medium": [
        "https://medium.com", "https://blog.medium.com", "https://help.medium.com",
        "https://www.medium.com/membership",
    ],
    "SoundCloud": [
        "https://soundcloud.com", "https://help.soundcloud.com", "https://developers.soundcloud.com",
        "https://www.soundcloud.com/login",
    ],
    "Dailymotion": [
        "https://www.dailymotion.com", "https://www.dailymotion.com/en", "https://www.dailymotion.com/login",
        "https://developers.dailymotion.com",
    ],
    "WeTV": [
        "https://wetv.com", "https://www.wetv.com", "https://www.wetv.vip", "https://www.we.tv",
    ],
    "iQIYI": [
        "https://www.iqiyi.com", "https://www.iq.com", "https://www.qiyipic.com",
        "https://static.iqiyi.com", "https://www.iqiyi.com/vip",
    ],
    "Youku": [
        "https://www.youku.com", "https://v.youku.com", "https://www.youku.com/login",
        "https://www.youku.com/vip",
    ],
    "Zhihu": [
        "https://www.zhihu.com", "https://www.zhihu.com/login", "https://www.zhihu.com/explore",
        "https://www.zhihu.com/topic", "https://www.zhihu.com/question",
    ],
    "Weibo": [
        "https://www.weibo.com", "https://weibo.com", "https://www.weibo.com/login.php",
        "https://m.weibo.cn", "https://open.weibo.com",
    ],
    "Baidu": [
        "https://www.baidu.com", "https://tieba.baidu.com", "https://pan.baidu.com",
        "https://yun.baidu.com", "https://baike.baidu.com", "https://www.baidu.com/login",
    ],
    "Toutiao": [
        "https://www.toutiao.com", "https://www.toutiao.com/login", "https://www.toutiao.com/category",
        "https://www.toutiao.com/video",
    ],
}

# 长连接(视频流)目标：模拟真人"看视频"行为，给 Smart 组提供
# 持续吞吐量 / 长连接稳定性类特征样本。两类：
#   mp4=True  → 真实支持 Range 的公开测试视频，做分段顺序拉取（像 DASH/HLS 自适应码率）
#   mp4=False → 视频平台观看页 + 子资源，模拟"打开视频页→看一会儿"的会话
STREAM_SITES = [
    {'label': '视频:YouTube', 'host': '视频:YouTube', 'url': 'https://www.youtube.com',
     'mp4': False, 'subs': ['https://ytimg.com', 'https://i.ytimg.com']},
    {'label': '视频:Netflix', 'host': '视频:Netflix', 'url': 'https://www.netflix.com',
     'mp4': False, 'subs': ['https://nflximg.com', 'https://fast.com']},
    {'label': '视频:Bilibili', 'host': '视频:Bilibili', 'url': 'https://www.bilibili.com',
     'mp4': False, 'subs': ['https://i0.hdslb.com', 'https://i1.hdslb.com']},
    {'label': '视频:Twitch', 'host': '视频:Twitch', 'url': 'https://www.twitch.tv',
     'mp4': False, 'subs': ['https://static-cdn.jtvnw.net', 'https://player.twitch.tv']},
    {'label': '视频:BigBuckBunny', 'host': '视频:BigBuckBunny',
     'url': 'https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4',
     'mp4': True},
    {'label': '视频:TestVideos', 'host': '视频:TestVideos',
     'url': 'https://test-videos.co.uk/vids/bigbuckbunny/mp4/h264/720/Big_Buck_Bunny_720_10s_1MB.mp4',
     'mp4': True},
]

# E2：DASH/HLS 形态的视频源（真实分片清单）。命中后按 manifest 拉 .ts/.m4s 分片，
# 变长 + 并行 2~4 路，模拟自适应码率的真实长连接形态（比单文件 Range 更接近流媒体）。
STREAM_M3U8 = [
    "https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8",
    "https://test-streams.mux.dev/pts_shift/master.m3u8",
    "https://demo.unified-streaming.com/k8s/features/stable/video/tears-of-steel/tears-of-steel.ism/.m3u8",
]
HLS_PROB = 0.5                 # 视频任务里走 HLS/DASH 分片的概率

# 品牌热度权重（幂律近似）：投喂器按权重抽样，头部站更频繁，避免"均匀访问 54 个品牌"
# 带来的训练样本偏置。A1-1：档位从 6/5/4/3/2/1 拉开到 1000/300/100/30，
# 让头尾比达到 ~100:1（原 6:1 太扁，幂律形态不足）。
# 注：任务书原表遗漏了 WEBSITES 里的游戏商店/资讯类品牌，此处补齐到对应档位，
# 并把 _feeder 的兜底权重从 1 提到 30，避免未列品牌被头部品牌按 1000:1 直接饿死。
BRAND_WEIGHT = {
    # 头部（1000/900/800）
    "Google": 1000, "YouTube": 1000, "Facebook": 900, "Microsoft": 800, "Amazon": 800,
    # 次头部（300）
    "Apple": 300, "Instagram": 300, "TikTok": 300, "Wikipedia": 300, "X": 300,
    "WhatsApp": 300, "Netflix": 300, "Reddit": 300, "Baidu": 300, "Bilibili": 300,
    # 中段（100）
    "Twitch": 100, "Discord": 100, "GitHub": 100, "Spotify": 100, "Zhihu": 100,
    "Weibo": 100, "LinkedIn": 100, "Pinterest": 100, "Telegram": 100, "Cloudflare": 100,
    "StackOverflow": 100, "Medium": 100, "eBay": 100, "BBC": 100, "CNN": 100,
    # 中段·游戏/社区商店（任务书原表未列，补齐，避免被饿死）
    "Toutiao": 100, "Xbox": 100, "PlayStation": 100, "Nintendo": 100,
    "EA": 100, "EpicGames": 100, "Ubisoft": 100,
    # 尾部（30）
    "DisneyPlus": 30, "PrimeVideo": 30, "HBOMax": 30, "iQIYI": 30, "Youku": 30,
    "WeTV": 30, "Dropbox": 30, "Vimeo": 30, "Hulu": 30, "RockstarGames": 30,
    "NexusMods": 30, "HumbleBundle": 30, "Itch": 30, "GOG": 30, "TGC": 30,
    "Quora": 10, "Dailymotion": 10, "SoundCloud": 10,
}
BRAND_WEIGHT_DEFAULT = 30      # 未列品牌兜底权重（原为 1，会让未列品牌被饿死）


def _app_dir():
    """程序所在目录：PyInstaller onefile 下 __file__ 在 _MEI 临时目录，必须用 exe 目录。"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


# ---- A1-3（可选）真实榜单：Tranco / Cisco Umbrella top-1M 导出为 top1m.csv ----
# 文件格式：每行 "rank,host"。默认关闭；置 USE_TOP_LIST = True 且文件存在时，
# 用榜单完全替代硬编码 WEBSITES（权重 w ∝ rank^-0.8）。
USE_TOP_LIST = False
TOP_LIST_CAP = 100000
TOP_LIST_PATH = os.path.join(_app_dir(), 'top1m.csv')
RANK_WEIGHT = {}               # url -> 榜单权重（幂律），供 _host_weight 使用


def _load_top_list(path=TOP_LIST_PATH, cap=TOP_LIST_CAP):
    """读取 top-1M 榜单，返回 {'TOP': [url, ...]}；文件不存在则返回 {}。"""
    sites = {}
    if not os.path.exists(path):
        return sites
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if not line or line[0] == '#':
                    continue
                parts = line.split(',')
                if len(parts) < 2:
                    continue
                try:
                    rank = int(parts[0])
                except ValueError:
                    continue
                if rank > cap or rank < 1:
                    continue
                host = parts[1].strip()
                if not host:
                    continue
                url = f'https://{host}'
                sites.setdefault('TOP', []).append(url)
                RANK_WEIGHT[url] = rank ** -0.8
    except Exception as e:
        logger.warning(f"读取榜单失败 {path}: {e}")
        return {}
    # 权重归一化到与 BRAND_WEIGHT 同量级（头部 ~1000）
    if RANK_WEIGHT:
        top = max(RANK_WEIGHT.values())
        if top > 0:
            for k in RANK_WEIGHT:
                RANK_WEIGHT[k] = max(1, int(RANK_WEIGHT[k] / top * 1000))
    return sites


def _host_weight(url):
    """A1-2：按子域角色给权重 —— www/api 重，静态/支持页轻。"""
    rw = RANK_WEIGHT.get(url)
    if rw:
        return rw
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return 3
    if host.startswith('www.') or host.startswith('api') or host.count('.') == 1:
        return 10
    if any(k in host for k in ('static', 'cdn', 'img', 'asset', 'support', 'about',
                               'help', 'investor', 'careers', 'legal', 'blog')):
        return 1
    return 3


if USE_TOP_LIST:
    _top = _load_top_list()
    if _top:
        WEBSITES = _top                       # 有榜单则完全替代硬编码表
        logger.info(f"已加载真实榜单 top1m.csv：{len(_top.get('TOP', []))} 个域名")


# ---------------------------------------------------------------------------
# 全局状态
# ---------------------------------------------------------------------------
request_counter = 0
error_counter = 0
counter_lock = threading.Lock()
stop_event = threading.Event()
executor = None
domain_status = {site: {'speed': 0, 'status': 'Idle', 'last_time': 0, 'size': 0} for site in WEBSITES}
status_lock = threading.Lock()
log_queue = Queue()
domain_fail_count = {}            # 每域名连续失败计数，用于自动剔除持续失效域名
sites_lock = threading.Lock()     # 保护 WEBSITES / domain_fail_count 的并发读写
FAIL_THRESHOLD = 3                # 连续失败达此次数即剔除该域名（DNS 错误立即剔除）

# 资源占用控制
MAX_WORKERS = 8                # 并发 worker 默认上限，降低对旁路由/ADG 的带宽与 DNS 日志扰动
MAX_BODY_BYTES = 256 * 1024    # 单次请求最多读取的响应体字节（流式），避免整页解压耗 CPU/内存
MAX_STREAM_BYTES = 50 * 1024 * 1024   # 单次"观看"最多拉取的字节，避免对测试视频 CDN 打流过猛
STREAM_PROB = 0.20             # 长连接(视频流)任务占比默认 20%，UI 可调
MAX_BULK_BYTES = 200 * 1024 * 1024    # C2：单次大文件持续下载上限
UPLOAD_PROB = 0.20             # C1：上传场景占 visit_one 的比例
BULK_DL_PROB = 0.05            # C2：大文件下载场景占比
INTERACTIVE_PROB = 0.12        # C3：小包高频交互场景占比
HTTPX_PROB = 0.70              # D1：走 httpx(h2/h3) 的概率，其余走 requests(h1.1)
CACHE_BUST = False             # E1：True 时才加 ?num= 强制穿透缓存（默认关，避免打穿 ADG 缓存）

# ---------------------------------------------------------------------------
# 软件信息 / GitHub 更新通道
# ---------------------------------------------------------------------------
APP_NAME = "拟真冲浪 RealSurf"
APP_VERSION = "1.3.1"
APP_UA = f"RealSurf/{APP_VERSION}"   # HTTP 头必须是 ASCII，绝不能用中文 APP_NAME（否则 latin-1 报错）
# 更新仓库（owner/repo）。构建/发布前由发布脚本填入真实 owner；
# 软件启动时查询该仓库的 latest release 判断是否有新版本。
UPDATE_REPO = "mmddxyg/realsurf"
GITHUB_API = "https://api.github.com"

# 启动自检：把运行环境写进 access_log.txt，方便现场排查
# （尤其确认打包后的 exe 里 httpx 到底有没有生效、h2/h3 通道是否可用）
logger.info(
    f"=== {APP_NAME} v{APP_VERSION} 启动 | Python {sys.version.split()[0]} | "
    f"frozen={getattr(sys, 'frozen', False)} | "
    f"httpx={'可用（h2/h3 通道启用）' if _HAS_HTTPX else '不可用（全部走 requests h1.1）'} | "
    f"缓存穿透={'开' if CACHE_BUST else '关'} | 品牌数={len(WEBSITES)}")


# ---------------------------------------------------------------------------
# 网络监控器：判断断联并自动恢复
# ---------------------------------------------------------------------------
class NetMonitor:
    def __init__(self, app):
        self.app = app
        self.outcomes = deque()          # (timestamp, ok)
        self.lock = threading.Lock()
        self.running = True
        self.window = 15.0               # 判定窗口（秒）
        self.min_attempts = 8            # 窗口内至少多少次尝试才判定
        self.probe_hosts = [
            "https://www.bilibili.com",
            "https://www.github.com",
            "https://www.gstatic.com/generate_204",
        ]

    def record(self, ok):
        with self.lock:
            self.outcomes.append((time.time(), ok))
            cutoff = time.time() - self.window
            while self.outcomes and self.outcomes[0][0] < cutoff:
                self.outcomes.popleft()

    def snapshot(self):
        with self.lock:
            return list(self.outcomes)

    def probe(self):
        """独立探测，确认网络是否真的恢复（不依赖 worker 上报）"""
        headers = {'User-Agent': random.choice([p['User-Agent'] for p in BROWSER_PROFILES])}
        for host in self.probe_hosts:
            try:
                _verify = getattr(self.app, 'params', {}).get('verify', True)
                r = self.app.session.get(host, timeout=10, verify=_verify,
                                         headers=headers)
                if r.status_code < 500:
                    return True
            except Exception:
                continue
        return False

    def run(self):
        while self.running and not stop_event.is_set():
            time.sleep(5)
            if stop_event.is_set():
                break
            items = self.snapshot()
            attempts = len(items)
            oks = sum(1 for _, o in items if o)

            if not self.app.network_down.is_set():
                # 正常态：窗口内失败率 100% 且样本足够 → 判定断联
                if attempts >= self.min_attempts and oks == 0:
                    self.app.network_down.set()
                    logger.warning("【断联】检测到网络中断，暂停发流并进入自动恢复等待…")
            else:
                # 断联态：独立探测，恢复后自动清除
                if self.probe():
                    self.app.network_down.clear()
                    logger.info("【恢复】网络已恢复，自动恢复正常访问。")
                else:
                    logger.info("【恢复中】探测仍未通，继续等待…")


# ---------------------------------------------------------------------------
# 主应用
# ---------------------------------------------------------------------------
class RealNetSimApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"{APP_NAME} v{APP_VERSION}")
        self.root.geometry("1000x800")
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        apply_app_icon(self.root)   # 任务栏/标题栏自定义图标
        # 关键：Tk 回调里的异常默认只在 stderr 打印，--noconsole 打包后完全不可见（=「点了没反应」）。
        # 统一接管，写日志并弹一次可见错误框，方便定位。
        self._cb_error_shown = False
        try:
            self.root.report_callback_exception = self._report_cb_exc
        except Exception:
            pass

        # UI 变量
        self.verify_var = tk.BooleanVar(value=True)          # 默认开启证书校验
        self.cachebust_var = tk.BooleanVar(value=CACHE_BUST)  # E1：默认关，勾选才加 ?num= 穿透缓存
        self.hx = None                                       # D1：httpx 通道（start_test 里创建）
        self.network_down = threading.Event()

        # 日志队列
        self.log_queue = Queue()
        self.queue_handler = QueueHandler(self.log_queue)
        self.queue_handler.setFormatter(
            logging.Formatter('%(asctime)s - %(threadName)s - %(levelname)s - %(message)s'))
        self.queue_handler.setLevel(logging.WARNING)   # 屏幕日志只显示告警/错误，降低 UI 刷新开销
        logger.addHandler(self.queue_handler)

        try:
            # 按配置(或 Windows 默认语言)确定界面语言
            cfg0 = self._load_config()
            lang0 = cfg0.get('language')
            if lang0 in I18N:
                set_language(lang0)
            set_lang_fonts()
            self.create_menu()
            self.create_widgets()
            self.update_log()
            self.update_chart()
            self.update_counters()
            # 启动后：默认弹出欢迎/关于窗口（含更新状态）；关闭后改为静默检查
            cfg = self._load_config()
            if cfg.get('show_welcome', True):
                self.root.after(800, self.show_about)
            else:
                threading.Thread(target=self._startup_check, daemon=True).start()
        except Exception as e:
            logger.error(f"初始化 UI 失败: {traceback.format_exc()}")
            messagebox.showerror(_("err_title"), _("init_fail", e=e))
            sys.exit(1)

    def _report_cb_exc(self, exc, val, tb):
        """接管 Tk 主线程回调里的未捕获异常：写日志 + 只弹一次可见错误框。"""
        try:
            logger.error("Tk 回调异常: %s\n%s", val, "".join(traceback.format_exception(exc, val, tb)))
        except Exception:
            pass
        if getattr(self, '_cb_error_shown', False):
            return
        self._cb_error_shown = True
        try:
            messagebox.showerror(_("err_title"), f"{val}")
        except Exception:
            pass

    # ---- 菜单 ----
    def create_menu(self):
        menubar = tk.Menu(self.root, tearoff=0)
        self.root.config(menu=menubar)
        self.menubar = menubar
        # 文件
        file_menu = tk.Menu(menubar, tearoff=0)
        self.file_menu = file_menu
        menubar.add_cascade(label=_("menu_file"), menu=file_menu)
        file_menu.add_command(label=_("menu_sites"), command=self.open_domain_editor)
        file_menu.add_command(label=_("menu_export"), command=self.export_sites)
        file_menu.add_separator()
        file_menu.add_command(label=_("menu_exit"), command=self.on_closing)
        # 语言子菜单
        lang_menu = tk.Menu(menubar, tearoff=0)
        self.lang_menu = lang_menu
        lang_menu.add_command(label=_("lang_zh"), command=lambda: self.switch_language('zh'))
        lang_menu.add_command(label=_("lang_en"), command=lambda: self.switch_language('en'))
        lang_menu.add_command(label=_("lang_vi"), command=lambda: self.switch_language('vi'))
        menubar.add_cascade(label=_("menu_language"), menu=lang_menu)
        # 帮助（检查更新 / 关于）
        help_menu = tk.Menu(menubar, tearoff=0)
        self.help_menu = help_menu
        menubar.add_cascade(label=_("menu_help"), menu=help_menu)
        help_menu.add_command(label=_("menu_check_update"), command=self.check_update_ui)
        help_menu.add_command(label=_("menu_about"), command=self.show_about)

    # ---- 控件 ----
    def create_widgets(self):
        main_frame = ttkb.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky="nsew")
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        # 输入框架
        input_frame = ttkb.Frame(main_frame, padding="10")
        input_frame.grid(row=0, column=0, sticky="ew")

        self.threads_label = ttkb.Label(input_frame, text=_("lbl_threads"), font=(UI_FONT, 12))
        self.threads_label.grid(row=0, column=0, padx=5)
        self.threads_entry = ttkb.Entry(input_frame, width=5, font=(UI_FONT, 12))
        self.threads_entry.insert(0, "8")
        self.threads_entry.grid(row=0, column=1, padx=5)

        self.interval_label = ttkb.Label(input_frame, text=_("lbl_interval"), font=(UI_FONT, 12))
        self.interval_label.grid(row=0, column=2, padx=5)
        self.interval_entry = ttkb.Entry(input_frame, width=5, font=(UI_FONT, 12))
        self.interval_entry.insert(0, "10")
        self.interval_entry.grid(row=0, column=3, padx=5)

        self.verify_check = ttkb.Checkbutton(
            input_frame, text=_("chk_verify"),
            variable=self.verify_var, bootstyle="round-toggle")
        self.verify_check.grid(row=0, column=4, padx=10)

        # 布局修复：原来 9 个控件全挤在一行，默认 1000px 窗口下「长连接比例」
        # 和「单次观看」会被右边缘裁掉（参数改不了 = 功能不可用）。拆成两行。
        self.stream_prob_label = ttkb.Label(input_frame, text=_("lbl_stream_prob"), font=(UI_FONT, 12))
        self.stream_prob_label.grid(row=1, column=0, padx=5, pady=(6, 0), sticky="w")
        self.stream_prob_entry = ttkb.Entry(input_frame, width=5, font=(UI_FONT, 12))
        self.stream_prob_entry.insert(0, "20")
        self.stream_prob_entry.grid(row=1, column=1, padx=5, pady=(6, 0))

        self.stream_dur_label = ttkb.Label(input_frame, text=_("lbl_stream_dur"), font=(UI_FONT, 12))
        self.stream_dur_label.grid(row=1, column=2, padx=5, pady=(6, 0), sticky="w")
        self.stream_dur_entry = ttkb.Entry(input_frame, width=5, font=(UI_FONT, 12))
        self.stream_dur_entry.insert(0, "45")
        self.stream_dur_entry.grid(row=1, column=3, padx=5, pady=(6, 0))


        # 按钮框架
        button_frame = ttkb.Frame(main_frame, padding="10")
        button_frame.grid(row=1, column=0, sticky="ew")

        self.start_button = ttkb.Button(button_frame, text=_("btn_start"), command=self.start_test, bootstyle=PRIMARY)
        self.start_button.grid(row=0, column=0, padx=5)
        self.stop_button = ttkb.Button(button_frame, text=_("btn_stop"), command=self.stop_test,
                                       state="disabled", bootstyle=DANGER)
        self.stop_button.grid(row=0, column=1, padx=5)

        # E1：缓存穿透开关（默认关，避免打穿 ADG 缓存）
        self.cachebust_check = ttkb.Checkbutton(
            button_frame, text=_("chk_cachebust"),
            variable=self.cachebust_var, bootstyle="round-toggle")
        self.cachebust_check.grid(row=0, column=2, padx=10)


        # 状态框架
        status_frame = ttkb.Frame(main_frame, padding="10")
        status_frame.grid(row=2, column=0, sticky="ew")

        self.request_label = ttkb.Label(status_frame, text=_("lbl_requests", n=0), font=(UI_FONT, 12))
        self.request_label.grid(row=0, column=0, padx=5)
        self.error_label = ttkb.Label(status_frame, text=_("lbl_errors", n=0), font=(UI_FONT, 12))
        self.error_label.grid(row=0, column=1, padx=5)
        self.net_label = ttkb.Label(status_frame, text=_("net_ok"), font=(UI_FONT, 12),
                                    bootstyle="success")
        self.net_label.grid(row=0, column=2, padx=15)

        # 日志显示
        self.log_text = scrolledtext.ScrolledText(main_frame, height=10, width=90,
                                                  state="disabled", font=(UI_FONT, 10))
        self.log_text.grid(row=3, column=0, padx=10, pady=10, sticky="nsew")

        # 图表
        self.fig, self.ax = plt.subplots(figsize=(8, 4))
        self.canvas = FigureCanvasTkAgg(self.fig, master=main_frame)
        self.canvas.get_tk_widget().grid(row=4, column=0, padx=10, pady=10, sticky="nsew")
        main_frame.grid_rowconfigure(4, weight=1)
        main_frame.grid_columnconfigure(0, weight=1)

    # ---- 站点编辑器 ----
    def open_domain_editor(self):
        # 避免重复打开多个编辑窗口
        if getattr(self, 'editor_window', None) and self.editor_window.winfo_exists():
            self.editor_window.lift()
            self.editor_window.focus_force()
            return
        editor_window = Toplevel(self.root)
        editor_window.title(_("editor_title"))
        editor_window.geometry("860x640")
        editor_window.minsize(720, 480)
        self.editor_window = editor_window

        # 顶部提示
        tip = ttkb.Label(editor_window, text=_("editor_tip"),
                         font=(UI_FONT, 10), bootstyle="secondary")
        tip.pack(side="top", fill="x", padx=10, pady=(6, 0))

        # 列表 + 滚动条
        list_frame = ttkb.Frame(editor_window)
        list_frame.pack(side="top", fill="both", expand=True, padx=10, pady=6)
        self.domain_listbox = ttkb.Treeview(list_frame, columns=("Site", "Domain"),
                                            show="headings", selectmode="extended")
        self.domain_listbox.heading("Site", text=_("col_site"))
        self.domain_listbox.heading("Domain", text=_("col_domain"))
        self.domain_listbox.column("Site", width=200, anchor="w")
        self.domain_listbox.column("Domain", width=560, anchor="w")
        self.domain_listbox.pack(side="left", fill="both", expand=True)
        scroll = ttkb.Scrollbar(list_frame, orient="vertical", command=self.domain_listbox.yview)
        scroll.pack(side="right", fill="y")
        self.domain_listbox.configure(yscrollcommand=scroll.set)

        # 操作按钮栏
        btn_frame = ttkb.Frame(editor_window, padding=(10, 4))
        btn_frame.pack(side="top", fill="x")
        self.editor_btn_del = ttkb.Button(btn_frame, text=_("btn_del_sel"), command=self.delete_domains,
                    bootstyle=DANGER)
        self.editor_btn_del.pack(side="left", padx=4)
        self.editor_btn_all = ttkb.Button(btn_frame, text=_("btn_select_all"), command=self._select_all_domains,
                    bootstyle=INFO)
        self.editor_btn_all.pack(side="left", padx=4)
        self.editor_btn_desel = ttkb.Button(btn_frame, text=_("btn_deselect"),
                    command=lambda: self.domain_listbox.selection_remove(
                        *self.domain_listbox.selection()),
                    bootstyle=INFO)
        self.editor_btn_desel.pack(side="left", padx=4)
        self.editor_btn_exp = ttkb.Button(btn_frame, text=_("btn_export"), command=self.export_sites,
                    bootstyle=OUTLINE)
        self.editor_btn_exp.pack(side="left", padx=4)
        self.editor_btn_ref = ttkb.Button(btn_frame, text=_("btn_refresh"), command=self.update_domain_list,
                    bootstyle=OUTLINE)
        self.editor_btn_ref.pack(side="left", padx=4)
        self.editor_btn_close = ttkb.Button(btn_frame, text=_("btn_close"), command=editor_window.destroy,
                    bootstyle=SECONDARY)
        self.editor_btn_close.pack(side="right", padx=4)

        # 新增网站输入栏
        add_frame = ttkb.Frame(editor_window, padding=(10, 8))
        add_frame.pack(side="top", fill="x")
        self.editor_site_lbl = ttkb.Label(add_frame, text=_("lbl_site_name"), font=(UI_FONT, 12))
        self.editor_site_lbl.pack(side="left", padx=5)
        self.site_name_entry = ttkb.Entry(add_frame, width=16, font=(UI_FONT, 12))
        self.site_name_entry.pack(side="left", padx=5)
        self.editor_dom_lbl = ttkb.Label(add_frame, text=_("lbl_domains"), font=(UI_FONT, 12))
        self.editor_dom_lbl.pack(side="left", padx=5)
        self.domain_list_entry = ttkb.Entry(add_frame, width=36, font=(UI_FONT, 12))
        self.domain_list_entry.pack(side="left", padx=5, fill="x", expand=True)
        self.editor_btn_add = ttkb.Button(add_frame, text=_("btn_add"), command=self.add_domain,
                    bootstyle=SUCCESS)
        self.editor_btn_add.pack(side="left", padx=5)

        # 右键菜单 + 键盘快捷键
        context_menu = tk.Menu(self.domain_listbox, tearoff=0)
        context_menu.add_command(label=_("ctx_del"), command=self.delete_domains)
        self.domain_listbox.bind("<Button-3>",
                                 lambda event: context_menu.post(event.x_root, event.y_root))
        self.domain_listbox.bind("<Delete>", lambda e: self.delete_domains())
        self.domain_listbox.bind("<Control-a>", lambda e: self._select_all_domains())
        self.domain_listbox.bind("<Control-A>", lambda e: self._select_all_domains())
        self.domain_list_entry.bind("<Return>", lambda e: self.add_domain())

        editor_window.protocol("WM_DELETE_WINDOW", editor_window.destroy)
        self.update_domain_list()

    def delete_domains(self):
        try:
            if not hasattr(self, 'domain_listbox') or not self.domain_listbox.winfo_exists():
                return
            selected = self.domain_listbox.selection()
            if not selected:
                messagebox.showwarning(_("warn_title"), _("warn_select"))
                return
            # 批量删除前先确认，避免误删
            if not messagebox.askyesno(_("confirm_del_title"),
                                       _("confirm_del", n=len(selected))):
                return
            for item in selected:
                site_name, domain = self.domain_listbox.item(item, "values")
                if site_name in WEBSITES and domain in WEBSITES[site_name]:
                    WEBSITES[site_name].remove(domain)
                    logger.info(f"删除域名: {site_name} - {domain}")
                    if not WEBSITES[site_name]:
                        del WEBSITES[site_name]
                        if site_name in domain_status:
                            del domain_status[site_name]
            self.update_domain_list()
            self.update_chart()
        except Exception as e:
            logger.error(f"删除域名失败: {traceback.format_exc()}")
            messagebox.showerror(_("err_title"), _("err_del_fail", e=e))

    def _select_all_domains(self):
        try:
            self.domain_listbox.selection_set(*self.domain_listbox.get_children())
        except Exception:
            pass

    def add_domain(self):
        try:
            site_name = self.site_name_entry.get().strip()
            domain_list = [d.strip() for d in self.domain_list_entry.get().split(',') if d.strip()]
            if not site_name or not domain_list:
                messagebox.showerror(_("err_title"), _("err_site_name"))
                return
            for i, domain in enumerate(domain_list):
                if not domain.startswith(('http://', 'https://')):
                    domain_list[i] = f"https://{domain}"
            if site_name in WEBSITES:
                WEBSITES[site_name].extend(domain_list)
            else:
                WEBSITES[site_name] = domain_list
                domain_status[site_name] = {'speed': 0, 'status': 'Idle', 'last_time': 0, 'size': 0}
            logger.info(f"添加网站: {site_name}, 域名: {domain_list}")
            self.site_name_entry.delete(0, tk.END)
            self.domain_list_entry.delete(0, tk.END)
            self.update_domain_list()
            self.update_chart()
        except Exception as e:
            logger.error(f"添加域名失败: {traceback.format_exc()}")
            messagebox.showerror(_("err_title"), _("err_add_fail", e=e))

    def export_sites(self):
        try:
            with open("sites_export.json", "w", encoding="utf-8") as f:
                json.dump(WEBSITES, f, ensure_ascii=False, indent=2)
            messagebox.showinfo(_("export_ok_title"), _("export_ok"))
        except Exception as e:
            messagebox.showerror(_("err_title"), _("err_export", e=e))

    # ---- 日志/图表/计数 刷新 ----
    def update_log(self):
        try:
            while not self.log_queue.empty():
                msg = self.log_queue.get()
                self.log_text.configure(state="normal")
                self.log_text.insert(tk.END, msg + "\n")
                self.log_text.see(tk.END)
                self.log_text.configure(state="disabled")
            self.root.after(100, self.update_log)
        except Exception:
            pass

    @staticmethod
    def _status_color(status):
        if status.startswith("OK"):
            return '#2e7d32'          # 绿
        if status in ('Idle',):
            return '#9e9e9e'          # 灰
        if status.startswith('Error') or status.startswith('E') or status.startswith('SSL') \
                or status.startswith('DNS'):
            return '#c62828'          # 红
        return '#ef6c00'              # 橙（Timeout 等）

    def update_chart(self):
        try:
            with status_lock:
                # 过滤掉从未被访问过的 Idle 站点，避免图表被一堆 0 高度灰条刷屏
                items = [(s, domain_status[s]) for s in domain_status
                         if domain_status[s]['status'] != 'Idle']
                sites = [s for s, _ in items]
                speeds = [d['speed'] for _, d in items]
                statuses = [d['status'] for _, d in items]

            if not sites:
                self.ax.clear()
                self.ax.set_title(_('chart_title_idle'), fontproperties=CHART_FONT)
                self.fig.tight_layout()
                self.canvas.draw()
                if not stop_event.is_set():
                    self.root.after(8000, self.update_chart)
                return

            self.ax.clear()
            colors = [self._status_color(st) for st in statuses]
            bars = self.ax.bar(sites, speeds, color=colors)
            self.ax.set_ylabel(_('chart_ylabel'), fontproperties=CHART_FONT)
            self.ax.set_title(_('chart_title'), fontproperties=CHART_FONT)
            self.ax.tick_params(axis='x', labelrotation=45, labelsize=7)

            for bar, status in zip(bars, statuses):
                height = bar.get_height()
                self.ax.text(bar.get_x() + bar.get_width() / 2, height, status,
                             ha='center', va='bottom', rotation=45, fontsize=6)
            self.fig.tight_layout()
            self.canvas.draw()
            if not stop_event.is_set():
                self.root.after(8000, self.update_chart)
        except Exception as e:
            logger.error(f"更新图表失败: {traceback.format_exc()}")

    def update_counters(self):
        try:
            self.request_label.configure(text=_("lbl_requests", n=request_counter))
            self.error_label.configure(text=_("lbl_errors", n=error_counter))
            if self.network_down.is_set():
                self.net_label.configure(text=_("net_down"), bootstyle="danger")
            else:
                self.net_label.configure(text=_("net_ok"), bootstyle="success")
            if not stop_event.is_set():
                self.root.after(1000, self.update_counters)
        except Exception:
            pass

    def update_domain_list(self):
        try:
            if hasattr(self, 'domain_listbox'):
                self.domain_listbox.delete(*self.domain_listbox.get_children())
                for site, domains in WEBSITES.items():
                    for domain in domains:
                        self.domain_listbox.insert("", "end", values=(site, domain))
        except Exception as e:
            logger.error(f"更新域名列表失败: {traceback.format_exc()}")

    # ---- 失败处理：累计失败次数，达到阈值即剔除持续失效域名 ----
    def _on_fail(self, site_name, url, msg, retry_sleep=1, force_drop=False, warn_if_verify=None):
        global error_counter
        with counter_lock:
            error_counter += 1
        logger.error(msg)
        if warn_if_verify and self.params.get('verify', False):
            logger.warning(warn_if_verify)
        time.sleep(retry_sleep)
        with sites_lock:
            if force_drop or domain_fail_count.get(url, 0) + 1 >= FAIL_THRESHOLD:
                if site_name in WEBSITES and url in WEBSITES[site_name]:
                    WEBSITES[site_name].remove(url)
                    logger.warning(f"剔除持续失效域名: {site_name} - {url}")
                    if not WEBSITES[site_name]:
                        del WEBSITES[site_name]
                        domain_status.pop(site_name, None)
                domain_fail_count.pop(url, None)
            else:
                domain_fail_count[url] = domain_fail_count.get(url, 0) + 1

    # ---- D1：统一请求层（httpx http2/h3 ↔ requests h1.1，接口归一） ----
    @staticmethod
    def _is_hx(resp):
        """判断响应是否来自 httpx（httpx 用 iter_bytes，requests 用 iter_content）。"""
        return _HAS_HTTPX and httpx is not None and isinstance(resp, httpx.Response)

    def _iter_chunks(self, resp, size=16384):
        """统一分块读取：屏蔽 httpx/requests 的接口差异。"""
        if self._is_hx(resp):
            return resp.iter_bytes(size)
        return resp.iter_content(size)

    def _close_resp(self, resp):
        try:
            resp.close()
        except Exception:
            pass

    def _get(self, url, session, headers=None, timeout=30):
        """D1：按概率分流 —— httpx(h2/h3) 优先，其余 requests(h1.1)。
        任何异常都自动回退 requests，保证功能不受影响。"""
        h = headers if headers is not None else dict(random.choice(BROWSER_PROFILES))
        hx = getattr(self, 'hx', None)
        if hx is not None and random.random() < HTTPX_PROB:
            try:
                req = hx.build_request('GET', url, headers=h, timeout=timeout)
                return hx.send(req, stream=True)
            except Exception as e:
                logger.debug(f"httpx GET 失败，回退 requests: {e}")
        return session.get(url, headers=h, timeout=timeout,
                           verify=self.params.get('verify', True), stream=True)

    def _post(self, url, session, data=None, headers=None, timeout=30):
        """D1：上传/表单用 POST，同样支持 httpx 分流与回退。"""
        h = headers if headers is not None else dict(random.choice(BROWSER_PROFILES))
        hx = getattr(self, 'hx', None)
        if hx is not None and random.random() < HTTPX_PROB:
            try:
                req = hx.build_request('POST', url, content=data, headers=h, timeout=timeout)
                return hx.send(req, stream=True)
            except Exception as e:
                logger.debug(f"httpx POST 失败，回退 requests: {e}")
        return session.post(url, data=data, timeout=timeout, headers=h,
                            verify=self.params.get('verify', True), stream=True)

    # ---- C1：上传场景（表单 / 媒体 / 大文件三档） ----
    def _upload(self, site_name, session):
        """模拟上传：给 Smart 组补充上行侧样本。返回大致上行字节数。"""
        global request_counter, error_counter
        with sites_lock:
            urls = list(WEBSITES.get(site_name, []))
        if not urls:
            return 0
        target = random.choice(urls)
        tier = random.choices(['form', 'media', 'bulk'], weights=[60, 30, 10], k=1)[0]
        sent = 0
        try:
            if tier == 'form':
                payload = os.urandom(random.randint(10 * 1024, 100 * 1024))
                sent = len(payload)
                r = self._post(target, session, data=payload, timeout=20)
                self._close_resp(r)
            elif tier == 'media':
                payload = os.urandom(random.randint(1 * 1024 * 1024, 5 * 1024 * 1024))
                sent = len(payload)
                r = self._post(target, session, data=payload, timeout=40)
                self._close_resp(r)
            else:  # bulk：持续写，模拟网盘/云备份
                total = min(random.randint(20, 100) * 1024 * 1024, MAX_BULK_BYTES)
                chunk = 256 * 1024
                state = {'n': 0}

                def _gen():
                    while state['n'] < total and not stop_event.is_set():
                        n = min(chunk, total - state['n'])
                        state['n'] += n
                        yield os.urandom(n)
                        time.sleep(random.uniform(0.02, 0.08))   # 限速，别打满上行

                r = self._post(target, session, data=_gen(), timeout=120)
                self._close_resp(r)
                sent = state['n']
            with counter_lock:
                request_counter += 1
        except _REQUEST_ERRORS:
            with counter_lock:
                error_counter += 1
        except Exception as e:
            logger.warning(f"上传场景异常 {site_name}: {e}")
        return sent

    # ---- C2：大文件持续下载（非视频：网盘 / 驱动 / 更新包） ----
    def _bulk_download(self, site_name, session):
        global request_counter, error_counter
        with sites_lock:
            urls = list(WEBSITES.get(site_name, []))
        if not urls:
            return
        url = random.choice(urls)
        target = min(random.randint(20, 100) * 1024 * 1024, MAX_BULK_BYTES)
        total = 0
        try:
            r = self._get(url, session, timeout=60)
            try:
                for chunk in self._iter_chunks(r, 65536):
                    total += len(chunk)
                    if total >= target or stop_event.is_set():
                        break
            finally:
                self._close_resp(r)
            with counter_lock:
                request_counter += 1
        except _REQUEST_ERRORS:
            with counter_lock:
                error_counter += 1

    # ---- C3：交互场景（小包高频：IM / 游戏心跳 / 长轮询） ----
    def _interactive(self, site_name, session, burst=8):
        global request_counter
        with sites_lock:
            urls = list(WEBSITES.get(site_name, []))
        if not urls:
            return
        target = random.choice(urls)
        for _ in range(random.randint(3, burst)):
            if stop_event.is_set() or self.network_down.is_set():
                break
            try:
                r = self._get(target, session, timeout=8)
                try:
                    for _c in self._iter_chunks(r, 512):
                        break
                finally:
                    self._close_resp(r)
                with counter_lock:
                    request_counter += 1
            except _REQUEST_ERRORS:
                pass
            time.sleep(random.uniform(0.2, 1.0))

    # ---- E2：HLS/DASH 分片拉取（变长分片 + 并行 2~4 路，模拟码率自适应） ----
    def _fetch_text(self, url, session, timeout=15):
        """拉取清单文本，返回 (文本, HTTP状态码)；失败返回 (None, 0)。"""
        try:
            r = self._get(url, session, timeout=timeout)
            try:
                body = r.read() if self._is_hx(r) else r.content
                code = getattr(r, 'status_code', 0)
            finally:
                self._close_resp(r)
            with counter_lock:
                global request_counter
                request_counter += 1
            return body.decode('utf-8', 'ignore'), code
        except Exception:
            return None, 0

    @staticmethod
    def _parse_m3u8(body, base):
        """解析 m3u8，返回 (媒体分片, 子清单, 初始化段)。

        注意：测试源给的都是**主清单**，里面列的是各清晰度的子清单
        （条目本身还是 .m3u8），不是 .ts 分片。只按"非 # 行"当分片下，
        实际只会下到几个几 KB 的文本文件（≈0 流量）—— 必须做两级解析。
        """
        def _abs(u):
            return u if u.startswith('http') else base + u

        maps, entries = [], []
        for line in body.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith('#EXT-X-MAP'):
                m = re.search(r'URI="([^"]+)"', line)
                if m:
                    maps.append(_abs(m.group(1)))
                continue
            if line.startswith('#'):
                continue
            entries.append(_abs(line))
        variants = [u for u in entries if '.m3u8' in u.split('?')[0].lower()]
        media = [u for u in entries if u not in variants]
        return media, variants, maps

    def _stream_hls(self, m3u8_url, session, seconds, max_bytes):
        """按 manifest 拉分片（支持 主清单 → 子清单 → 媒体分片 两级）。

        返回 (累计字节数, 清单 HTTP 状态码)。
        """
        body, code = self._fetch_text(m3u8_url, session)
        if not body:
            return 0.0, code
        base = m3u8_url.rsplit('/', 1)[0] + '/'
        media, variants, maps = self._parse_m3u8(body, base)

        if not media and variants:
            # 主清单：随机挑一个清晰度子清单，再解析出真正的媒体分片
            v = random.choice(variants)
            vbody, vcode = self._fetch_text(v, session)
            if vbody:
                code = vcode or code
                m2, _, map2 = self._parse_m3u8(vbody, v.rsplit('/', 1)[0] + '/')
                if m2:
                    media = m2
                if map2:
                    maps = map2 + maps
        if not media:
            return 0.0, code

        # 真实播放器行为：先取初始化段（fMP4/DASH 的 moov），再顺序拉分片
        total = [0.0]
        deadline = time.time() + seconds

        def _fetch(u):
            if time.time() > deadline or total[0] >= max_bytes or stop_event.is_set():
                return
            try:
                rr = self._get(u, session, timeout=20)
                try:
                    for c in self._iter_chunks(rr, 32768):
                        total[0] += len(c)
                        if total[0] >= max_bytes:
                            break
                finally:
                    self._close_resp(rr)
                with counter_lock:
                    global request_counter
                    request_counter += 1
            except _REQUEST_ERRORS:
                pass

        # 初始化段（若清单里有 EXT-X-MAP）
        if maps:
            with ThreadPoolExecutor(max_workers=min(2, len(maps))) as ex:
                list(ex.map(_fetch, maps[:2]))

        # 变长分片 + 并行 2~4 路
        while time.time() < deadline and total[0] < max_bytes and media:
            if stop_event.is_set():
                break
            k = random.randint(2, 4)
            batch = [media.pop(0) for _ in range(min(k, len(media)))]
            with ThreadPoolExecutor(max_workers=k) as ex:
                list(ex.map(_fetch, batch))
            time.sleep(random.uniform(0.2, 1.2))
        return total[0], code


    # ---- 页面簇发（P1：模拟真实页面加载多个兄弟子资源，还原簇发形态） ----
    def _page_burst(self, site_name, base_url, session):
        """B1：真并发拉取同品牌兄弟子域（原实现是串行 + 0.3~1.2s 间隔，
        形态上根本不是"簇发"）。单资源上限提到 512KB，更接近真实页面资源量。"""
        with sites_lock:
            sibs = [u for u in WEBSITES.get(site_name, []) if u != base_url]
        if not sibs:
            return
        n = min(random.randint(6, 15), len(sibs))
        targets = random.sample(sibs, n)

        def _one(u):
            if stop_event.is_set() or self.network_down.is_set():
                return
            try:
                r = self._get(u, session, timeout=15)
                try:
                    tot = 0
                    for chunk in self._iter_chunks(r, 16384):
                        tot += len(chunk)
                        if tot >= 512 * 1024:
                            break
                finally:
                    self._close_resp(r)
                with counter_lock:
                    global request_counter
                    request_counter += 1
            except _REQUEST_ERRORS:
                pass

        with ThreadPoolExecutor(max_workers=min(n, 8)) as ex:
            list(ex.map(_one, targets))


    # ---- 单次访问（真实浏览器模拟，流式读取，限制体积） ----
    def visit_one(self, site_name, session):
        global request_counter, error_counter
        # 复制一份站点列表再选，避免与"剔除失效域名"并发修改冲突
        with sites_lock:
            urls = list(WEBSITES.get(site_name, []))
        if not urls:
            return

        # C1：上传场景（表单/媒体/大文件，整体 ~20%）
        if random.random() < UPLOAD_PROB:
            try:
                self._upload(site_name, session)
            except Exception as e:
                logger.debug(f"上传场景异常: {e}")
        # C2：大文件持续下载场景（~5%）
        if random.random() < BULK_DL_PROB:
            try:
                self._bulk_download(site_name, session)
            except Exception as e:
                logger.debug(f"大文件下载异常: {e}")
        # C3：小包高频交互场景（~12%）
        if random.random() < INTERACTIVE_PROB:
            try:
                self._interactive(site_name, session)
            except Exception as e:
                logger.debug(f"交互场景异常: {e}")

        # A1-2：按子域角色加权选 URL（www/api 重，静态/支持页轻）
        url = random.choices(urls, weights=[_host_weight(u) for u in urls], k=1)[0]
        # E1：?num= 缓存穿透改成开关，默认关闭（原实现每次都加，直接把 ADG 缓存打穿，
        # 反而破坏了"预热缓存"这个初衷）
        if CACHE_BUST:
            req_url = f"{url}{'?num=' if '?' not in url else '&num='}{request_counter}"
        else:
            req_url = url
        profile = dict(random.choice(BROWSER_PROFILES))
        profile['Referer'] = url
        if random.random() < 0.3:
            profile['Cache-Control'] = 'max-age=0'
        start_time = time.time()
        size = 0.0
        status = 'Idle'
        ok = False
        response = None
        try:
            # 流式读取，最多 MAX_BODY_BYTES，避免整页解压占用大量 CPU/内存
            response = self._get(req_url, session, headers=profile, timeout=30)
            try:
                for chunk in self._iter_chunks(response, 16384):
                    size += len(chunk)
                    if size >= MAX_BODY_BYTES:
                        break
            finally:
                self._close_resp(response)
            with counter_lock:
                request_counter += 1
            # S2：ok 语义收窄 —— 只有 2xx/3xx 才算成功。
            # 原实现"没抛异常就 True"，把 403/404/500 也标成成功，样本标签是错的。
            code = getattr(response, 'status_code', 0)
            ok = 200 <= code < 400
            # B1：页面簇发概率 0.4 → 0.9（真实页面几乎必然并发拉取子资源）
            if random.random() < 0.9:
                try:
                    self._page_burst(site_name, url, session)
                except Exception as e:
                    logger.debug(f"page burst 异常: {e}")
            with sites_lock:
                domain_fail_count.pop(url, None)   # 成功：清零该域名失败计数
            if code == 429:
                logger.warning(f"触发 429 限流 {site_name}，额外等待 5 秒")
                time.sleep(5)
                status = "OK (429)"
            else:
                status = f"OK ({code})" if 200 <= code < 400 else f"Error ({code})"
        except requests.exceptions.SSLError as e:
            self._on_fail(site_name, url, f"SSL 错误 {site_name} ({req_url}): {e} - 跳过",
                          retry_sleep=1 if not self.params.get('verify', False) else 3,
                          warn_if_verify="证书错误：如走代理 TLS 拦截，请勾选「跳过证书校验」")
            status = 'SSL Error'
        except requests.exceptions.ConnectTimeout as e:
            self._on_fail(site_name, url, f"连接超时 {site_name} ({req_url}): {e} - 重试", retry_sleep=2)
            status = 'Timeout'
        except requests.exceptions.ReadTimeout as e:
            self._on_fail(site_name, url, f"读取超时 {site_name} ({req_url}): {e} - 跳过", retry_sleep=1)
            status = 'Timeout'
        except requests.exceptions.ConnectionError as e:
            # DNS 解析失败 = 域名已死，立即剔除（不再走慢路径阈值）
            if is_dns_error(e):
                self._on_fail(site_name, url, f"域名解析失败 {site_name} ({req_url}): {e} - 剔除该域名",
                              force_drop=True)
                status = 'DNS Error'
            else:
                self._on_fail(site_name, url, f"连接错误 {site_name} ({req_url}): {e} - 等待恢复", retry_sleep=2)
                status = 'ConnErr'
        except _REQUEST_ERRORS as e:
            # 其余 requests 异常 + 全部 httpx(h2/h3) 异常走这里
            self._on_fail(site_name, url, f"其他请求错误 {site_name} ({req_url}): {e} - 跳过", retry_sleep=1)
            status = 'Error'
        finally:
            duration = time.time() - start_time
            speed = size / duration if duration > 0 else 0
            with status_lock:
                domain_status[site_name] = {'speed': speed, 'status': status,
                                            'last_time': time.time(), 'size': size}
            if hasattr(self, 'monitor'):
                self.monitor.record(ok)


    # ---- 长连接(视频流)会话：模拟真人看视频 ----
    def stream_session(self, session):
        global request_counter, error_counter
        try:
            stream_seconds = float(self.params['stream_dur'])
            stream_seconds = max(20.0, min(stream_seconds, 120.0))
        except (ValueError, KeyError):
            stream_seconds = 45.0
        target = random.choice(STREAM_SITES)
        is_mp4 = target.get('mp4', False)
        host = target['host']
        url = target['url']
        start_time = time.time()
        ok = False
        total = 0.0
        status = 'Idle'
        try:
            profile = dict(random.choice(BROWSER_PROFILES))
            # E2：优先走 HLS/DASH 分片形态（真实流媒体就是 m3u8 + 一堆 .ts/.m4s 分片，
            # 原来的"单 mp4 打 Range"形态太干净，骗不过 Smart 的特征工程）
            if STREAM_M3U8 and random.random() < HLS_PROB:
                hls_url = random.choice(STREAM_M3U8)
                url = hls_url
                total, _code = self._stream_hls(hls_url, session, stream_seconds,
                                                MAX_STREAM_BYTES)
                ok = total > 0
                status = f"HLS {int(total / 1024 / 1024)}MB" if total > 0 else 'StreamErr'
            elif is_mp4:
                # 像视频播放器一样：Range 分段顺序拉取，段间有缓冲间隙
                profile['Sec-Fetch-Dest'] = 'video'
                profile['Sec-Fetch-Mode'] = 'cors'
                profile['Sec-Fetch-Site'] = 'cross-site'
                profile['Accept'] = '*/*'
                pos = 0
                seg = 1024 * 1024            # 每段 1MB，模拟自适应码率切片
                while (not stop_event.is_set() and not self.network_down.is_set()
                       and time.time() - start_time < stream_seconds
                       and total < MAX_STREAM_BYTES):
                    if stop_event.is_set() or self.network_down.is_set():
                        break
                    end = pos + seg - 1
                    req_headers = dict(profile)
                    req_headers['Range'] = f'bytes={pos}-{end}'
                    try:
                        r = self._get(url, session, headers=req_headers, timeout=30)
                        try:
                            for chunk in self._iter_chunks(r, 16384):
                                total += len(chunk)
                                if total >= MAX_STREAM_BYTES:
                                    break
                        finally:
                            self._close_resp(r)
                        with counter_lock:
                            request_counter += 1
                        ok = 200 <= getattr(r, 'status_code', 0) < 400 or ok
                    except _REQUEST_ERRORS as e:
                        with counter_lock:
                            error_counter += 1
                        logger.error(f"长连接分段错误 {host}: {e}")
                        status = 'StreamErr'
                        time.sleep(2)
                        break
                    pos = end + 1
                    time.sleep(random.uniform(1.0, 4.0))   # 模拟缓冲/卡顿间隙
                status = f"STREAM {int(total / 1024 / 1024)}MB"
            else:
                # 视频平台：打开观看页 → 看一会儿（零星子资源请求）
                profile['Sec-Fetch-Dest'] = 'document'
                try:
                    r = self._get(url, session, headers=profile, timeout=30)
                    try:
                        for chunk in self._iter_chunks(r, 16384):
                            total += len(chunk)
                            if total >= 512 * 1024:
                                break
                    finally:
                        self._close_resp(r)
                    with counter_lock:
                        request_counter += 1
                    ok = 200 <= getattr(r, 'status_code', 0) < 400
                except _REQUEST_ERRORS as e:
                    with counter_lock:
                        error_counter += 1
                    logger.error(f"长连接页面错误 {host}: {e}")
                    status = 'StreamErr'
                # 观看中的零星请求（缩略图/心跳），带真实间隔
                for _ in range(random.randint(2, 5)):
                    if stop_event.is_set() or self.network_down.is_set():
                        break
                    if time.time() - start_time > stream_seconds:
                        break
                    subs = target.get('subs', [])
                    if not subs:
                        break
                    sub = random.choice(subs)
                    try:
                        sr = self._get(sub, session, timeout=20)
                        try:
                            tot = 0
                            for chunk in self._iter_chunks(sr, 16384):
                                tot += len(chunk)
                                if tot >= 256 * 1024:
                                    break
                        finally:
                            self._close_resp(sr)
                        with counter_lock:
                            request_counter += 1
                    except _REQUEST_ERRORS:
                        pass
                    time.sleep(random.uniform(2.0, 6.0))
                status = "WATCH"
        finally:
            duration = time.time() - start_time
            with status_lock:
                domain_status[host] = {'speed': total / duration if duration > 0 else 0,
                                       'status': status, 'last_time': time.time(), 'size': total}
            if hasattr(self, 'monitor'):
                self.monitor.record(ok)


    # ---- worker 主循环：从队列取站点，访问后按间隔休息 ----
    def worker_loop(self, session):
        while not stop_event.is_set():
            if self.network_down.is_set():
                time.sleep(3)
                continue
            # 按概率切换到"长连接(视频流)"任务，模拟真人边看视频边偶尔浏览
            stream_prob = self.params['stream_prob']
            if random.random() < stream_prob:
                try:
                    self.stream_session(session)
                except Exception as e:
                    logger.error(f"stream worker 异常: {e}")
                time.sleep(random.uniform(1.0, 3.0))
                continue
            try:
                site = self.task_queue.get(timeout=2)
            except Empty:
                continue
            try:
                self.visit_one(site, session)
            except Exception as e:
                logger.error(f"worker 异常 {site}: {e}")
            interval = self.params['interval']
            time.sleep(random.uniform(interval / 2, interval))

    # ---- 站点投喂器：持续把各站点名放入队列（带背压，防止队列堆积） ----
    def _feeder(self):
        while not stop_event.is_set() and not self.feeder_stop.is_set():
            # 按品牌热度加权抽样（幂律近似），让头部站更频繁，缓解均匀分布偏置
            pool = []
            for site in list(WEBSITES.keys()):
                if WEBSITES.get(site):
                    pool.extend([site] * BRAND_WEIGHT.get(site, BRAND_WEIGHT_DEFAULT))
            if not pool:
                time.sleep(0.5)
                continue
            while not stop_event.is_set() and not self.feeder_stop.is_set():
                site = random.choice(pool)
                while self.task_queue.qsize() > self.p_maxq and \
                        not stop_event.is_set() and not self.feeder_stop.is_set():
                    time.sleep(0.5)
                if stop_event.is_set() or self.feeder_stop.is_set():
                    break
                self.task_queue.put(site)
            time.sleep(0.2)

    # ---- 开始/停止 ----
    def start_test(self):
        global executor
        try:
            max_workers = int(self.threads_entry.get())
            if not 1 <= max_workers <= 20:
                raise ValueError
        except ValueError:
            messagebox.showerror(_("err_title"), _("err_threads"))
            max_workers = 8
            self.threads_entry.delete(0, tk.END)
            self.threads_entry.insert(0, "8")

        # 快照 UI 参数（普通变量），worker 子线程只读快照，杜绝子线程访问 Tk 控件崩溃
        try:
            interval = max(5.0, min(float(self.interval_entry.get()), 30.0))
        except ValueError:
            interval = 10.0
        try:
            stream_prob = max(0.0, min(float(self.stream_prob_entry.get()) / 100.0, 0.5))
        except ValueError:
            stream_prob = STREAM_PROB
        try:
            stream_dur = max(20.0, min(float(self.stream_dur_entry.get()), 120.0))
        except ValueError:
            stream_dur = 45.0
        self.params = {
            'verify': bool(self.verify_var.get()),
            'interval': interval,
            'stream_prob': stream_prob,
            'stream_dur': stream_dur,
        }
        self.p_maxq = max_workers * 2   # 背压上限用真实并发数，而非写死的常量

        # E1：把 UI 勾选写入全局开关（worker 子线程只读）
        global CACHE_BUST
        CACHE_BUST = bool(self.cachebust_var.get())

        global request_counter, error_counter
        with counter_lock:
            request_counter = 0
            error_counter = 0
        with status_lock:
            for site in WEBSITES:
                domain_status[site] = {'speed': 0, 'status': 'Idle', 'last_time': 0, 'size': 0}
            for k in list(domain_status.keys()):
                if k.startswith('视频:'):
                    del domain_status[k]

        self.log_text.configure(state="normal")
        self.log_text.delete(1.0, tk.END)
        self.log_text.configure(state="disabled")

        # B5：关闭旧 session，避免连接泄漏
        if getattr(self, 'session', None) is not None:
            try:
                self.session.close()
            except Exception:
                pass

        self.session = requests.Session()
        # B8：仅 1 次连接重试，不对 429/5xx 重试，避免放大流量冲击旁路由/ADG
        retry = Retry(total=1, backoff_factor=0.5, status_forcelist=[])
        adapter = HTTPAdapter(max_retries=retry, pool_connections=max_workers + 4,
                              pool_maxsize=max_workers + 4)
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)

        # D1：HTTP/2 + HTTP/3 通道（可选）。httpx 缺失 / 构造失败 / 请求失败都自动回退
        # requests，因此不会影响任何既有功能。
        self.hx = None
        if _HAS_HTTPX:
            verify_opt = bool(self.params['verify'])
            for kwargs in ({'http1': True, 'http2': True, 'http3': True},
                           {'http1': True, 'http2': True}):
                try:
                    self.hx = httpx.Client(
                        timeout=30.0, verify=verify_opt, follow_redirects=True,
                        limits=httpx.Limits(max_connections=max_workers + 8,
                                            max_keepalive_connections=max_workers + 4),
                        **kwargs)
                    logger.info(f"httpx 通道已启用: {kwargs}")
                    break
                except Exception as e:
                    logger.warning(f"httpx 初始化失败 {kwargs}，回退: {e}")
                    self.hx = None

        self.network_down.clear()
        self.task_queue = Queue()
        self.feeder_stop = threading.Event()

        self.monitor = NetMonitor(self)
        self.monitor_thread = threading.Thread(target=self.monitor.run, daemon=True)
        self.monitor_thread.start()

        self.feeder_thread = threading.Thread(target=self._feeder, daemon=True)
        self.feeder_thread.start()

        stop_event.clear()
        executor = ThreadPoolExecutor(max_workers=max_workers)
        for _ in range(max_workers):
            executor.submit(self.worker_loop, self.session)

        # B4：重新启动图表刷新循环（stop→start 后图表不会自动恢复）
        self.root.after(1500, self.update_chart)

        logger.info(f"模拟开始，并发线程: {max_workers}，站点数: {len(WEBSITES)}，"
                    f"证书校验: {'关' if not self.params['verify'] else '开'}")
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")

    def stop_test(self):
        global executor
        stop_event.set()
        if hasattr(self, 'feeder_stop'):
            self.feeder_stop.set()
        if executor:
            executor.shutdown(wait=False)
        if hasattr(self, 'monitor'):
            self.monitor.running = False
        self.network_down.clear()
        # D1：关闭 httpx 通道，避免连接泄漏
        if getattr(self, 'hx', None) is not None:
            try:
                self.hx.close()
            except Exception:
                pass
            self.hx = None
        logger.info("模拟已停止")
        self.start_button.configure(state="normal")
        self.stop_button.configure(state="disabled")

    def on_closing(self):
        if messagebox.askokcancel(_("exit_title"), _("exit_confirm")):
            self.stop_test()
            self.root.destroy()
            sys.exit(0)

    # ---- 关于 / 欢迎窗口 / GitHub 更新通道 ----
    def switch_language(self, code):
        """切换界面语言并持久化到配置。"""
        set_language(code)
        cfg = self._load_config()
        cfg['language'] = code
        self._save_config(cfg)
        self.refresh_language()

    def refresh_language(self):
        """重新应用当前语言到所有已打开的窗口与控件。"""
        try:
            # 菜单
            self.menubar.entryconfig(0, label=_("menu_file"))
            self.file_menu.entryconfig(0, label=_("menu_sites"))
            self.file_menu.entryconfig(1, label=_("menu_export"))
            self.file_menu.entryconfig(3, label=_("menu_exit"))
            self.menubar.entryconfig(1, label=_("menu_language"))
            self.menubar.entryconfig(2, label=_("menu_help"))
            self.help_menu.entryconfig(0, label=_("menu_check_update"))
            self.help_menu.entryconfig(1, label=_("menu_about"))
            # 主窗口控件
            self.threads_label.configure(text=_("lbl_threads"))
            self.interval_label.configure(text=_("lbl_interval"))
            self.verify_check.configure(text=_("chk_verify"))
            self.cachebust_check.configure(text=_("chk_cachebust"))
            self.stream_prob_label.configure(text=_("lbl_stream_prob"))
            self.stream_dur_label.configure(text=_("lbl_stream_dur"))
            self.start_button.configure(text=_("btn_start"))
            self.stop_button.configure(text=_("btn_stop"))
            self.request_label.configure(text=_("lbl_requests", n=request_counter))
            self.error_label.configure(text=_("lbl_errors", n=error_counter))
            down = self.network_down.is_set()
            self.net_label.configure(text=_("net_down") if down else _("net_ok"),
                                     bootstyle="danger" if down else "success")
            # 图表（下一次重绘自动取新语言；立即触发一次）
            try:
                self.update_chart()
            except Exception:
                pass
            # 站点编辑器（若打开）
            if getattr(self, 'editor_window', None) and self.editor_window.winfo_exists():
                self.editor_window.title(_("editor_title"))
                self.domain_listbox.heading("Site", text=_("col_site"))
                self.domain_listbox.heading("Domain", text=_("col_domain"))
                self.editor_btn_del.configure(text=_("btn_del_sel"))
                self.editor_btn_all.configure(text=_("btn_select_all"))
                self.editor_btn_desel.configure(text=_("btn_deselect"))
                self.editor_btn_exp.configure(text=_("btn_export"))
                self.editor_btn_ref.configure(text=_("btn_refresh"))
                self.editor_btn_close.configure(text=_("btn_close"))
                self.editor_site_lbl.configure(text=_("lbl_site_name"))
                self.editor_dom_lbl.configure(text=_("lbl_domains"))
                self.editor_btn_add.configure(text=_("btn_add"))
            # 关于窗口（若打开）
            if getattr(self, 'about_window', None) and self.about_window.winfo_exists():
                self._apply_about_texts()
        except Exception as e:
            logger.error(f"刷新语言失败: {e}")

    def _load_config(self):
        try:
            with open('realsurf_config.json', 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_config(self, cfg):
        try:
            with open('realsurf_config.json', 'w', encoding='utf-8') as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _set_update_status(self, text, style='secondary'):
        # 可能在后台线程调用，统一切回主线程操作 Tk 控件，避免随机崩溃
        try:
            self.root.after(0, lambda: self._set_update_status_impl(text, style))
        except Exception:
            pass

    def _set_update_status_impl(self, text, style='secondary'):
        try:
            if getattr(self, 'update_status_var', None):
                self.update_status_var.set(text)
            lbl = getattr(self, 'update_status_label', None)
            if lbl is not None and lbl.winfo_exists():
                lbl.configure(bootstyle=style)
        except Exception:
            pass

    def _apply_about_texts(self):
        try:
            self.about_title_label.configure(text=APP_NAME)
            self.about_ver_label.configure(text=_("about_ver", ver=APP_VERSION))
            self.about_intro_label.configure(text=_("about_intro"))
            self.about_repo_label.configure(text=_("about_repo_label"))
            self.about_autoshow_chk.configure(text=_("about_autoshow"))
            self.about_btn_check.configure(text=_("btn_check_update"))
            self.about_btn_repo.configure(text=_("btn_open_repo"))
            self.about_btn_close.configure(text=_("btn_close"))
            # 语言切换行：标题文字 + 高亮当前语言
            _lbl = getattr(self, 'about_lang_label', None)
            if _lbl is not None and _lbl.winfo_exists():
                _lbl.configure(text=_("about_lang_label"))
            for _c, _b in getattr(self, 'about_lang_btns', {}).items():
                try:
                    _b.configure(bootstyle=(SUCCESS if _c == CURRENT_LANG else OUTLINE))
                except Exception:
                    pass
        except Exception:
            pass

    def show_about(self, startup=False):
        # 单例：避免重复打开多个窗口；关闭后仍可通过菜单「关于」重新打开
        try:
            if getattr(self, 'about_window', None) and self.about_window.winfo_exists():
                self._apply_about_texts()
                self.about_window.lift()
                self.about_window.focus_force()
                return
        except Exception:
            pass
        win = Toplevel(self.root)
        win.title(_("about_title", name=APP_NAME))
        win.geometry("590x575")
        win.resizable(False, False)
        apply_app_icon(win)
        self.about_window = win

        self.about_title_label = ttkb.Label(win, text=APP_NAME, font=(UI_FONT, 18, "bold"))
        self.about_title_label.pack(pady=(18, 2))
        self.about_ver_label = ttkb.Label(win, text=_("about_ver", ver=APP_VERSION), font=(UI_FONT, 11),
                   bootstyle="secondary")
        self.about_ver_label.pack()
        ttkb.Separator(win).pack(fill="x", padx=24, pady=12)

        self.about_intro_label = ttkb.Label(win, text=_("about_intro"), font=(UI_FONT, 10), justify="left")
        self.about_intro_label.pack(padx=26, anchor="w")
        ttkb.Separator(win).pack(fill="x", padx=24, pady=12)

        # 更新仓库链接（可点击）
        repo_url = f"https://github.com/{UPDATE_REPO}"
        row = ttkb.Frame(win)
        row.pack(fill="x", padx=26)
        self.about_repo_label = ttkb.Label(row, text=_("about_repo_label"), font=(UI_FONT, 10))
        self.about_repo_label.pack(side="left")
        link = ttkb.Label(row, text=repo_url, font=(UI_FONT, 10, "underline"),
                          bootstyle="info", cursor="hand2")
        link.pack(side="left")
        link.bind("<Button-1>", lambda e: webbrowser.open(repo_url))

        # 更新状态行（启动检查/手动检查都会刷新这里）
        self.update_status_var = tk.StringVar(value=_("about_status_checking"))
        self.update_status_label = ttkb.Label(win, textvariable=self.update_status_var,
                                              font=(UI_FONT, 10), bootstyle="secondary")
        self.update_status_label.pack(padx=26, pady=(10, 2), anchor="w")

        # 是否下次启动仍自动显示
        cfg = self._load_config()
        show_var = tk.BooleanVar(value=bool(cfg.get('show_welcome', True)))
        self.about_autoshow_chk = ttkb.Checkbutton(win, text=_("about_autoshow"), variable=show_var,
                         bootstyle="round-toggle")
        self.about_autoshow_chk.pack(padx=26, pady=(6, 0), anchor="w")

        # 界面语言切换（在此窗口内即可直接切换：中文 / English / Tiếng Việt）
        lang_row = ttkb.Frame(win)
        lang_row.pack(padx=26, pady=(10, 0), anchor="w")
        self.about_lang_label = ttkb.Label(lang_row, text=_("about_lang_label"), font=(UI_FONT, 10))
        self.about_lang_label.pack(side="left")
        self.about_lang_btns = {}
        for _code, _key in (('zh', 'lang_zh'), ('en', 'lang_en'), ('vi', 'lang_vi')):
            _b = ttkb.Button(lang_row, text=_(_key), width=9,
                             bootstyle=(SUCCESS if _code == CURRENT_LANG else OUTLINE),
                             command=lambda c=_code: self.switch_language(c))
            _b.pack(side="left", padx=4)
            self.about_lang_btns[_code] = _b

        def _close_about():
            cfg2 = self._load_config()
            cfg2['show_welcome'] = bool(show_var.get())
            self._save_config(cfg2)
            win.destroy()

        btns = ttkb.Frame(win)
        btns.pack(pady=14)
        self.about_btn_check = ttkb.Button(btns, text=_("btn_check_update"), bootstyle=INFO,
                    command=self.check_update_ui)
        self.about_btn_check.pack(side="left", padx=6)
        self.about_btn_repo = ttkb.Button(btns, text=_("btn_open_repo"), bootstyle=OUTLINE,
                    command=lambda: webbrowser.open(repo_url))
        self.about_btn_repo.pack(side="left", padx=6)
        self.about_btn_close = ttkb.Button(btns, text=_("btn_close"), bootstyle=SECONDARY,
                    command=_close_about)
        self.about_btn_close.pack(side="left", padx=6)
        win.protocol("WM_DELETE_WINDOW", _close_about)

        # 打开即静默检查一次：结果只刷新状态行，绝不弹原始错误框
        threading.Thread(target=self.check_update, args=(False, True), daemon=True).start()

    def check_update_ui(self):
        # 手动检查：开线程避免界面卡顿
        threading.Thread(target=self.check_update, args=(True, False), daemon=True).start()

    def _startup_check(self):
        # 关闭了欢迎窗口时，仍静默检查一次（仅发现新版本才提示）
        try:
            time.sleep(2)
            self.check_update(manual=False, quiet=True)
        except Exception:
            pass

    @staticmethod
    def _version_tuple(v):
        # 'v1.2.3' / '1.2.3' -> (1, 2, 3)
        v = str(v).lstrip('vV').strip()
        parts = []
        for p in v.split('.'):
            num = ''
            for ch in p:
                if ch.isdigit():
                    num += ch
                else:
                    break
            parts.append(int(num) if num else 0)
        while len(parts) < 3:
            parts.append(0)
        return tuple(parts[:3])

    # releases.atom / 网页里抓 tag 用；无鉴权、无 REST 的 60次/小时限制
    _TAG_RE = re.compile(r'releases/tag/([^"\'<>\s]+)')

    def _fetch_latest_release_info(self):
        """不用受速率限制的 GitHub REST API（未鉴权仅 60次/小时/IP；代理共享出口极易被打满 → 403
        → 旧版就一直提示「更新频繁」）。改用 Atom feed（首选）+ 网页 /releases/latest 302 兜底，二者均无速率限制。
        返回 (tag, notes, html_url, asset_url, asset_size)；无版本返回 tag=None；两者都网络失败则抛出异常。"""
        import html as _html
        ua = {'User-Agent': 'Mozilla/5.0 (compatible; RealSurf updater)'}
        tag = notes = html_url = None
        err = None
        # 1) Atom feed（含 tag + 发布说明）
        try:
            r = requests.get(f"https://github.com/{UPDATE_REPO}/releases.atom",
                             headers=ua, timeout=20)
            if r.status_code == 200:
                m = re.search(r'<entry>.*?</entry>', r.text, re.S)
                entry = m.group(0) if m else ''
                mt = self._TAG_RE.search(entry)
                if mt:
                    tag = mt.group(1)
                    html_url = f"https://github.com/{UPDATE_REPO}/releases/tag/{tag}"
                mc = re.search(r'<content[^>]*>(.*?)</content>', entry, re.S)
                if mc:
                    notes = re.sub(r'<[^>]+>', '', _html.unescape(mc.group(1))).strip()
                err = None
        except Exception as e:
            err = e
            logger.warning(f"Atom 检查更新失败: {e}")
        # 2) 网页 302 兜底（同样无速率限制）
        if not tag:
            try:
                r = requests.get(f"https://github.com/{UPDATE_REPO}/releases/latest",
                                 headers=ua, timeout=20, allow_redirects=True)
                mt = self._TAG_RE.search(r.url or '')
                if mt:
                    tag = mt.group(1)
                    html_url = r.url
                err = None
            except Exception as e:
                err = e
                logger.warning(f"网页检查更新失败: {e}")
        if not tag:
            if err is not None:
                raise err          # 纯网络失败 → 让上层按「无法连接」处理
            return None, None, None, None, 0
        # 资产名不写死（发布时带版本号，如 realsurf1.2.1.exe）：
        # 优先从 expanded_assets 页面解析真实下载链接（命名无关），失败再退回命名约定。
        asset_url = None
        try:
            ea = requests.get(
                f"https://github.com/{UPDATE_REPO}/releases/expanded_assets/{tag}",
                headers=ua, timeout=20)
            if ea.status_code == 200:
                links = re.findall(
                    r'/' + re.escape(UPDATE_REPO) + r'/releases/download/[^"\'\s<>]+', ea.text)
                exes = [l for l in links if l.lower().endswith('.exe')]
                pick = exes[0] if exes else (links[0] if links else None)
                if pick:
                    asset_url = 'https://github.com' + pick
        except Exception as e:
            logger.warning(f"解析资产链接失败: {e}")
        if not asset_url:
            ver_bare = str(tag).lstrip('vV')
            for cand in (f"realsurf{ver_bare}.exe", "realsurf.exe"):
                u = f"https://github.com/{UPDATE_REPO}/releases/download/{tag}/{cand}"
                try:
                    h = requests.head(u, headers=ua, timeout=30, allow_redirects=True)
                    if h.status_code == 200:
                        asset_url = u
                        break
                except Exception:
                    continue
        if not asset_url:
            # 兜底也优先用带版本号的资产名（与发布脚本命名一致）
            asset_url = (f"https://github.com/{UPDATE_REPO}/releases/download/"
                         f"{tag}/realsurf{str(tag).lstrip('vV')}.exe")
        asset_size = 0
        try:
            h = requests.head(asset_url, headers=ua, timeout=30, allow_redirects=True)
            asset_size = int(h.headers.get('Content-Length', 0) or 0)
        except Exception:
            asset_size = 0
        return tag, (notes or ''), html_url, asset_url, asset_size

    def check_update(self, manual=False, quiet=False):
        """检查 GitHub 更新。quiet=True 时只刷新状态行，绝不弹任何错误框。"""
        try:
            if manual:
                self._set_update_status(_("upd_checking"), 'secondary')
            tag, notes, html_url, asset_url, asset_size = self._fetch_latest_release_info()
            if not tag:
                self._set_update_status(_("upd_no_release"), 'warning')
                if manual:
                    self.root.after(0, lambda: messagebox.showinfo(_("menu_check_update"), _("upd_no_release_msg")))
                return
            remote_ver = self._version_tuple(tag)
            local_ver = self._version_tuple(APP_VERSION)
            if remote_ver <= local_ver:
                self._set_update_status(_("upd_latest", ver=APP_VERSION), 'success')
                if manual:
                    self.root.after(0, lambda: messagebox.showinfo(_("menu_check_update"), _("upd_latest_msg", ver=APP_VERSION)))
                return
            # 发现新版本
            self._set_update_status(_("upd_found_status", tag=tag), 'info')
            if manual:
                parent = self.about_window if (getattr(self, 'about_window', None)
                                               and self.about_window.winfo_exists()) else self.root
                if asset_url:
                    info = _("upd_found_msg", tag=tag, ver=APP_VERSION, notes=notes[:600])
                    def _ask_and_apply():
                        # 必须在主线程执行；任何异常都要「看得见」，否则 --noconsole 下就是「点了没反应」
                        try:
                            if messagebox.askyesno(_("menu_check_update"), info, parent=parent):
                                self._start_update_download(parent, asset_url, tag, asset_size)
                        except Exception as ex:
                            logger.error(f"启动更新失败: {ex}")
                            try:
                                messagebox.showerror(_("upd_apply_fail_title"),
                                                     _("upd_apply_fail_msg") + f"\n\n{ex}")
                            except Exception:
                                pass
                    self.root.after(0, _ask_and_apply)
                else:
                    def _open_repo():
                        webbrowser.open(html_url or f"https://github.com/{UPDATE_REPO}/releases/latest")
                    self.root.after(0, _open_repo)
            else:
                logger.info(f"发现新版本 {tag}（当前 v{APP_VERSION}）")
                if quiet:
                    # 无窗口时用主线程弹一次轻提示（非阻塞后台线程）
                    try:
                        self.root.after(0, lambda: messagebox.showinfo(
                            _("menu_check_update"),
                            _("upd_found_quiet", tag=tag, ver=APP_VERSION)))
                    except Exception:
                        pass
        except requests.exceptions.RequestException:
            # 网络类失败：只记日志 + 刷新状态行，绝不把原始异常抛给用户
            self._set_update_status(_("upd_conn_fail"), 'warning')
            logger.warning("检查更新失败：无法连接 GitHub（网络或代理问题）")
            if manual:
                self.root.after(0, lambda: messagebox.showwarning(_("menu_check_update"), _("upd_conn_fail_msg")))
        except Exception as e:
            self._set_update_status(_("upd_fail_status"), 'warning')
            logger.error(f"检查更新异常: {e}")
            if manual:
                self.root.after(0, lambda: messagebox.showerror(_("menu_check_update"), _("upd_fail_msg")))

    def _start_update_download(self, parent, asset_url, new_version, asset_size=0):
        """主线程创建下载进度对话框，并启动后台下载线程（不再同步卡界面）。"""
        parent = parent if parent else self.root
        dlg = ttkb.Toplevel(parent)
        dlg.title(_("menu_check_update"))
        dlg.resizable(False, False)
        try:
            dlg.transient(parent)
        except Exception:
            pass
        apply_app_icon(dlg)
        cancel_event = threading.Event()
        lbl = ttkb.Label(dlg, text=_("upd_downloading", ver=new_version), font=(UI_FONT, 10))
        lbl.pack(pady=(18, 8))
        # 进度条统一按 0-100 百分比；一创建就可见（空条），不再等到第一块数据
        bar = ttkb.Progressbar(dlg, length=380, mode='determinate', maximum=100, value=0,
                               bootstyle=INFO)
        bar.pack(padx=24)
        pct = ttkb.Label(dlg, text='0%', font=(UI_FONT, 9), bootstyle='secondary')
        pct.pack(pady=(4, 4))
        btn_cancel = ttkb.Button(dlg, text=_("btn_cancel"), bootstyle=SECONDARY,
                                 command=cancel_event.set)
        btn_cancel.pack(pady=(2, 10))
        # 居中到父窗口，并短暂置顶，确保一定看得见（解决「弹窗跑到后面」）
        try:
            dlg.update_idletasks()
            w, h = dlg.winfo_width(), dlg.winfo_height()
            px, py = parent.winfo_rootx(), parent.winfo_rooty()
            pw, ph = parent.winfo_width(), parent.winfo_height()
            dlg.geometry(f"+{max(0, px + (pw - w)//2)}+{max(0, py + (ph - h)//2)}")
        except Exception:
            pass
        try:
            dlg.grab_set()
            dlg.lift()
            dlg.attributes('-topmost', True)
            dlg.after(800, lambda: dlg.attributes('-topmost', False))
            dlg.focus_force()
        except Exception:
            pass
        t = threading.Thread(target=self._download_worker,
                             args=(asset_url, new_version, dlg, bar, pct, lbl, cancel_event, asset_size),
                             daemon=True)
        t.start()

    def _init_bar(self, bar, total):
        # 进度条统一按 0-100 百分比；拿不到总大小则退化为滚动条
        try:
            if total > 0:
                bar.configure(mode='determinate', maximum=100, value=0)
            else:
                bar.configure(mode='indeterminate')
                bar.start()
        except Exception:
            pass

    def _upd_progress(self, bar, pct, v, t, el=0.0):
        try:
            if t > 0:
                pct_v = min(100, v * 100 // t)
                bar.configure(value=pct_v)
                speed = (v / el / 1048576) if el > 0.001 else 0.0
                pct.configure(text=f"{pct_v}%   {v/1048576:.1f}/{t/1048576:.1f} MB   {speed:.2f} MB/s")
            else:
                pct.configure(text=f"{v/1048576:.1f} MB   ...")
        except Exception:
            pass

    def _stop_bar(self, bar):
        try:
            bar.stop()
        except Exception:
            pass

    def _set_restart_label(self, lbl):
        try:
            lbl.configure(text=_("upd_restart"))
        except Exception:
            pass

    def _cancel_update_ui(self, dlg):
        try:
            dlg.destroy()
        except Exception:
            pass
        self._set_update_status(_("upd_canceled"), 'secondary')

    def _update_fail_ui(self, dlg, detail=''):
        try:
            dlg.destroy()
        except Exception:
            pass
        self._set_update_status(_("upd_apply_fail_title"), 'warning')
        msg = _("upd_apply_fail_msg")
        if detail:
            msg = msg + "\n\n" + str(detail)[:300]
        messagebox.showerror(_("upd_apply_fail_title"), msg)
        webbrowser.open(f"https://github.com/{UPDATE_REPO}/releases/latest")

    def _finish_update(self, dlg, bat):
        import subprocess, sys
        try:
            dlg.destroy()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass
        subprocess.Popen(bat, shell=True)
        sys.exit(0)

    def _download_worker(self, asset_url, new_version, dlg, bar, pct, lbl, cancel_event, asset_size=0):
        """后台线程：带进度条下载更新，完成后写 bat 并重启替换。所有 Tk 操作回主线程。"""
        import tempfile, os, sys, subprocess
        tmp = tempfile.gettempdir()
        new_exe = os.path.join(tmp, "realsurf_update.exe")
        started = time.time()
        try:
            # 总大小优先用 GitHub API 给的 asset size（最可靠），其次 HEAD / GET 的 Content-Length
            total = int(asset_size or 0)
            if total <= 0:
                try:
                    h = requests.head(asset_url, timeout=30, allow_redirects=True)
                    total = int(h.headers.get('Content-Length', 0) or 0)
                except Exception:
                    total = 0
            logger.info(f"开始下载更新 {new_version}: {asset_url} (size={total})")
            r = requests.get(asset_url, stream=True, timeout=120)
            r.raise_for_status()
            if total <= 0:
                total = int(r.headers.get('Content-Length', 0) or 0)
            self.root.after(0, lambda: self._init_bar(bar, total))
            written = 0
            last_ui = 0.0
            with open(new_exe, 'wb') as f:
                for chunk in r.iter_content(128 * 1024):
                    if cancel_event.is_set():
                        raise _CancelUpdate()
                    if not chunk:
                        continue
                    f.write(chunk)
                    written += len(chunk)
                    now = time.time()
                    if now - last_ui >= 0.1:      # 限频，别刷爆 UI
                        last_ui = now
                        w, t, el = written, total, now - started
                        self.root.after(0, lambda w=w, t=t, el=el: self._upd_progress(bar, pct, w, t, el))
            if cancel_event.is_set():
                raise _CancelUpdate()
            el = time.time() - started
            self.root.after(0, lambda: self._upd_progress(bar, pct, written, (total or written), el))
            self.root.after(0, lambda: self._stop_bar(bar))
            self.root.after(0, lambda: self._set_restart_label(lbl))
            cur = sys.executable          # onefile 下指向真实磁盘 exe（已实测）
            # 新文件按「带版本号」命名（如 realsurf1.2.1.exe），便于区分版本；
            # 旧版文件保留不删（用户可能想留着旧版本对照）。
            ver_bare = str(new_version).lstrip('vV')
            target = os.path.join(os.path.dirname(cur), f"realsurf{ver_bare}.exe")
            bat = os.path.join(tmp, "realsurf_updater.bat")
            with open(bat, 'w', encoding='utf-8') as f:
                f.write('@echo off\n')
                f.write('timeout /t 1 >nul\n')
                f.write(f'taskkill /f /im "{os.path.basename(cur)}" >nul 2>nul\n')
                f.write(f'copy /Y "{new_exe}" "{target}"\n')
                f.write(f'del /Q "{new_exe}"\n')
                f.write(f'start "" "{target}"\n')
            logger.info(f"更新文件将保存为 {target}")
            self.root.after(900, lambda: self._finish_update(dlg, bat))
        except _CancelUpdate:
            try:
                if os.path.exists(new_exe):
                    os.remove(new_exe)
            except Exception:
                pass
            self.root.after(0, lambda: self._cancel_update_ui(dlg))
        except Exception as e:
            logger.error(f"更新失败: {e}")
            det = str(e)
            self.root.after(0, lambda det=det: self._update_fail_ui(dlg, det))


class _CancelUpdate(Exception):
    """下载被用户取消时抛出，用于干净退出下载循环。"""
    pass


def main():
    root = ttkb.Window(themename="litera")
    app = RealNetSimApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
