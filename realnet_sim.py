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
import json
import logging
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
        'menu_language': '语言', 'lang_zh': '中文', 'lang_en': 'English', 'lang_vi': 'Tiếng Việt',
        'about_title': '关于 {name}', 'about_ver': '当前版本  v{ver}',
        'lbl_threads': '最大并发线程 (1-20):', 'lbl_interval': '访问间隔 (秒, 5-30):',
        'chk_verify': '跳过证书校验(代理环境)', 'lbl_stream_prob': '长连接比例(0-50):',
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
        'err_threads': '并发线程数必须在 1-20 之间，使用默认值 16',
        'exit_title': '退出', 'exit_confirm': '确定要退出吗？',
        'chart_title': '各站点实时网速与状态', 'chart_title_idle': '各站点实时网速与状态（暂无活动）',
        'chart_ylabel': '网速 (KB/s)',
        'about_intro': '模拟真人上网行为：短请求浏览 + 长连接视频流，用于\n'
                       'OpenClash / 代理链路连通性验证，以及 Smart 策略组\n'
                       '训练数据采集。\n\n'
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
        'upd_found_quiet': '发现新版本 {tag}（当前 v{ver}）。\n请用菜单「文件 → 检查更新」升级。',
        'upd_conn_fail': '更新状态：无法连接更新服务器（请检查网络/代理）',
        'upd_conn_fail_msg': '无法连接更新服务器。\n请检查网络或代理设置后再试。',
        'upd_fail_status': '更新状态：检查更新失败',
        'upd_fail_msg': '检查更新时出现问题，请稍后再试。',
        'upd_apply_fail_title': '更新失败',
        'upd_apply_fail_msg': '自动更新未能完成，已为你打开发布页，\n请手动下载最新版 realsurf.exe 覆盖即可。',
    },
    'en': {
        'menu_file': 'File', 'menu_sites': 'Site List', 'menu_export': 'Export Site List (JSON)',
        'menu_check_update': 'Check for Update', 'menu_about': 'About', 'menu_exit': 'Exit',
        'menu_language': 'Language', 'lang_zh': '中文', 'lang_en': 'English', 'lang_vi': 'Tiếng Việt',
        'about_title': 'About {name}', 'about_ver': 'Version  v{ver}',
        'lbl_threads': 'Max Threads (1-20):', 'lbl_interval': 'Visit Interval (s, 5-30):',
        'chk_verify': 'Skip Cert Verify (proxy)', 'lbl_stream_prob': 'Stream Ratio (0-50):',
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
        'err_threads': 'Thread count must be 1-20; using default 16',
        'exit_title': 'Exit', 'exit_confirm': 'Exit the application?',
        'chart_title': 'Real-time Speed & Status per Site', 'chart_title_idle': 'Real-time Speed & Status (no activity yet)',
        'chart_ylabel': 'Speed (KB/s)',
        'about_intro': 'Simulates realistic human browsing: short requests + long video streams.\n'
                       'For OpenClash / proxy link connectivity checks and Smart group\n'
                       'training data collection.\n\n'
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
        'upd_found_quiet': 'New version {tag} (current v{ver}).\nUse menu "File → Check for Update" to upgrade.',
        'upd_conn_fail': 'Update: cannot reach server (check network/proxy)',
        'upd_conn_fail_msg': 'Cannot reach update server.\nCheck network or proxy settings.',
        'upd_fail_status': 'Update: check failed',
        'upd_fail_msg': 'Problem during update check; retry later.',
        'upd_apply_fail_title': 'Update Failed',
        'upd_apply_fail_msg': 'Auto-update incomplete; release page opened.\nDownload latest realsurf.exe manually.',
    },
    'vi': {
        'menu_file': 'Tập tin', 'menu_sites': 'Danh sách trang', 'menu_export': 'Xuất danh sách (JSON)',
        'menu_check_update': 'Kiểm tra cập nhật', 'menu_about': 'Giới thiệu', 'menu_exit': 'Thoát',
        'menu_language': 'Ngôn ngữ', 'lang_zh': '中文', 'lang_en': 'English', 'lang_vi': 'Tiếng Việt',
        'about_title': 'Giới thiệu {name}', 'about_ver': 'Phiên bản  v{ver}',
        'lbl_threads': 'Số luồng tối đa (1-20):', 'lbl_interval': 'Khoảng cách truy cập (giây, 5-30):',
        'chk_verify': 'Bỏ xác thực chứng chỉ (proxy)', 'lbl_stream_prob': 'Tỉ lệ luồng (0-50):',
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
        'err_threads': 'Số luồng phải từ 1-20; dùng mặc định 16',
        'exit_title': 'Thoát', 'exit_confirm': 'Thoát ứng dụng?',
        'chart_title': 'Tốc độ & trạng thái theo trang', 'chart_title_idle': 'Tốc độ & trạng thái (chưa có hoạt động)',
        'chart_ylabel': 'Tốc độ (KB/s)',
        'about_intro': 'Mô phỏng lướt web thật của con người: truy cập ngắn + luồng video dài.\n'
                       'Dùng để kiểm tra kết nối OpenClash / proxy và thu thập dữ liệu\n'
                       'huấn luyện nhóm Smart.\n\n'
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
        'upd_found_quiet': 'Phiên bản mới {tag} (hiện tại v{ver}).\nDùng menu "Tập tin → Kiểm tra cập nhật" để nâng cấp.',
        'upd_conn_fail': 'Cập nhật: không thể kết nối (kiểm tra mạng/proxy)',
        'upd_conn_fail_msg': 'Không thể kết nối máy chủ cập nhật.\nKiểm tra mạng hoặc proxy.',
        'upd_fail_status': 'Cập nhật: kiểm tra thất bại',
        'upd_fail_msg': 'Lỗi khi kiểm tra cập nhật; thử lại sau.',
        'upd_apply_fail_title': 'Cập nhật thất bại',
        'upd_apply_fail_msg': 'Tự cập nhật chưa xong; đã mở trang phát hành.\nTải realsurf.exe mới nhất thủ công.',
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
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(threadName)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('access_log.txt', encoding='utf-8'),
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
MAX_WORKERS = 16               # 并发 worker 上限，避免开大量线程拖垮系统/卡鼠标
MAX_BODY_BYTES = 256 * 1024    # 单次请求最多读取的响应体字节（流式），避免整页解压耗 CPU/内存
MAX_STREAM_BYTES = 50 * 1024 * 1024   # 单次"观看"最多拉取的字节，避免对测试视频 CDN 打流过猛
STREAM_PROB = 0.20             # 长连接(视频流)任务占比默认 20%，UI 可调

# ---------------------------------------------------------------------------
# 软件信息 / GitHub 更新通道
# ---------------------------------------------------------------------------
APP_NAME = "拟真冲浪 RealSurf"
APP_VERSION = "1.1.0"
APP_UA = f"RealSurf/{APP_VERSION}"   # HTTP 头必须是 ASCII，绝不能用中文 APP_NAME（否则 latin-1 报错）
# 更新仓库（owner/repo）。构建/发布前由发布脚本填入真实 owner；
# 软件启动时查询该仓库的 latest release 判断是否有新版本。
UPDATE_REPO = "mmddxyg/realsurf"
GITHUB_API = "https://api.github.com"


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
                r = self.app.session.get(host, timeout=10, verify=self.app.verify_var.get(),
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

        # UI 变量
        self.verify_var = tk.BooleanVar(value=True)          # 默认开启证书校验
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

    # ---- 菜单 ----
    def create_menu(self):
        menubar = tk.Menu(self.root, tearoff=0)
        self.root.config(menu=menubar)
        self.menubar = menubar
        file_menu = tk.Menu(menubar, tearoff=0)
        self.file_menu = file_menu
        menubar.add_cascade(label=_("menu_file"), menu=file_menu)
        file_menu.add_command(label=_("menu_sites"), command=self.open_domain_editor)
        file_menu.add_command(label=_("menu_export"), command=self.export_sites)
        file_menu.add_separator()
        file_menu.add_command(label=_("menu_check_update"), command=self.check_update_ui)
        file_menu.add_command(label=_("menu_about"), command=self.show_about)
        file_menu.add_separator()
        file_menu.add_command(label=_("menu_exit"), command=self.on_closing)
        # 语言子菜单
        lang_menu = tk.Menu(menubar, tearoff=0)
        self.lang_menu = lang_menu
        lang_menu.add_command(label=_("lang_zh"), command=lambda: self.switch_language('zh'))
        lang_menu.add_command(label=_("lang_en"), command=lambda: self.switch_language('en'))
        lang_menu.add_command(label=_("lang_vi"), command=lambda: self.switch_language('vi'))
        menubar.add_cascade(label=_("menu_language"), menu=lang_menu)

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
        self.threads_entry.insert(0, "16")
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

        self.stream_prob_label = ttkb.Label(input_frame, text=_("lbl_stream_prob"), font=(UI_FONT, 12))
        self.stream_prob_label.grid(row=0, column=5, padx=5)
        self.stream_prob_entry = ttkb.Entry(input_frame, width=5, font=(UI_FONT, 12))
        self.stream_prob_entry.insert(0, "20")
        self.stream_prob_entry.grid(row=0, column=6, padx=5)

        self.stream_dur_label = ttkb.Label(input_frame, text=_("lbl_stream_dur"), font=(UI_FONT, 12))
        self.stream_dur_label.grid(row=0, column=7, padx=5)
        self.stream_dur_entry = ttkb.Entry(input_frame, width=5, font=(UI_FONT, 12))
        self.stream_dur_entry.insert(0, "45")
        self.stream_dur_entry.grid(row=0, column=8, padx=5)

        # 按钮框架
        button_frame = ttkb.Frame(main_frame, padding="10")
        button_frame.grid(row=1, column=0, sticky="ew")

        self.start_button = ttkb.Button(button_frame, text=_("btn_start"), command=self.start_test, bootstyle=PRIMARY)
        self.start_button.grid(row=0, column=0, padx=5)
        self.stop_button = ttkb.Button(button_frame, text=_("btn_stop"), command=self.stop_test,
                                       state="disabled", bootstyle=DANGER)
        self.stop_button.grid(row=0, column=1, padx=5)

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
        if warn_if_verify and self.verify_var.get():
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

    # ---- 单次访问（真实浏览器模拟，流式读取，限制体积） ----
    def visit_one(self, site_name, session):
        global request_counter, error_counter
        # 复制一份站点列表再选，避免与"剔除失效域名"并发修改冲突
        with sites_lock:
            urls = list(WEBSITES.get(site_name, []))
        if not urls:
            return
        url = random.choice(urls)
        req_url = f"{url}{'?num=' if '?' not in url else '&num='}{request_counter}"
        profile = dict(random.choice(BROWSER_PROFILES))
        profile['Referer'] = url
        if random.random() < 0.3:
            profile['Cache-Control'] = 'max-age=0'
        start_time = time.time()
        size = 0.0
        status = 'Idle'
        ok = False
        try:
            # 流式读取，最多 MAX_BODY_BYTES，避免整页解压占用大量 CPU/内存
            response = session.get(req_url, timeout=30, verify=self.verify_var.get(),
                                   headers=profile, stream=True)
            try:
                for chunk in response.iter_content(16384):
                    size += len(chunk)
                    if size >= MAX_BODY_BYTES:
                        break
            finally:
                response.close()
            with counter_lock:
                request_counter += 1
            ok = True
            with sites_lock:
                domain_fail_count.pop(url, None)   # 成功：清零该域名失败计数
            if response.status_code == 429:
                logger.warning(f"触发 429 限流 {site_name}，额外等待 5 秒")
                time.sleep(5)
                status = "OK (429)"
            else:
                status = f"OK ({response.status_code})" if response.status_code == 200 \
                    else f"Error ({response.status_code})"
        except requests.exceptions.SSLError as e:
            self._on_fail(site_name, url, f"SSL 错误 {site_name} ({req_url}): {e} - 跳过",
                          retry_sleep=1 if not self.verify_var.get() else 3,
                          warn_if_verify="证书错误：如走代理 TLS 拦截，请勾选「跳过证书校验」")
            status = 'SSL Error'
        except requests.exceptions.ConnectTimeout as e:
            self._on_fail(site_name, url, f"连接超时 {site_name} ({req_url}): {e} - 重试", retry_sleep=2)
            status = 'Timeout'
        except requests.exceptions.ReadTimeout as e:
            self._on_fail(site_name, url, f"读取超时 {site_name} ({req_url}): {e} - 跳过", retry_sleep=1)
            status = 'Timeout'
        except requests.exceptions.ConnectionError as e:
            self._on_fail(site_name, url, f"连接错误 {site_name} ({req_url}): {e} - 等待恢复", retry_sleep=2)
            status = 'ConnErr'
        except requests.exceptions.NameResolutionError as e:
            # DNS 解析失败 = 域名已死，立即剔除
            self._on_fail(site_name, url, f"域名解析失败 {site_name} ({req_url}): {e} - 剔除该域名",
                          force_drop=True)
            status = 'DNS Error'
        except requests.exceptions.RequestException as e:
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
            stream_seconds = float(self.stream_dur_entry.get())
            stream_seconds = max(20.0, min(stream_seconds, 120.0))
        except ValueError:
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
            if is_mp4:
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
                        r = session.get(url, timeout=30, verify=self.verify_var.get(),
                                        headers=req_headers, stream=True)
                        try:
                            for chunk in r.iter_content(16384):
                                total += len(chunk)
                                if total >= MAX_STREAM_BYTES:
                                    break
                        finally:
                            r.close()
                        with counter_lock:
                            request_counter += 1
                        ok = True
                    except requests.exceptions.RequestException as e:
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
                    r = session.get(url, timeout=30, verify=self.verify_var.get(),
                                    headers=profile, stream=True)
                    try:
                        for chunk in r.iter_content(16384):
                            total += len(chunk)
                            if total >= 512 * 1024:
                                break
                    finally:
                        r.close()
                    with counter_lock:
                        request_counter += 1
                    ok = True
                except requests.exceptions.RequestException as e:
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
                    sub = random.choice(target.get('subs', []))
                    try:
                        sr = session.get(sub, timeout=20, verify=self.verify_var.get(),
                                        headers=dict(random.choice(BROWSER_PROFILES)), stream=True)
                        try:
                            for _ in sr.iter_content(16384):
                                pass
                        finally:
                            sr.close()
                        with counter_lock:
                            request_counter += 1
                    except requests.exceptions.RequestException:
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
            try:
                stream_prob = float(self.stream_prob_entry.get()) / 100.0
            except ValueError:
                stream_prob = STREAM_PROB
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
            try:
                interval = float(self.interval_entry.get())
                interval = max(5.0, min(interval, 30.0))
            except ValueError:
                interval = 10.0
            time.sleep(random.uniform(interval / 2, interval))

    # ---- 站点投喂器：持续把各站点名放入队列（带背压，防止队列堆积） ----
    def _feeder(self):
        while not stop_event.is_set() and not self.feeder_stop.is_set():
            for site in list(WEBSITES.keys()):
                if not WEBSITES.get(site):
                    continue
                while self.task_queue.qsize() > MAX_WORKERS * 2 and \
                        not stop_event.is_set() and not self.feeder_stop.is_set():
                    time.sleep(0.5)
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
            max_workers = 16
            self.threads_entry.delete(0, tk.END)
            self.threads_entry.insert(0, "16")

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

        self.session = requests.Session()
        retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry, pool_connections=max_workers + 4,
                              pool_maxsize=max_workers + 4)
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)

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

        logger.info(f"模拟开始，并发线程: {max_workers}，站点数: {len(WEBSITES)}，"
                    f"证书校验: {'关' if not self.verify_var.get() else '开'}")
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
            self.file_menu.entryconfig(3, label=_("menu_check_update"))
            self.file_menu.entryconfig(4, label=_("menu_about"))
            self.file_menu.entryconfig(6, label=_("menu_exit"))
            self.menubar.entryconfig(1, label=_("menu_language"))
            # 主窗口控件
            self.threads_label.configure(text=_("lbl_threads"))
            self.interval_label.configure(text=_("lbl_interval"))
            self.verify_check.configure(text=_("chk_verify"))
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
        # 刷新欢迎窗口里的状态文字（窗口未打开时静默忽略）
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
        win.geometry("560x500")
        win.resizable(False, False)
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

    def check_update(self, manual=False, quiet=False):
        """检查 GitHub 更新。quiet=True 时只刷新状态行，绝不弹任何错误框。"""
        try:
            url = f"{GITHUB_API}/repos/{UPDATE_REPO}/releases/latest"
            # 注意：HTTP 头必须是 latin-1 可编码，UA 只能用纯 ASCII
            hdr = {'Accept': 'application/vnd.github+json', 'User-Agent': APP_UA}
            resp = requests.get(url, headers=hdr, timeout=15)
            if resp.status_code == 404:
                self._set_update_status(_("upd_no_release"), 'warning')
                if manual:
                    messagebox.showinfo(_("menu_check_update"), _("upd_no_release_msg"))
                return
            if resp.status_code == 403:
                self._set_update_status(_("upd_rate_limit"), 'warning')
                if manual:
                    messagebox.showwarning(_("menu_check_update"), _("upd_rate_limit_msg"))
                return
            resp.raise_for_status()
            rel = resp.json()
            tag = rel.get('tag_name', '')
            remote_ver = self._version_tuple(tag)
            local_ver = self._version_tuple(APP_VERSION)
            notes = rel.get('body', '') or ''
            if remote_ver <= local_ver:
                self._set_update_status(_("upd_latest", ver=APP_VERSION), 'success')
                if manual:
                    messagebox.showinfo(_("menu_check_update"), _("upd_latest_msg", ver=APP_VERSION))
                return
            # 发现新版本
            self._set_update_status(_("upd_found_status", tag=tag), 'info')
            asset_url = None
            for a in rel.get('assets', []):
                if a.get('name', '').lower().endswith('.exe'):
                    asset_url = a.get('browser_download_url')
                    break
            if manual:
                info = _("upd_found_msg", tag=tag, ver=APP_VERSION, notes=notes[:600])
                if asset_url and messagebox.askyesno(_("menu_check_update"), info):
                    self._apply_update(asset_url, tag)
                elif not asset_url:
                    webbrowser.open(rel.get('html_url',
                                            f"https://github.com/{UPDATE_REPO}/releases/latest"))
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
                messagebox.showwarning(_("menu_check_update"), _("upd_conn_fail_msg"))
        except Exception as e:
            self._set_update_status(_("upd_fail_status"), 'warning')
            logger.error(f"检查更新异常: {e}")
            if manual:
                messagebox.showerror(_("menu_check_update"), _("upd_fail_msg"))

    def _apply_update(self, asset_url, new_version):
        import tempfile, os, sys, subprocess
        try:
            tmp = tempfile.gettempdir()
            new_exe = os.path.join(tmp, "realsurf_update.exe")
            logger.info(f"开始下载更新 {new_version}: {asset_url}")
            r = requests.get(asset_url, stream=True, timeout=120)
            r.raise_for_status()
            with open(new_exe, 'wb') as f:
                for chunk in r.iter_content(1024 * 1024):
                    if chunk:
                        f.write(chunk)
            cur = sys.executable          # 当前运行的 exe（如 realsurf.exe）
            bat = os.path.join(tmp, "realsurf_updater.bat")
            with open(bat, 'w', encoding='utf-8') as f:
                f.write('@echo off\n')
                f.write('timeout /t 1 >nul\n')
                f.write(f'taskkill /f /im "{os.path.basename(cur)}" >nul 2>nul\n')
                f.write(f'copy /Y "{new_exe}" "{cur}"\n')
                f.write(f'del /Q "{new_exe}"\n')
                f.write(f'start "" "{cur}"\n')
            subprocess.Popen(bat, shell=True)
            logger.info("更新已下载，即将重启应用以完成替换")
            self.root.destroy()
            sys.exit(0)
        except Exception as e:
            logger.error(f"更新失败: {e}")
            webbrowser.open(f"https://github.com/{UPDATE_REPO}/releases/latest")
            messagebox.showerror(_("upd_apply_fail_title"),
                _("upd_apply_fail_msg"))


def main():
    root = ttkb.Window(themename="litera")
    app = RealNetSimApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
