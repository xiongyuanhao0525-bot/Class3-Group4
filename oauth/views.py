"""
oauth/views.py
==============
#yjh 本模块是第三方登录（OAuth2.0）的视图层，串联完整登录流程：
    ① oauthlogin      接收"使用XX登录"点击，跳转到第三方授权页
    ② authorize       第三方回调入口：code换token → 拉取用户信息 → 绑定/创建本地账号 → 完成登录
    ③ RequireEmailView 第三方未返回邮箱时，要求用户补填邮箱
    ④ emailconfirm    用户点击邮件中的确认链接，完成邮箱绑定并登录
    ⑤ bindsuccess     绑定结果提示页
#yjh 安全要点：回跳地址做白名单校验防开放重定向；邮箱确认链接用
    SECRET_KEY+id 的 SHA256 签名防伪；写库操作包在事务里保证一致性。
"""
import logging
# Create your views here.
from urllib.parse import urlparse

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth import login
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.http import HttpResponseForbidden
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.generic import FormView
from django.utils.http import url_has_allowed_host_and_scheme

from djangoblog.blog_signals import oauth_user_login_signal
from djangoblog.utils import get_current_site
from djangoblog.utils import send_email, get_sha256
from oauth.forms import RequireEmailForm
from .models import OAuthUser
from .oauthmanager import get_manager_by_type, OAuthAccessTokenException

logger = logging.getLogger(__name__)


def get_redirecturl(request):
    # yjh: 解析登录成功后的回跳地址，并做严格的安全校验
    nexturl = request.GET.get('next_url', None)
    if not nexturl or nexturl == '/login/' or nexturl == '/login':
        # yjh: 未指定或回跳目标是登录页本身（会形成循环），默认回首页
        return '/'

    # Only allow relative URLs or URLs pointing to the current host
    # yjh: 防"开放重定向"漏洞：只允许相对路径或指向本站的 URL，
    # 否则攻击者可构造 ?next_url=http://evil.com 把登录后的用户钓走
    site_domain = get_current_site().domain
    if url_has_allowed_host_and_scheme(
        url=nexturl,
        allowed_hosts={site_domain},
        require_https=request.is_secure()
    ):
        return nexturl

    logger.info('非法url:' + str(nexturl))
    return '/'


def oauthlogin(request):
    # yjh: 第三方登录第一步：根据 type 参数找到对应管理器，跳转到其授权页
    type = request.GET.get('type', None)
    if not type:
        return HttpResponseRedirect('/')
    manager = get_manager_by_type(type)
    if not manager:
        # yjh: 平台未启用或类型非法，直接回首页（静默失败，不暴露内部信息）
        return HttpResponseRedirect('/')
    nexturl = get_redirecturl(request)
    authorizeurl = manager.get_authorization_url(nexturl)
    return HttpResponseRedirect(authorizeurl)


