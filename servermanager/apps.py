# -*- coding: utf-8 -*-
"""#wxy servermanager/apps.py：Django app 配置类。"""
from django.apps import AppConfig


class ServermanagerConfig(AppConfig):
    """#wxy servermanager 应用配置，name 与目录名一致，供 INSTALLED_APPS 引用。"""
    name = 'servermanager'
