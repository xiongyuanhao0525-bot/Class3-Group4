# -*- coding: utf-8 -*-
"""#wxy servermanager/urls.py：把 WeRoBot 实例挂载为 Django 视图。
微信公众平台后台配置的服务器地址即 <本站域名>/servermanager/robot。
"""
from django.urls import path
from werobot.contrib.django import make_view

from .robot import robot

# #wxy 命名空间，避免与 blog/accounts 的 URL 命名冲突
app_name = "servermanager"
urlpatterns = [
    # #wxy WeRoBot 提供的 make_view 把 robot 包装成 Django view，
    # 同时处理微信的 GET 校验（token 校验）与 POST 消息推送
    path(r'robot', make_view(robot)),

]
