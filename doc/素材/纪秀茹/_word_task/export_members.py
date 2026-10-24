# -*- coding: utf-8 -*-
"""从各成员远程分支导出清单A与工具结果到本地。"""
import subprocess, pathlib

ROOT = pathlib.Path(r'C:\Users\16570\Class3-Group4')
OUT = ROOT / 'doc' / '素材' / '纪秀茹' / '_word_task' / 'members_raw'
OUT.mkdir(parents=True, exist_ok=True)

items = [
    ('origin/ZJC_branch', 'doc/素材/翟旌超/清单A-质量分析报告素材.md', '翟旌超_清单A.md'),
    ('origin/ZJC_branch', 'doc/素材/翟旌超/blog注释清单.md', '翟旌超_blog注释清单.md'),
    ('origin/yjh_branch', 'doc/素材/杨杰翰/信息收集清单A-交纪秀茹.md', '杨杰翰_清单A.md'),
    ('origin/yjh_branch', 'doc/素材/杨杰翰/注释文件清单-oauth.md', '杨杰翰_注释文件清单.md'),
    ('origin/wxy_branch', 'doc/素材/王鑫悦/清单A_交纪秀茹.md', '王鑫悦_清单A.md'),
    ('origin/wxy_branch', 'doc/素材/王鑫悦/清单B_交陈汉佳.md', '王鑫悦_清单B.md'),
    ('origin/xyh_branch', 'doc/素材/熊圆好/信息收集清单A-交纪秀茹-熊圆好.md', '熊圆好_清单A_remote.md'),
    ('origin/xyh_branch', 'doc/素材/熊圆好/注释文件清单-djangoblog.md', '熊圆好_注释文件清单.md'),
]
for ref, path, name in items:
    try:
        data = subprocess.run(['git', 'show', f'{ref}:{path}'],
                              capture_output=True, cwd=ROOT, timeout=60)
        if data.returncode == 0:
            (OUT / name).write_bytes(data.stdout)
            print('OK', name, len(data.stdout))
        else:
            print('FAIL', name, data.stderr.decode('utf-8', 'replace')[:200])
    except Exception as e:
        print('ERR', name, e)

# 王鑫悦工具结果（6 app × flake8/pylint）
for app in ['accounts', 'blog', 'comments', 'djangoblog', 'oauth', 'servermanager']:
    for tool in ['flake8', 'pylint']:
        path = f'doc/素材/王鑫悦/工具结果/{tool}_{app}.txt'
        name = f'wxy_{tool}_{app}.txt'
        try:
            data = subprocess.run(['git', 'show', f'origin/wxy_branch:{path}'],
                                  capture_output=True, cwd=ROOT, timeout=60)
            if data.returncode == 0:
                (OUT / name).write_bytes(data.stdout)
                print('OK', name, len(data.stdout))
            else:
                print('FAIL', name, data.stderr.decode('utf-8', 'replace')[:200])
        except Exception as e:
            print('ERR', name, e)
