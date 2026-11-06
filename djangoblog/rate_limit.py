#!/usr/bin/env python
# encoding: utf-8
"""
访问限流中间件（功能点 2：安全加固）
标注人：熊圆好（#xyh）

【改造前的问题】
    项目原有的安全防护都是“被动防御”：CSRF 中间件、点击劫持 X-Frame-Options、
    密码强度校验器、XSS 白名单清洗。但登录 / 注册 / 找回密码验证码这几个
    “可以被脚本反复刷”的入口没有任何频率限制——
      · 登录：可以无限次撞库（撞库成功一次就拿到账号）；
      · 注册：可以被批量刷垃圾账号；
      · 找回密码验证码接口：可以被无限调用，把邮箱额度刷爆、骚扰真实用户。
    这类“主动滥用”是 CSRF 之类机制拦不住的。

【本中间件的做法】
    按「客户端 IP + 接口」做固定窗口计数限流，超过阈值直接返回 429
    （Too Many Requests）并给出 Retry-After，同时通过 X-RateLimit-* 响应头
    告诉正常用户还剩多少次。
    计数落在 Django cache 里：单机 LocMem 够用；接 Redis 后多进程/多机共享同一计数。

【设计取舍】
    · 只对 settings.RATE_LIMIT_RULES 里登记的敏感接口限流，不搞全站限流，
      避免正常浏览用户被误伤；
    · 默认不信任 X-Forwarded-For（该头可被客户端伪造），只有部署在可信反向
      代理后面时才通过 DJANGO_RATE_LIMIT_TRUST_XFF=True 打开；
    · i18n 语言前缀（/en/login/）会先被剥离再匹配规则，保证中英文入口共用一份限流。
"""

import logging

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse

logger = logging.getLogger(__name__)

# 缓存键模板：ratelimit:<接口标识>:<客户端 IP>
CACHE_KEY_TEMPLATE = 'ratelimit:{}:{}'

# 超限返回的状态码与提示文案
TOO_MANY_REQUESTS = 429
TOO_MANY_REQUESTS_MESSAGE = '请求过于频繁，请稍后再试。'
# 响应头常量（对外暴露限流状态，方便前端/运维排查）
HEADER_LIMIT = 'X-RateLimit-Limit'
HEADER_REMAINING = 'X-RateLimit-Remaining'
HEADER_RESET = 'X-RateLimit-Reset'
HEADER_RETRY_AFTER = 'Retry-After'


def _language_prefixes():
    """取项目支持的语言代码集合（用于剥离 /en/、/zh-hans/ 之类前缀）。"""
    languages = getattr(settings, 'LANGUAGES', ()) or ()
    return {code.lower() for code, _name in languages}


def normalize_path(path):
    """剥离 i18n 语言前缀：/en/login/ 归一化为 /login/。

    注意保留结尾斜杠 —— 限流规则以 'login/' 这类带斜杠的后缀登记，
    若归一化时把尾斜杠吃掉（/login/ → /login），规则就永远匹配不上。
    """
    trailing_slash = path.endswith('/')
    parts = [segment for segment in path.strip('/').split('/') if segment]
    if not parts:
        return '/'
    if parts[0].lower() in _language_prefixes():
        parts = parts[1:]
    normalized = '/' + '/'.join(parts)
    if trailing_slash and not normalized.endswith('/'):
        normalized += '/'
    return normalized


def get_client_ip(request):
    """取客户端标识。

    默认用 REMOTE_ADDR（服务端看到的真实对端地址，客户端无法伪造）。
    只有显式配置 RATE_LIMIT_TRUST_X_FORWARDED_FOR=True（部署在可信反向代理后）时，
    才采信 X-Forwarded-For 的第一段。
    """
    if getattr(settings, 'RATE_LIMIT_TRUST_X_FORWARDED_FOR', False):
        forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
        if forwarded:
            return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR') or 'unknown'


def match_rule(path):
    """按「路径后缀」匹配限流规则，返回 (接口标识, 次数上限, 窗口秒数) 或 None。

    用后缀匹配而不是全等匹配，是为了兼容 i18n 前缀与可能的子路径挂载；
    规则按后缀长度从长到短匹配，保证 forget_password_code/ 优先于 forget_password/。
    """
    rules = getattr(settings, 'RATE_LIMIT_RULES', None) or {}
    for suffix in sorted(rules, key=len, reverse=True):
        if path.endswith(suffix):
            limit, window = rules[suffix]
            return suffix, int(limit), int(window)
    return None


def _current_ttl(cache_key, default_window):
    """取当前计数键的剩余 TTL，用于拼 Retry-After / X-RateLimit-Reset。"""
    try:
        ttl = cache.ttl(cache_key)
    except Exception:   # pragma: no cover - 少数自定义缓存后端不支持 ttl()
        ttl = None
    if not ttl or ttl < 0:
        return default_window
    return int(ttl)


class RateLimitMiddleware:
    """基于「客户端 IP + 接口」的固定窗口访问限流中间件。"""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # 总开关：测试环境默认关闭（见 settings.RATE_LIMIT_ENABLED），避免干扰其他 app 的用例
        if not getattr(settings, 'RATE_LIMIT_ENABLED', True):
            return self.get_response(request)

        path = normalize_path(request.path_info)
        matched = match_rule(path)
        if matched is None:   # 非敏感接口直接放行，不影响正常浏览
            return self.get_response(request)

        scope, limit, window = matched
        client = get_client_ip(request)
        cache_key = CACHE_KEY_TEMPLATE.format(scope, client)

        count = cache.get(cache_key, 0) or 0

        # ① 已超限：不执行业务逻辑，直接拒绝
        if count >= limit:
            retry_after = _current_ttl(cache_key, window)
            logger.warning(
                '触发限流：path=%s ip=%s 已请求 %s 次 / 上限 %s 次 / %s 秒',
                path, client, count, limit, window)
            response = HttpResponse(
                TOO_MANY_REQUESTS_MESSAGE,
                status=TOO_MANY_REQUESTS,
                content_type='text/plain; charset=utf-8',
            )
            response[HEADER_RETRY_AFTER] = str(retry_after)
            response[HEADER_LIMIT] = str(limit)
            response[HEADER_REMAINING] = '0'
            response[HEADER_RESET] = str(retry_after)
            return response

        # ② 未超限：计数 +1（cache.add 成功说明是本窗口第一次）
        if cache.add(cache_key, 1, window):
            count = 1
        else:
            try:
                count = cache.incr(cache_key)
            except ValueError:   # 键刚好过期，重置计数
                cache.set(cache_key, 1, window)
                count = 1

        response = self.get_response(request)

        # ③ 把限流状态通过响应头告诉调用方
        response[HEADER_LIMIT] = str(limit)
        response[HEADER_REMAINING] = str(max(0, limit - count))
        response[HEADER_RESET] = str(_current_ttl(cache_key, window))
        return response
