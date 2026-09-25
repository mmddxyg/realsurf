# 拟真冲浪 RealSurf

> 模拟真人上网行为的轻量工具，用于 **OpenClash / 代理链路连通性验证** 与 **Smart 策略组训练数据采集**。

![private](https://img.shields.io/badge/visibility-私有仓库-red)

## 这是什么

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

> ⚠️ 本工具仅用于个人代理连通性验证 / 训练数据采集，请遵守目标站点服务条款，勿用于高强度打流或攻击。

## 下载 / 更新

- 到本仓库 **Releases** 下载最新的 `realsurf.exe`（单文件，双击即用，无需安装）。
- 软件启动后会**静默检查一次 GitHub 更新**；也可通过菜单「文件 → 检查更新」手动检查，
  发现新版本可一键下载并自动替换重启。

## 使用方法

1. 双击 `realsurf.exe`。
2. 设置并发线程（默认 16）、访问间隔（默认 10s）。
3. 若走做了 TLS 拦截的代理，勾选「跳过证书校验」。
4. 设置长连接比例（默认 20%）与单次观看时长（默认 45s）。
5. 点「开始」即可。日志写入同目录 `access_log.txt`。

## 从源码构建

需要 **Python 3.14.x（系统安装版，托管版缺 tkinter 无法打包 GUI）**：

```bash
python -m venv realnet_venv314
realnet_venv314\Scripts\pip install pyinstaller ttkbootstrap matplotlib requests
realnet_venv314\Scripts\pyinstaller --onefile --noconsole --name realsurf realnet_sim.py
```

产物在 `dist/realsurf.exe`。

## 目录结构

| 文件 | 说明 |
| --- | --- |
| `realnet_sim.py` | 主程序源码 |
| `smoke_headless.py` | 无界面冒烟测试（驱动 `visit_one` / `stream_session`，验证流量产生） |
| `test_traffic.py` | 受控流量验证（对可达站点确认请求计数与状态） |
| `realsurf.exe` | 发布用的单文件可执行程序（见 Releases） |

## 版本

当前版本：`v1.0.0`
