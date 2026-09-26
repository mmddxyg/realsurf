# -*- coding: utf-8 -*-
"""RealSurf 发布脚本：推送源码 + 建/更新 GitHub Release + 上传 exe。

用法：
    python deploy.py                     # 发布 realnet_sim.py 里的 APP_VERSION
    python deploy.py --notes-file x.md   # 自定义发布说明
    python deploy.py --exe dist/realsurf.exe
    python deploy.py --public            # 发布后把仓库设为公开

依赖：.github_token（仓库根目录，已 gitignore）内的 GitHub PAT（需 repo 权限）。
"""
import argparse
import json
import os
import re
import subprocess
import sys

import requests

REPO = 'mmddxyg/realsurf'
API = 'https://api.github.com'
ROOT = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(ROOT, '.github_token')


def read_token():
    if not os.path.exists(TOKEN_FILE):
        sys.exit(f'缺少 {TOKEN_FILE}，请先写入 GitHub PAT。')
    with open(TOKEN_FILE, encoding='utf-8') as f:
        return f.read().strip()


def read_version():
    with open(os.path.join(ROOT, 'realnet_sim.py'), encoding='utf-8') as f:
        m = re.search(r'APP_VERSION\s*=\s*"([^"]+)"', f.read())
    if not m:
        sys.exit('无法从 realnet_sim.py 读取 APP_VERSION')
    return m.group(1)


def git(*args, token=None):
    exe = 'C:/Program Files/Git/cmd/git.exe'
    if not os.path.exists(exe):
        exe = 'git'
    return subprocess.run([exe, *args], cwd=ROOT, check=True,
                          capture_output=True, text=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--exe', default=None)
    ap.add_argument('--notes-file', default=None)
    ap.add_argument('--public', action='store_true')
    ap.add_argument('--no-push', action='store_true')
    args = ap.parse_args()

    token = read_token()
    ver = read_version()
    tag = f'v{ver}'
    H = {'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github+json'}

    exe = args.exe or ('dist/realsurf.exe' if os.path.exists(os.path.join(ROOT, 'dist', 'realsurf.exe'))
                       else 'dist2/realsurf.exe')
    exe_abs = exe if os.path.isabs(exe) else os.path.join(ROOT, exe)
    if not os.path.exists(exe_abs):
        sys.exit(f'找不到 exe: {exe_abs}')

    # 1) 推送源码
    if not args.no_push:
        url = f'https://github.com/{REPO}.git'
        auth = f'https://x-access-token:{token}@github.com/{REPO}.git'
        git('remote', 'set-url', 'origin', auth)
        try:
            print(git('push', 'origin', 'HEAD:main').stderr.strip() or 'push ok')
        finally:
            git('remote', 'set-url', 'origin', url)

    # 2) 发布说明
    body = ''
    if args.notes_file:
        with open(args.notes_file, encoding='utf-8') as f:
            body = f.read()

    # 3) 建或更新 release
    r = requests.get(f'{API}/repos/{REPO}/releases/tags/{tag}', headers=H, timeout=60)
    if r.status_code == 200:
        rel = r.json()
        rel = requests.patch(f"{API}/repos/{REPO}/releases/{rel['id']}", headers=H,
                             json={'name': f'RealSurf {tag}', 'body': body}, timeout=60).json()
        print('release 已存在，已更新:', rel['html_url'])
    else:
        r = requests.post(f'{API}/repos/{REPO}/releases', headers=H, timeout=60, json={
            'tag_name': tag, 'target_commitish': 'main', 'name': f'RealSurf {tag}',
            'body': body, 'draft': False, 'prerelease': False})
        r.raise_for_status()
        rel = r.json()
        print('release 已创建:', rel['html_url'])

    # 4) 上传 exe（同名则先删旧的）
    for a in rel.get('assets', []):
        if a['name'] == 'realsurf.exe':
            requests.delete(f"{API}/repos/{REPO}/releases/assets/{a['id']}", headers=H, timeout=60)
            print('已删除旧 asset')
    upload_url = rel['upload_url'].split('{')[0] + '?name=realsurf.exe'
    size = os.path.getsize(exe_abs)
    print(f'上传 {exe_abs} ({size/1048576:.1f} MB) ...')
    with open(exe_abs, 'rb') as f:
        rr = requests.post(upload_url, headers={**H, 'Content-Type': 'application/octet-stream'},
                           data=f, timeout=900)
    rr.raise_for_status()
    print('asset:', rr.json()['browser_download_url'])

    # 5) 可选：公开仓库
    if args.public:
        rp = requests.patch(f'{API}/repos/{REPO}', headers=H, json={'private': False}, timeout=60)
        rp.raise_for_status()
        print('仓库 private =', rp.json()['private'])

    print('DONE', tag)


if __name__ == '__main__':
    main()
