#!/usr/bin/env python
# encoding: utf-8

"""
Django Blog 基础视图类
提供带有常用装饰器的视图基类，减少重复的 dispatch 方法定义
"""

# xyh：基础视图模块——预置装饰器组合的 CBV 安全基类族。
# xyh：设计意图：把 CSRF/登录态/敏感参数/禁缓存等横切保护收敛到 dispatch 层，
# xyh：业务视图继承对应基类即可，避免每个视图重复手写 method_decorator（高内聚、防遗漏）。

from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.debug import sensitive_post_parameters
from django.views.generic import FormView, RedirectView


# xyh：最基础的表单视图安全形态——只加 CSRF 保护，供公开表单页继承
class SecureFormView(FormView):
    """
    安全的 FormView 基类

    自动添加 CSRF 保护，适用于所有需要表单提交的视图

    Usage:
        class MyFormView(SecureFormView):
            form_class = MyForm
            template_name = 'my_form.html'

            def form_valid(self, form):
                # 处理表单数据
                return super().form_valid(form)
    """

    @method_decorator(csrf_protect)  # xyh：拦截不带 CSRF token 的表单提交
    def dispatch(self, *args, **kwargs):
        """添加 CSRF 保护"""
        return super().dispatch(*args, **kwargs)


# xyh：需登录表单基类——未登录自动重定向 LOGIN_URL，登录后才校验 CSRF
class AuthenticatedFormView(FormView):
    """
    需要登录的 FormView

    自动检查用户登录状态并添加 CSRF 保护
    未登录用户会被重定向到登录页面

    Usage:
        class MyAuthFormView(AuthenticatedFormView):
            form_class = MyForm
            template_name = 'my_form.html'
    """

    @method_decorator(login_required)  # xyh：先做登录态检查（装饰器自下而上生效）
    @method_decorator(csrf_protect)
    def dispatch(self, *args, **kwargs):
        """添加登录要求和 CSRF 保护"""
        return super().dispatch(*args, **kwargs)


# xyh：登录页专用基类——三重保护叠加，accounts.LoginView 即继承此类
class LoginFormView(FormView):
    """
    登录专用 FormView

    包含以下保护措施：
    - 敏感参数保护（password 等）
    - CSRF 保护
    - 禁用缓存（防止登录状态被缓存）

    Usage:
        class LoginView(LoginFormView):
            form_class = LoginForm
            template_name = 'login.html'

            def form_valid(self, form):
                # 处理登录逻辑
                return super().form_valid(form)
    """

    @method_decorator(sensitive_post_parameters('password'))  # xyh：日志中脱敏 password 字段，防明文密码落盘
    @method_decorator(csrf_protect)
    @method_decorator(never_cache)  # xyh：登录页禁用缓存，防凭证/表单残留
    def dispatch(self, request, *args, **kwargs):
        """添加敏感参数保护、CSRF 保护和禁用缓存"""
        return super().dispatch(request, *args, **kwargs)


# xyh：登出重定向基类——确保登出响应不被缓存复用
class LogoutRedirectView(RedirectView):
    """
    登出专用 RedirectView

    自动禁用缓存，确保登出操作不会被缓存

    Usage:
        class LogoutView(LogoutRedirectView):
            url = '/login/'

            def get(self, request, *args, **kwargs):
                logout(request)
                return super().get(request, *args, **kwargs)
    """

    @method_decorator(never_cache)  # xyh：登出动作不可被缓存，否则会话状态可能错乱
    def dispatch(self, request, *args, **kwargs):
        """禁用缓存"""
        return super().dispatch(request, *args, **kwargs)


# xyh：实时数据表单基类——不要求登录但禁缓存+CSRF，适合验证码类场景
class NoCacheFormView(FormView):
    """
    禁用缓存的 FormView

    适用于需要实时数据的表单（如验证码、动态内容等）

    Usage:
        class MyCacheDisabledFormView(NoCacheFormView):
            form_class = MyForm
            template_name = 'my_form.html'
    """

    @method_decorator(never_cache)  # xyh：每次请求都重新生成表单内容
    @method_decorator(csrf_protect)
    def dispatch(self, request, *args, **kwargs):
        """禁用缓存并添加 CSRF 保护"""
        return super().dispatch(request, *args, **kwargs)
