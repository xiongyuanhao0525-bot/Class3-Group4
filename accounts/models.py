# accounts/models.py
# 用户模块数据模型：BlogUser 继承 Django AbstractUser 并扩展字段
# 注释人：陈汉佳 #chj （只加注释，不改逻辑）
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.urls import reverse
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from djangoblog.utils import get_current_site


# Create your models here.

class BlogUser(AbstractUser):
    # #chj 自定义用户模型：继承系统用户，追加 4 个业务字段
    nickname = models.CharField(_('nick name'), max_length=100, blank=True)          # #chj 昵称
    creation_time = models.DateTimeField(_('creation time'), default=now)            # #chj 创建时间
    last_modify_time = models.DateTimeField(_('last modify time'), default=now)      # #chj 最后修改时间
    source = models.CharField(_('create source'), max_length=100, blank=True)        # #chj 注册来源(Register/QQ/Weibo/adminsite)

    def get_absolute_url(self):
        # #chj 返回用户主页 URL（作者详情页）
        return reverse(
            'blog:author_detail', kwargs={
                'author_name': self.username})

    def __str__(self):
        # #chj 后台展示默认显示邮箱
        return self.email

    def get_full_url(self):
        # #chj 拼接带域名的完整 URL（用于邮件等外链场景）
        site = get_current_site().domain
        url = "https://{site}{path}".format(site=site,
                                            path=self.get_absolute_url())
        return url

    class Meta:
        ordering = ['-id']                        # #chj 默认按 id 倒序
        verbose_name = _('user')
        verbose_name_plural = verbose_name
        get_latest_by = 'id'
