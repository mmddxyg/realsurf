import threading
import requests
import time
import sys
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
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from queue import Queue
import os
import traceback

# 配置 Matplotlib 使用 SimHei 字体（支持中文）
plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False

# 配置日志
try:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(threadName)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('access_log.txt', encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )
except PermissionError as e:
    print(f"无法写入日志文件: {e}. 请检查 access_log.txt 权限")
    sys.exit(1)
logger = logging.getLogger()

# 自定义日志处理器，将日志推送到 UI
class QueueHandler(logging.Handler):
    def __init__(self, queue):
        super().__init__()
        self.queue = queue

    def emit(self, record):
        try:
            msg = self.format(record)
            self.queue.put(msg)
        except Exception:
            self.handleError(record)

# User-Agent 列表
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Firefox/89.0',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.101 Safari/537.36'
]

# 目标网站，包含所有 30 个网站及其子域名，补充自 OpenClash 规则集
WEBSITES = {
    "TikTok": [
        "https://www.tiktok.com",
        "https://m.tiktok.com",
        "https://api.tiktok.com",
        "https://ads.tiktok.com",
        "https://business.tiktok.com",
        "https://creators.tiktok.com",
        "https://shop.tiktok.com",
        "https://live.tiktok.com",
        "https://analytics.tiktok.com",
        "https://developer.tiktok.com",
        "https://link.tiktok.com",
        "https://us.tiktok.com",
        "https://v.tiktok.com",
        "https://vm.tiktok.com",
        "https://vt.tiktok.com",
        "https://support.tiktok.com",
        "https://careers.tiktok.com",
        "https://newsroom.tiktok.com",
        "https://effecthouse.tiktok.com",
        "https://tiktokcdn.com",
        "https://api-h2.tiktokv.com",
        "https://webcast.tiktok.com"
    ],
    "YouTube": [
        "https://www.youtube.com",
        "https://m.youtube.com",
        "https://music.youtube.com",
        "https://tv.youtube.com",
        "https://studio.youtube.com",
        "https://kids.youtube.com",
        "https://accounts.youtube.com",
        "https://ads.youtube.com",
        "https://support.youtube.com",
        "https://about.youtube.com",
        "https://blog.youtube.com",
        "https://developers.youtube.com",
        "https://ytimg.com",
        "https://creatoracademy.youtube.com",
        "https://gaming.youtube.com",
        "https://apis.youtube.com",
        "https://play.google.com/store/apps/details?id=com.google.android.youtube",
        "https://youtube.googleapis.com",
        "https://upload.youtube.com",
        "https://redirect.youtube.com",
        "https://search.youtube.com",
        "https://myaccount.youtube.com",
        "https://creators.youtube.com",
        "https://shopping.youtube.com",
        "https://shorts.youtube.com",
        "https://live.youtube.com",
        "https://yt.be",
        "https://m.youtube.googleapis.com",
        "https://youtubekids.com",
        "https://analytics.youtube.com",
        "https://notifications.youtube.com",
        "https://embed.youtube.com",
        "https://youtu.be",
        "https://www.youtube.com/feed/subscriptions",
        "https://www.youtube.com/feed/history",
        "https://www.youtube.com/premium",
        "https://www.youtube.com/channel/",
        "https://www.youtube.com/watch"
    ],
    "Netflix": [
        "https://www.netflix.com",
        "https://account.netflix.com",
        "https://media.netflix.com",
        "https://app.netflix.com",
        "https://help.netflix.com",
        "https://blog.netflix.com",
        "https://jobs.netflix.com",
        "https://ir.netflix.com",
        "https://partner.netflix.com",
        "https://devices.netflix.com",
        "https://investor.netflix.com",
        "https://signup.netflix.com",
        "https://api.netflix.com",
        "https://developer.netflix.com",
        "https://support.netflix.com",
        "https://netflix.net",
        "https://nflxvideo.net",
        "https://fast.com",
        "https://about.netflix.com",
        "https://openconnect.netflix.com",
        "https://api-global.netflix.com",
        "https://customerevents.netflix.com",
        "https://ichnaea.netflix.com",
        "https://nmc.netflix.com",
        "https://nrdp.netflix.com",
        "https://ntech.netflix.com",
        "https://push.netflix.com",
        "https://secure.netflix.com",
        "https://uiboot.netflix.com",
        "https://cdn.netflix.com",
        "https://www.netflix.com/login",
        "https://www.netflix.com/browse",
        "https://www.netflix.com/kids",
        "https://www.netflix.com/profiles",
        "https://www.netflix.com/latest",
        "https://www.netflix.com/title/",
        "https://www.netflix.com/watch/",
        "https://nflximg.com",
        "https://netflixcdn.com"
    ],
    "Reddit": [
        "https://www.reddit.com",
        "https://m.reddit.com",
        "https://oauth.reddit.com",
        "https://old.reddit.com",
        "https://np.reddit.com",
        "https://mod.reddit.com",
        "https://ads.reddit.com",
        "https://about.reddit.com",
        "https://blog.reddit.com",
        "https://api.reddit.com",
        "https://i.reddit.com",
        "https://ssl.reddit.com",
        "https://developer.reddit.com",
        "https://support.reddit.com",
        "https://careers.reddit.com",
        "https://store.reddit.com",
        "https://redditinc.com",
        "https://accounts.reddit.com",
        "https://gateway.reddit.com",
        "https://strapi.reddit.com",
        "https://events.reddit.com",
        "https://help.reddit.com",
        "https://mods.reddit.com",
        "https://www.reddit.com/r/",
        "https://www.reddit.com/user/",
        "https://www.reddit.com/search/"
    ],
    "X": [
        "https://www.x.com",
        "https://mobile.x.com",
        "https://api.x.com",
        "https://ads.x.com",
        "https://developer.x.com",
        "https://blog.x.com",
        "https://about.x.com",
        "https://support.x.com",
        "https://business.x.com",
        "https://cards.x.com",
        "https://media.x.com",
        "https://help.x.com",
        "https://careers.x.com",
        "https://status.x.com",
        "https://analytics.x.com",
        "https://pay.x.com",
        "https://m.x.com",
        "https://syndication.x.com",
        "https://upload.x.com",
        "https://video.x.com",
        "https://abs.twimg.com",
        "https://pbs.twimg.com",
        "https://x.com/home",
        "https://x.com/explore",
        "https://x.com/notifications",
        "https://t.co"
    ],
    "Instagram": [
        "https://www.instagram.com",
        "https://i.instagram.com",
        "https://api.instagram.com",
        "https://business.instagram.com",
        "https://help.instagram.com",
        "https://about.instagram.com",
        "https://developers.instagram.com",
        "https://blog.instagram.com",
        "https://ads.instagram.com",
        "https://careers.instagram.com",
        "https://creator.instagram.com",
        "https://support.instagram.com",
        "https://privacy.instagram.com",
        "https://graph.instagram.com",
        "https://m.instagram.com",
        "https://l.instagram.com",
        "https://accountscenter.instagram.com",
        "https://direct.instagram.com",
        "https://www.instagram.com/explore/",
        "https://www.instagram.com/reels/",
        "https://www.instagram.com/stories/",
        "https://www.instagram.com/accounts/login/",
        "https://www.instagram.com/p/",
        "https://www.instagram.com/direct/inbox/"
    ],
    "Facebook": [
        "https://www.facebook.com",
        "https://m.facebook.com",
        "https://graph.facebook.com",
        "https://business.facebook.com",
        "https://developers.facebook.com",
        "https://about.facebook.com",
        "https://help.facebook.com",
        "https://ads.facebook.com",
        "https://careers.facebook.com",
        "https://blog.facebook.com",
        "https://investor.facebook.com",
        "https://privacy.facebook.com",
        "https://messenger.facebook.com",
        "https://api.facebook.com",
        "https://l.facebook.com",
        "https://connect.facebook.com",
        "https://pay.facebook.com",
        "https://security.facebook.com",
        "https://api.messenger.com",
        "https://accountscenter.facebook.com",
        "https://web.facebook.com",
        "https://touch.facebook.com",
        "https://static.facebook.com",
        "https://upload.facebook.com",
        "https://www.facebook.com/groups/",
        "https://www.facebook.com/events/",
        "https://www.facebook.com/marketplace/",
        "https://www.facebook.com/watch/",
        "https://www.facebook.com/gaming/"
    ],
    "Twitch": [
        "https://www.twitch.tv",
        "https://m.twitch.tv",
        "https://api.twitch.tv",
        "https://blog.twitch.tv",
        "https://help.twitch.tv",
        "https://developer.twitch.tv",
        "https://ads.twitch.tv",
        "https://partners.twitch.tv",
        "https://about.twitch.tv",
        "https://status.twitch.tv",
        "https://affiliate.twitch.tv",
        "https://dashboard.twitch.tv",
        "https://link.twitch.tv",
        "https://music.twitch.tv",
        "https://prime.twitch.tv",
        "https://clips.twitch.tv",
        "https://player.twitch.tv",
        "https://spade.twitch.tv",
        "https://gql.twitch.tv",
        "https://passport.twitch.tv",
        "https://usher.twitch.tv",
        "https://www.twitch.tv/directory",
        "https://www.twitch.tv/subscriptions",
        "https://www.twitch.tv/drops"
    ],
    "Hulu": [
        "https://www.hulu.com",
        "https://secure.hulu.com",
        "https://play.hulu.com",
        "https://help.hulu.com",
        "https://blog.hulu.com",
        "https://ads.hulu.com",
        "https://developer.hulu.com",
        "https://about.hulu.com",
        "https://press.hulu.com",
        "https://careers.hulu.com",
        "https://support.hulu.com",
        "https://m.hulu.com",
        "https://api.hulu.com",
        "https://content.hulu.com",
        "https://live.hulu.com",
        "https://auth.hulu.com",
        "https://activate.hulu.com",
        "https://account.hulu.com",
        "https://help.hulu.com/legal/privacy",
        "https://www.hulu.com/start",
        "https://www.hulu.com/live-tv",
        "https://www.hulu.com/movies"
    ],
    "BBC": [
        "https://www.bbc.co.uk",
        "https://news.bbc.co.uk",
        "https://iplayer.bbc.co.uk",
        "https://sport.bbc.co.uk",
        "https://weather.bbc.co.uk",
        "https://shop.bbc.co.uk",
        "https://careers.bbc.co.uk",
        "https://about.bbc.co.uk",
        "https://help.bbc.co.uk",
        "https://api.bbc.co.uk",
        "https://developer.bbc.co.uk",
        "https://blog.bbc.co.uk",
        "https://support.bbc.co.uk",
        "https://m.bbc.co.uk",
        "https://feeds.bbc.co.uk",
        "https://education.bbc.co.uk",
        "https://music.bbc.co.uk",
        "https://www.bbc.com",
        "https://www.bbc.com/news",
        "https://www.bbc.com/sport",
        "https://www.bbc.com/weather"
    ],
    "CNN": [
        "https://www.cnn.com",
        "https://edition.cnn.com",
        "https://m.cnn.com",
        "https://money.cnn.com",
        "https://politics.cnn.com",
        "https://travel.cnn.com",
        "https://health.cnn.com",
        "https://ads.cnn.com",
        "https://api.cnn.com",
        "https://blog.cnn.com",
        "https://about.cnn.com",
        "https://developer.cnn.com",
        "https://support.cnn.com",
        "https://careers.cnn.com",
        "https://video.cnn.com",
        "https://weather.cnn.com",
        "https://www.cnn.com/videos",
        "https://www.cnn.com/specials",
        "https://www.cnn.com/interactive"
    ],
    "Amazon": [
        "https://www.amazon.com",
        "https://aws.amazon.com",
        "https://smile.amazon.com",
        "https://seller.amazon.com",
        "https://developer.amazon.com",
        "https://advertising.amazon.com",
        "https://affiliates.amazon.com",
        "https://about.amazon.com",
        "https://help.amazon.com",
        "https://blog.amazon.com",
        "https://careers.amazon.com",
        "https://api.amazon.com",
        "https://music.amazon.com",
        "https://video.amazon.com",
        "https://prime.amazon.com",
        "https://m.amazon.com",
        "https://kindle.amazon.com",
        "https://pay.amazon.com",
        "https://www.amazon.com/gp/cart/view.html",
        "https://www.amazon.com/gp/your-account/order-history",
        "https://www.amazon.com/ap/signin",
        "https://www.amazon.com/prime",
        "https://www.amazon.com/deals",
        "https://a.co",
        "https://aws.amazon.com/marketplace"
    ],
    "eBay": [
        "https://www.ebay.com",
        "https://m.ebay.com",
        "https://signin.ebay.com",
        "https://seller.ebay.com",
        "https://developer.ebay.com",
        "https://about.ebay.com",
        "https://help.ebay.com",
        "https://www.ebay.com/sch/",
        "https://www.ebay.com/myebay",
        "https://www.ebay.com/deals",
        "https://www.ebay.com/usr/",
        "https://auth.ebay.com",
        "https://cart.ebay.com",
        "https://pay.ebay.com"
    ],
    "Ubisoft": [
        "https://status.ubisoft.com",
        "https://shop.ubisoft.com",
        "https://redirection.ubisoft.com",
        "https://www.ubisoft.com",
        "https://account.ubisoft.com",
        "https://support.ubisoft.com",
        "https://forums.ubisoft.com",
        "https://connect.ubisoft.com",
        "https://uplay.ubi.com"
    ],
    "Dropbox": [
        "https://about.dropbox.com",
        "https://www.dropbox.com",
        "https://www.dropboxforum.com",
        "https://help.dropbox.com",
        "https://www.dropbox.com/login",
        "https://www.dropbox.com/home",
        "https://api.dropbox.com",
        "https://content.dropbox.com"
    ],
    "Telegram": [
        "https://core.telegram.org",
        "https://telegram.org",
        "https://t.me",
        "https://status.telegram.org",
        "https://desktop.telegram.org",
        "https://web.telegram.org",
        "https://api.telegram.org",
        "https://my.telegram.org"
    ],
    "Discord": [
        "https://careers.discord.com",
        "https://community.discord.com",
        "https://about.discord.com",
        "https://discord.com",
        "https://safety.discord.com",
        "https://support.discord.com",
        "https://status.discord.com",
        "https://discord.com/invite",
        "https://cdn.discordapp.com",
        "https://gateway.discord.gg"
    ],
    "EpicGames": [
        "https://community.epicgames.com",
        "https://launcher.epicgames.com",
        "https://support.epicgames.com",
        "https://www.epicgames.com",
        "https://store.epicgames.com",
        "https://account.epicgames.com",
        "https://unrealengine.com",
        "https://api.epicgames.com"
    ],
    "GitHub": [
        "https://about.github.com",
        "https://actions.github.com",
        "https://www.github.com",
        "https://docs.github.com",
        "https://support.github.com",
        "https://status.github.com",
        "https://api.github.com",
        "https://raw.githubusercontent.com",
        "https://gist.github.com"
    ],
    "HumbleBundle": [
        "https://store.humblebundle.com",
        "https://www.humblebundle.com",
        "https://support.humblebundle.com",
        "https://blog.humblebundle.com",
        "https://account.humblebundle.com"
    ],
    "PlayStation": [
        "https://psnprofiles.com",
        "https://store.playstation.com",
        "https://www.playstation.com",
        "https://my.playstation.com",
        "https://support.playstation.com",
        "https://account.sonyentertainmentnetwork.com",
        "https://direct.playstation.com"
    ],
    "Itch": [
        "https://account.itch.io",
        "https://itch.io",
        "https://api.itch.io",
        "https://itch.io/login",
        "https://itch.io/docs",
        "https://itch.io/jam",
        "https://itch.io/community"
    ],
    "Nintendo": [
        "https://www.nintendo.co.jp",
        "https://support.nintendo.com",
        "https://www.nintendo.com",
        "https://accounts.nintendo.com",
        "https://store.nintendo.com",
        "https://my.nintendo.com",
        "https://ec.nintendo.com",
        "https://api.accounts.nintendo.com"
    ],
    "GOG": [
        "https://cdn.gog.com",
        "https://shop.gog.com",
        "https://developer.gog.com",
        "https://status.gog.com",
        "https://blog.gog.com",
        "https://www.gog.com",
        "https://support.gog.com",
        "https://auth.gog.com"
    ],
    "Xbox": [
        "https://events.xbox.com",
        "https://www.xbox.com",
        "https://account.xbox.com",
        "https://support.xbox.com",
        "https://store.xbox.com",
        "https://gamepass.xbox.com",
        "https://rewards.xbox.com"
    ],
    "NexusMods": [
        "https://community.nexusmods.com",
        "https://support.nexusmods.com",
        "https://www.nexusmods.com",
        "https://users.nexusmods.com",
        "https://forums.nexusmods.com",
        "https://api.nexusmods.com"
    ],
    "EA": [
        "https://eaapp.com",
        "https://account.ea.com",
        "https://www.ea.com",
        "https://help.ea.com",
        "https://www.origin.com",
        "https://api.ea.com",
        "https://signin.ea.com"
    ],
    "RockstarGames": [
        "https://careers.rockstargames.com",
        "https://store.rockstargames.com",
        "https://www.rockstargames.com",
        "https://support.rockstargames.com",
        "https://socialclub.rockstargames.com",
        "https://media.rockstargames.com"
    ],
    "TGC": [
        "https://cdn.tgcofficial.games",
        "https://store.tgcofficial.games",
        "https://community.tgcofficial.games",
        "https://thatgamecompany.com",
        "https://sky.thatgamecompany.com",
        "https://api.thatgamecompany.com",
        "https://support.thatgamecompany.com",
        "https://blog.thatgamecompany.com",
        "https://sky-api.thatgamecompany.com",
        "https://account.thatgamecompany.com",
        "https://live.thatgamecompany.com"
    ],
    "Bilibili": [
        "https://www.bilibili.tv",
        "https://www.bilibili.com",
        "https://m.bilibili.com",
        "https://api.bilibili.com",
        "https://live.bilibili.com",
        "https://space.bilibili.com",
        "https://search.bilibili.com",
        "https://account.bilibili.com",
        "https://app.bilibili.com",
        "https://passport.bilibili.com",
        "https://pay.bilibili.com",
        "https://cm.bilibili.com",
        "https://message.bilibili.com",
        "https://member.bilibili.com",
        "https://comic.bilibili.com",
        "https://h.bilibili.com",
        "https://link.bilibili.com",
        "https://game.bilibili.com",
        "https://shop.bilibili.com",
        "https://www.bilibili.com/video/",
        "https://www.bilibili.com/anime/",
        "https://www.bilibili.com/read/",
        "https://www.bilibili.com.tw",
        "https://passport.biliapi.com",
        "https://data.bilibili.com",
        "https://interface.bilibili.com",
        "https://bangumi.bilibili.com",
        "https://big.bilibili.com",
        "https://pay.biliapi.com",
        "https://grpc.biliapi.net"
    ]
}

