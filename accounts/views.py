# accounts/views.py
# 用户模块视图层：注册 / 登录 / 登出 / 邮箱验证 / 找回密码
# 注释人：陈汉佳 #chj （只加注释，不改逻辑）
import logging
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from django.contrib import auth
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.contrib.auth import get_user_model
from django.contrib.auth import logout
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.hashers import make_password
from django.http import HttpResponseRedirect, HttpResponseForbidden
from django.http.request import HttpRequest
from django.http.response import HttpResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View

from djangoblog.utils import send_email, get_sha256, get_current_site, generate_code, delete_sidebar_cache
from djangoblog.base_views import SecureFormView, LoginFormView, LogoutRedirectView
from . import utils
from .forms import RegisterForm, LoginForm, ForgetPasswordForm, ForgetPasswordCodeForm
from .models import BlogUser

logger = logging.getLogger(__name__)


# Create your views here.

class RegisterView(SecureFormView):
    """
    用户注册视图（重构版）

    使用 SecureFormView 基类，自动提供 CSRF 保护
    #chj
    """
    form_class = RegisterForm
    template_name = 'account/registration_form.html'

    def form_valid(self, form):
        # #chj 表单校验通过后执行：创建用户并发送邮箱验证邮件
        if form.is_valid():
            user = form.save(False)              # #chj 先不落库，稍后补字段
            user.is_active = False               # #chj 注册后先冻结，等邮箱验证通过再激活
            user.source = 'Register'             # #chj 标记注册来源为站点注册
            user.save(True)
            site = get_current_site().domain
            # #chj 用 SECRET_KEY + 用户id 双重哈希生成签名，防止验证链接被伪造
            sign = get_sha256(get_sha256(settings.SECRET_KEY + str(user.id)))

            if settings.DEBUG:
                # #chj 本地调试时域名替换为本机地址
                site = '127.0.0.1:8000'
            path = reverse('account:result')
            # #chj 拼接邮箱验证链接，携带 type/id/sign 三个参数
            url = "http://{site}{path}?type=validation&id={id}&sign={sign}".format(
                site=site, path=path, id=user.id, sign=sign)

            content = """
                            <p>请点击下面链接验证您的邮箱</p>

                            <a href="{url}" rel="bookmark">{url}</a>

                            再次感谢您！
                            <br />
                            如果上面链接无法打开，请将此链接复制至浏览器。
                            {url}
                            """.format(url=url)
            # #chj 发送带验证链接的邮件到用户邮箱
            send_email(
                emailto=[
                    user.email,
                ],
                title='验证您的电子邮箱',
                content=content)

            # #chj 跳转到注册成功提示页
            url = reverse('accounts:result') + \
                  '?type=register&id=' + str(user.id)
            return HttpResponseRedirect(url)
        else:
            # #chj 校验失败则重新渲染注册页并回显错误
            return self.render_to_response({
                'form': form
            })


class LogoutView(LogoutRedirectView):
    """
    用户登出视图（重构版）

    使用 LogoutRedirectView 基类，自动禁用缓存
    #chj
    """
    url = '/login/'

    def get(self, request, *args, **kwargs):
        logout(request)                          # #chj 清空登录态
        delete_sidebar_cache()                   # #chj 登录用户变化，清除侧边栏缓存
        # 获取响应对象并删除登录标记 cookie
        response = super(LogoutView, self).get(request, *args, **kwargs)
        response.delete_cookie('logged_user')    # #chj 删除前端登录标记 cookie
        return response


