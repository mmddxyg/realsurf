# 拟真冲浪 RealSurf

<img src="icon_preview.png" width="110" alt="RealSurf icon">

> 模拟真人上网行为的轻量工具，用于 **OpenClash / 代理链路连通性验证**、**Smart 策略组训练数据采集** 与 **AdGuardHome (ADG) DNS 缓存预热 / 命中测试**。

**🌐 语言 / Language / Ngôn ngữ：** [中文](#中文) · [English](#english) · [Tiếng Việt](#tiếng-việt)

<sub>公开仓库 · Public repository · Kho công khai</sub>

---

## 更新日志 / Changelog / Nhật ký thay đổi

**v1.3.1（2026-09-28）** — 移除「记录连接明细(CSV)」功能

- 🗑️ **整体下线 CSV 记录功能**：删除界面上的「记录连接明细(CSV)」勾选框，以及背后的全部实现——`conn_log.csv` / 分卷轮转 / 15 列字段 / `_record_conn` / `_open_conn_log` / `_proto_of` / `_status_code` / `conn_lock` / `conn_file` 状态、`csv` 与 `datetime` 导入一并清除。理由：该表客户端拿不到 `group_name` / `node_name`，无法替代内核打标；训练样本的核对已在 mihomo 日志侧完成，继续在客户端落盘 32MB×N 的 CSV 属于无效负担。
- ✅ **其余功能全部保留且不受影响**：曲线/速率统计仍走 `self.monitor.record(ok)`；上传 / 大文件下载 / 小包交互 / HLS 分片 / 页面真并发 / HTTP/2·HTTP/3 通道 / 缓存穿透开关 / 更新通道 / 三语言界面 全部照旧。
- 🧹 **界面与代码清理**：按钮行恢复为【开始】【停止】【穿透缓存(?num=)】三件套（`穿透缓存` 回填到 column=2，不留空列）；源码中不再残留任何 CSV 相关标识符（已加自动化守护测试 R1）。
- 📦 **版本号升到 1.3.1**（同版本号重发老用户检查不到更新）。

<details><summary>English</summary>

**v1.3.1 (2026-09-28)** — Removed the "Log connections (CSV)" feature.

- **Feature fully retired**: the UI checkbox and the entire implementation are gone — `conn_log.csv`, 32MB rotation, the 15-column schema, `_record_conn` / `_open_conn_log` / `_proto_of` / `_status_code`, the `conn_lock` / `conn_file` state, and the `csv` / `datetime` imports. Rationale: the file cannot carry `group_name` / `node_name` client-side and does not replace kernel-level tagging; sample auditing already happens on the mihomo log side, so writing 32MB×N of CSV locally was pure overhead.
- **Everything else is untouched and verified**: chart/rate stats still go through `self.monitor.record(ok)`; uploads, bulk downloads, small-packet bursts, HLS segments, real concurrent page bursts, the HTTP/2·HTTP/3 channel, the cache-bust toggle, the update channel and the three-language UI all behave exactly as before.
- **UI cleanup**: the button row is back to 【Start】【Stop】【Bust cache (?num=)】 (the toggle moved to column 2, no empty column); no CSV identifier remains in the source (guarded by an automated R1 test).
- **Version bumped to 1.3.1** (re-releasing an existing version number would leave current users with no update).

</details>

<details><summary>Tiếng Việt</summary>

**v1.3.1 (2026-09-28)** — Loại bỏ tính năng "Ghi kết nối (CSV)".

- **Gỡ bỏ hoàn toàn**: hộp kiểm trên giao diện và toàn bộ phần triển khai phía sau — `conn_log.csv`, quay vòng 32MB, lược đồ 15 cột, `_record_conn` / `_open_conn_log` / `_proto_of` / `_status_code`, trạng thái `conn_lock` / `conn_file`, cùng các import `csv` và `datetime`. Lý do: tệp không có `group_name` / `node_name` ở phía client và không thay thế được việc gắn nhãn ở kernel; việc kiểm tra mẫu đã được thực hiện ở phía log mihomo, nên ghi 32MB×N CSV cục bộ chỉ là gánh nặng vô ích.
- **Mọi tính năng khác giữ nguyên, đã kiểm chứng**: thống kê tốc độ/biểu đồ vẫn qua `self.monitor.record(ok)`; tải lên, tải xuống tệp lớn, gói nhỏ, phân đoạn HLS, bùng nổ trang song song, kênh HTTP/2·HTTP/3, công tắc phá cache, kênh cập nhật và giao diện ba ngôn ngữ đều hoạt động như cũ.
- **Dọn dẹp giao diện**: hàng nút trở lại 【Bắt đầu】【Dừng】【Phá cache (?num=)】 (công tắc về cột 2, không còn cột trống); mã nguồn không còn định danh CSV nào (được bảo vệ bằng kiểm thử R1 tự động).
- **Nâng số phiên bản lên 1.3.1** (phát hành lại cùng số phiên bản sẽ khiến người dùng hiện tại không thấy cập nhật).

</details>

**v1.3.0（2026-09-28）** — 流量形态大升级：上传 / 大文件 / 小包交互 + HTTP/2·HTTP/3 + HLS 分片

- 📤 **补齐上行与长尾流量形态（P0）**：原来只有「短请求 + 视频」两种形态，上行侧与小包几乎空白，Smart/LightGBM 的特征工程拿不到这些维度的样本。
  - **上传**（约 20% 命中）：表单 10–100KB / 媒体 1–5MB / 大文件 20–100MB 三档（60/30/10 加权），大文件档带限速，不占满上行。
  - **大文件持续下载**（约 5% 命中）：网盘 / 驱动 / 更新包型，单次 20–100MB（上限 200MB）。
  - **小包高频交互**（约 12% 命中）：IM / 游戏心跳 / 长轮询，3–8 次连发、0.2–1.0s 间隔。
- ⚖️ **域名池换真实榜单档位 + 幂律加权（P1）**：品牌权重从 6/5/4/3/2/1 拉开到 **1000/300/100/30**（头尾比 ~100:1，原 6:1 太扁）；品牌内部再按**子域角色**加权（`www`/`api`/裸域 = 10，`static`/`cdn`/`img`/`support` 等 = 1，其余 = 3）；可选加载 **Tranco / Cisco Umbrella top-1M**（`top1m.csv`，`USE_TOP_LIST=True` 生效，`w ∝ rank^-0.8`），没文件时行为不变。
  > 注：任务书原表漏了站点池里的 14 个品牌（Xbox / PlayStation / Nintendo / EA / Epic / Ubisoft / Toutiao / Hulu 等），已补齐到对应档位，并把兜底权重 1 → **30**，否则未列品牌会被头部按 1000:1 直接饿死。
- ⚡ **页面簇发改真并发（P1）**：旧实现是「串行 + 每个子资源 `sleep` 0.3–1.2s」，形态上根本不是簇发；现改为线程池真并发（6–15 个子资源、单资源上限 64KB → 512KB），触发概率 0.4 → **0.9**。
- 🚀 **新增 HTTP/2 · HTTP/3 通道（P1）**：接入可选 `httpx` 通道（约 70% 流量走 h2/h3，其余仍走 requests h1.1），统一 `_iter_chunks()` 屏蔽两套响应接口差异；协议版本曾写入 `conn_log.csv` 的 `proto_ver` 列（该 CSV 已在 v1.3.1 移除）。**未安装 httpx 或握手失败自动回退 requests，任何既有功能都不受影响。**
- 🎬 **视频改 DASH/HLS 分片形态（P2）**：新增 m3u8 **主清单 → 子清单 → 媒体分片**两级解析（测试源给的都是主清单，只按「非 `#` 行」当分片下，实际只会拉到几个几 KB 的文本文件 ≈ 0 流量），变长分片 + 并行 2–4 路，并支持 `EXT-X-MAP` 初始化段。
- 🔁 **`?num=` 缓存穿透改成开关（P2）**：新增「穿透缓存(?num=)」勾选项，**默认关闭**。原来每次请求都加 `?num=`，直接把 ADG 缓存打穿，反而破坏了「缓存预热」这个初衷。
- 🗂️ **`conn_log.csv` 增强（P3，已在 v1.3.1 整体移除）**：32MB 自动分卷轮转；`ts` 改 **UTC ISO8601**（带 `Z`）；`ok` 语义收窄为 **2xx/3xx**（原来「没抛异常就算成功」，403/404/500 也被标成成功，样本标签是错的），新增 `ok_2xx` / `ok_3xx` 保留细分；字段扩到 **15 列**（新增 `method` / `bytes_up` / `proto_ver` / `scene_hint` / `tier` 等），便于离线核对样本分布。
- 🐞 **顺手修掉两个既有 bug**：① 切换界面语言时「记录连接明细(CSV)」勾选框文案不刷新（该勾选框已在 v1.3.1 随功能一并移除）；② 主窗口输入行 9 个控件挤一行，默认 1000px 窗口下「长连接比例」「单次观看」被右边缘裁掉（参数改不了 = 功能不可用），已拆成两行。

<details><summary>English</summary>

**v1.3.0 (2026-09-28)** — Traffic-shape upgrade: uploads / bulk downloads / small-packet bursts + HTTP/2·HTTP/3 + HLS segments.

- **New traffic shapes (P0)**: uploads (~20%: form 10–100KB / media 1–5MB / bulk 20–100MB, rate-limited), bulk downloads (~5%, 20–100MB, cap 200MB), and high-frequency small-packet interaction (~12%, 3–8 bursts @0.2–1.0s). Previously only "short request + video" existed, so upstream and small-packet features were missing from the training samples.
- **Power-law weighting (P1)**: brand tiers widened from 6/5/4/3/2/1 to **1000/300/100/30** (~100:1 head-to-tail); per-subdomain role weighting inside a brand (`www`/`api`/bare = 10, `static`/`cdn`/`img`/`support` = 1, else 3); optional **Tranco / Umbrella top-1M** list (`top1m.csv`, `USE_TOP_LIST=True`, `w ∝ rank^-0.8`). The 14 brands missing from the original spec table were restored to their tiers and the fallback weight raised 1 → 30 (otherwise unlisted brands get starved 1000:1).
- **Real concurrent page burst (P1)**: the old code was serial with a 0.3–1.2s sleep per subresource — not a burst at all. Now a thread pool (6–15 subresources, per-resource cap 64KB → 512KB), trigger probability 0.4 → **0.9**.
- **HTTP/2 · HTTP/3 (P1)**: optional `httpx` channel (~70% of traffic via h2/h3, rest h1.1 requests), with `_iter_chunks()` unifying both response APIs; the protocol version used to be logged in the new `proto_ver` column (that CSV was removed in v1.3.1). **Falls back to requests automatically if httpx is missing or the handshake fails — no feature is affected.**
- **DASH/HLS video (P2)**: two-level m3u8 resolution (master → variant → media segments; the test sources are masters, so naive parsing only fetched a few KB of text ≈ zero traffic), variable-length segments, 2–4 parallel fetches, `EXT-X-MAP` init segment support.
- **`?num=` cache-busting is now a toggle (P2)**, **off by default** — previously every request appended `?num=`, punching straight through the ADG cache and defeating the "cache warm-up" purpose.
- **`conn_log.csv` (P3, removed entirely in v1.3.1)**: 32MB rotation; `ts` is now **UTC ISO8601** (`Z`); `ok` narrowed to **2xx/3xx** (previously "no exception = success", mislabelling 403/404/500 as successes) with new `ok_2xx` / `ok_3xx`; 15 columns (adds `method` / `bytes_up` / `proto_ver` / `scene_hint` / `tier`).
- **Two pre-existing bugs fixed**: (1) the "Log connections (CSV)" checkbox text was not refreshed on language switch (that checkbox was dropped along with the feature in v1.3.1); (2) the 9 control row overflowed the default 1000px window, clipping "Stream Ratio" and "Watch Duration" (unusable settings) — now split into two rows.

</details>

<details><summary>Tiếng Việt</summary>

**v1.3.0 (2026-09-28)** — Nâng cấp hình thái lưu lượng: tải lên / tải xuống tệp lớn / gói nhỏ tần suất cao + HTTP/2·HTTP/3 + phân đoạn HLS.

- **Hình thái mới (P0)**: tải lên (~20%: biểu mẫu 10–100KB / media 1–5MB / tệp lớn 20–100MB, có giới hạn tốc độ), tải xuống tệp lớn (~5%, 20–100MB, tối đa 200MB), tương tác gói nhỏ tần suất cao (~12%, 3–8 lần, cách 0.2–1.0s). Trước đây chỉ có "yêu cầu ngắn + video" nên thiếu đặc trưng phía tải lên và gói nhỏ.
- **Trọng số luật lũy thừa (P1)**: mở rộng từ 6/5/4/3/2/1 thành **1000/300/100/30** (~100:1); thêm trọng số theo vai trò tên miền con (`www`/`api`/tên miền trần = 10, `static`/`cdn`/`img`/`support` = 1, còn lại 3); hỗ trợ tùy chọn danh sách **Tranco / Umbrella top-1M** (`top1m.csv`, `USE_TOP_LIST=True`, `w ∝ rank^-0.8`). 14 thương hiệu bị thiếu trong bảng gốc đã được bổ sung và trọng số mặc định tăng 1 → 30.
- **Bùng nổ trang song song thật (P1)**: bản cũ chạy tuần tự với sleep 0.3–1.2s mỗi tài nguyên — không phải "bùng nổ". Nay dùng thread pool (6–15 tài nguyên, giới hạn 64KB → 512KB), xác suất kích hoạt 0.4 → **0.9**.
- **HTTP/2 · HTTP/3 (P1)**: kênh `httpx` tùy chọn (~70% lưu lượng qua h2/h3, còn lại requests h1.1), `_iter_chunks()` thống nhất hai API phản hồi; phiên bản giao thức từng được ghi vào cột `proto_ver` (tệp CSV đó đã bị gỡ ở v1.3.1). **Tự động quay về requests nếu thiếu httpx hoặc bắt tay thất bại.**
- **Video DASH/HLS (P2)**: phân tích m3u8 hai cấp (master → biến thể → phân đoạn), phân đoạn dài thay đổi, 2–4 luồng song song, hỗ trợ `EXT-X-MAP`.
- **`?num=` thành công tắc (P2)**, **mặc định TẮT** — trước đây luôn thêm `?num=`, phá hỏng mục đích "làm nóng cache" của ADG.
- **`conn_log.csv` (P3, đã gỡ hoàn toàn ở v1.3.1)**: quay vòng 32MB; `ts` theo **UTC ISO8601** (`Z`); `ok` thu hẹp còn **2xx/3xx** (trước đây "không lỗi = thành công", gán nhãn sai cho 403/404/500), thêm `ok_2xx` / `ok_3xx`; 15 cột.
- **Sửa 2 lỗi cũ**: (1) nhãn hộp kiểm "Ghi kết nối (CSV)" không đổi khi chuyển ngôn ngữ (hộp kiểm đó đã bị gỡ cùng tính năng ở v1.3.1); (2) hàng 9 control tràn cửa sổ 1000px làm mất "Tỉ lệ luồng" và "Thời gian xem" — nay tách thành hai hàng.

</details>

**v1.2.1（2026-09-28）** — 更新通道修复 + 下载可视化

- 🚫 **修复「一直提示更新频繁 / 检查更新失败」（核心）**：旧版用 GitHub **REST API** 检查更新（未鉴权仅 **60 次/小时/IP**），代理共享出口被别人打满即返回 **403** → 程序一直报「更新频繁」，更新通道等于废掉。现改用 **`releases.atom` 订阅源 + 网页 `/releases/latest` 302 重定向**（**两者均无速率限制**）取最新版本号与说明，彻底摆脱 403。
- 🐞 **修复「识别到更新但点击没反应 / 无进度反馈」（用户反馈）**：
  - 根因①：旧版 `_apply_update` 在调用线程里**同步下载约 42MB 且零进度**，界面长时间卡死，看起来像「点了没反应」。
  - 根因②：发现新版本后的 `messagebox.askyesno` 在**后台线程**直接弹出，弹窗可能落到「关于」窗口背后，用户点了却看不到确认框。
  - 修复：下载改为**后台线程**，弹出进度条对话框（**百分比 + 已下载/总大小 + 实时速度 MB/s** + 可取消按钮）；所有更新相关弹窗统一经主线程 `root.after(0, …)` 弹出，并指定正确父窗口。下载完成自动写重启脚本并替换重启。
  - 强化：进度总大小取 GitHub 资源 `Content-Length`（HEAD 失败则用 GET 响应头），确保**一定显示百分比进度条**而非空转；对话框**居中并短暂置顶**，确保一定看得见；下载失败会**显示具体原因**，不再静默无反应。（本机已用真实桌面截图验证进度条确实渲染）
- 🏷️ **EXE 名字带版本号**：Release 资产命名为 `realsurf<版本>.exe`（如 `realsurf1.2.1.exe`）；自动更新也把新文件保存为**带版本号**的名字（旧版本文件保留不删，便于对照）——一眼就知道哪个是哪个。更新检查用「发布页解析」拿资产名，不写死文件名。

<details><summary>English</summary>

**v1.2.1 (2026-09-28)** — Update-channel fix + visualized download. The old build checked updates via the GitHub **REST API** (unauthenticated = only 60 req/hour/IP) and permanently said "rate limited" once the shared proxy IP hit 403 — now it uses the **releases.atom feed + the web /releases/latest redirect** (both rate-limit free). Root causes of "no reaction": the old updater downloaded ~42MB synchronously with no feedback (UI froze), and the "new version" dialog was shown from a background thread (could appear behind the About window). Fix: download runs in a background thread with a progress dialog (**percentage + downloaded/total + live MB/s** + Cancel button); all update dialogs are posted on the main thread via `root.after(0, …)` with the correct parent; total size comes from the asset `Content-Length` so a real percentage bar always shows; the dialog is centered and briefly forced on top; failures now show the concrete reason. Verified with a real-desktop screenshot.

</details>

<details><summary>Tiếng Việt</summary>

**v1.2.1 (2026-09-28)** — Sửa kênh cập nhật + tải có tiến trình. Bản cũ kiểm tra bằng **REST API** GitHub (không xác thực = chỉ 60 lần/giờ/IP) và luôn báo "bị giới hạn" khi IP proxy chia sẻ bị 403 — nay dùng **feed releases.atom + chuyển hướng web /releases/latest** (đều không giới hạn). Nguyên nhân "không phản hồi": bản cũ tải ~42MB đồng bộ không phản hồi; hộp thoại "có bản mới" hiện từ luồng phụ (có thể nằm sau cửa sổ Giới thiệu). Sửa: tải chạy ở luồng phụ với hộp thoại tiến trình (**phần trăm + đã tải/tổng + tốc độ MB/s** + nút Hủy); mọi hộp thoại hiện trên luồng chính với đúng cửa sổ cha; tổng dung lượng lấy từ `Content-Length` của asset nên luôn có thanh phần trăm thật; hộp thoại căn giữa và tạm đưa lên trên; lỗi nay hiện rõ nguyên nhân. Đã xác minh bằng ảnh chụp màn hình thật.

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
让出口流量具备**多种真实形态**（短请求 / 长视频流 / 上传 / 大文件下载 / 小包高频交互），
从而更贴近真实用户、补足 Smart 组训练所需的流量特征；
此外也能给 **AdGuardHome (ADG) 的 DNS 缓存做预热与命中测试**（先跑一轮把常用域名灌进缓存，
再对比命中率 / 解析延迟的变化）：

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
- **站点编辑器**：图形化增删站点、导出 JSON；柱状图实时展示各站点网速与状态（不显示未访问的 Idle 站点）。
- **ADG DNS 缓存预热 / 命中测试**：先跑一轮把常用域名解析结果灌入 AdGuardHome 缓存，
  再观察命中率与解析延迟的变化，用来验证 ADG 缓存链路是否正常工作。
  > 注意：`?num=` 缓存穿透现在是**默认关闭**的勾选项（「穿透缓存(?num=)」）。旧版每次都加 `?num=`，
  > 会把 ADG 缓存直接打穿，反而与「预热缓存」的目的相悖。
- **~~连接明细审计~~（v1.3.1 已移除）**：原「记录连接明细(CSV)」功能及其 `conn_log.csv`（15 列、
  32MB 分卷）已整体下线——客户端拿不到 `group_name` / `node_name`，该表不能替代内核打标，
  样本核对已在 mihomo 日志侧完成，继续落盘 CSV 只是无效负担。
- **多语言界面**：中文 / English / Tiếng Việt，**自动识别 Windows 默认语言**切换
  （中文系列→中文，越南语→越南语，其余地区→英文），也可用菜单「语言」手动切换并持久化。

> ⚠️ 本工具仅用于个人代理连通性验证 / 训练数据采集，请遵守目标站点服务条款，勿用于高强度打流或攻击。

### 下载 / 更新

- 到本仓库 **Releases** 下载最新的 `realsurf<版本>.exe`（如 `realsurf1.3.1.exe`；单文件，双击即用，无需安装）。
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
| `tests/` | 测试：`smoke_headless.py`（冒烟）、`test_traffic.py`、`test_v12.py`、`test_v13.py`（v1.3.x 优化专项，含 R1「CSV 残留必须为 0」守护、真网络与离线自检）、`test_update_dl.py`（无头下载验证）、`gui_update_test.py`（GUI 截图验证更新弹窗）、`gui_v13_test.py`（GUI 三语言 + 按钮行连续性 + 布局 + 更新通道 + 启停回归） |
| `packaging/` | 打包相关：`realsurf.spec`、`realnet_sim.spec`、`make_icon.py` |
| `archive/` | 历史遗留文件（旧版 `multi_site_access.py` 与旧 `readme.txt`） |
| `dist/` | 构建产物目录（已在 `.gitignore` 中；`deploy.py` 从这里取 exe 上传） |

运行测试（在项目根目录）：`python tests/test_v13.py`（v1.3.x 全量专项，含真网络）、
`python tests/test_v13.py --offline`（只跑离线静态 + R1 残留检查 + 权重抽样自检）、
`python tests/gui_v13_test.py`（GUI 三语言 + 按钮行连续性 + 布局 + 更新通道 + 启停回归，产出截图）、
`python tests/smoke_headless.py`、`python tests/test_update_dl.py` 等。

### 版本

当前版本：`v1.3.1`

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
- **Site editor**: add/remove sites and export JSON; a bar chart shows live per-site speed & status
  (Idle sites with no activity are hidden).
- **ADG DNS cache warm-up / hit test**: run one pass to populate the AdGuardHome cache, then watch
  hit rate and resolve latency change — a quick sanity check that the ADG cache chain works.
  > Note: `?num=` cache-busting is now an **off-by-default** toggle ("Bust cache (?num=)"). The old
  > build appended `?num=` to every request, punching straight through the ADG cache and defeating
  > the warm-up purpose.
- **~~Connection audit trail~~ (removed in v1.3.1)**: the "Log connections (CSV)" feature and its
  `conn_log.csv` (15 columns, 32MB rotation) are gone — `group_name` / `node_name` are not available
  client-side, the file does not replace kernel-level tagging, and sample auditing already happens on
  the mihomo log side, so writing CSV locally was pure overhead.
- **Multilingual UI**: 中文 / English / Tiếng Việt. **Auto-detects the Windows display language**
  (Chinese family → 中文, Vietnamese → Tiếng Việt, everything else → English); you can also switch
  manually via the "Language" menu (persisted).

> ⚠️ For personal proxy connectivity checks / training-data collection only. Respect target sites'
> terms and do not use it for heavy flooding or attacks.

### Download / Update

- Get the latest `realsurf<version>.exe` (e.g. `realsurf1.3.1.exe`) from this repo's **Releases** — the
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

Current version: `v1.3.1`

[↑ Back to top](#拟真冲浪-realsurf) · [切换到 中文](#中文) · [Chuyển sang Tiếng Việt](#tiếng-việt)

---

## Tiếng Việt

### Đây là gì

`拟真冲浪 RealSurf` (RealSurf) tạo ra nhiều yêu cầu web giống con người ở máy local, giúp lưu lượng
đầu ra có **nhiều dạng thực tế** (yêu cầu ngắn / luồng video dài / tải lên / tải xuống tệp lớn /
gói nhỏ tần suất cao) và giống người thật hơn — cung cấp đặc trưng lưu lượng nhóm Smart cần để huấn luyện.
Cũng rất tiện để **làm nóng và kiểm tra cache DNS của AdGuardHome (ADG)** (chạy một lượt để nạp cache,
rồi so sánh tỉ lệ hit / độ trễ phân giải):

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
- **Trình biên tập trang**: thêm/xóa trang và xuất JSON; biểu đồ cột hiển thị tốc độ & trạng thái từng
  trang theo thời gian thực (ẩn các trang Idle chưa hoạt động).
- **Làm nóng / kiểm tra cache DNS ADG**: chạy một lượt để nạp cache AdGuardHome, rồi theo dõi tỉ lệ
  hit và độ trễ phân giải — cách nhanh để xác nhận chuỗi cache ADG hoạt động.
  > Lưu ý: phá cache `?num=` nay là tùy chọn **mặc định TẮT** ("Phá cache (?num=)"). Bản cũ luôn thêm
  > `?num=`, phá hỏng mục đích "làm nóng cache" của ADG.
- **~~Nhật ký kết nối~~ (đã gỡ ở v1.3.1)**: tính năng "Ghi kết nối (CSV)" và tệp `conn_log.csv`
  (15 cột, quay vòng 32MB) đã bị loại bỏ — phía client không có `group_name` / `node_name`, tệp này
  không thay thế được việc gắn nhãn ở kernel, và việc kiểm tra mẫu đã làm ở phía log mihomo.
- **Giao diện đa ngôn ngữ**: 中文 / English / Tiếng Việt. **Tự nhận biết ngôn ngữ hiển thị Windows**
  (họ tiếng Trung → 中文, tiếng Việt → Tiếng Việt, còn lại → English); cũng có thể đổi thủ công qua menu
  "Ngôn ngữ" (được lưu).

> ⚠️ Chỉ dùng để kiểm tra kết nối proxy cá nhân / thu thập dữ liệu huấn luyện. Tôn trọng điều khoản
> của trang đích, đừng dùng để flood cường độ cao hay tấn công.

### Tải / Cập nhật

- Tải `realsurf<phiên bản>.exe` mới nhất (vd `realsurf1.3.1.exe`) từ **Releases** — tên asset có kèm
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

Phiên bản hiện tại: `v1.3.1`

[↑ Về đầu](#拟真冲浪-realsurf) · [切换到 中文](#中文) · [Switch to English](#english)
