# accounts/urls.py
# 用户模块 URL 路由配置
# 注释人：陈汉佳 #chj （只加注释，不改逻辑）
from django.urls import path
from django.urls import re_path

from . import views
from .forms import LoginForm

app_name = "accounts"

urlpatterns = [re_path(r'^login/$',                       # #chj 登录页，登录成功后跳首页
                       views.LoginView.as_view(success_url='/'),
                       name='login',
                       kwargs={'authentication_form': LoginForm}),
               re_path(r'^register/$',                    # #chj 注册页
                       views.RegisterView.as_view(success_url="/"),
                       name='register'),
               re_path(r'^logout/$',                      # #chj 登出
                       views.LogoutView.as_view(),
                       name='logout'),
               path(r'account/result.html',               # #chj 注册/验证结果提示页
                    views.account_result,
                    name='result'),
               re_path(r'^forget_password/$',             # #chj 找回密码表单页
                       views.ForgetPasswordView.as_view(),
                       name='forget_password'),
               re_path(r'^forget_password_code/$',        # #chj 发送重置密码验证码接口
                       views.ForgetPasswordEmailCode.as_view(),
                       name='forget_password_code'),
               ]
