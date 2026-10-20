"""
oauth/urls.py
=============
#yjh 本模块定义 oauth 应用的 URL 路由，命名空间 app_name='oauth'：
    oauth/oauthlogin                        第三方登录入口（跳授权页）
    oauth/authorize                         第三方授权回调（code换token+登录）
    oauth/requireemail/<oauthid>.html       补填邮箱页
    oauth/emailconfirm/<id>/<sign>.html     邮箱确认链接落地（带签名）
    oauth/bindsuccess/<oauthid>.html        绑定结果提示页
"""
from django.urls import path

from . import views

app_name = "oauth"
urlpatterns = [
    path(
        r'oauth/authorize',
        views.authorize),
    # yjh: 回调地址未命名 name，因为第三方平台回调 URL 需配置绝对地址，不依赖 reverse
    path(
        r'oauth/requireemail/<int:oauthid>.html',
        views.RequireEmailView.as_view(),
        name='require_email'),
    path(
        r'oauth/emailconfirm/<int:id>/<sign>.html',
        views.emailconfirm,
        name='email_confirm'),
    # yjh: sign 段即邮件链接中的防伪签名，由 views.emailconfirm 校验
    path(
        r'oauth/bindsuccess/<int:oauthid>.html',
        views.bindsuccess,
        name='bindsuccess'),
    path(
        r'oauth/oauthlogin',
        views.oauthlogin,
        name='oauthlogin')]