class LoginView(LoginFormView):
    """
    用户登录视图（重构版）

    使用 LoginFormView 基类，自动提供：
    - 敏感参数保护（password）
    - CSRF 保护
    - 禁用缓存
    #chj
    """
    form_class = LoginForm
    template_name = 'account/login.html'
    success_url = '/'
    redirect_field_name = REDIRECT_FIELD_NAME

    def get_context_data(self, **kwargs):
        # #chj 把 ?next= 参数带进模板，登录后跳回原页面
        redirect_to = self.request.GET.get(self.redirect_field_name)
        if redirect_to is None:
            redirect_to = '/'
        kwargs['redirect_to'] = redirect_to

        return super(LoginView, self).get_context_data(**kwargs)

    def form_valid(self, form):
        # #chj 重新用 AuthenticationForm 校验用户名密码
        form = AuthenticationForm(data=self.request.POST, request=self.request)

        if form.is_valid():
            delete_sidebar_cache()               # #chj 登录后侧边栏数据可能变化，清缓存
            logger.info(self.redirect_field_name)

            auth.login(self.request, form.get_user())   # #chj 写入 Django 登录态
            # 设置登录有效期
            if self.request.POST.get("remember"):
                # #chj 勾选"记住我"则用较长有效期
                self.request.session.set_expiry(settings.REMEMBER_ME_LOGIN_TTL)
                cookie_max_age = settings.REMEMBER_ME_LOGIN_TTL
            else:
                # 使用Django默认的2周
                self.request.session.set_expiry(settings.SESSION_COOKIE_AGE)
                cookie_max_age = settings.SESSION_COOKIE_AGE

            # 获取响应对象并设置登录标记 cookie
            response = super(LoginView, self).form_valid(form)
            # #chj 写一个前端可读的登录标记 cookie（非 HttpOnly）
            response.set_cookie(
                'logged_user',
                'true',
                max_age=cookie_max_age,
                httponly=False,  # 允许 JavaScript 访问
                samesite='Lax'
            )
            return response
            # return HttpResponseRedirect('/')
        else:
            # #chj 校验失败回登录页展示错误
            return self.render_to_response({
                'form': form
            })

    def get_success_url(self):
        # #chj 校验 next 参数是否本站地址，防止开放重定向攻击
        redirect_to = self.request.POST.get(self.redirect_field_name)
        if not url_has_allowed_host_and_scheme(
                url=redirect_to, allowed_hosts=[
                    self.request.get_host()]):
            redirect_to = self.success_url
        return redirect_to


def account_result(request):
    # #chj 注册成功 / 邮箱验证结果的通用提示页视图
    type = request.GET.get('type')
    id = request.GET.get('id')

    user = get_object_or_404(get_user_model(), id=id)
    logger.info(type)
    if user.is_active:
        # #chj 已激活用户直接回首页
        return HttpResponseRedirect('/')
    if type and type in ['register', 'validation']:
        if type == 'register':
            # #chj 注册成功提示
            content = '''
    恭喜您注册成功，一封验证邮件已经发送到您的邮箱，请验证您的邮箱后登录本站。
    '''
            title = '注册成功'
        else:
            # #chj 邮箱验证：校验签名是否与服务器计算一致
            c_sign = get_sha256(get_sha256(settings.SECRET_KEY + str(user.id)))
            sign = request.GET.get('sign')
            if sign != c_sign:
                # #chj 签名不合法直接 403
                return HttpResponseForbidden()
            user.is_active = True                # #chj 验证通过，激活账号
            user.save()
            content = '''
            恭喜您已经成功的完成邮箱验证，您现在可以使用您的账号来登录本站。
            '''
            title = '验证成功'
        return render(request, 'account/result.html', {
            'title': title,
            'content': content
        })
    else:
        # #chj 未知 type 一律回首页
        return HttpResponseRedirect('/')


class ForgetPasswordView(SecureFormView):
    """
    忘记密码视图（重构版）

    使用 SecureFormView 基类，自动提供 CSRF 保护
    #chj
    """
    form_class = ForgetPasswordForm
    template_name = 'account/forget_password.html'

    def form_valid(self, form):
        # #chj 校验通过后：按邮箱找到用户并重置密码
        if form.is_valid():
            blog_user = BlogUser.objects.filter(email=form.cleaned_data.get("email")).get()
            # #chj 用 Django 哈希器加密新密码再保存
            blog_user.password = make_password(form.cleaned_data["new_password2"])
            blog_user.save()
            return HttpResponseRedirect('/login/')   # #chj 改完跳登录页
        else:
            return self.render_to_response({'form': form})


class ForgetPasswordEmailCode(View):
    # #chj 发送重置密码邮箱验证码的接口（AJAX 调用）
    def post(self, request: HttpRequest):
        form = ForgetPasswordCodeForm(request.POST)
        if not form.is_valid():
            return HttpResponse("错误的邮箱")
        to_email = form.cleaned_data["email"]

        code = generate_code()                   # #chj 生成随机验证码
        utils.send_verify_email(to_email, code)  # #chj 发送到邮箱
        utils.set_code(to_email, code)           # #chj 写入缓存（5分钟有效）

        return HttpResponse("ok")
