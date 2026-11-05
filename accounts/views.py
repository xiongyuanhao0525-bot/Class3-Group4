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
    """
    form_class = RegisterForm
    template_name = 'account/registration_form.html'

    def form_valid(self, form):
        if form.is_valid():
            user = form.save(False)
            user.is_active = False
            user.source = 'Register'
            user.save(True)
            site = get_current_site().domain
            sign = get_sha256(get_sha256(settings.SECRET_KEY + str(user.id)))

            if settings.DEBUG:
                site = '127.0.0.1:8000'
            path = reverse('account:result')
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
            send_email(
                emailto=[
                    user.email,
                ],
                title='验证您的电子邮箱',
                content=content)

            url = reverse('accounts:result') + \
                  '?type=register&id=' + str(user.id)
            return HttpResponseRedirect(url)
        else:
            return self.render_to_response({
                'form': form
            })


class LogoutView(LogoutRedirectView):
    """
    用户登出视图（重构版）

    使用 LogoutRedirectView 基类，自动禁用缓存
    """
    url = '/login/'

    def get(self, request, *args, **kwargs):
        logout(request)
        delete_sidebar_cache()
        # 获取响应对象并删除登录标记 cookie
        response = super(LogoutView, self).get(request, *args, **kwargs)
        response.delete_cookie('logged_user')
        return response


class LoginView(LoginFormView):
    """
    用户登录视图（重构版）

    使用 LoginFormView 基类，自动提供：
    - 敏感参数保护（password）
    - CSRF 保护
    - 禁用缓存
    """
    form_class = LoginForm
    template_name = 'account/login.html'
    success_url = '/'
    redirect_field_name = REDIRECT_FIELD_NAME

    def get_context_data(self, **kwargs):
        redirect_to = self.request.GET.get(self.redirect_field_name)
        if redirect_to is None:
            redirect_to = '/'
        kwargs['redirect_to'] = redirect_to

        return super(LoginView, self).get_context_data(**kwargs)

    def form_valid(self, form):
        request = self.request
        username = self._submitted_username()
        user = self._get_user_by_username(username)

        # 一、账号还在锁定期内：即使密码正确也不允许登录，直接返回锁定提示（429）
        lock_remaining = utils.get_login_lock_remaining(username, user=user)
        if lock_remaining:
            return self._render_locked(username, lock_remaining)

        form = AuthenticationForm(data=self.request.POST, request=self.request)

        if form.is_valid():
            # 登录成功：清空失败计数与锁定状态
            utils.reset_login_failures(form.get_user(), username)
            delete_sidebar_cache()
            logger.info(self.redirect_field_name)

            auth.login(self.request, form.get_user())
            # 设置登录有效期
            if self.request.POST.get("remember"):
                self.request.session.set_expiry(settings.REMEMBER_ME_LOGIN_TTL)
                cookie_max_age = settings.REMEMBER_ME_LOGIN_TTL
            else:
                # 使用Django默认的2周
                self.request.session.set_expiry(settings.SESSION_COOKIE_AGE)
                cookie_max_age = settings.SESSION_COOKIE_AGE

            # 获取响应对象并设置登录标记 cookie
            response = super(LoginView, self).form_valid(form)
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
            return self._register_failure(form)

    def form_invalid(self, form):
        """用户名/密码错误：累计失败次数，达到阈值后锁定账号"""
        return self._register_failure(form)

    def _submitted_username(self):
        return (self.request.POST.get('username') or '').strip()

    def _get_user_by_username(self, username):
        """按用户名取用户对象，不存在时返回 None（用于失败计数与锁定判断）"""
        if not username:
            return None
        return get_user_model().objects.filter(username=username).first()

    def _register_failure(self, form):
        """记录一次登录失败，并把剩余可试次数或锁定提示写回表单"""
        username = self._submitted_username()
        user = self._get_user_by_username(username)

        lock_remaining = utils.get_login_lock_remaining(username, user=user)
        if lock_remaining:
            return self._render_locked(username, lock_remaining)

        if not username:
            # 连用户名都没填，不做计数
            return self.render_to_response(self.get_context_data(form=form))

        count, lock_remaining = utils.register_login_failure(
            username, user=user)
        if lock_remaining:
            logger.warning(
                '账号 %s 连续登录失败 %d 次，已锁定 %d 秒',
                username, count, lock_remaining)
            return self._render_locked(username, lock_remaining)
        else:
            fail_limit = utils.get_login_failure_limit()
            lock_minutes = max(1, utils.get_login_lock_seconds() // 60)
            form.add_error(
                None,
                '用户名或密码错误，再失败 %d 次后账号将被临时锁定 %d 分钟' % (
                    max(fail_limit - count, 1), lock_minutes))

        return self.render_to_response(self.get_context_data(form=form))

    def _render_locked(self, username, lock_remaining):
        """渲染"账号已被临时锁定"的登录页"""
        logger.warning('账号 %s 处于登录锁定期，剩余 %d 秒', username, lock_remaining)
        locked_form = AuthenticationForm(
            data=self.request.POST, request=self.request)
        locked_form.add_error(None, utils.build_login_lock_message(lock_remaining))
        response = self.render_to_response({
            'form': locked_form,
            'lock_remaining': lock_remaining,
        })
        response.status_code = 429
        return response

    def get_success_url(self):

        redirect_to = self.request.POST.get(self.redirect_field_name)
        if not url_has_allowed_host_and_scheme(
                url=redirect_to, allowed_hosts=[
                    self.request.get_host()]):
            redirect_to = self.success_url
        return redirect_to


def account_result(request):
    type = request.GET.get('type')
    id = request.GET.get('id')

    user = get_object_or_404(get_user_model(), id=id)
    logger.info(type)
    if user.is_active:
        return HttpResponseRedirect('/')
    if type and type in ['register', 'validation']:
        if type == 'register':
            content = '''
    恭喜您注册成功，一封验证邮件已经发送到您的邮箱，请验证您的邮箱后登录本站。
    '''
            title = '注册成功'
        else:
            c_sign = get_sha256(get_sha256(settings.SECRET_KEY + str(user.id)))
            sign = request.GET.get('sign')
            if sign != c_sign:
                return HttpResponseForbidden()
            user.is_active = True
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
        return HttpResponseRedirect('/')


class ForgetPasswordView(SecureFormView):
    """
    忘记密码视图（重构版）

    使用 SecureFormView 基类，自动提供 CSRF 保护
    """
    form_class = ForgetPasswordForm
    template_name = 'account/forget_password.html'

    def form_valid(self, form):
        if form.is_valid():
            blog_user = BlogUser.objects.filter(email=form.cleaned_data.get("email")).get()
            blog_user.password = make_password(form.cleaned_data["new_password2"])
            blog_user.save()
            return HttpResponseRedirect('/login/')
        else:
            return self.render_to_response({'form': form})


class ForgetPasswordEmailCode(View):

    def post(self, request: HttpRequest):
        form = ForgetPasswordCodeForm(request.POST)
        if not form.is_valid():
            return HttpResponse("错误的邮箱")
        to_email = form.cleaned_data["email"]

        code = generate_code()
        utils.send_verify_email(to_email, code)
        utils.set_code(to_email, code)

        return HttpResponse("ok")
