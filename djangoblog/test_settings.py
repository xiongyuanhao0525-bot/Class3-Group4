#!/usr/bin/env python
# encoding: utf-8
"""
测试专用配置（标注人：熊圆好 #xyh）

用途：复用 djangoblog/settings.py 的全部业务配置，只把「数据库」与「搜索后端」
替换为无外部依赖的实现，使得任何组员机器上都能直接跑：

    python manage.py test --settings=djangoblog.test_settings

设计要点：
  1. 数据库 → SQLite 内存库：测试跑完即销毁，不碰开发/生产的 MySQL 数据；
  2. 搜索 → Haystack SimpleEngine：不做真实索引写入，避免测试污染 whoosh_index/；
  3. 缓存 → 进程内 LocMemCache：每次测试可精确断言「命中/未命中」，且不依赖 Redis；
  4. 关闭向外部推送/爬虫通知等真实外呼（由 TESTING=True 及各接收器自行判断）。

⚠ 本文件只在运行测试时生效，不影响 `manage.py runserver` 使用的 djangoblog/settings.py。
"""
from djangoblog.settings import *  # noqa: F401,F403  —— 先继承主配置，再逐项覆盖

import os
import tempfile

# 标记当前处于测试模式：blog_signals.py 等模块据此跳过真实邮件/HTTP 外呼
TESTING = True

# ①数据库：SQLite 文件库（放在系统临时目录），测试结束由框架销毁
# xyh：⚠ 这里刻意不用 ':memory:'。项目里 blog_signals 会用子线程异步发邮件/写
# xyh：EmailSendLog，而内存库在不同连接/线程之间不共享，会报 "no such table"。
# xyh：换成文件库后所有连接看到同一个库，既能脱机跑测试，行为也与生产一致。
TEST_DB_PATH = os.path.join(
    tempfile.gettempdir(), 'djangoblog_test_{}.sqlite3'.format(os.getpid()))
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': TEST_DB_PATH,
        'TEST': {'NAME': TEST_DB_PATH},
        'OPTIONS': {'timeout': 20},   # xyh：并发写（异步线程）时避免 database is locked
    }
}

# ②搜索后端：SimpleEngine 不落盘，避免测试写入 whoosh_index/
HAYSTACK_CONNECTIONS = {
    'default': {
        'ENGINE': 'haystack.backends.simple_backend.SimpleEngine',
    },
}
# 关闭实时索引信号，避免每次模型保存都触发索引重建
HAYSTACK_SIGNAL_PROCESSOR = 'haystack.signals.BaseSignalProcessor'

# ③缓存：每个测试进程独立的进程内缓存，便于断言缓存命中与失效
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'djangoblog-test-cache',
        'TIMEOUT': 300,
    }
}

# ④测试期强制关闭静态资源压缩（compressor 在测试中无意义且拖慢速度）
COMPRESS_ENABLED = False
COMPRESS_OFFLINE = False

# ⑤日志：测试期间只保留控制台输出，避免写入 logs/ 目录干扰真实日志
LOGGING['handlers'] = {
    'console': {
        'level': 'CRITICAL',   # 只输出严重问题，测试报告保持干净
        'class': 'logging.StreamHandler',
    },
}
LOGGING['loggers']['djangoblog'] = {
    'handlers': ['console'],
    'level': 'CRITICAL',
    'propagate': False,
}
LOGGING['root'] = {'level': 'CRITICAL', 'handlers': ['console']}
