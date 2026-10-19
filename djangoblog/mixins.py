#!/usr/bin/env python
# encoding: utf-8

"""
Django Blog 混入类 (Mixins)
提供可复用的功能模块，减少代码重复
"""

# xyh：模块级说明 —— 可复用的 Mixin 工具箱，分模型层与视图层两组：
# xyh：  模型层：TimeStampedModel（抽象基类，统一 created_at/updated_at 时间戳）；
# xyh：  视图层：SlugCachedMixin（slug 查询结果请求内缓存）、OptimizedArticleQueryMixin
# xyh：    （select_related/prefetch_related 防 N+1）、CachedListViewMixin（ListView 结果缓存）、
# xyh：    PageNumberMixin（页码解析）、ArticleListMixin（前四者组合，文章列表视图一键继承）。
# xyh：设计意图：把跨视图/跨模型的横切逻辑沉到 Mixin，业务 View 只声明差异部分，
# xyh：体现 Django"组合优先于继承"的视图组织方式（blog/views.py 直接组合使用）。

import logging
from django.db import models
from django.shortcuts import get_object_or_404
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


# ===== 模型层 Mixin =====
# xyh：模型层 Mixin（抽象基类）——继承后自动获得字段与行为，不额外建表

# xyh：时间戳抽象模型：created_at + updated_at 两个字段一次配齐，子类无需重复声明
class TimeStampedModel(models.Model):
    """
    抽象模型：为所有模型提供统一的时间戳字段

    提供 created_at 和 updated_at 字段，自动管理时间戳
    继承此模型可以消除重复的时间字段定义

    Usage:
        class MyModel(TimeStampedModel):
            name = models.CharField(max_length=100)
    """
    # xyh：创建时间——默认取当前时间，建索引支持按时间排序/范围过滤
    created_at = models.DateTimeField(
        _('creation time'),
        default=now,
        db_index=True,
        help_text=_('The date and time when this object was created')
    )
    # xyh：最后修改时间——无索引（更新频繁，索引维护成本高）
    updated_at = models.DateTimeField(
        _('last modify time'),
        default=now,
        help_text=_('The date and time when this object was last modified')
    )

    class Meta:
        abstract = True   # xyh：抽象基类——不生成独立数据表，字段下发给子类
        ordering = ['-created_at']   # xyh：默认按创建时间倒序（最新在前）
        get_latest_by = 'created_at'  # xyh：latest()/earliest() 的排序依据

    # xyh：重写 save：把 updated_at 刷新为当前时间；若指定了 update_fields 且未含该字段则补上
    def save(self, *args, **kwargs):
        """
        重写 save 方法，自动更新 updated_at 字段

        注意：如果使用 update_fields 参数，需要明确包含 updated_at
        """
        # 检查是否是部分更新（指定了 update_fields）
        update_fields = kwargs.get('update_fields')
        if update_fields:
            # 如果指定了 update_fields 但不包含 updated_at，则添加它
            if 'updated_at' not in update_fields:
                update_fields = list(update_fields) + ['updated_at']
                kwargs['update_fields'] = update_fields

        # 更新时间戳
        self.updated_at = now()

        super().save(*args, **kwargs)


# ===== 视图层 Mixin =====
# xyh：视图层 Mixin —— 供 CBV 多继承组合，各自解决一类横切问题

# xyh：slug 查询缓存：同一请求内反复取同一 slug 对象只查库一次（典型：详情页多次取分类）
class SlugCachedMixin:
    """
    Mixin: 缓存 slug 查询结果，避免重复数据库查询

    在同一个请求周期内，多次获取同一个 slug 对应的对象时，
    只会执行一次数据库查询，后续调用会使用缓存的对象

    Attributes:
        slug_url_kwarg: URL 参数名，默认为 'slug'
        slug_model: 要查询的模型类

    Usage:
        class MyView(SlugCachedMixin, ListView):
            slug_url_kwarg = 'category_slug'
            slug_model = Category

            def get_queryset(self):
                category = self.get_slug_object()
                return Article.objects.filter(category=category)
    """
    slug_url_kwarg = 'slug'   # xyh：URL 中 slug 参数的键名（可从 kwargs 取出）
    slug_model = None          # xyh：子类必须指定的模型类（None 时调用即抛错）

    def get_slug_object(self):
        """
        获取并缓存 slug 对应的对象

        Returns:
            Model instance: slug 对应的模型实例

        Raises:
            Http404: 如果 slug 对应的对象不存在
        """
        if not hasattr(self, '_slug_object'):   # xyh：以实例属性做请求内缓存标志
            if self.slug_model is None:
                raise ValueError(
                    f'{self.__class__.__name__} must define slug_model attribute'
                )

            slug = self.kwargs.get(self.slug_url_kwarg)
            self._slug_object = get_object_or_404(self.slug_model, slug=slug)  # xyh：不存在对象直接抛 404
            logger.debug(
                f'Loaded {self.slug_model.__name__} object: {self._slug_object} (slug={slug})'
            )

        return self._slug_object


