# 拟真冲浪 RealSurf

> 模拟真人上网行为的轻量工具，用于 **OpenClash / 代理链路连通性验证** 与 **Smart 策略组训练数据采集**。

![private](https://img.shields.io/badge/visibility-私有仓库-red)
![lang](https://img.shields.io/badge/语言-中文%20%7C%20English%20%7C%20Tiếng%20Việt-blue)

---

## 中文

### 这是什么

`拟真冲浪 RealSurf`（原名「真实上网环境模拟器」）在本地发起大量「像真人」的网络访问，
让出口流量同时具备两种形态，从而更贴近真实用户、补足 Smart 组训练所需的流量特征：

- **短请求浏览**：轮换 4 套浏览器 UA（Chrome / Edge / Firefox × Win / macOS），
  带 `Referer` / `Sec-Fetch-*` / `Accept-Language` 等完整请求头，5–30s 随机间隔，
  多子域名访问，连接保活（keep-alive）。
- **长连接（视频流）模拟**：按可配比例把部分 worker 切换为「看视频」会话——
  Range 分段拉取公开测试视频（类似 DASH/HLS 自适应码率），或打开视频平台观看页并伴随
  零星子资源请求，带真实缓冲间隙与观看时长。
- **断联自动恢复**：内置网络监控线程，全部失败即判定断联、暂停发流并探测，恢复后自动续上。
- **失效域名自动剔除**：连续失败达阈值（DNS 错误立即）的域名自动从列表移除。
- **站点编辑器**：图形化增删站点、导出 JSON；柱状图实时展示各站点网速与状态（不显示未访问的 Idle 站点）。
- **多语言界面**：中文 / English / Tiếng Việt，**自动识别 Windows 默认语言**切换
  （中文系列→中文，越南语→越南语，其余地区→英文），也可用菜单「语言」手动切换并持久化。

> ⚠️ 本工具仅用于个人代理连通性验证 / 训练数据采集，请遵守目标站点服务条款，勿用于高强度打流或攻击。

### 下载 / 更新

- 到本仓库 **Releases** 下载最新的 `realsurf.exe`（单文件，双击即用，无需安装）。
- 软件启动后会**静默检查一次 GitHub 更新**；也可通过菜单「文件 → 检查更新」手动检查，
  发现新版本可一键下载并自动替换重启。

### 使用方法

1. 双击 `realsurf.exe`。
2. 设置并发线程（默认 16）、访问间隔（默认 10s）。
3. 若走做了 TLS 拦截的代理，勾选「跳过证书校验」。
4. 设置长连接比例（默认 20%）与单次观看时长（默认 45s）。
5. 点「开始」即可。日志写入同目录 `access_log.txt`。
6. 关于本软件 / GitHub 地址 / 更新状态：菜单「文件 → 关于」（启动默认弹出，关闭后仍可在此重新打开）。

### 从源码构建

需要 **Python 3.14.x（系统安装版，托管版缺 tkinter 无法打包 GUI）**：

```bash
python -m venv realnet_venv314
realnet_venv314\Scripts\pip install pyinstaller ttkbootstrap matplotlib requests
realnet_venv314\Scripts\pyinstaller --onefile --noconsole --name realsurf realnet_sim.py
```

产物在 `dist/realsurf.exe`。

### 目录结构

| 文件 | 说明 |
| --- | --- |
| `realnet_sim.py` | 主程序源码 |
| `smoke_headless.py` | 无界面冒烟测试（驱动 `visit_one` / `stream_session`，验证流量产生） |
| `test_traffic.py` | 受控流量验证（对可达站点确认请求计数与状态） |
| `realsurf.exe` | 发布用的单文件可执行程序（见 Releases） |

### 版本

当前版本：`v1.1.0`

---

## English

### What is this

`拟真冲浪 RealSurf` (RealSurf) generates many human-like web requests locally, so the outbound
traffic mixes two shapes and better resembles a real user — supplying the traffic features Smart
groups need for training:

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
- **Multilingual UI**: 中文 / English / Tiếng Việt. **Auto-detects the Windows display language**
  (Chinese family → 中文, Vietnamese → Tiếng Việt, everything else → English); you can also switch
  manually via the "Language" menu (persisted).

> ⚠️ For personal proxy connectivity checks / training-data collection only. Respect target sites'
> terms and do not use it for heavy flooding or attacks.

### Download / Update

- Get the latest `realsurf.exe` from this repo's **Releases** (single file, double-click to run).
- On launch it **silently checks GitHub once** for updates; or use "File → Check for Update" to
  check manually and one-click download + auto-replace & restart.

### Usage

1. Double-click `realsurf.exe`.
2. Set threads (default 16) and visit interval (default 10s).
3. If behind a TLS-inspecting proxy, check "Skip Cert Verify".
4. Set stream ratio (default 20%) and watch duration (default 45s).
5. Click **Start**. Logs go to `access_log.txt` next to the app.
6. About / GitHub link / update status: menu "File → About" (shown on startup by default; reopen
   anytime from that menu after closing).

### Build from source

Requires **Python 3.14.x (system install; the managed build lacks tkinter and can't package GUI)**:

```bash
python -m venv realnet_venv314
realnet_venv314\Scripts\pip install pyinstaller ttkbootstrap matplotlib requests
realnet_venv314\Scripts\pyinstaller --onefile --noconsole --name realsurf realnet_sim.py
```

Output: `dist/realsurf.exe`.

### Version

Current version: `v1.1.0`

---

## Tiếng Việt

### Đây là gì

`拟真冲浪 RealSurf` (RealSurf) tạo ra nhiều yêu cầu web giống con người ở máy local, giúp lưu lượng
đầu ra kết hợp hai dạng và giống người thật hơn — cung cấp đặc trưng lưu lượng nhóm Smart cần để huấn luyện:

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
- **Giao diện đa ngôn ngữ**: 中文 / English / Tiếng Việt. **Tự nhận biết ngôn ngữ hiển thị Windows**
  (họ tiếng Trung → 中文, tiếng Việt → Tiếng Việt, còn lại → English); cũng có thể đổi thủ công qua menu
  "Ngôn ngữ" (được lưu).

> ⚠️ Chỉ dùng để kiểm tra kết nối proxy cá nhân / thu thập dữ liệu huấn luyện. Tôn trọng điều khoản
> của trang đích, đừng dùng để flood cường độ cao hay tấn công.

### Tải / Cập nhật

- Tải `realsurf.exe` mới nhất từ **Releases** của repo (file duy nhất, bấm đúp để chạy).
- Khi khởi động sẽ **tự kiểm tra GitHub một lần**; hoặc dùng "Tập tin → Kiểm tra cập nhật" để kiểm tra
  thủ công và tải + tự thay thế, khởi động lại một chạm.

### Cách dùng

1. Bấm đúp `realsurf.exe`.
2. Đặt số luồng (mặc định 16) và khoảng cách truy cập (mặc định 10s).
3. Nếu qua proxy có chặn TLS, tích "Bỏ xác thực chứng chỉ".
4. Đặt tỉ lệ luồng (mặc định 20%) và thời gian xem (mặc định 45s).
5. Bấm **Bắt đầu**. Nhật ký ghi vào `access_log.txt` cạnh app.
6. Giới thiệu / link GitHub / trạng thái cập nhật: menu "Tập tin → Giới thiệu" (hiện khi khởi động
   mặc định; đóng rồi vẫn mở lại từ menu đó bất cứ lúc nào).

### Build từ mã nguồn

Cần **Python 3.14.x (bản cài hệ thống; bản quản lý thiếu tkinter không đóng gói được GUI)**:

```bash
python -m venv realnet_venv314
realnet_venv314\Scripts\pip install pyinstaller ttkbootstrap matplotlib requests
realnet_venv314\Scripts\pyinstaller --onefile --noconsole --name realsurf realnet_sim.py
```

Kết quả: `dist/realsurf.exe`.

### Phiên bản

Phiên bản hiện tại: `v1.1.0`
