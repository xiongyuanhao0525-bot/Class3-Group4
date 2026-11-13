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
import hmac
import logging
import secrets
# Create your views here.
from urllib.parse import urlparse

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
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
from django.views.decorators.http import require_POST
from django.utils.http import url_has_allowed_host_and_scheme

from djangoblog.blog_signals import oauth_user_login_signal
from djangoblog.utils import get_current_site
from djangoblog.utils import send_email, get_sha256
from oauth.forms import RequireEmailForm
from .models import OAuthUser
from .oauthmanager import get_manager_by_type, get_oauth_apps, OAuthAccessTokenException

logger = logging.getLogger(__name__)

# yjh: session 中保存 OAuth 一次性 state 的键名
OAUTH_STATE_SESSION_KEY = 'oauth_state'

# yjh: 平台标识 → 中文名（账号管理页与失败提示页共用）
OAUTH_TYPE_NAMES = {
    'weibo': '微博',
    'google': 'Google',
    'github': 'GitHub',
    'facebook': 'FaceBook',
    'qq': 'QQ',
}

# yjh: 功能点3：各类授权失败的友好提示文案（不暴露内部异常细节）
OAUTH_ERROR_MESSAGES = {
    'unsupported_type': '不支持的第三方登录方式，请返回登录页重试。',
    'invalid_state': '授权请求已失效或来源不可信，请重新发起登录。',
    'token_failed': '获取授权凭证失败，可能是授权已过期，请重新登录。',
    'userinfo_failed': '获取第三方用户信息失败，请稍后重试。',
}


def _oauth_error(request, oauth_type, reason, detail=''):
    # yjh: 功能点3：统一失败出口——渲染友好提示页；按"阶段"记录带上下文的日志
    # yjh: state 失败返回 400（属于可疑请求），其余返回 200 便于用户自行重试
    logger.warning(
        'oauth 授权失败 type=%s stage=%s detail=%s ip=%s',
        oauth_type, reason, detail, request.META.get('REMOTE_ADDR', '-'))
    status = 400 if reason == 'invalid_state' else 200
    return render(request, 'oauth/oauth_error.html', {
        'type_name': OAUTH_TYPE_NAMES.get(oauth_type, oauth_type or '第三方平台'),
        'oauth_type': oauth_type or '',
        'message': OAUTH_ERROR_MESSAGES.get(reason, '登录失败，请稍后重试。'),
        'stage': reason,
    }, status=status)



def _build_state(request, oauth_type, nexturl, bind=False):
    # yjh: 生成一次性随机 state 并写入 session，供回调时校验"本次授权确由本站发起"
    state = secrets.token_urlsafe(32)
    request.session[OAUTH_STATE_SESSION_KEY] = state
    request.session['oauth_state_type'] = oauth_type
    request.session['oauth_state_next'] = nexturl
    # yjh: 标记本次授权是"已登录用户绑定新平台"，回调时据此走绑定逻辑而非登录
    request.session['oauth_bind'] = bind
    return state


def _consume_state(request):
    # yjh: 校验 state 并立即从 session 删除（一次性消费），通过返回 True
    # yjh: 缺少 state（伪造回调）、session 无记录（跨站伪造）、值不匹配均拒绝
    expected = request.session.pop(OAUTH_STATE_SESSION_KEY, None)
    request.session.pop('oauth_state_type', None)
    request.session.pop('oauth_state_next', None)
    provided = request.GET.get('state') or ''
    if not expected or not provided:
        return False
    # yjh: 用 compare_digest 做常量时间比较，避免时序侧信道
    return hmac.compare_digest(expected, provided)


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
    # yjh: 已登录用户带 bind=1 进入时，本次授权用于"绑定新平台"，不是登录
    bind = request.GET.get('bind') == '1' and request.user.is_authenticated
    # yjh: 跳转授权页前先生成 state 存 session，回调时校验
    state = _build_state(request, type, nexturl, bind)
    authorizeurl = manager.get_authorization_url(nexturl, state)
    return HttpResponseRedirect(authorizeurl)