# xyh：文章查询优化：预加载外键与多对多关联，避免列表页 N+1 查询
class OptimizedArticleQueryMixin:
    """
    Mixin: 优化文章查询（预加载关联对象）

    使用 select_related 和 prefetch_related 优化文章查询，
    减少数据库查询次数，避免 N+1 查询问题

    Usage:
        class MyView(OptimizedArticleQueryMixin, ListView):
            def get_queryset(self):
                return self.get_optimized_article_queryset().filter(status='p')
    """

    def get_optimized_article_queryset(self):
        """
        返回优化后的 Article queryset

        使用 select_related 预加载外键关联：
            - author: 文章作者
            - category: 文章分类

        使用 prefetch_related 预加载多对多关联：
            - tags: 文章标签

        Returns:
            QuerySet: 优化后的 Article queryset
        """
        from blog.models import Article   # xyh：函数内导入避免模块级循环依赖

        return Article.objects.select_related(
            'author',      # 预加载作者（ForeignKey）
            'category'     # 预加载分类（ForeignKey）
        ).prefetch_related(
            'tags'         # 预加载标签（ManyToMany）
        )


# xyh：ListView 结果缓存：按子类提供的键缓存整个 queryset，命中即省掉数据库查询
class CachedListViewMixin:
    """
    Mixin: 为 ListView 提供统一的缓存逻辑

    自动缓存 queryset 结果，减少数据库查询
    子类需要实现 get_queryset_cache_key() 和 get_queryset_data() 方法

    Usage:
        class MyView(CachedListViewMixin, ListView):
            def get_queryset_cache_key(self):
                return f'my_list_{self.page_number}'

            def get_queryset_data(self):
                return Article.objects.filter(status='p')
    """

    def get_queryset_cache_key(self):
        """
        子类实现：返回缓存 key

        Returns:
            str: 缓存键

        Raises:
            NotImplementedError: 子类必须实现此方法
        """
        raise NotImplementedError(
            f'{self.__class__.__name__} must implement get_queryset_cache_key()'
        )

    def get_queryset_data(self):
        """
        子类实现：返回实际数据

        Returns:
            QuerySet: 要缓存的 queryset

        Raises:
            NotImplementedError: 子类必须实现此方法
        """
        raise NotImplementedError(
            f'{self.__class__.__name__} must implement get_queryset_data()'
        )

    def get_queryset_from_cache(self, cache_key):
        """
        从缓存获取 queryset，如果缓存不存在则查询并缓存

        Args:
            cache_key: 缓存键

        Returns:
            QuerySet: 查询结果
        """
        from djangoblog.utils import cache   # xyh：延迟导入复用全局缓存实例（LocMem/Redis 由 settings 决定）

        value = cache.get(cache_key)
        if value:
            logger.info(f'Cache HIT: {cache_key}')
            return value

        queryset = self.get_queryset_data()   # xyh：未命中则真正查库
        cache.set(cache_key, queryset)        # xyh：默认 TTL（LocMem 配置 10800s）；失效由 signals 中清键逻辑负责
        logger.info(f'Cache MISS: {cache_key}')
        return queryset

    def get_queryset(self):
        """
        重写 get_queryset，使用缓存

        Returns:
            QuerySet: 查询结果（从缓存或数据库）
        """
        key = self.get_queryset_cache_key()   # xyh：缓存键由子类按场景拼出（含页码/名称等）
        return self.get_queryset_from_cache(key)


# xyh：页码解析：优先 URL kwargs，其次 GET 参数，非法/缺失一律回退第 1 页
class PageNumberMixin:
    """
    Mixin: 提供页码获取功能

    从 URL 参数或 GET 参数中获取当前页码

    Usage:
        class MyView(PageNumberMixin, ListView):
            def get_queryset_cache_key(self):
                return f'list_{self.page_number}'
    """
    page_kwarg = 'page'   # xyh：页码参数名（可被子类覆盖）

    @property   # xyh：只读属性，供上方 get_queryset_cache_key 之类直接引用
    def page_number(self):
        """
        获取当前页码

        从 URL kwargs 或 GET 参数中获取页码，默认为 1

        Returns:
            int: 当前页码
        """
        page = self.kwargs.get(self.page_kwarg) or \
               self.request.GET.get(self.page_kwarg) or 1   # xyh：URL 优先于查询串，均缺省用 1

        try:
            return int(page)
        except (ValueError, TypeError):
            return 1   # xyh：非数字页码（如 ?page=abc）容错回第 1 页，避免 500


# xyh：组合型 Mixin —— 一继承即具备"优化查询 + 缓存 + 页码"三项能力，文章列表视图复用
class ArticleListMixin(
    OptimizedArticleQueryMixin,
    CachedListViewMixin,
    PageNumberMixin
):
    """
    Mixin: 组合多个 Mixin，提供完整的文章列表功能

    继承此 Mixin 的视图自动具备：
    - 优化的文章查询
    - 缓存支持
    - 页码处理

    Usage:
        class MyArticleListView(ArticleListMixin, ListView):
            def get_queryset_data(self):
                return self.get_optimized_article_queryset().filter(status='p')

            def get_queryset_cache_key(self):
                return f'my_list_{self.page_number}'
    """
    pass   # xyh：本身无实现，靠 MRO 继承三个父 Mixin 的方法（blog/views.py 的 ArticleListView 即组合使用）
