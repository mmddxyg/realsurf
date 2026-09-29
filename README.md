# 拟真冲浪 RealSurf

<img src="icon_preview.png" width="110" alt="RealSurf icon">

> 模拟真人上网行为的轻量工具，用于 **OpenClash / 代理链路连通性验证**、**Smart 策略组训练数据采集** 与 **AdGuardHome (ADG) DNS 缓存预热 / 命中测试**。

**🌐 语言 / Language / Ngôn ngữ：** [中文](#中文) · [English](#english) · [Tiếng Việt](#tiếng-việt)

<sub>公开仓库 · Public repository · Kho công khai</sub>

---

## 更新日志 / Changelog / Nhật ký thay đổi

### v1.3.2（2026-09-29）— 图表换指标 + 域名池扩容 `当前版本`

- 📊 **柱状图指标：网速 KB/s → 真实访问次数**。原指标有个硬伤——大量站点只回 204/302、命中 ADG/DNS 缓存，或本身没有可下载的 body，读到的字节数恒为 0，**网速恒为 0 KB/s**，图表看上去一片空白。现改为：
  - **柱高 = 整轮累计访问次数**（请求真发出去了就 ≥ 1，是「真实访问」的直接证据）；
  - **柱顶标注 = 平均响应耗时 ms**（该站有失败时改标失败原因，如 `Timeout` / `DNS Error`）；
  - **配色按成功率**：🟢 全成功 / 🟠 部分失败 / 🔴 全失败（右上角带图例）；
  - 按次数排序取 **Top 24**，超出时标题显示 `Top 24/总数`，避免几十根柱子糊成一片。
- 🌐 **域名池扩容：54 → 79 个品牌，543 → 649 条域名（新增 106 条）**。新增站点全部**逐个真机实测可达后**才加入：OpenAI / ChatGPT、Claude、Steam、腾讯 QQ·微信、淘宝天猫·阿里、京东、网易、抖音、小红书、华为、NVIDIA、Adobe、Zoom、Slack、Notion、Figma、Yahoo、IMDb、纽约时报、PayPal、Airbnb、Booking、Stripe、DuckDuckGo、Speedtest。
  > 实测淘汰 3 条死链：`steamstatic.com`（代理拒绝）、`www.iesdouyin.com`（SSL 握手失败）、`www.adobe.com`（读超时）——加进去只会被自动剔除并刷日志，所以不放。
- 🐞 **修复站点统计**：原来每次访问**整体覆盖**（只留最后一次的状态与网速），新站点的成功率无从统计；现改为**整轮累加**（`visits` / `ok` / `ms` / `size`），统一走 `bump_site_stat()`，顺带消除三处重复的字面量初始化。

<details><summary>English</summary>

**v1.3.2 (2026-09-29)** — Chart metric switched (speed → real visits) + domain pool expanded.

- **The bar chart no longer plots KB/s.** Many sites only return 204/302, are served from the ADG/DNS cache, or simply have no downloadable body — the byte count is always 0, so **speed is always 0 KB/s** and the chart looked empty. Now: **bar height = cumulative visit count** (a request that actually went out is always ≥ 1), **bar label = average latency in ms** (switches to the failure reason when that site has failures), **colour by success rate** 🟢 all OK / 🟠 partly failed / 🔴 all failed with a legend, and sorted by visits with **top 24 only**.
- **Domain pool expanded: 54 → 79 brands, 543 → 649 URLs (+106).** Every new site was **probed on the real network first**: OpenAI/ChatGPT, Claude, Steam, Tencent, Taobao·Ali, JD, NetEase, Douyin, Xiaohongshu, Huawei, NVIDIA, Adobe, Zoom, Slack, Notion, Figma, Yahoo, IMDb, NYTimes, PayPal, Airbnb, Booking, Stripe, DuckDuckGo, Speedtest. Three dead ones were rejected: `steamstatic.com` (proxy refused), `www.iesdouyin.com` (SSL handshake failure), `www.adobe.com` (read timeout).
- **Fix**: per-site stats used to be **overwritten** on every visit, making success rates impossible to compute; now they **accumulate over the run** through a single `bump_site_stat()`.

</details>

<details><summary>Tiếng Việt</summary>

**v1.3.2 (2026-09-29)** — Đổi chỉ số biểu đồ (tốc độ → lượt truy cập thật) + mở rộng danh sách tên miền.

- **Biểu đồ cột không còn vẽ KB/s.** Nhiều trang chỉ trả 204/302, được phục vụ từ cache ADG/DNS, hoặc không có nội dung tải về — số byte luôn bằng 0 nên **tốc độ luôn là 0 KB/s** và biểu đồ trông trống rỗng. Nay: **chiều cao cột = số lượt truy cập tích lũy** (yêu cầu đã thực sự gửi đi thì luôn ≥ 1), **nhãn trên cột = độ trễ trung bình (ms)** (đổi thành lý do lỗi nếu trang đó có lỗi), **màu theo tỉ lệ thành công** 🟢 / 🟠 / 🔴 kèm chú giải, sắp xếp theo số lượt và **chỉ vẽ top 24**.
- **Mở rộng danh sách: 54 → 79 thương hiệu, 543 → 649 URL (+106).** Mọi trang mới đều được **kiểm tra thật trên mạng trước** khi thêm. Ba tên miền chết đã bị loại: `steamstatic.com`, `www.iesdouyin.com`, `www.adobe.com`.
- **Sửa lỗi**: thống kê theo trang trước đây bị **ghi đè** mỗi lần truy cập, khiến không thể tính tỉ lệ thành công; nay **tích lũy cả lượt chạy** qua một hàm `bump_site_stat()` duy nhất.

</details>

### 历史版本 / Older releases

| 版本 | 日期 | 变更摘要 |
| --- | --- | --- |
| **v1.3.1** | 2026-09-28 | **移除「记录连接明细(CSV)」功能**：勾选框与 `conn_log.csv`（15 列、32MB 分卷）、`_record_conn` / `_open_conn_log` / `csv`·`datetime` 导入整体下线（客户端拿不到 `group_name` / `node_name`，该表不能替代内核打标，样本核对已在 mihomo 日志侧完成）；按钮行恢复【开始】【停止】【穿透缓存】三件套，源码零 CSV 残留。 |
| **v1.3.0** | 2026-09-28 | **流量形态大升级**：新增**上传**（约 20%：表单/媒体/大文件三档）、**大文件持续下载**（约 5%）、**小包高频交互**（约 12%），补齐上行与小包特征；域名池换真实榜单档位 + **幂律加权**（6:1 → 1000/300/100/30 ≈ 100:1）；页面簇发改**真并发**（触发率 0.4 → 0.9）；新增可选 **HTTP/2·HTTP/3（httpx）** 通道，握手失败自动回退 requests；视频改 **DASH/HLS 两级分片**（主清单 → 子清单 → 媒体分片）；`?num=` 缓存穿透改为**默认关闭**的开关。 |
| **v1.2.1** | 2026-09-28 | **修复「一直提示更新频繁 / 检查更新失败」**：弃用有速率限制的 GitHub REST API（未鉴权仅 60 次/小时/IP，共享出口被打满即 403），改用**无速率限制的 `releases.atom` + 发布页 302**；修复「发现新版本点击没反应」——下载改**后台线程 + 百分比进度条弹窗**（含已下载/总大小/实时速度，可取消），所有更新弹窗回归主线程并居中置顶；EXE 资产名带版本号。 |
| **v1.2.0** | 2026-09-28 | 修复 3 个稳定性 bug（DNS 解析失败域名现在能立即剔除 / 子线程不再读 Tk 控件消除崩溃 / 日志改 5MB×2 轮转 + 修 Session 泄漏）；默认并发 16→8、重试降为 1 次连接重试、子资源加 256KB 上限，降低对旁路由与 ADG 的冲击。 |
| v1.1.0 | 2026-09-26 | 多语言界面：中文 / English / Tiếng Việt，**自动识别 Windows 默认语言**。 |
| v1.0.0 | 2026-09-25 | 首个版本：短请求浏览 + 长连接视频流模拟、断联自动恢复、失效域名自动剔除、站点编辑器、GitHub 更新检查。 |

<sub>各版本完整说明见 [Releases](https://github.com/mmddxyg/realsurf/releases)。</sub>

---

## 中文

### 这是什么

`拟真冲浪 RealSurf`（原名「真实上网环境模拟器」）在本地发起大量「像真人」的网络访问，
让出口流量具备**多种真实形态**（短请求 / 长视频流 / 上传 / 大文件下载 / 小包高频交互），
从而更贴近真实用户、补足 Smart 组训练所需的流量特征；
此外也能给 **AdGuardHome (ADG) 的 DNS 缓存做预热与命中测试**：

- **短请求浏览**：轮换 4 套浏览器 UA（Chrome / Edge / Firefox × Win / macOS），
  带 `Referer` / `Sec-Fetch-*` / `Accept-Language` 等完整请求头，5–30s 随机间隔，
  多子域名访问，连接保活（keep-alive）。
- **长连接（视频流）模拟**：按可配比例把部分 worker 切换为「看视频」会话——
  **HLS/DASH 分片拉取**（m3u8 主清单 → 子清单 → 媒体分片两级解析，变长分片 + 并行 2–4 路，
  含 `EXT-X-MAP` 初始化段），或 Range 分段拉取公开测试视频，或打开视频平台观看页并伴随
  零星子资源请求，带真实缓冲间隙与观看时长。
- **上传 / 大文件下载 / 小包交互（v1.3.0 新增）**：约 20% 概率发**上传**（表单 10–100KB /
  媒体 1–5MB / 大文件 20–100MB 三档），约 5% 发**大文件持续下载**（网盘 / 驱动型，20–100MB），
  约 12% 发**小包高频交互**（IM / 游戏心跳 / 长轮询，3–8 次连发）——补齐上行与小包特征。
- **HTTP/2 · HTTP/3 通道**：约 70% 流量走可选 `httpx` 通道（h2/h3），其余走 requests h1.1；
  未安装 httpx 时自动回退，功能不受影响。
- **断联自动恢复**：内置网络监控线程，全部失败即判定断联、暂停发流并探测，恢复后自动续上。
- **失效域名自动剔除**：连续失败达阈值（DNS 错误立即）的域名自动从列表移除。
- **站点编辑器**：图形化增删站点、导出 JSON；柱状图实时展示**各站点真实访问次数**（柱高=整轮累计访问次数，
  柱顶标注平均响应耗时 ms，配色按成功率：🟢 全成功 / 🟠 部分失败 / 🔴 全失败），按次数排序取 Top 24。
  > 早期版本画的是「网速 KB/s」，但大量站点只回 204/302 或命中缓存、body 恒为 0 字节，画出来永远是 0，故 v1.3.2 换成访问次数。
- **ADG DNS 缓存预热 / 命中测试**：先跑一轮把常用域名解析结果灌入 AdGuardHome 缓存，
  再观察命中率与解析延迟的变化，用来验证 ADG 缓存链路是否正常工作。
  > 注意：`?num=` 缓存穿透现在是**默认关闭**的勾选项「穿透缓存(?num=)」。旧版每次都加 `?num=`，会把 ADG 缓存直接打穿，与「预热缓存」的目的相悖。
- **多语言界面**：中文 / English / Tiếng Việt，**自动识别 Windows 默认语言**切换
  （中文系列→中文，越南语→越南语，其余地区→英文），也可用菜单「语言」手动切换并持久化。

> ⚠️ 本工具仅用于个人代理连通性验证 / 训练数据采集，请遵守目标站点服务条款，勿用于高强度打流或攻击。

### 下载 / 更新

- 到本仓库 **Releases** 下载最新的 `realsurf<版本>.exe`（如 `realsurf1.3.2.exe`；单文件，双击即用，无需安装）。
  **发布资产名带版本号**，下载后一看文件名就知道是哪个版本。
- 软件启动后会**静默检查一次 GitHub 更新**；也可通过菜单「帮助 → 检查更新」手动检查，
  发现新版本可一键下载并自动替换重启。

### 使用方法

1. 双击 `realsurf.exe`。
2. 设置并发线程（默认 8）、访问间隔（默认 10s）。
3. 若走做了 TLS 拦截的代理，勾选「跳过证书校验」。
4. 设置长连接比例（默认 20%）与单次观看时长（默认 45s）。
5. 点「开始」即可。日志写入同目录 `access_log.txt`。
6. 关于本软件 / GitHub 地址 / 更新状态 / **界面语言切换**：菜单「帮助 → 关于」
   （启动默认弹出，窗口内可直接切中文 / English / Tiếng Việt，关闭后仍可从此菜单重新打开）。

### 从源码构建

需要 **Python 3.14.x（系统安装版，托管版缺 tkinter 无法打包 GUI）**：

```bash
python -m venv realnet_venv314
realnet_venv314\Scripts\pip install pyinstaller ttkbootstrap matplotlib requests "httpx[http2]"
realnet_venv314\Scripts\pyinstaller --onefile --noconsole --name realsurf --icon realsurf.ico --add-data "realsurf.ico;." --collect-all httpx --collect-all h2 --collect-all httpcore --collect-all anyio realnet_sim.py
```

产物在 `dist/realsurf.exe`。

### 目录结构

| 路径 | 说明 |
| --- | --- |
| `realnet_sim.py` | 主程序源码 |
| `deploy.py` | 发布脚本（推送源码 + 建/更新 GitHub Release + 上传 exe） |
| `realsurf.ico` / `icon_preview.png` | 应用图标 / README 预览图 |
| `tests/` | 测试：`smoke_headless.py`（冒烟）、`test_traffic.py`、`test_v12.py`、`test_v13.py`（v1.3.x 专项：残留守护、图表指标/配色、域名池完整性、真网络 + 离线自检）、`gui_v13_test.py`（GUI 三语言 + 布局 + 图表 + 更新通道 + 启停）、`test_update_dl.py`、`gui_update_test.py` |
| `packaging/` | 打包相关：`realsurf.spec`、`realnet_sim.spec`、`make_icon.py` |
| `archive/` | 历史遗留文件（旧版 `multi_site_access.py` 与旧 `readme.txt`） |
| `dist/` | 构建产物目录（已在 `.gitignore` 中；`deploy.py` 从这里取 exe 上传） |

运行测试（在项目根目录）：`python tests/test_v13.py`（全量，含真网络）、
`python tests/test_v13.py --offline`（只跑离线静态 + 残留检查 + 权重抽样自检）、
`python tests/gui_v13_test.py`（GUI 回归，产出截图）、
`python tests/smoke_headless.py`、`python tests/test_update_dl.py`。

### 版本

当前版本：`v1.3.2`

[↑ 回到顶部](#拟真冲浪-realsurf) · [切换到 English](#english) · [Chuyển sang Tiếng Việt](#tiếng-việt)

---

## English

### What is this

`拟真冲浪 RealSurf` (RealSurf) generates many human-like web requests locally, so the outbound
traffic mixes **several realistic shapes** (short requests / long video streams / uploads / bulk
downloads / small-packet bursts) and better resembles a real user — supplying the traffic features
Smart groups need for training. It is also handy for **warming up and hit-testing the AdGuardHome
(ADG) DNS cache**:

- **Short browsing**: rotates 4 browser UA profiles (Chrome / Edge / Firefox × Win / macOS) with
  full headers (`Referer`, `Sec-Fetch-*`, `Accept-Language`), random 5–30s intervals, many
  subdomains, keep-alive connections.
- **Long-connection (video stream) simulation**: a configurable ratio of workers become "watching
  video" sessions — **HLS/DASH segment fetching** (two-level m3u8 resolution: master → variant →
  media segments; variable-length segments, 2–4 parallel fetches, `EXT-X-MAP` init segments),
  Range-fetching public test videos, or opening video pages with sporadic sub-resource requests,
  with realistic buffering gaps and watch time.
- **Uploads / bulk downloads / small-packet bursts (new in v1.3.0)**: ~20% uploads (form 10–100KB /
  media 1–5MB / bulk 20–100MB), ~5% bulk downloads (20–100MB), ~12% high-frequency small-packet
  interaction (IM / game heartbeat / long-polling, 3–8 bursts) — filling the upstream and
  small-packet feature space that was previously empty.
- **HTTP/2 · HTTP/3**: ~70% of traffic uses the optional `httpx` channel (h2/h3), the rest stays on
  requests h1.1. Falls back automatically when httpx is unavailable — no feature is affected.
- **Auto-recovery on disconnect**: a built-in monitor detects full failure, pauses, probes, and
  auto-resumes when the network recovers.
- **Dead-domain auto-removal**: domains that keep failing (DNS errors immediately) are removed.
- **Site editor**: add/remove sites and export JSON; the bar chart shows **real visit counts per site**
  (bar = cumulative visits, label = avg latency in ms, colour by success rate: 🟢 all OK / 🟠 partly
  failed / 🔴 all failed), top 24 by visits.
  > Earlier builds plotted KB/s, but most sites only return 204/302 or come from cache so the body is
  > always 0 bytes and the chart stayed empty — v1.3.2 switched to visit counts.
- **ADG DNS cache warm-up / hit test**: run one pass to populate the AdGuardHome cache, then watch
  hit rate and resolve latency change — a quick sanity check that the ADG cache chain works.
  > Note: `?num=` cache-busting is now an **off-by-default** toggle ("Bust cache (?num=)"). The old
  > build appended `?num=` to every request, punching straight through the ADG cache and defeating
  > the warm-up purpose.
- **Multilingual UI**: 中文 / English / Tiếng Việt. **Auto-detects the Windows display language**
  (Chinese family → 中文, Vietnamese → Tiếng Việt, everything else → English); you can also switch
  manually via the "Language" menu (persisted).

> ⚠️ For personal proxy connectivity checks / training-data collection only. Respect target sites'
> terms and do not use it for heavy flooding or attacks.

### Download / Update

- Get the latest `realsurf<version>.exe` (e.g. `realsurf1.3.2.exe`) from this repo's **Releases** — the
  asset name carries the version, so you can tell versions apart at a glance (single file, just run it).
- On launch it **silently checks GitHub once** for updates; or use "Help → Check for Update" to
  check manually and one-click download + auto-replace & restart.

### Usage

1. Double-click `realsurf.exe`.
2. Set threads (default 8) and visit interval (default 10s).
3. If behind a TLS-inspecting proxy, check "Skip Cert Verify".
4. Set stream ratio (default 20%) and watch duration (default 45s).
5. Click **Start**. Logs go to `access_log.txt` next to the app.
6. About / GitHub link / update status / **UI language**: menu "Help → About" (shown on startup by
   default; switch 中文 / English / Tiếng Việt right inside the window; reopen anytime from that menu).

### Build from source

Requires **Python 3.14.x (system install; the managed build lacks tkinter and can't package GUI)**:

```bash
python -m venv realnet_venv314
realnet_venv314\Scripts\pip install pyinstaller ttkbootstrap matplotlib requests "httpx[http2]"
realnet_venv314\Scripts\pyinstaller --onefile --noconsole --name realsurf --icon realsurf.ico --add-data "realsurf.ico;." --collect-all httpx --collect-all h2 --collect-all httpcore --collect-all anyio realnet_sim.py
```

Output: `dist/realsurf.exe`.

### Version

Current version: `v1.3.2`

[↑ Back to top](#拟真冲浪-realsurf) · [切换到 中文](#中文) · [Chuyển sang Tiếng Việt](#tiếng-việt)

---

## Tiếng Việt

### Đây là gì

`拟真冲浪 RealSurf` (RealSurf) tạo ra nhiều yêu cầu web giống con người ở máy local, giúp lưu lượng
đầu ra có **nhiều dạng thực tế** (yêu cầu ngắn / luồng video dài / tải lên / tải xuống tệp lớn /
gói nhỏ tần suất cao) và giống người thật hơn — cung cấp đặc trưng lưu lượng nhóm Smart cần để huấn luyện.
Cũng rất tiện để **làm nóng và kiểm tra cache DNS của AdGuardHome (ADG)**:

- **Duyệt ngắn**: luân phiên 4 profile UA trình duyệt (Chrome / Edge / Firefox × Win / macOS) với
  header đầy đủ (`Referer`, `Sec-Fetch-*`, `Accept-Language`), khoảng cách ngẫu nhiên 5–30s, nhiều
  tên miền phụ, giữ kết nối (keep-alive).
- **Mô phỏng luồng dài (video)**: tỉ lệ worker cấu hình được chuyển thành phiên "xem video" —
  **tải phân đoạn HLS/DASH** (phân tích m3u8 hai cấp: master → biến thể → phân đoạn; phân đoạn dài
  thay đổi, 2–4 luồng song song, có `EXT-X-MAP`), lấy video kiểm thử công khai theo Range, hoặc mở
  trang video kèm yêu cầu tài nguyên thưa thớt, có khoảng nghỉ bộ đệm và thời gian xem thực tế.
- **Tải lên / tải xuống tệp lớn / gói nhỏ (mới ở v1.3.0)**: ~20% tải lên (biểu mẫu 10–100KB / media
  1–5MB / tệp lớn 20–100MB), ~5% tải xuống tệp lớn (20–100MB), ~12% tương tác gói nhỏ tần suất cao
  (IM / nhịp tim game / long-polling, 3–8 lần) — bổ sung đặc trưng phía tải lên và gói nhỏ.
- **HTTP/2 · HTTP/3**: ~70% lưu lượng dùng kênh `httpx` tùy chọn (h2/h3), còn lại requests h1.1.
  Tự động quay về khi thiếu httpx — không ảnh hưởng tính năng nào.
- **Tự phục hồi khi mất mạng**: luồng giám sát phát hiện toàn bộ thất bại, tạm dừng, dò và tự tiếp tục
  khi mạng hồi phục.
- **Tự xóa tên miền chết**: tên miền thất bại liên tục (lỗi DNS thì lập tức) sẽ bị xóa.
- **Trình biên tập trang**: thêm/xóa trang và xuất JSON; biểu đồ cột hiển thị **số lượt truy cập thật
  của từng trang** (cột = tổng lượt trong cả lượt chạy, nhãn = độ trễ trung bình ms, màu theo tỉ lệ
  thành công: 🟢 thành công hết / 🟠 lỗi một phần / 🔴 lỗi toàn bộ), lấy top 24 theo số lượt.
  > Bản cũ vẽ KB/s, nhưng hầu hết trang chỉ trả 204/302 hoặc lấy từ cache nên phần thân luôn 0 byte và biểu đồ trống — v1.3.2 đổi sang số lượt truy cập.
- **Làm nóng / kiểm tra cache DNS ADG**: chạy một lượt để nạp cache AdGuardHome, rồi theo dõi tỉ lệ
  hit và độ trễ phân giải — cách nhanh để xác nhận chuỗi cache ADG hoạt động.
  > Lưu ý: phá cache `?num=` nay là tùy chọn **mặc định TẮT** ("Phá cache (?num=)"). Bản cũ luôn thêm `?num=`, phá hỏng mục đích "làm nóng cache" của ADG.
- **Giao diện đa ngôn ngữ**: 中文 / English / Tiếng Việt. **Tự nhận biết ngôn ngữ hiển thị Windows**
  (họ tiếng Trung → 中文, tiếng Việt → Tiếng Việt, còn lại → English); cũng có thể đổi thủ công qua menu
  "Ngôn ngữ" (được lưu).

> ⚠️ Chỉ dùng để kiểm tra kết nối proxy cá nhân / thu thập dữ liệu huấn luyện. Tôn trọng điều khoản
> của trang đích, đừng dùng để flood cường độ cao hay tấn công.

### Tải / Cập nhật

- Tải `realsurf<phiên bản>.exe` mới nhất (vd `realsurf1.3.2.exe`) từ **Releases** — tên asset có kèm
  phiên bản nên nhìn là biết ngay (file duy nhất, bấm đúp để chạy).
- Khi khởi động sẽ **tự kiểm tra GitHub một lần**; hoặc dùng "Trợ giúp → Kiểm tra cập nhật" để kiểm tra
  thủ công và tải + tự thay thế, khởi động lại một chạm.

### Cách dùng

1. Bấm đúp `realsurf.exe`.
2. Đặt số luồng (mặc định 8) và khoảng cách truy cập (mặc định 10s).
3. Nếu qua proxy có chặn TLS, tích "Bỏ xác thực chứng chỉ".
4. Đặt tỉ lệ luồng (mặc định 20%) và thời gian xem (mặc định 45s).
5. Bấm **Bắt đầu**. Nhật ký ghi vào `access_log.txt` cạnh app.
6. Giới thiệu / link GitHub / trạng thái cập nhật / **ngôn ngữ giao diện**: menu "Trợ giúp → Giới thiệu"
   (hiện khi khởi động mặc định; đổi 中文 / English / Tiếng Việt ngay trong cửa sổ; mở lại từ menu đó bất cứ lúc nào).

### Build từ mã nguồn

Cần **Python 3.14.x (bản cài hệ thống; bản quản lý thiếu tkinter không đóng gói được GUI)**:

```bash
python -m venv realnet_venv314
realnet_venv314\Scripts\pip install pyinstaller ttkbootstrap matplotlib requests "httpx[http2]"
realnet_venv314\Scripts\pyinstaller --onefile --noconsole --name realsurf --icon realsurf.ico --add-data "realsurf.ico;." --collect-all httpx --collect-all h2 --collect-all httpcore --collect-all anyio realnet_sim.py
```

Kết quả: `dist/realsurf.exe`.

### Phiên bản

Phiên bản hiện tại: `v1.3.2`

[↑ Về đầu](#拟真冲浪-realsurf) · [切换到 中文](#中文) · [Switch to English](#english)
