#!/usr/bin/env python
# encoding: utf-8
"""
页面缓存工具（功能点 1：全站缓存策略优化 —— 视图级缓存 + 自动刷新）
标注人：熊圆好（#xyh）

【改造前的问题】
    项目在 settings.CACHES 里已经配好了 LocMem/Redis 缓存，utils.py 里也写了
    expire_view_cache / delete_sidebar_cache 等失效函数，但真正能把「整页 HTML」
    缓存起来的两条中间件（UpdateCacheMiddleware / FetchFromCacheMiddleware）
    在 MIDDLEWARE 里是**注释掉**的，全站没有任何视图级整页缓存，
    缓存设施等于建好了却没用上。
    另外，原有失效逻辑是「手写枚举要删哪些 key」（cache.delete('index_1') 等），
    分页第 2 页及以后、分类改名后的旧列表页等场景都清不到，必然出现读到旧页的问题。

【本模块的三层改进】
    1) versioned_page_cache：视图级整页缓存装饰器，支持 CBV（TemplateResponse）；
    2) 全局版本号失效（自动刷新）：内容一变就把版本号 +1，所有历史页面 key
       瞬间失效；不需要遍历删除、不会漏 key，旧 key 交给 TTL 自然回收；
    3) 只缓存匿名用户的 GET/HEAD 响应：登录用户页面带个性化内容，一律绕过，
       避免「A 用户的登录态页面被缓存后返回给 B 用户」这类串号泄露。

【验证方式】
    curl -I http://127.0.0.1:8000/ 连续两次，观察响应头：
        第一次  X-Cache: MISS    第二次  X-Cache: HIT
    修改任意文章后再次访问，应重新变回 X-Cache: MISS（自动刷新已生效）。
"""

import logging
from functools import wraps

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse

logger = logging.getLogger(__name__)

# 页面缓存全局版本号的存放位置（永久键，不设 TTL）
CACHE_VERSION_KEY = 'site:page_cache:version'
# 未在 settings 中配置 PAGE_CACHE_TIMEOUT 时的兜底时长（秒）
DEFAULT_PAGE_CACHE_TIMEOUT = 300
# 响应头：方便在浏览器 Network 面板 / curl -I 里直接看到缓存命中情况
HEADER_CACHE = 'X-Cache'
HEADER_CACHE_VERSION = 'X-Cache-Version'


# ===== 全局版本号：自动刷新的核心 =====

def get_cache_version():
    """读取当前页面缓存版本号；首次访问时初始化为 1。"""
    version = cache.get(CACHE_VERSION_KEY)
    if version is None:
        cache.set(CACHE_VERSION_KEY, 1, None)   # xyh：None = 永不过期
        return 1
    return version


def bump_cache_version(reason=''):
    """把版本号 +1，使全部历史页面缓存失效（即“自动刷新”）。

    比逐个 cache.delete(key) 更可靠：
      - 不需要预先知道有哪些 key（分页第 N 页、分类改名后的旧页都能覆盖）；
      - 旧 key 不做删除操作，等 TTL 到期自然回收，避免一次清空造成的缓存雪崩。
    """
    try:
        version = cache.incr(CACHE_VERSION_KEY)   # xyh：原子自增，多进程下也安全
    except ValueError:   # 键不存在（首次或缓存被清空）
        version = get_cache_version() + 1
        cache.set(CACHE_VERSION_KEY, version, None)
    logger.info('页面缓存自动刷新：%s，版本号 -> %s', reason or '内容变更', version)
    return version


def invalidate_page_cache(reason=''):
    """对外语义化入口：内容变更后调用，等价于 bump_cache_version。"""
    return bump_cache_version(reason=reason)


# ===== 缓存键与装饰器 =====

def build_view_cache_key(key_prefix, request):
    """按「版本号 + 视图前缀 + 方法 + 完整路径(含查询串)」生成缓存键。

    路径里带上了查询串，因此 ?page=2 与 ?page=1、?sort=hot 等不同变体各自成键，
    不会互相覆盖。
    """
    version = get_cache_version()
    return 'page:v{}:{}:{}'.format(version, key_prefix, request.get_full_path())


def _should_bypass(request):
    """判断本次请求是否应绕过页面缓存。"""
    if not getattr(settings, 'PAGE_CACHE_ENABLED', True):
        return True
    if request.method not in ('GET', 'HEAD'):
        return True
    user = getattr(request, 'user', None)
    if user is not None and getattr(user, 'is_authenticated', False):
        # xyh：登录用户页面含“退出登录/后台入口/我的资料”等个性化内容，不缓存
        return True
    return False


def _timeout_for(timeout):
    if timeout is not None:
        return timeout
    return getattr(settings, 'PAGE_CACHE_TIMEOUT', DEFAULT_PAGE_CACHE_TIMEOUT)


def versioned_page_cache(timeout=None, key_prefix='page'):
    """视图级整页缓存装饰器（支持 FBV 与 CBV）。

    用法（CBV）：
        from django.utils.decorators import method_decorator
        from djangoblog.cache_utils import versioned_page_cache

        @method_decorator(versioned_page_cache(key_prefix='index'), name='dispatch')
        class IndexView(ListView):
            ...

    CBV 返回的是 TemplateResponse，内容要等框架调用 render() 之后才存在，
    所以命中缓存写入时通过 add_post_render_callback 延迟到渲染完成再存。
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if _should_bypass(request):
                return view_func(request, *args, **kwargs)

            cache_key = build_view_cache_key(key_prefix, request)
            payload = cache.get(cache_key)
            if payload is not None:
                response = HttpResponse(
                    payload['content'],
                    status=payload['status'],
                    content_type=payload['content_type'],
                )
                response[HEADER_CACHE] = 'HIT'
                response[HEADER_CACHE_VERSION] = str(payload['version'])
                return response

            response = view_func(request, *args, **kwargs)

            def _store(rendered):
                # xyh：只缓存成功的完整响应；流式响应（如文件下载）不缓存
                if rendered.status_code != 200:
                    return
                if getattr(rendered, 'streaming', False):
                    return
                cache.set(
                    cache_key,
                    {
                        'content': rendered.content,
                        'status': rendered.status_code,
                        'content_type': rendered.get(
                            'Content-Type', 'text/html; charset=utf-8'),
                        'version': get_cache_version(),
                    },
                    _timeout_for(timeout),
                )

            if hasattr(response, 'add_post_render_callback'):
                response.add_post_render_callback(_store)   # TemplateResponse 分支
            else:
                _store(response)                            # HttpResponse 分支

            response[HEADER_CACHE] = 'MISS'
            response[HEADER_CACHE_VERSION] = str(get_cache_version())
            return response

        return _wrapped

    return decorator


def clear_page_cache():
    """调试用：清掉版本号与全部页面缓存（后台“清空缓存”接口可复用）。"""
    cache.delete(CACHE_VERSION_KEY)
    logger.info('页面缓存已全部清空')
