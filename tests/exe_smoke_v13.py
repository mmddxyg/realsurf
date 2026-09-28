# -*- coding: utf-8 -*-
"""对打包后的 dist/realsurf.exe 做真机冒烟：启动 → 等界面起来 → 截图 → 读启动自检日志。

验证点：exe 能起来（tkinter/ttkbootstrap 打进包）、httpx 在 frozen 环境里可用、
更新通道在 frozen 环境里可用（关于窗口的更新状态）。
"""
import os
import subprocess
import sys
import time

from PIL import ImageGrab

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXE = os.path.join(ROOT, 'dist', 'realsurf.exe')
LOG = os.path.join(ROOT, 'access_log.txt')
TAG = sys.argv[1] if len(sys.argv) > 1 else '07_exe_frozen'
SHOT = os.path.join(ROOT, '_shots_v13', f'{TAG}.png')
os.makedirs(os.path.dirname(SHOT), exist_ok=True)


def log_size():
    try:
        return os.path.getsize(LOG)
    except OSError:
        return 0


before = log_size()
print(f'exe = {EXE}  ({os.path.getsize(EXE)/1048576:.1f} MB)')
print(f'access_log.txt 起始大小 = {before}')

p = subprocess.Popen([EXE], cwd=ROOT)
print(f'已启动 PID={p.pid}')
time.sleep(14)          # 等 About 窗口弹出 + 更新检查跑完

alive = p.poll() is None
print(f'进程存活 = {alive}')

try:
    ImageGrab.grab().save(SHOT)
    print('SHOT:', SHOT)
except Exception as e:
    print('截图失败:', e)

# 读新增的日志
print('\n---- access_log.txt 新增部分 ----')
try:
    with open(LOG, 'r', encoding='utf-8', errors='ignore') as f:
        f.seek(before)
        new = f.read()
    lines = [l for l in new.splitlines() if l.strip()]
    for l in lines[-18:]:
        print(l)
except Exception as e:
    print('读日志失败:', e)

try:
    p.terminate()
    time.sleep(1.5)
    if p.poll() is None:
        p.kill()
    print('\n已结束 exe 进程')
except Exception as e:
    print('结束失败:', e)

sys.exit(0 if alive else 1)
