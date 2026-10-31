# accounts/user_login_backend.py
# 自定义登录后端：允许用"邮箱"或"用户名"任一方式登录
# 注释人：陈汉佳 #chj （只加注释，不改逻辑）
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class EmailOrUsernameModelBackend(ModelBackend):
    """
    允许使用用户名或邮箱登录
    #chj
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        # #chj 用户名里含 @ 就按邮箱查，否则按用户名查
        if '@' in username:
            kwargs = {'email': username}
        else:
            kwargs = {'username': username}
        try:
            user = get_user_model().objects.get(**kwargs)
            if user.check_password(password):     # #chj 校验密码哈希
                return user
        except get_user_model().DoesNotExist:
            return None                           # #chj 用户不存在返回 None 表示认证失败

    def get_user(self, username):
        # #chj 按主键取回用户（登录成功后 Django 会调用）
        try:
            return get_user_model().objects.get(pk=username)
        except get_user_model().DoesNotExist:
            return None
