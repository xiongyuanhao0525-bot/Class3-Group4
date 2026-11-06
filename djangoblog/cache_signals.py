#!/usr/bin/env python
# encoding: utf-8
"""
缓存自动刷新信号（功能点 1 的「自动刷新」部分）
标注人：熊圆好（#xyh）

【做法】
    监听内容类模型的增 / 改 / 删（含 Article 的多对多标签变更），
    统一把页面缓存全局版本号 +1，并顺带清掉侧边栏片段缓存与站点配置单例缓存。

【为什么放在独立模块里】
    原有 blog_signals.py 依赖“被 import 才注册”的隐式时机（utils.send_email 里才
    延迟导入），一旦某次启动路径没 import 到，信号就静默不生效。
    这里改成由 djangoblog/apps.py 的 ready() 显式注册，启动即生效、也可重复调用。

【为什么要排除“只更新浏览量”】
    view_count 插件每访问一次文章就写一次 views 字段。若这种保存也触发整站刷新，
    热门文章会把页面缓存刷穿（缓存永远命中不了），因此 update_fields == {'views'}
    的保存直接跳过。
"""

import logging

from django.db.models.signals import m2m_changed, post_delete, post_save

logger = logging.getLogger(__name__)

# 防止 Django 重复调用 ready() 导致同一信号注册多次
_registered = False


def _invalidate(reason):
    """执行一次“整站页面缓存失效”，并清理易被遗漏的缓存点。"""
    from django.core.cache import cache

    from djangoblog.cache_utils import invalidate_page_cache
    from djangoblog.utils import delete_sidebar_cache

    invalidate_page_cache(reason=reason)

    # xyh：侧边栏是模板片段缓存（键形如 sidebarX），不受版本号控制，需单独清
    try:
        delete_sidebar_cache()
    except Exception:   # pragma: no cover - 侧边栏清理失败不应影响主流程
        logger.warning('清理侧边栏缓存失败', exc_info=True)

    # xyh：站点配置是整行对象缓存（utils.get_blog_setting 里 set 且不设 TTL）
    cache.delete('get_blog_setting')
    cache.delete('seo_processor')


def _on_content_changed(sender, instance=None, **kwargs):
    """模型 post_save / post_delete 统一处理。"""
    # 只更新浏览量的保存不触发整站刷新，避免热门文章把缓存刷穿
    update_fields = kwargs.get('update_fields')
    if update_fields and set(update_fields) == {'views'}:
        return

    model_name = sender.__name__ if sender is not None else 'unknown'
    # xyh：post_save / post_delete 都会把自身作为 signal 关键字传入，据此区分动作
    kind = '删除' if kwargs.get('signal') is post_delete else '保存'
    _invalidate('{} {}'.format(model_name, kind))


def _on_m2m_changed(sender, instance=None, action=None, **kwargs):
    """文章标签等多对多关系变化（增/删/清空）同样需要刷新页面缓存。"""
    if action in ('post_add', 'post_remove', 'post_clear'):
        _invalidate('{} 标签关系变更({})'.format(
            type(instance).__name__ if instance is not None else 'unknown', action))


def register_cache_invalidation():
    """把缓存自动刷新信号挂到内容模型上（幂等，可重复调用）。"""
    global _registered
    if _registered:
        return

    # xyh：延迟导入，避免 app 加载阶段与 models 循环依赖
    from blog.models import (Article, BlogSettings, Category, Links, SideBar,
                             Tag)
    from comments.models import Comment

    watched_models = (Article, Comment, Category, Tag,
                      BlogSettings, Links, SideBar)

    for model in watched_models:
        name = model.__name__
        post_save.connect(
            _on_content_changed,
            sender=model,
            dispatch_uid='xyh_cache_save_{}'.format(name),
            weak=False,
        )
        post_delete.connect(
            _on_content_changed,
            sender=model,
            dispatch_uid='xyh_cache_delete_{}'.format(name),
            weak=False,
        )

    # xyh：Article.tags 是 M2M，改标签不产生 post_save，需要单独监听 m2m_changed
    m2m_changed.connect(
        _on_m2m_changed,
        sender=Article.tags.through,
        dispatch_uid='xyh_cache_m2m_article_tags',
        weak=False,
    )

    _registered = True
    logger.info('页面缓存自动刷新信号已注册（监听 %s 个内容模型）',
                len(watched_models))
