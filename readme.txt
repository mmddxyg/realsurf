# 真实上网环境模拟器 v2.0 (RealNet Simulator)

> 旧版名为「网络压力测试工具」，实则为代理连通性/流量模拟器。v2 重命名为「真实上网环境模拟器」，
> 目标：模拟真人电脑对主流站点的访问，用于 OpenClash / 代理链路连通性验证、保活与网速监测。
> （用途之一：为 OpenClash smart 策略组模型训练快速积累真实上网行为数据；该训练本身不在本软件内。）

## 功能
1. 真实浏览器模拟：内置 Chrome / Edge / Firefox（Windows + macOS）完整请求头档案，随机切换 UA，
   带 Referer、Sec-Fetch-*、Accept-Language 等字段，行为贴近真实上网。
2. 断联自动恢复：内置网络监控线程。worker 持续上报访问成败；窗口内（约 15s）全部失败即判定
   「网络断联」→ 暂停发流 → 监控线程独立探测探针站点 → 恢复后自动清除暂停、worker 自动续访问，
   无需人工重启。
3. 安全默认：默认开启 SSL 证书校验（verify=True）。仅在代理做 TLS 拦截的环境下，勾选
   「跳过证书校验(代理环境)」。

## 使用
- 每站点并发线程 (1-10)：默认 5。线程总数 = 线程数 × 站点数。
- 访问间隔 (秒, 5-30)：默认 10，每次随机抖动，模拟真人节奏。
- 开始 / 停止：启动或停止模拟。
- 文件 → 站点列表：可增删站点/子域名（实时生效）。导出站点列表(JSON)。
- 状态栏：请求总数 / 错误总数 / 网络状态（正常 / 断联恢复中…）。
- 图表：各站点实时网速(KB/s)，按状态着色（绿=正常，橙=超时，红=错误，灰=Idle）。
- 日志：写入同目录 access_log.txt。

## 依赖
requests / ttkbootstrap / matplotlib / numpy
Python 3.9+（3.13 需用新版依赖，见下方打包命令）

## 打包（PyInstaller onefile，无控制台窗口）
推荐在 Python 3.13 环境下用最新版依赖（旧版 matplotlib 3.7.3 / numpy 1.24.3 不支持 3.13）：

    pip install -i https://mirrors.aliyun.com/pypi/simple requests ttkbootstrap matplotlib numpy pyinstaller
    pyinstaller --onefile --noconsole --name realnet_sim ^
        --hidden-import matplotlib.backends.backend_tkagg ^
        --hidden-import numpy --hidden-import numpy._core --hidden-import numpy._core._exceptions ^
        --hidden-import ttkbootstrap ^
        realnet_sim.py

> 旧版（Python 3.11/3.12 可用）等价命令：
> pip install requests==2.32.3 pyinstaller==6.10.0 urllib3 matplotlib==3.7.3 numpy==1.24.3 ttkbootstrap
> pyinstaller --onefile --noconsole --hidden-import matplotlib.backends.backend_tkagg --hidden-import numpy --hidden-import numpy._core --hidden-import numpy._core._exceptions --hidden-import ttkbootstrap multi_site_access.py

## 说明
- 本工具仅用于个人代理连通性验证/训练数据采集，请遵守目标站点服务条款，勿用于高强度打流或攻击。
- 旧文件 multi_site_access.py 为 v1 遗留，可删除。