def authorize(request):
    # yjh: 第三方登录回调入口（核心视图），完成"code → token → 用户 → 登录"全流程
    type = request.GET.get('type', None)
    if not type:
        # yjh: 功能点3：缺少平台标识 → 友好提示，而不是静默跳首页
        return _oauth_error(request, type, 'unsupported_type')
    manager = get_manager_by_type(type)
    if not manager:
        # yjh: 功能点3：平台未启用或类型非法 → 友好提示
        return _oauth_error(request, type, 'unsupported_type')
    # yjh: 功能点1：任何业务处理前先校验 state，阻断"伪造回调"式登录 CSRF
    if not _consume_state(request):
        # yjh: 功能点3：state 失败属于可疑请求，返回 400 提示页
        return _oauth_error(request, type, 'invalid_state')
    # yjh: 第三方回调时携带的授权码 code（有效期很短，通常几分钟）
    code = request.GET.get('code', None)
    try:
        rsp = manager.get_access_token_by_code(code)
    except OAuthAccessTokenException as e:
        # yjh: 功能点3：换 token 失败（code 过期/被重放等）→ 友好提示 + 阶段日志
        return _oauth_error(request, type, 'token_failed', str(e))
    except Exception as e:
        # yjh: 兜底捕获网络超时等意外异常，rsp 置 None 走下方重新授权逻辑
        logger.error('oauth 换取 token 异常 type=%s err=%s', type, e)
        rsp = None
    nexturl = get_redirecturl(request)
    if not rsp:
        # yjh: 拿 token 失败：重新生成授权 URL 让用户再走一遍授权流程
        # yjh: state 已被消费，重新发起前必须再生成一个新的
        state = _build_state(request, type, nexturl)
        return HttpResponseRedirect(
            manager.get_authorization_url(nexturl, state))
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
        # yjh: 功能点2：已登录用户主动发起的绑定，直接把该第三方身份绑到当前账号
        if request.session.pop('oauth_bind', False) and request.user.is_authenticated:
            if user.author_id and user.author_id != request.user.id:
                # yjh: 该第三方身份已属于别的本地账号，禁止抢占，避免账号劫持
                logger.warning(
                    '第三方身份已绑定其他账号，type=%s openid=%s', type, user.openid)
                return HttpResponseRedirect(
                    reverse('oauth:bindings') + '?result=conflict')
            user.author = request.user
            user.save()
            logger.info('绑定第三方账号成功，user_id=%s type=%s',
                        request.user.id, type)
            return HttpResponseRedirect(
                reverse('oauth:bindings') + '?result=bound')
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
        # yjh: 功能点3：拉取用户信息失败 → 友好提示，不再静默回跳原页面
        return _oauth_error(request, type, 'userinfo_failed')


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


# yjh: 功能点2：第三方账号管理页与解绑视图


@login_required
def bindings(request):
    # yjh: 功能点2：第三方账号管理页（已绑定项可解绑，未绑定平台可发起绑定）
    bound_qs = OAuthUser.objects.filter(author=request.user)
    bound_accounts = [
        {'id': item.id,
         'nickname': item.nickname,
         'picture': item.picture,
         'type_name': OAUTH_TYPE_NAMES.get(item.type, item.type)}
        for item in bound_qs
    ]
    bound_types = {item.type for item in bound_qs}
    available_apps = [
        {'type': app.ICON_NAME,
         'name': OAUTH_TYPE_NAMES.get(app.ICON_NAME, app.ICON_NAME)}
        for app in get_oauth_apps() if app.ICON_NAME not in bound_types]
    return render(request, 'oauth/oauth_bindings.html', {
        'bound_accounts': bound_accounts,
        'available_apps': available_apps,
        'result': request.GET.get('result', ''),
        # yjh: 账号没有可用密码且只剩一个绑定时禁止解绑，避免把自己锁在门外
        'can_unbind': request.user.has_usable_password() or len(bound_accounts) > 1,
    })


@login_required
@require_POST
def unbind(request, oauthid):
    # yjh: 功能点2：解绑第三方账号；只能操作自己名下的绑定，且必须 POST
    oauthuser = get_object_or_404(OAuthUser, id=oauthid, author=request.user)
    if not request.user.has_usable_password() and \
            OAuthUser.objects.filter(author=request.user).count() <= 1:
        logger.info('拒绝解绑最后一个登录方式，user_id=%s', request.user.id)
        return HttpResponseRedirect(reverse('oauth:bindings') + '?result=last')
    logger.info('解绑第三方账号，user_id=%s type=%s',
                request.user.id, oauthuser.type)
    oauthuser.delete()
    return HttpResponseRedirect(reverse('oauth:bindings') + '?result=unbound')