# 全局变量
request_counter = 0
error_counter = 0
counter_lock = threading.Lock()
stop_event = threading.Event()
executor = None
domain_status = {site: {'speed': 0, 'status': 'Idle', 'last_time': 0, 'size': 0} for site in WEBSITES}
status_lock = threading.Lock()
log_queue = Queue()

class NetworkStressTestApp:
    def __init__(self, root):
        self.root = root
        self.root.title("网络压力测试工具 v1.0.1")  # 添加版本号
        self.root.geometry("1000x800")
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        # 初始化日志队列
        self.log_queue = Queue()
        self.queue_handler = QueueHandler(self.log_queue)
        self.queue_handler.setFormatter(logging.Formatter('%(asctime)s - %(threadName)s - %(levelname)s - %(message)s'))
        logger.addHandler(self.queue_handler)

        # UI 组件
        try:
            self.create_menu()
            self.create_widgets()
            self.update_log()
            self.update_chart()
            self.update_domain_list()
        except Exception as e:
            logger.error(f"初始化 UI 失败: {traceback.format_exc()}")
            messagebox.showerror("错误", f"初始化失败: {e}\n请检查 access_log.txt 和 error_log.txt")
            sys.exit(1)

    def create_menu(self):
        """创建顶部菜单栏"""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="文件", menu=file_menu)
        file_menu.add_command(label="域名列表", command=self.open_domain_editor)
        file_menu.add_command(label="检查更新", command=lambda: None)

    def create_widgets(self):
        """创建 UI 组件"""
        main_frame = ttkb.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky="nsew")
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        # 输入框架
        input_frame = ttkb.Frame(main_frame, padding="10")
        input_frame.grid(row=0, column=0, sticky="ew")

        ttkb.Label(input_frame, text="每个网站的线程数 (1-10):", font=("SimHei", 12)).grid(row=0, column=0, padx=5)
        self.threads_entry = ttkb.Entry(input_frame, width=5, font=("SimHei", 12))
        self.threads_entry.insert(0, "5")
        self.threads_entry.grid(row=0, column=1, padx=5)

        ttkb.Label(input_frame, text="访问间隔 (秒, 5-15):", font=("SimHei", 12)).grid(row=0, column=2, padx=5)
        self.interval_entry = ttkb.Entry(input_frame, width=5, font=("SimHei", 12))
        self.interval_entry.insert(0, "10")  # 默认值改为 10
        self.interval_entry.grid(row=0, column=3, padx=5)

        # 按钮框架
        button_frame = ttkb.Frame(main_frame, padding="10")
        button_frame.grid(row=1, column=0, sticky="ew")

        self.start_button = ttkb.Button(button_frame, text="开始", command=self.start_test, bootstyle=PRIMARY)
        self.start_button.grid(row=0, column=0, padx=5)
        self.stop_button = ttkb.Button(button_frame, text="停止", command=self.stop_test, state="disabled", bootstyle=DANGER)
        self.stop_button.grid(row=0, column=1, padx=5)

        # 状态框架
        status_frame = ttkb.Frame(main_frame, padding="10")
        status_frame.grid(row=2, column=0, sticky="ew")

        self.request_label = ttkb.Label(status_frame, text="请求总数: 0", font=("SimHei", 12))
        self.request_label.grid(row=0, column=0, padx=5)
        self.error_label = ttkb.Label(status_frame, text="错误总数: 0", font=("SimHei", 12))
        self.error_label.grid(row=0, column=1, padx=5)

        # 日志显示
        self.log_text = scrolledtext.ScrolledText(main_frame, height=10, width=90, state="disabled", font=("SimHei", 10))
        self.log_text.grid(row=3, column=0, padx=10, pady=10, sticky="nsew")

        # 图表显示
        self.fig, self.ax = plt.subplots(figsize=(8, 4))
        self.canvas = FigureCanvasTkAgg(self.fig, master=main_frame)
        self.canvas.get_tk_widget().grid(row=4, column=0, padx=10, pady=10, sticky="nsew")
        main_frame.grid_rowconfigure(4, weight=1)
        main_frame.grid_columnconfigure(0, weight=1)

    def open_domain_editor(self):
        """打开域名列表编辑窗口"""
        editor_window = Toplevel(self.root)
        editor_window.title("域名列表编辑")
        editor_window.geometry("800x600")

        # 域名列表显示
        self.domain_listbox = ttkb.Treeview(editor_window, columns=("Site", "Domain"), show="headings", selectmode="extended")
        self.domain_listbox.heading("Site", text="网站名称")
        self.domain_listbox.heading("Domain", text="域名")
        self.domain_listbox.column("Site", width=200)
        self.domain_listbox.column("Domain", width=500)
        self.domain_listbox.pack(padx=10, pady=10, fill="both", expand=True)

        # 滚动条
        scroll = ttkb.Scrollbar(editor_window, orient="vertical", command=self.domain_listbox.yview)
        scroll.pack(side="right", fill="y")
        self.domain_listbox.configure(yscrollcommand=scroll.set)

        # 添加域名输入框和按钮
        add_frame = ttkb.Frame(editor_window, padding="10")
        add_frame.pack(fill="x")

        ttkb.Label(add_frame, text="新网站名称:", font=("SimHei", 12)).pack(side="left", padx=5)
        self.site_name_entry = ttkb.Entry(add_frame, width=15, font=("SimHei", 12))
        self.site_name_entry.pack(side="left", padx=5)

        ttkb.Label(add_frame, text="域名列表 (逗号分隔):", font=("SimHei", 12)).pack(side="left", padx=5)
        self.domain_list_entry = ttkb.Entry(add_frame, width=30, font=("SimHei", 12))
        self.domain_list_entry.pack(side="left", padx=5)

        self.add_domain_button = ttkb.Button(add_frame, text="添加网站", command=self.add_domain, bootstyle=SUCCESS)
        self.add_domain_button.pack(side="left", padx=5)

        # 右键菜单
        context_menu = tk.Menu(self.domain_listbox, tearoff=0)
        context_menu.add_command(label="删除选中域名", command=self.delete_domains)
        self.domain_listbox.bind("<Button-3>", lambda event: self.show_context_menu(event, context_menu))

        # 填充域名列表
        self.update_domain_list()

    def show_context_menu(self, event, menu):
        """显示右键菜单"""
        menu.post(event.x_root, event.y_root)

    def delete_domains(self):
        """删除选中的多个域名"""
        try:
            selected_items = self.domain_listbox.selection()
            if not selected_items:
                messagebox.showwarning("警告", "请至少选择一个域名")
                return

            for item in selected_items:
                values = self.domain_listbox.item(item, "values")
                site_name, domain = values
                if site_name in WEBSITES and domain in WEBSITES[site_name]:
                    WEBSITES[site_name].remove(domain)
                    logger.info(f"删除域名: {site_name} - {domain}")
                    if not WEBSITES[site_name]:
                        del WEBSITES[site_name]
                        del domain_status[site_name]
            self.update_domain_list()
            self.update_chart()
        except Exception as e:
            logger.error(f"删除域名失败: {traceback.format_exc()}")
            messagebox.showerror("错误", f"删除域名失败: {e}")

    def add_domain(self):
        """手动添加域名"""
        try:
            site_name = self.site_name_entry.get().strip()
            domain_list = [d.strip() for d in self.domain_list_entry.get().split(',') if d.strip()]
            if not site_name or not domain_list:
                messagebox.showerror("错误", "请输入网站名称和至少一个域名")

            for i, domain in enumerate(domain_list):
                if not domain.startswith(('http://', 'https://')):
                    domain_list[i] = f"https://{domain}"

            if site_name in WEBSITES:
                messagebox.showwarning("警告", "网站已存在，追加域名")
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
            messagebox.showerror("错误", f"添加域名失败: {e}\n请检查 access_log.txt")

    def update_log(self):
        """实时更新日志到文本框"""
        try:
            while not self.log_queue.empty():
                msg = self.log_queue.get()
                self.log_text.configure(state="normal")
                self.log_text.insert(tk.END, msg + "\n")
                self.log_text.see(tk.END)
                self.log_text.configure(state="disabled")
            self.root.after(100, self.update_log)
        except Exception as e:
            logger.error(f"更新日志失败: {traceback.format_exc()}")

    def update_chart(self):
        """更新图表"""
        try:
            with status_lock:
                sites = list(domain_status.keys())
                speeds = [domain_status[s]['speed'] for s in sites]
                statuses = [domain_status[s]['status'] for s in sites]

            self.ax.clear()
            bars = self.ax.bar(sites, speeds, color='orange')
            self.ax.set_ylabel('网速 (KB/s)', fontproperties='SimHei')
            self.ax.set_title('每个网站实时网速和状态', fontproperties='SimHei')
            self.ax.tick_params(labelrotation=45)

            for bar, status in zip(bars, statuses):
                height = bar.get_height()
                self.ax.text(bar.get_x() + bar.get_width() / 2, height, status, ha='center', va='bottom', rotation=45, fontsize=8)

            self.fig.tight_layout()
            self.canvas.draw()
            if not stop_event.is_set():
                self.root.after(5000, self.update_chart)
        except Exception as e:
            logger.error(f"更新图表失败: {traceback.format_exc()}")

    def update_counters(self):
        """更新请求和错误计数"""
        try:
            self.request_label.configure(text=f"请求总数: {request_counter}")
            self.error_label.configure(text=f"错误总数: {error_counter}")
            if not stop_event.is_set():
                self.root.after(1000, self.update_counters)
        except Exception as e:
            logger.error(f"更新计数器失败: {traceback.format_exc()}")

    def update_domain_list(self):
        """更新域名列表显示"""
        try:
            if hasattr(self, 'domain_listbox'):
                self.domain_listbox.delete(*self.domain_listbox.get_children())
                for site, domains in WEBSITES.items():
                    for domain in domains:
                        self.domain_listbox.insert("", "end", values=(site, domain))
        except Exception as e:
            logger.error(f"更新域名列表失败: {traceback.format_exc()}")

    def visit_url(self, site_name, urls, session):
        """访问单个网站的随机 URL"""
        global request_counter, error_counter
        while not stop_event.is_set():
            start_time = time.time()
            size = 0
            status = 'Idle'
            try:
                url = random.choice(urls)
                request_url = f"{url}{'?num=' if '?' not in url else '&num='}{request_counter}"
                headers = {'User-Agent': random.choice(USER_AGENTS)}
                response = session.get(request_url, timeout=30, verify=False, headers=headers)
                size = len(response.content) / 1024
                with counter_lock:
                    request_counter += 1
                    logger.info(f"访问 {site_name} ({request_url}), 状态码: {response.status_code}")
                if response.status_code == 429:
                    logger.warning(f"触发 429 率限，额外等待 5 秒")
                    time.sleep(5)
                status = f"OK ({response.status_code})" if response.status_code == 200 else f"Error ({response.status_code})"
                try:
                    interval = float(self.interval_entry.get())
                    interval = max(5.0, min(interval, 15.0))  # 限制区间为 5-15 秒
                except ValueError:
                    interval = 10.0  # 默认值 10 秒
                time.sleep(random.uniform(interval / 2, interval))
            except requests.exceptions.SSLError as e:
                with counter_lock:
                    error_counter += 1
                logger.error(f"SSL 错误 {site_name} ({request_url}): {e} - 跳过")
                time.sleep(1)
                status = 'SSL Error'
            except requests.exceptions.ConnectTimeout as e:
                with counter_lock:
                    error_counter += 1
                logger.error(f"连接超时 {site_name} ({request_url}): {e} - 重试")
                time.sleep(2)
                status = 'Timeout'
            except requests.exceptions.ReadTimeout as e:
                with counter_lock:
                    error_counter += 1
                logger.error(f"读取超时 {site_name} ({request_url}): {e} - 跳过")
                time.sleep(1)
                status = 'Timeout'
            except requests.exceptions.NameResolutionError as e:
                with counter_lock:
                    error_counter += 1
                logger.error(f"域名解析失败 {site_name} ({request_url}): {e} - 跳过域名")
                urls.remove(url) if url in urls else None
                status = 'DNS Error'
            except requests.exceptions.RequestException as e:
                with counter_lock:
                    error_counter += 1
                logger.error(f"其他请求错误 {site_name} ({request_url}): {e} - 跳过")
                time.sleep(1)
                status = 'Error'
            finally:
                duration = time.time() - start_time
                speed = size / duration if duration > 0 else 0
                with status_lock:
                    domain_status[site_name] = {'speed': speed, 'status': status, 'last_time': time.time(), 'size': size}

    def start_test(self):
        """启动测试"""
        global executor
        try:
            threads_per_site = int(self.threads_entry.get())
            if not 1 <= threads_per_site <= 10:
                raise ValueError("线程数必须在 1-10 之间")
        except ValueError:
            messagebox.showerror("错误", "无效线程数，使用默认值 5")
            threads_per_site = 5
            self.threads_entry.delete(0, tk.END)
            self.threads_entry.insert(0, "5")

        global request_counter, error_counter
        with counter_lock:
            request_counter = 0
            error_counter = 0
        with status_lock:
            for site in WEBSITES:
                domain_status[site] = {'speed': 0, 'status': 'Idle', 'last_time': 0, 'size': 0}

        self.log_text.configure(state="normal")
        self.log_text.delete(1.0, tk.END)
        self.log_text.configure(state="disabled")

        session = requests.Session()
        retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry)
        session.mount('http://', adapter)
        session.mount('https://', adapter)

        stop_event.clear()
        executor = ThreadPoolExecutor(max_workers=threads_per_site * len(WEBSITES))
        for site_name, urls in WEBSITES.items():
            for i in range(threads_per_site):
                executor.submit(self.visit_url, site_name, urls, session)

        logger.info(f"测试开始，线程数: {threads_per_site}，目标网站: {list(WEBSITES.keys())}")
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.update_counters()

    def stop_test(self):
        """停止测试"""
        global executor
        stop_event.set()
        if executor:
            executor.shutdown(wait=False)
        logger.info("测试已停止")
        self.start_button.configure(state="normal")
        self.stop_button.configure(state="disabled")

    def on_closing(self):
        """处理窗口关闭"""
        if messagebox.askokcancel("退出", "确定要退出吗？"):
            self.stop_test()
            self.root.destroy()
            sys.exit(0)

def main():
    root = ttkb.Window(themename="litera")
    app = NetworkStressTestApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()