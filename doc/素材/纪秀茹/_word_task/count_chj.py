# -*- coding: utf-8 -*-
"""统计 chj_branch 上 accounts 的 #chj 注释；汇总王鑫悦工具结果概要。"""
import subprocess, pathlib, re

ROOT = pathlib.Path(r'C:\Users\16570\Class3-Group4')
RAW = ROOT / 'doc' / '素材' / '纪秀茹' / '_word_task' / 'members_raw'

# 1) 统计 accounts 各文件 #chj 标记数（chj_branch）
out = subprocess.run(['git', 'grep', '-c', '#chj', 'origin/chj_branch', '--', 'accounts/'],
                     capture_output=True, cwd=ROOT)
if out.returncode == 0:
    lines = out.stdout.decode('utf-8', 'replace').splitlines()
    total = 0
    for ln in lines:
        if ':' in ln:
            path, _, cnt = ln.rpartition(':')
            total += int(cnt)
            print('chj', path, cnt)
    print('chj_total =', total)
else:
    print('grep chj failed:', out.stderr.decode('utf-8', 'replace')[:300])

# 2) 王鑫悦工具结果 README
for name in ['wxy_pylint_comments.txt', 'wxy_flake8_comments.txt']:
    p = RAW / name
    if p.exists():
        txt = p.read_text(encoding='utf-8', errors='replace')
        tail = txt.strip().splitlines()[-6:]
        print('---', name, 'tail ---')
        print('\n'.join(tail))
