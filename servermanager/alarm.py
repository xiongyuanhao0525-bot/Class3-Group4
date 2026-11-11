# -*- coding: utf-8 -*-
"""#wxy 网站异常告警邮件通道：重复报警合并 + 发送限频。

与业务邮件（注册激活 / 找回密码 / 评论通知）隔离：本模块只处理服务器异常
告警，通过 Django 缓存按「告警指纹」聚合，避免同一故障在短时间内刷屏邮件。

  - 重复报警合并（coalesce）：同一指纹在合并窗口内重复触发，不重复发信，
    只累计次数；窗口结束后的首次触发把累计次数并入汇总邮件正文。
  - 发送限频（rate limit）：同一指纹在限频窗口内最多发送 N 封，超出部分
    被抑制并累计 suppressed 计数，不再触发 SMTP。

窗口与阈值默认值取自 settings（可用 ALARM_* 环境/配置覆盖），构造告警器时
也可显式传入，便于单元测试注入内存缓存、假发信函数与可控时钟。
"""
import hashlib
import logging
import time

from django.conf import settings
from django.core.cache import cache as default_cache

logger = logging.getLogger(__name__)

# 默认窗口（秒）与限频阈值
DEFAULT_COALESCE_WINDOW = 5 * 60       # 合并窗口：5 分钟内同类告警合并
DEFAULT_RATE_LIMIT_WINDOW = 10 * 60    # 限频窗口：10 分钟
DEFAULT_MAX_PER_WINDOW = 3             # 限频窗口内同一告警最多发 3 封
CACHE_KEY_PREFIX = 'wxy:alarm:'


def _normalize(message):
    """归一化告警消息：压缩空白、统一小写，避免仅空格/大小写差异被当成不同告警。"""
    return ' '.join(str(message).split()).lower()


def _admins():
    """从 settings.ADMINS 提取收件邮箱列表；未配置时返回空列表。"""
    emails = []
    for item in getattr(settings, 'ADMINS', []) or []:
        if isinstance(item, (tuple, list)) and len(item) >= 2:
            emails.append(item[1])
    return emails


class AlarmNotifier:
    """告警邮件通知器（重复合并 + 发送限频）。

    :param coalesce_window: 合并窗口（秒），窗口内同类告警只累计不发信
    :param rate_limit_window: 限频窗口（秒）
    :param max_per_window: 限频窗口内同一指纹最大发信数
    :param cache_backend: 可注入缓存后端（需 get/set），默认 Django 缓存
    :param sender: 可注入发信函数 (emailto, title, content)，默认 send_email
    :param clock: 可注入时间函数（返回 Unix 时间戳），默认 time.time
    """

    def __init__(self, coalesce_window=None, rate_limit_window=None,
                 max_per_window=None, cache_backend=None, sender=None, clock=None):
        self.coalesce_window = (
            coalesce_window if coalesce_window is not None
            else getattr(settings, 'ALARM_COALESCE_WINDOW', DEFAULT_COALESCE_WINDOW))
        self.rate_limit_window = (
            rate_limit_window if rate_limit_window is not None
            else getattr(settings, 'ALARM_RATE_LIMIT_WINDOW', DEFAULT_RATE_LIMIT_WINDOW))
        self.max_per_window = (
            max_per_window if max_per_window is not None
            else getattr(settings, 'ALARM_MAX_PER_WINDOW', DEFAULT_MAX_PER_WINDOW))
        self._cache = cache_backend or default_cache
        self._sender = sender
        self._clock = clock or time.time

    @staticmethod
    def fingerprint(kind, message):
        """按告警类别 + 归一化消息生成稳定指纹（SHA1 摘要）。"""
        raw = f"{kind}|{_normalize(message)}"
        return hashlib.sha1(raw.encode('utf-8')).hexdigest()

    def _key(self, fingerprint):
        return CACHE_KEY_PREFIX + fingerprint

    @staticmethod
    def _within_window(state, field, window, now):
        """判断 state 中 field 记录的时间戳是否仍在窗口内。"""
        ts = state.get(field)
        return ts is not None and (now - ts) < window

    def report(self, kind, message, title=None):
        """上报一条异常告警。

        :param kind: 告警类别（如 openai_error / command_error）
        :param message: 告警详情（异常堆栈、命令等）
        :param title: 可选邮件主题，缺省按类别生成
        :return: 'sent' 已发信 / 'merged' 并入上一封 / 'suppressed' 被限频抑制
        """
        now = self._clock()
        fingerprint = self.fingerprint(kind, message)
        key = self._key(fingerprint)
        state = self._cache.get(key) or {}

        # 1) 限频：限频窗口内已达上限 -> 抑制，不再发信，仅累计 suppressed
        if self._within_window(state, 'window_start', self.rate_limit_window, now):
            if state.get('sent_in_window', 0) >= self.max_per_window:
                state['suppressed'] = state.get('suppressed', 0) + 1
                state['last_at'] = now
                self._cache.set(key, state, self.rate_limit_window)
                logger.warning("告警被限频抑制: kind=%s suppressed=%s", kind, state['suppressed'])
                return 'suppressed'

        # 2) 合并：合并窗口内已有未结算告警 -> 累加次数，不重复发信
        if self._within_window(state, 'last_at', self.coalesce_window, now):
            state['coalesce_count'] = state.get('coalesce_count', 1) + 1
            state['last_at'] = now
            # 若限频窗口已过期，重置限频计数，避免跨窗口沿用旧阈值
            if not self._within_window(state, 'window_start', self.rate_limit_window, now):
                state['window_start'] = now
                state['sent_in_window'] = 0
            self._cache.set(key, state, self.rate_limit_window)
            logger.info("重复告警已合并: kind=%s count=%s", kind, state['coalesce_count'])
            return 'merged'

        # 3) 首封或合并窗口已过期 -> 真正发信（若之前合并过，正文附累计次数）
        merged_count = state.get('coalesce_count', 0)
        self._send(kind, message, title, merged_count)

        state['coalesce_count'] = 1
        state['last_at'] = now
        if self._within_window(state, 'window_start', self.rate_limit_window, now):
            state['sent_in_window'] = state.get('sent_in_window', 0) + 1
        else:
            state['window_start'] = now
            state['sent_in_window'] = 1
        self._cache.set(key, state, self.rate_limit_window)
        return 'sent'

    def _send(self, kind, message, title, merged_count):
        """构造并发送告警邮件；告警通道自身异常不得打断主业务流程。"""
        recipients = _admins()
        if not recipients:
            logger.warning("未配置 ADMINS 收件人，告警邮件未发送: kind=%s", kind)
            return
        if title is None:
            title = f"[站点告警] {kind}"
        body_parts = [f"告警类别：{kind}", f"告警详情：{message}"]
        if merged_count > 1:
            body_parts.append(f"本窗口内同类告警累计 {merged_count} 次（已合并）")
        content = '<br/>'.join(body_parts)
        sender = self._sender
        if sender is None:
            from djangoblog.utils import send_email
            sender = send_email
        try:
            sender(recipients, title, content)
        except Exception as exc:  # noqa: BLE001 告警通道需兜底，不能二次抛错
            logger.error("告警邮件发送失败: %s", exc)


# 模块级单例，供业务代码直接调用
alarm = AlarmNotifier()


def report_alarm(kind, message, title=None):
    """便捷入口：上报一条异常告警，返回处理状态（sent/merged/suppressed）。"""
    return alarm.report(kind, message, title=title)
