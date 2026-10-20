"""
oauth/models.py
===============
#yjh 本模块定义 oauth 应用的数据模型：
    - OAuthUser   第三方平台用户（与本地 BlogUser 通过 author 外键绑定）
    - OAuthConfig 第三方平台应用配置（appkey/appsecret/回调地址，后台可维护）
"""
# Create your models here.
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _


class OAuthUser(models.Model):
    # yjh: 第三方登录用户表：一条记录 = 某用户在某平台的一个身份
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_('author'),
        blank=True,
        null=True,
        on_delete=models.CASCADE)
    # yjh: author 外键指向本地账号，允许为空——第三方未提供邮箱时先不绑定，
    # 待邮箱确认后再回填；本地账号删除时级联删除（CASCADE）其第三方身份
    openid = models.CharField(max_length=50)
    # yjh: openid 是第三方平台内的用户唯一标识，与 type 联合标识一个第三方身份
    nickname = models.CharField(max_length=50, verbose_name=_('nick name'))
    token = models.CharField(max_length=150, null=True, blank=True)
    # yjh: token 存 access_token 备查；Facebook token 超长会置空（见 views.authorize）
    picture = models.CharField(max_length=350, blank=True, null=True)
    type = models.CharField(blank=False, null=False, max_length=50)
    # yjh: type 取值：weibo/google/github/facebook/qq，对应 OAuthConfig.type
    email = models.CharField(max_length=50, null=True, blank=True)
    metadata = models.TextField(null=True, blank=True)
    # yjh: metadata 存第三方接口返回的原始 JSON 报文，便于后续扩展解析
    creation_time = models.DateTimeField(_('creation time'), default=now)
    last_modify_time = models.DateTimeField(_('last modify time'), default=now)

    def __str__(self):
        return self.nickname

    class Meta:
        verbose_name = _('oauth user')
        verbose_name_plural = verbose_name
        ordering = ['-creation_time']
        # yjh: 默认按创建时间倒序，最新绑定的第三方用户排在前面


class OAuthConfig(models.Model):
    # yjh: 第三方应用配置表：每种平台一条记录（clean 中保证唯一），
    # 支持后台动态启停，get_oauth_apps() 只加载 is_enable=True 的配置
    TYPE = (
        ('weibo', _('weibo')),
        ('google', _('google')),
        ('github', 'GitHub'),
        ('facebook', 'FaceBook'),
        ('qq', 'QQ'),
    )
    type = models.CharField(_('type'), max_length=10, choices=TYPE, default='a')
    appkey = models.CharField(max_length=200, verbose_name='AppKey')
    appsecret = models.CharField(max_length=200, verbose_name='AppSecret')
    # yjh: appkey/appsecret 即第三方开放平台分配的 client_id/client_secret
    callback_url = models.CharField(
        max_length=200,
        verbose_name=_('callback url'),
        blank=False,
        default='')
    is_enable = models.BooleanField(
        _('is enable'), default=True, blank=False, null=False)
    creation_time = models.DateTimeField(_('creation time'), default=now)
    last_modify_time = models.DateTimeField(_('last modify time'), default=now)

    def clean(self):
        # yjh: 模型层唯一性校验：同类型平台只允许一条启用配置，
        # 注意 exclude(id=self.id) 是编辑已有记录时排除自身的经典写法
        if OAuthConfig.objects.filter(
                type=self.type).exclude(id=self.id).count():
            raise ValidationError(_(self.type + _('already exists')))

    def __str__(self):
        return self.type

    class Meta:
        verbose_name = 'oauth配置'
        verbose_name_plural = verbose_name
        ordering = ['-creation_time']
