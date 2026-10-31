# -*- coding: utf-8 -*-
"""统计 chj_branch accounts 各文件 #chj 数量与行数；汇总 pylint 各 app 评分。"""
import subprocess, pathlib, re

ROOT = pathlib.Path(r'C:\Users\16570\Class3-Group4')
RAW = ROOT / 'doc' / '素材' / '纪秀茹' / '_word_task' / 'members_raw'

def git(args):
    return subprocess.run(['git'] + args, capture_output=True, cwd=ROOT, timeout=60)

# 1) accounts 文件清单（chj_branch，含 tests 但排除 migrations/__init__）
ls = git(['ls-tree', '-r', '--name-only', 'origin/chj_branch', '--', 'accounts/'])
if ls.returncode != 0:
    print('ls-tree failed:', ls.stderr.decode('utf-8', 'replace')[:300])
else:
    files = [f.decode('utf-8') for f in ls.stdout.splitlines() if f.decode('utf-8').endswith('.py')]
    total_chj = 0
    print('===== accounts files on chj_branch =====')
    for f in sorted(files):
        if '/migrations/' in f or f.endswith('__init__.py'):
            continue
        data = git(['show', 'origin/chj_branch:' + f])
        if data.returncode != 0:
            continue
        text = data.stdout.decode('utf-8', 'replace')
        n = text.count('#chj')
        total_chj += n
        lines = len(text.splitlines())
        print(f'{f}: lines={lines}, #chj={n}')
    print('total #chj =', total_chj)

# 2) 王鑫悦 pylint 各 app 最终评分
print('===== pylint final ratings =====')
for app in ['accounts', 'blog', 'comments', 'djangoblog', 'oauth', 'servermanager']:
    p = RAW / f'wxy_pylint_{app}.txt'
    if p.exists():
        txt = p.read_text(encoding='utf-8', errors='replace')
        m = re.findall(r'rated at ([\d.]+)/10', txt)
        print(app, '->', m[-1] if m else 'N/A')
