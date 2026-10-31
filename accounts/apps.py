# accounts/apps.py
# 用户模块应用配置
# 注释人：陈汉佳 #chj （只加注释，不改逻辑）
from django.apps import AppConfig


class AccountsConfig(AppConfig):
    name = 'accounts'   # #chj 应用名，与项目 settings 中 INSTALLED_APPS 一致
