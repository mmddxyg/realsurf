# 拟真冲浪 RealSurf

<img src="icon_preview.png" width="110" alt="RealSurf icon">

> 模拟真人上网行为的轻量工具，用于 **OpenClash / 代理链路连通性验证**、**Smart 策略组训练数据采集** 与 **AdGuardHome (ADG) DNS 缓存预热 / 命中测试**。

**🌐 语言 / Language / Ngôn ngữ：** [中文](#中文) · [English](#english) · [Tiếng Việt](#tiếng-việt)

<sub>公开仓库 · Public repository · Kho công khai</sub>

---

## 更新日志 / Changelog / Nhật ký thay đổi

**v1.2.1（2026-09-28）** — 更新组件修复

- 🐞 **修复「识别到更新但点击没反应 / 无进度反馈」（用户反馈）**：
  - 根因①：旧版 `_apply_update` 在调用线程里**同步下载约 42MB 且零进度**，界面长时间卡死，看起来像「点了没反应」。
  - 根因②：发现新版本后的 `messagebox.askyesno` 在**后台线程**直接弹出，弹窗可能落到「关于」窗口背后，用户点了却看不到确认框。
  - 修复：下载改为**后台线程**，弹出带百分比 / MB 的**进度条对话框 + 可取消按钮**；所有更新相关弹窗统一经主线程 `root.after(0, …)` 弹出，并指定正确父窗口（关于窗口打开时置于其上方）。下载完成自动写重启脚本并替换重启。

<details><summary>English</summary>

**v1.2.1 (2026-09-28)** — Update component fix. Root cause: the old updater downloaded ~42MB synchronously with no feedback (UI froze, looked unresponsive); and the "new version" yes/no dialog was shown from a background thread (could appear behind the About window). Fix: download now runs in a background thread with a progress dialog (percentage / MB bar + Cancel button); all update dialogs are posted on the main thread via `root.after(0, …)` with the correct parent window; on completion it writes a restart script and replaces itself.

</details>

<details><summary>Tiếng Việt</summary>

**v1.2.1 (2026-09-28)** — Sửa thành phần cập nhật. Nguyên nhân: bản cũ tải ~42MB đồng bộ không phản hồi (UI đông cứng); hộp thoại "có bản mới" hiện từ luồng phụ (có thể nằm sau cửa sổ Giới thiệu). Sửa: tải chạy ở luồng phụ với hộp thoại tiến trình (thanh % / MB + nút Hủy); mọi hộp thoại cập nhật hiện trên luồng chính qua `root.after(0, …)` với đúng cửa sổ cha; xong thì ghi script khởi động lại và tự thay thế.

</details>

**v1.2.0（2026-09-28）**

- **修复 3 个稳定性 bug（P0）**：① DNS 解析失败现在能被正确识别并**立即剔除失效域名**（旧版 `requests.exceptions.NameResolutionError` 不存在导致该逻辑 100% 失效）；② 子线程不再读取 Tk 控件，消除 `main thread is not in main loop` 崩溃；③ 修复日志无限膨胀（改为 5MB×2 轮转）、旧 Session 泄漏、停止后再开始图表不刷新。
- **降低对旁路由 / ADG 的冲击（P3）**：默认并发 16→**8**；重试由「3 次 + 429/5xx 重试」降为「仅 1 次连接重试」避免放大流量；子资源加 256KB 上限；背压上限改用真实并发数。
- **训练样本质量（P1 / P2）**：品牌按**热度幂律加权**投喂（头部站更频繁，缓解均匀分布偏置）；新增**页面簇发**（访问成功后并发拉取同品牌兄弟子域，还原真实页面多资源加载）；新增**连接明细 CSV 导出** `conn_log.csv`（ts / host / url / status / bytes / ms / ok），可离线审计样本分布、验证 ADG 缓存命中。
- **未做项（后续）**：真实 **HTTP/2 · QUIC** 协议栈改写（建议 P1 第三项）本期未纳入 —— 它会显著增加打包与回归风险，而本工具的 ADG DNS 缓存预热按主机名生效、不受 HTTP 版本影响。如确需 h2/QUIC 流量形态用于 Smart/LightGBM 训练，将在下个版本以可选 `httpx` 通道实现。

<details><summary>English</summary>

**v1.2.0 (2026-09-28)** — Fixed 3 stability bugs (DNS-failure domains now dropped immediately; no more sub-thread Tk crashes; log rotation + session leak + chart-resume fixed). Reduced impact on side-router/ADG (default 16→8 threads; 1 connection retry only; 256KB subresource cap). Training-quality: power-law brand weighting, page-burst (sibling subdomain fetches), and `conn_log.csv` structured export. HTTP/2·QUIC rewrite deferred to a later release (optional `httpx` channel).

</details>

<details><summary>Tiếng Việt</summary>

**v1.2.0 (2026-09-28)** — Sửa 3 lỗi ổn định (tên miền lỗi DNS giờ bị xóa ngay; hết crash luồng phụ đọc Tk; log quay vòng + leak session + chart hồi phục). Giảm tác động lên router/ADG (mặc định 16→8 luồng; chỉ 1 lần thử lại kết nối; giới hạn 256KB tài nguyên phụ). Chất lượng huấn luyện: trọng số thương hiệu theo luật lũy thừa, bùng nổ trang (tải tên miền anh em), xuất CSV `conn_log.csv`. Hoãn viết lại HTTP/2·QUIC (kênh `httpx` tùy chọn ở bản sau).

</details>

---

## 中文

### 这是什么

`拟真冲浪 RealSurf`（原名「真实上网环境模拟器」）在本地发起大量「像真人」的网络访问，
让出口流量同时具备两种形态，从而更贴近真实用户、补足 Smart 组训练所需的流量特征；
此外也能给 **AdGuardHome (ADG) 的 DNS 缓存做预热与命中测试**（先跑一轮把常用域名灌进缓存，
再对比命中率 / 解析延迟的变化）：

- **短请求浏览**：轮换 4 套浏览器 UA（Chrome / Edge / Firefox × Win / macOS），
  带 `Referer` / `Sec-Fetch-*` / `Accept-Language` 等完整请求头，5–30s 随机间隔，
  多子域名访问，连接保活（keep-alive）。
- **长连接（视频流）模拟**：按可配比例把部分 worker 切换为「看视频」会话——
  Range 分段拉取公开测试视频（类似 DASH/HLS 自适应码率），或打开视频平台观看页并伴随
  零星子资源请求，带真实缓冲间隙与观看时长。
- **断联自动恢复**：内置网络监控线程，全部失败即判定断联、暂停发流并探测，恢复后自动续上。
- **失效域名自动剔除**：连续失败达阈值（DNS 错误立即）的域名自动从列表移除。
- **站点编辑器**：图形化增删站点、导出 JSON；柱状图实时展示各站点网速与状态（不显示未访问的 Idle 站点）。
- **ADG DNS 缓存预热 / 命中测试**：先跑一轮把常用域名解析结果灌入 AdGuardHome 缓存，
  再观察命中率与解析延迟的变化，用来验证 ADG 缓存链路是否正常工作。
- **多语言界面**：中文 / English / Tiếng Việt，**自动识别 Windows 默认语言**切换
  （中文系列→中文，越南语→越南语，其余地区→英文），也可用菜单「语言」手动切换并持久化。

> ⚠️ 本工具仅用于个人代理连通性验证 / 训练数据采集，请遵守目标站点服务条款，勿用于高强度打流或攻击。

### 下载 / 更新

- 到本仓库 **Releases** 下载最新的 `realsurf.exe`（单文件，双击即用，无需安装）。
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
realnet_venv314\Scripts\pip install pyinstaller ttkbootstrap matplotlib requests
realnet_venv314\Scripts\pyinstaller --onefile --noconsole --name realsurf --icon realsurf.ico --add-data "realsurf.ico;." realnet_sim.py
```

产物在 `dist/realsurf.exe`。

### 目录结构

| 文件 | 说明 |
| --- | --- |
| `realnet_sim.py` | 主程序源码 |
| `smoke_headless.py` | 无界面冒烟测试（驱动 `visit_one` / `stream_session`，验证流量产生） |
| `test_traffic.py` | 受控流量验证（对可达站点确认请求计数与状态） |
| `realsurf.ico` | 应用图标（由 `make_icon.py` 生成，构建时 `--icon` 使用） |
| `make_icon.py` | 生成 `realsurf.ico` 的脚本（Pillow 绘制，无需 AI 出图） |
| `realsurf.exe` | 发布用的单文件可执行程序（见 Releases） |

### 版本

当前版本：`v1.2.1`

[↑ 回到顶部](#拟真冲浪-realsurf) · [切换到 English](#english) · [Chuyển sang Tiếng Việt](#tiếng-việt)

---

## English

### What is this

`拟真冲浪 RealSurf` (RealSurf) generates many human-like web requests locally, so the outbound
traffic mixes two shapes and better resembles a real user — supplying the traffic features Smart
groups need for training. It is also handy for **warming up and hit-testing the AdGuardHome (ADG)
DNS cache** (run one pass to populate the cache, then compare hit rate / resolve latency):

- **Short browsing**: rotates 4 browser UA profiles (Chrome / Edge / Firefox × Win / macOS) with
  full headers (`Referer`, `Sec-Fetch-*`, `Accept-Language`), random 5–30s intervals, many
  subdomains, keep-alive connections.
- **Long-connection (video stream) simulation**: a configurable ratio of workers become "watching
  video" sessions — Range-fetching public test videos (like DASH/HLS adaptive bitrate) or opening
  video pages with sporadic sub-resource requests, with realistic buffering gaps and watch time.
- **Auto-recovery on disconnect**: a built-in monitor detects full failure, pauses, probes, and
  auto-resumes when the network recovers.
- **Dead-domain auto-removal**: domains that keep failing (DNS errors immediately) are removed.
- **Site editor**: add/remove sites and export JSON; a bar chart shows live per-site speed & status
  (Idle sites with no activity are hidden).
- **ADG DNS cache warm-up / hit test**: run one pass to populate the AdGuardHome cache, then watch
  hit rate and resolve latency change — a quick sanity check that the ADG cache chain works.
- **Multilingual UI**: 中文 / English / Tiếng Việt. **Auto-detects the Windows display language**
  (Chinese family → 中文, Vietnamese → Tiếng Việt, everything else → English); you can also switch
  manually via the "Language" menu (persisted).

> ⚠️ For personal proxy connectivity checks / training-data collection only. Respect target sites'
> terms and do not use it for heavy flooding or attacks.

### Download / Update

- Get the latest `realsurf.exe` from this repo's **Releases** (single file, double-click to run).
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
realnet_venv314\Scripts\pip install pyinstaller ttkbootstrap matplotlib requests
realnet_venv314\Scripts\pyinstaller --onefile --noconsole --name realsurf --icon realsurf.ico --add-data "realsurf.ico;." realnet_sim.py
```

Output: `dist/realsurf.exe`.

### Version

Current version: `v1.2.1`

[↑ Back to top](#拟真冲浪-realsurf) · [切换到 中文](#中文) · [Chuyển sang Tiếng Việt](#tiếng-việt)

---

## Tiếng Việt

### Đây là gì

`拟真冲浪 RealSurf` (RealSurf) tạo ra nhiều yêu cầu web giống con người ở máy local, giúp lưu lượng
đầu ra kết hợp hai dạng và giống người thật hơn — cung cấp đặc trưng lưu lượng nhóm Smart cần để huấn luyện.
Cũng rất tiện để **làm nóng và kiểm tra cache DNS của AdGuardHome (ADG)** (chạy một lượt để nạp cache,
rồi so sánh tỉ lệ hit / độ trễ phân giải):

- **Duyệt ngắn**: luân phiên 4 profile UA trình duyệt (Chrome / Edge / Firefox × Win / macOS) với
  header đầy đủ (`Referer`, `Sec-Fetch-*`, `Accept-Language`), khoảng cách ngẫu nhiên 5–30s, nhiều
  tên miền phụ, giữ kết nối (keep-alive).
- **Mô phỏng luồng dài (video)**: tỉ lệ worker cấu hình được chuyển thành phiên "xem video" —
  lấy video kiểm thử công khai theo Range (như DASH/HLS), hoặc mở trang video kèm yêu cầu tài nguyên
  thưa thớt, có khoảng nghỉ bộ đệm và thời gian xem thực tế.
- **Tự phục hồi khi mất mạng**: luồng giám sát phát hiện toàn bộ thất bại, tạm dừng, dò và tự tiếp tục
  khi mạng hồi phục.
- **Tự xóa tên miền chết**: tên miền thất bại liên tục (lỗi DNS thì lập tức) sẽ bị xóa.
- **Trình biên tập trang**: thêm/xóa trang và xuất JSON; biểu đồ cột hiển thị tốc độ & trạng thái từng
  trang theo thời gian thực (ẩn các trang Idle chưa hoạt động).
- **Làm nóng / kiểm tra cache DNS ADG**: chạy một lượt để nạp cache AdGuardHome, rồi theo dõi tỉ lệ
  hit và độ trễ phân giải — cách nhanh để xác nhận chuỗi cache ADG hoạt động.
- **Giao diện đa ngôn ngữ**: 中文 / English / Tiếng Việt. **Tự nhận biết ngôn ngữ hiển thị Windows**
  (họ tiếng Trung → 中文, tiếng Việt → Tiếng Việt, còn lại → English); cũng có thể đổi thủ công qua menu
  "Ngôn ngữ" (được lưu).

> ⚠️ Chỉ dùng để kiểm tra kết nối proxy cá nhân / thu thập dữ liệu huấn luyện. Tôn trọng điều khoản
> của trang đích, đừng dùng để flood cường độ cao hay tấn công.

### Tải / Cập nhật

- Tải `realsurf.exe` mới nhất từ **Releases** của repo (file duy nhất, bấm đúp để chạy).
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
realnet_venv314\Scripts\pip install pyinstaller ttkbootstrap matplotlib requests
realnet_venv314\Scripts\pyinstaller --onefile --noconsole --name realsurf --icon realsurf.ico --add-data "realsurf.ico;." realnet_sim.py
```

Kết quả: `dist/realsurf.exe`.

### Phiên bản

Phiên bản hiện tại: `v1.2.1`

[↑ Về đầu](#拟真冲浪-realsurf) · [切换到 中文](#中文) · [Switch to English](#english)