def authorize(request):
    # yjh: 第三方登录回调入口（核心视图），完成"code → token → 用户 → 登录"全流程
    type = request.GET.get('type', None)
    if not type:
        return HttpResponseRedirect('/')
    manager = get_manager_by_type(type)
    if not manager:
        return HttpResponseRedirect('/')
    # yjh: 第三方回调时携带的授权码 code（有效期很短，通常几分钟）
    code = request.GET.get('code', None)
    try:
        rsp = manager.get_access_token_by_code(code)
    except OAuthAccessTokenException as e:
        # yjh: 换 token 失败（code 过期/被重放等），记警告日志后回首页
        logger.warning("OAuthAccessTokenException:" + str(e))
        return HttpResponseRedirect('/')
    except Exception as e:
        # yjh: 兜底捕获网络超时等意外异常，rsp 置 None 走下方重新授权逻辑
        logger.error(e)
        rsp = None
    nexturl = get_redirecturl(request)
    if not rsp:
        # yjh: 拿 token 失败：重新生成授权 URL 让用户再走一遍授权流程
        return HttpResponseRedirect(manager.get_authorization_url(nexturl))
    user = manager.get_oauth_userinfo()
    if user:
        if not user.nickname or not user.nickname.strip():
            # yjh: 第三方昵称为空时生成兜底昵称：djangoblog+时间戳，保证非空
            user.nickname = "djangoblog" + timezone.now().strftime('%y%m%d%I%M%S')
        try:
            # yjh: 老用户（同 type+openid）已存在：更新头像/昵称/metadata 后复用原记录
            temp = OAuthUser.objects.get(type=type, openid=user.openid)
            temp.picture = user.picture
            temp.metadata = user.metadata
            temp.nickname = user.nickname
            user = temp
        except ObjectDoesNotExist:
            # yjh: 新用户：保持新对象，后续 save() 时插入
            pass
        # facebook的token过长
        # yjh: Facebook token 超长会超出模型 150 字符限制，干脆不落库
        if type == 'facebook':
            user.token = ''
        if user.email:
            # yjh: 有邮箱 → 直接走"绑定/创建本地账号 + 登录"分支（事务保证一致性）
            with transaction.atomic():
                author = None
                try:
                    # yjh: OAuthUser 已绑定过本地账号（老用户再次登录）
                    author = get_user_model().objects.get(id=user.author_id)
                except ObjectDoesNotExist:
                    pass
                if not author:
                    # yjh: 按邮箱匹配/创建本地账号：同一邮箱的第三方登录自动合并到同一账号
                    result = get_user_model().objects.get_or_create(email=user.email)
                    author = result[0]
                    if result[1]:
                        # yjh: 新建账号时尽量用第三方昵称作用户名；重名则降级为时间戳名
                        try:
                            get_user_model().objects.get(username=user.nickname)
                        except ObjectDoesNotExist:
                            author.username = user.nickname
                        else:
                            author.username = "djangoblog" + timezone.now().strftime('%y%m%d%I%M%S')
                        author.source = 'authorize'
                        author.save()

                # yjh: 建立 OAuthUser ↔ 本地用户的外键绑定
                user.author = author
                user.save()

                # yjh: 发送"第三方登录成功"信号（用于记录登录日志等扩展点）
                oauth_user_login_signal.send(
                    sender=authorize.__class__, id=user.id)
                login(request, author)
                # 设置session过期时间为2周（默认）
                request.session.set_expiry(settings.SESSION_COOKIE_AGE)
                # 设置登录标记 cookie
                # yjh: logged_user cookie 供前端 JS 判断登录态（httponly=False 故意放开）
                response = HttpResponseRedirect(nexturl)
                response.set_cookie(
                    'logged_user',
                    'true',
                    max_age=settings.SESSION_COOKIE_AGE,
                    httponly=False,  # 允许 JavaScript 访问
                    samesite='Lax'
                )
                return response
        else:
            # yjh: 第三方未提供邮箱 → 先存 OAuthUser，再跳转补填邮箱页面
            user.save()
            url = reverse('oauth:require_email', kwargs={
                'oauthid': user.id
            })

            return HttpResponseRedirect(url)
    else:
        # yjh: 拉取用户信息失败（如接口异常），回跳原页面
        return HttpResponseRedirect(nexturl)


def emailconfirm(request, id, sign):
    # yjh: 邮箱确认链接的落地视图：校验签名 → 绑定账号 → 自动登录 → 发通知邮件
    if not sign:
        return HttpResponseForbidden()
    # yjh: 签名校验：sha256(SECRET_KEY + id + SECRET_KEY)，双向包裹密钥
    # 防止攻击者用已知 id 构造合法签名（类似 HMAC 的简易实现）
    if not get_sha256(settings.SECRET_KEY +
                      str(id) +
                      settings.SECRET_KEY).upper() == sign.upper():
        return HttpResponseForbidden()
    oauthuser = get_object_or_404(OAuthUser, pk=id)
    with transaction.atomic():
        if oauthuser.author:
            # yjh: 已绑定过本地账号，直接复用
            author = get_user_model().objects.get(pk=oauthuser.author_id)
        else:
            # yjh: 按确认的邮箱匹配/创建本地账号
            result = get_user_model().objects.get_or_create(email=oauthuser.email)
            author = result[0]
            if result[1]:
                author.source = 'emailconfirm'
                author.username = oauthuser.nickname.strip() if oauthuser.nickname.strip(
                ) else "djangoblog" + timezone.now().strftime('%y%m%d%I%M%S')
                author.save()
        oauthuser.author = author
        oauthuser.save()
    oauth_user_login_signal.send(
        sender=emailconfirm.__class__,
        id=oauthuser.id)
    login(request, author)
    # 设置session过期时间为2周（默认）
    request.session.set_expiry(settings.SESSION_COOKIE_AGE)

    site = 'http://' + get_current_site().domain
    content = _('''
     <p>Congratulations, you have successfully bound your email address. You can use
      %(oauthuser_type)s to directly log in to this website without a password.</p>
       You are welcome to continue to follow this site, the address is
        <a href="%(site)s" rel="bookmark">%(site)s</a>
            Thank you again!
            <br />
        If the link above cannot be opened, please copy this link to your browser.
        %(site)s
    ''') % {'oauthuser_type': oauthuser.type, 'site': site}

    # yjh: 绑定成功后发送通知邮件，告知用户以后可用第三方账号免密登录
    send_email(emailto=[oauthuser.email, ], title=_('Congratulations on your successful binding!'), content=content)
    url = reverse('oauth:bindsuccess', kwargs={
        'oauthid': id
    })
    url = url + '?type=success'
    # 设置登录标记 cookie
    response = HttpResponseRedirect(url)
    response.set_cookie(
        'logged_user',
        'true',
        max_age=settings.SESSION_COOKIE_AGE,
        httponly=False,  # 允许 JavaScript 访问
        samesite='Lax'
    )
    return response


