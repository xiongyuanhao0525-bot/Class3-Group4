# accounts/utils.py
# 用户模块工具函数：邮箱验证码的发送 / 校验 / 存取
# 注释人：陈汉佳 #chj （只加注释，不改逻辑）
import typing
from datetime import timedelta

from django.core.cache import cache
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from djangoblog.utils import send_email

# #chj 验证码有效期：5 分钟
_code_ttl = timedelta(minutes=5)


def send_verify_email(to_mail: str, code: str, subject: str = _("Verify Email")):
    """发送重设密码验证码
    Args:
        to_mail: 接受邮箱
        subject: 邮件主题
        code: 验证码
    #chj
    """
    html_content = _(
        "You are resetting the password, the verification code is：%(code)s, valid within 5 minutes, please keep it "
        "properly") % {'code': code}
    send_email([to_mail], subject, html_content)


def verify(email: str, code: str) -> typing.Optional[str]:
    """验证code是否有效
    Args:
        email: 请求邮箱
        code: 验证码
    Return:
        如果有错误就返回错误str
    Node:
        这里的错误处理不太合理，应该采用raise抛出
        否测调用方也需要对error进行处理
    #chj
    """
    cache_code = get_code(email)      # #chj 从缓存取出该邮箱存的验证码
    if cache_code != code:            # #chj 比对不一致返回错误文案
        return gettext("Verification code error")


def set_code(email: str, code: str):
    """设置code
    #chj 把验证码写入缓存，过期时间 5 分钟
    """
    cache.set(email, code, _code_ttl.seconds)


def get_code(email: str) -> typing.Optional[str]:
    """获取code
    #chj 从缓存读取验证码
    """
    return cache.get(email)
