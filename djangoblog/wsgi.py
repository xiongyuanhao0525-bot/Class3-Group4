# xyh：WSGI 部署入口 —— gunicorn/uWSGI 等应用服务器加载本模块获取 application，
# xyh：完成 Django 启动（加载 settings、初始化 app 注册表与中间件链）。
"""
WSGI config for djangoblog project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/1.10/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "djangoblog.settings")   # xyh：未显式指定时默认使用本项目配置模块

application = get_wsgi_application()   # xyh：WSGI 可调用对象，容器层请求由此进入 Django