class RequireEmailView(FormView):
    # yjh: 补填邮箱页（类视图）：第三方账号拿不到邮箱时，
    # 引导用户手动填写邮箱，提交后发送带签名链接的确认邮件
    form_class = RequireEmailForm
    template_name = 'oauth/require_email.html'

    def get(self, request, *args, **kwargs):
        oauthid = self.kwargs['oauthid']
        # yjh: oauthid 不存在直接 404，防止遍历探测
        oauthuser = get_object_or_404(OAuthUser, pk=oauthid)
        if oauthuser.email:
            pass
            # return HttpResponseRedirect('/')

        return super(RequireEmailView, self).get(request, *args, **kwargs)

    def get_initial(self):
        # yjh: 表单初始值：email 留空，oauthid 藏进隐藏字段随表单回传
        oauthid = self.kwargs['oauthid']
        return {
            'email': '',
            'oauthid': oauthid
        }

    def get_context_data(self, **kwargs):
        # yjh: 把第三方头像传给模板展示，提升填写时的信任感
        oauthid = self.kwargs['oauthid']
        oauthuser = get_object_or_404(OAuthUser, pk=oauthid)
        if oauthuser.picture:
            kwargs['picture'] = oauthuser.picture
        return super(RequireEmailView, self).get_context_data(**kwargs)

    def form_valid(self, form):
        # yjh: 表单校验通过：保存邮箱 → 生成签名确认链接 → 发送确认邮件
        email = form.cleaned_data['email']
        oauthid = form.cleaned_data['oauthid']
        oauthuser = get_object_or_404(OAuthUser, pk=oauthid)
        oauthuser.email = email
        oauthuser.save()
        # yjh: 生成防伪造签名（详见 emailconfirm 中的校验逻辑）
        sign = get_sha256(settings.SECRET_KEY +
                          str(oauthuser.id) + settings.SECRET_KEY)
        site = get_current_site().domain
        if settings.DEBUG:
            # yjh: 开发环境下站点域名替换为本地地址，方便调试邮件链接
            site = '127.0.0.1:8000'
        path = reverse('oauth:email_confirm', kwargs={
            'id': oauthid,
            'sign': sign
        })
        url = "http://{site}{path}".format(site=site, path=path)

        content = _("""
               <p>Please click the link below to bind your email</p>

                 <a href="%(url)s" rel="bookmark">%(url)s</a>

                 Thank you again!
                 <br />
                 If the link above cannot be opened, please copy this link to your browser.
                  <br />
                 %(url)s
                """) % {'url': url}
        send_email(emailto=[email, ], title=_('Bind your email'), content=content)
        # yjh: 邮件已发出，跳转提示页让用户去邮箱点确认链接
        url = reverse('oauth:bindsuccess', kwargs={
            'oauthid': oauthid
        })
        url = url + '?type=email'
        return HttpResponseRedirect(url)


def bindsuccess(request, oauthid):
    # yjh: 绑定结果提示页：type=email 提示去收邮件；否则提示绑定成功
    type = request.GET.get('type', None)
    oauthuser = get_object_or_404(OAuthUser, pk=oauthid)
    if type == 'email':
        title = _('Bind your email')
        content = _(
            'Congratulations, the binding is just one step away. '
            'Please log in to your email to check the email to complete the binding. Thank you.')
    else:
        title = _('Binding successful')
        content = _(
            "Congratulations, you have successfully bound your email address. You can use %(oauthuser_type)s"
            " to directly log in to this website without a password. You are welcome to continue to follow this site." % {
                'oauthuser_type': oauthuser.type})
    return render(request, 'oauth/bindsuccess.html', {
        'title': title,
        'content': content
    })
