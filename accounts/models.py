from datetime import timedelta

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from djangoblog.utils import get_current_site


# Create your models here.

class BlogUser(AbstractUser):
    nickname = models.CharField(_('nick name'), max_length=100, blank=True)
    creation_time = models.DateTimeField(_('creation time'), default=now)
    last_modify_time = models.DateTimeField(_('last modify time'), default=now)
    source = models.CharField(_('create source'), max_length=100, blank=True)

    # 登录失败锁定相关字段：连续失败若干次后锁定一段时间，防止暴力破解
    failed_login_count = models.PositiveSmallIntegerField(
        _('failed login count'), default=0,
        help_text=_('continuous failed login attempts in current window'))
    last_failed_login_at = models.DateTimeField(
        _('last failed login at'), null=True, blank=True)
    lock_until = models.DateTimeField(
        _('locked until'), null=True, blank=True,
        help_text=_('login is rejected before this time'))

    def get_absolute_url(self):
        return reverse(
            'blog:author_detail', kwargs={
                'author_name': self.username})

    def __str__(self):
        return self.email

    def get_full_url(self):
        site = get_current_site().domain
        url = "https://{site}{path}".format(site=site,
                                            path=self.get_absolute_url())
        return url

    # ------------------------------------------------------------------
    # 登录失败锁定
    # ------------------------------------------------------------------

    def is_login_locked(self, now=None) -> bool:
        """账号当前是否处于锁定期

        Args:
            now: 当前时间，默认取 timezone.now()（测试时可注入）
        """
        now = now or timezone.now()
        return bool(self.lock_until and self.lock_until > now)

    def get_lock_remaining_seconds(self, now=None) -> int:
        """剩余锁定秒数，0 表示未锁定或已解锁"""
        now = now or timezone.now()
        if not self.is_login_locked(now):
            return 0
        remaining = (self.lock_until - now).total_seconds()
        # 向上取整，避免显示 0 秒但实际仍被拒绝
        return int(remaining) + 1 if remaining > 0 else 0

    def register_login_failure(self, limit: int = 5, lock_seconds: int = 900,
                               window_seconds: int = 900, now=None) -> int:
        """记录一次登录失败，累计达到 limit 次时锁定账号

        计数窗口：如果距离上次失败已超过 window_seconds，重新计数；
        上次锁定已经过期时同样重新计数。

        Args:
            limit: 触发锁定所需的连续失败次数
            lock_seconds: 锁定时长（秒）
            window_seconds: 连续失败的计数窗口（秒）
            now: 当前时间，默认取 timezone.now()（测试时可注入）
        Returns:
            本次失败后的累计失败次数（触发锁定时等于 limit）
        """
        now = now or timezone.now()

        lock_expired = self.lock_until is not None and self.lock_until <= now
        out_of_window = (
            self.last_failed_login_at is not None
            and (now - self.last_failed_login_at).total_seconds() > window_seconds
        )
        if lock_expired or out_of_window:
            self.failed_login_count = 0
            self.lock_until = None

        self.failed_login_count = (self.failed_login_count or 0) + 1
        self.last_failed_login_at = now

        if self.failed_login_count >= limit:
            self.lock_until = now + timedelta(seconds=lock_seconds)

        self.save(update_fields=[
            'failed_login_count', 'last_failed_login_at', 'lock_until'])
        return self.failed_login_count

    def reset_login_failures(self) -> None:
        """登录成功后清空失败计数与锁定状态"""
        if not self.failed_login_count and self.lock_until is None \
                and self.last_failed_login_at is None:
            return
        self.failed_login_count = 0
        self.last_failed_login_at = None
        self.lock_until = None
        self.save(update_fields=[
            'failed_login_count', 'last_failed_login_at', 'lock_until'])

    class Meta:
        ordering = ['-id']
        verbose_name = _('user')
        verbose_name_plural = verbose_name
        get_latest_by = 'id'
