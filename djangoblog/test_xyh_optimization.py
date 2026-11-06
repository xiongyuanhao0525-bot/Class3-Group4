#!/usr/bin/env python
# encoding: utf-8
"""
熊圆好（#xyh）第 9-10 周功能点单元测试

覆盖本次三个功能点：
    任务 1-1  全站缓存策略优化（视图级缓存 + 自动刷新）
    任务 1-2  安全加固（SECURE_* 响应头 + 敏感接口访问限流）
    任务 1-3  列表查询性能（select_related / prefetch_related / defer 消除 N+1）

运行方式（无需本地 MySQL，使用 SQLite 内存库）：
    python manage.py test djangoblog.test_xyh_optimization --settings=djangoblog.test_settings -v 2
"""

from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext

from djangoblog.cache_utils import (bump_cache_version, get_cache_version,
                                    invalidate_page_cache)
from djangoblog.rate_limit import (get_client_ip, match_rule, normalize_path)
from djangoblog.test_base import BaseTestCase


# ============================================================
# 一、功能点 1：页面缓存（视图级缓存 + 自动刷新）
# ============================================================

@override_settings(PAGE_CACHE_ENABLED=True)
class PageCacheTest(BaseTestCase):
    """页面缓存核心行为：首次 MISS、二次 HIT、内容变更后自动刷新。"""

    def setUp(self):
        super().setUp()
        cache.clear()   # 每个用例从干净缓存开始，避免相互影响

    def test_first_request_miss_second_request_hit(self):
        """第一次访问回源（MISS），第二次直接命中缓存（HIT），且内容一致。"""
        first = self.client.get('/')
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.headers.get('X-Cache'), 'MISS')

        second = self.client.get('/')
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.headers.get('X-Cache'), 'HIT')
        self.assertEqual(first.content, second.content)

    def test_cache_version_header_present(self):
        """响应头里能读到当前缓存版本号，便于排查“看到的是哪一代缓存”。"""
        response = self.client.get('/')
        self.assertIn('X-Cache-Version', response.headers)
        self.assertEqual(
            int(response.headers['X-Cache-Version']), get_cache_version())

    def test_new_article_triggers_auto_refresh(self):
        """新建文章后，旧首页缓存自动失效——这是“自动刷新”最关键的行为。"""
        self.client.get('/')
        self.assertEqual(self.client.get('/').headers.get('X-Cache'), 'HIT')

        self.create_article(title='自动刷新验证文章')

        refreshed = self.client.get('/')
        self.assertEqual(refreshed.headers.get('X-Cache'), 'MISS',
                         '文章变更后首页缓存未自动刷新')

    def test_comment_save_triggers_auto_refresh(self):
        """评论保存同样触发刷新（评论数会显示在页面上）。"""
        self.client.get('/')
        self.assertEqual(self.client.get('/').headers.get('X-Cache'), 'HIT')

        self.create_comment(article=self.article)

        self.assertEqual(self.client.get('/').headers.get('X-Cache'), 'MISS')

    def test_manual_bump_invalidates_all_pages(self):
        """手动/全局刷新：版本号 +1 后所有页面缓存失效。"""
        self.client.get('/')
        self.client.get('/')
        old_version = get_cache_version()

        new_version = bump_cache_version(reason='单元测试手动刷新')
        self.assertEqual(new_version, old_version + 1)

        self.assertEqual(self.client.get('/').headers.get('X-Cache'), 'MISS')

    def test_update_views_only_does_not_bump_version(self):
        """只更新浏览量的保存不应触发整站刷新（否则热门文章会把缓存刷穿）。"""
        from django.db.models.signals import post_save

        from djangoblog.cache_signals import _on_content_changed

        version = get_cache_version()
        _on_content_changed(
            sender=type(self.article), instance=self.article,
            update_fields={'views'}, signal=post_save)
        self.assertEqual(get_cache_version(), version)

    def test_authenticated_user_bypasses_page_cache(self):
        """登录用户的页面含个性化内容，必须绕过页面缓存，避免串号泄露。"""
        self.assertTrue(self.login_user())
        response = self.client.get('/')
        self.assertNotIn('X-Cache', response.headers)

    def test_pagination_pages_are_cached_separately(self):
        """?page=1 与 ?page=2 各自成键，互不覆盖。"""
        for index in range(12):   # 每页 10 条，制造出第 2 页
            self.create_article(title='分页文章{}'.format(index))

        page1 = self.client.get('/')
        page2 = self.client.get('/page/2/')
        self.assertEqual(page1.headers.get('X-Cache'), 'MISS')
        self.assertEqual(page2.headers.get('X-Cache'), 'MISS')
        # 再取一次都应命中
        self.assertEqual(self.client.get('/').headers.get('X-Cache'), 'HIT')
        self.assertEqual(
            self.client.get('/page/2/').headers.get('X-Cache'), 'HIT')

    def test_get_view_cache_key_no_attribute_error(self):
        """回归测试：原实现 self.request.get['pages'] 必然抛 AttributeError。"""
        from blog.views import ArticleListView

        view = ArticleListView()
        view.request = self.factory.get('/')
        key = view.get_view_cache_key()
        self.assertIsInstance(key, str)
        self.assertTrue(key.startswith('page:v'))

    def test_page_cache_can_be_disabled_by_settings(self):
        """总开关关闭时不写任何缓存响应头（测试/排障时使用）。"""
        with override_settings(PAGE_CACHE_ENABLED=False):
            response = self.client.get('/')
        self.assertNotIn('X-Cache', response.headers)


# ============================================================
# 二、功能点 2-A：访问限流中间件
# ============================================================

@override_settings(RATE_LIMIT_ENABLED=True, RATE_LIMIT_RULES={'login/': (2, 60)})
class RateLimitTest(BaseTestCase):
    """敏感接口限流：达到阈值返回 429，并给出标准限流响应头。"""

    def setUp(self):
        super().setUp()
        cache.clear()   # 清掉其他用例残留的计数

    def test_requests_under_limit_pass_with_headers(self):
        """未超限的请求正常放行，并通过响应头告知剩余额度。"""
        response = self.client.get('/login/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['X-RateLimit-Limit'], '2')
        self.assertEqual(response.headers['X-RateLimit-Remaining'], '1')

    def test_exceed_limit_returns_429(self):
        """超过阈值的请求返回 429，且带 Retry-After。"""
        self.assertEqual(self.client.get('/login/').status_code, 200)
        self.assertEqual(self.client.get('/login/').status_code, 200)

        blocked = self.client.get('/login/')
        self.assertEqual(blocked.status_code, 429)
        self.assertIn('Retry-After', blocked.headers)
        self.assertGreater(int(blocked.headers['Retry-After']), 0)
        self.assertEqual(blocked.headers['X-RateLimit-Remaining'], '0')

    def test_other_paths_not_limited(self):
        """未登记规则的接口不受影响（避免误伤正常浏览）。"""
        for _ in range(8):
            response = self.client.get('/health/')
            self.assertNotEqual(response.status_code, 429)

    def test_i18n_prefix_shares_same_counter(self):
        """/en/login/ 与 /login/ 归一化到同一接口，共用同一个计数。"""
        self.client.get('/login/')
        self.client.get('/en/login/')
        self.assertEqual(self.client.get('/login/').status_code, 429)

    def test_different_clients_counted_separately(self):
        """不同 IP 各自计数，一个 IP 被限流不影响其他 IP。"""
        self.client.get('/login/', REMOTE_ADDR='10.0.0.1')
        self.client.get('/login/', REMOTE_ADDR='10.0.0.1')
        self.assertEqual(
            self.client.get('/login/', REMOTE_ADDR='10.0.0.1').status_code, 429)
        self.assertEqual(
            self.client.get('/login/', REMOTE_ADDR='10.0.0.2').status_code, 200)


class RateLimitUnitTest(BaseTestCase):
    """限流组件的纯函数单测。"""

    def test_normalize_path_strips_language_prefix(self):
        self.assertEqual(normalize_path('/login/'), '/login/')
        self.assertEqual(normalize_path('/en/login/'), '/login/')
        self.assertEqual(normalize_path('/zh-hans/login/'), '/login/')
        self.assertEqual(normalize_path('/zh-hant/forget_password/'),
                         '/forget_password/')

    @override_settings(RATE_LIMIT_RULES={
        'login/': (10, 60),
        'forget_password/': (5, 300),
        'forget_password_code/': (3, 300),
    })
    def test_match_rule_prefers_longest_suffix(self):
        """forget_password_code/ 必须优先于 forget_password/ 命中。"""
        matched = match_rule('/login/')
        self.assertEqual(matched, ('login/', 10, 60))

        matched = match_rule('/forget_password_code/')
        self.assertEqual(matched, ('forget_password_code/', 3, 300))

        self.assertIsNone(match_rule('/'))

    def test_x_forwarded_for_not_trusted_by_default(self):
        """默认不信任 X-Forwarded-For（可被客户端伪造）。"""
        request = self.factory.get(
            '/login/', REMOTE_ADDR='1.2.3.4', HTTP_X_FORWARDED_FOR='9.9.9.9')
        self.assertEqual(get_client_ip(request), '1.2.3.4')

    @override_settings(RATE_LIMIT_TRUST_X_FORWARDED_FOR=True)
    def test_x_forwarded_for_trusted_when_configured(self):
        """部署在可信代理后面时才采信 X-Forwarded-For。"""
        request = self.factory.get(
            '/login/', REMOTE_ADDR='1.2.3.4',
            HTTP_X_FORWARDED_FOR='9.9.9.9, 8.8.8.8')
        self.assertEqual(get_client_ip(request), '9.9.9.9')


# ============================================================
# 三、功能点 2-B：安全配置与安全响应头
# ============================================================

class SecurityHardeningTest(BaseTestCase):
    """安全配置项与浏览器侧安全响应头。"""

    def test_security_settings_are_hardened(self):
        self.assertTrue(settings.SECURE_CONTENT_TYPE_NOSNIFF)
        self.assertTrue(settings.SESSION_COOKIE_HTTPONLY)
        self.assertEqual(settings.SECURE_REFERRER_POLICY,
                         'strict-origin-when-cross-origin')
        self.assertEqual(settings.SECURE_CROSS_ORIGIN_OPENER_POLICY,
                         'same-origin')
        self.assertEqual(settings.X_FRAME_OPTIONS, 'SAMEORIGIN')

    def test_csrf_cookie_kept_readable_for_frontend(self):
        """CSRF Cookie 必须保持 JS 可读，否则评论/表情接口会全部 403。

        frontend/js/commentSystem.js 需要从 cookie 读取 csrftoken 放进请求头，
        所以这里的期望值就是 False —— 这是有意为之，不是漏配。
        """
        self.assertFalse(settings.CSRF_COOKIE_HTTPONLY)

    def test_security_headers_sent_in_response(self):
        response = self.client.get('/health/')
        self.assertEqual(response.headers['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(response.headers['X-Frame-Options'], 'SAMEORIGIN')
        self.assertEqual(response.headers['Referrer-Policy'],
                         'strict-origin-when-cross-origin')
        self.assertEqual(response.headers['Cross-Origin-Opener-Policy'],
                         'same-origin')


# ============================================================
# 四、功能点 3：查询优化（消除 N+1）
# ============================================================

class QueryOptimizationTest(BaseTestCase):
    """验证列表/详情查询的 SQL 条数不随数据量增长（N+1 已消除）。"""

    def setUp(self):
        super().setUp()
        cache.clear()   # 清掉 queryset 缓存，否则第二次请求会直接读缓存测不出 SQL

    def _count_queries(self, url):
        cache.clear()
        with CaptureQueriesContext(connection) as context:
            response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        return len(context.captured_queries)

    def test_index_query_count_does_not_grow_with_articles(self):
        """首页 SQL 条数不随文章数量增长。"""
        baseline = self._count_queries('/')

        for index in range(6):
            self.create_article(title='N+1验证文章{}'.format(index))

        after = self._count_queries('/')
        self.assertLessEqual(
            after, baseline + 1,
            '文章数增加后首页 SQL 条数明显变多（{} → {}），存在 N+1'.format(
                baseline, after))

    def test_detail_queryset_relation_access_is_constant(self):
        """详情页 queryset 访问 标签/分类/作者/评论数 时的 SQL 条数固定，不随标签增长。

        说明：整页 SQL 条数里还包含 article_recommendation 插件的推荐查询（与本功能点
        无关、非 N+1），所以这里直接对「详情页 queryset」做断言，测的是本功能点本身。
        """
        from blog.views import ArticleDetailView

        for index in range(6):
            self.article.tags.add(self.create_tag(name='预加载标签{}'.format(index)))

        queryset = ArticleDetailView().get_queryset()
        with CaptureQueriesContext(connection) as context:
            article = queryset.get(pk=self.article.pk)
            list(article.tags.all())      # 触发标签关联
            article.category.name         # 触发分类关联
            article.author.username       # 触发作者关联
            article.comment_set.count()   # 触发评论计数

        # 预加载生效时：主查询 1 + tags 1 + comments 1 = 3 条；
        # 若未预加载，6 个标签会额外产生 1(标签关系)+6(标签)+1(分类)+1(作者)+1(评论) 条。
        self.assertLessEqual(
            len(context.captured_queries), 5,
            '详情页关联访问 SQL 条数偏多（{}），预加载未生效'.format(
                len(context.captured_queries)))

    def test_list_queryset_prefetches_comment_set(self):
        """列表查询应预加载评论关联，消除卡片上 comment_set.count 的 N+1。"""
        from djangoblog.mixins import OptimizedArticleQueryMixin

        class DummyView(OptimizedArticleQueryMixin):
            pass

        queryset = DummyView().get_optimized_article_queryset()
        prefetch_lookups = [
            getattr(item, 'prefetch_to', item)
            for item in queryset._prefetch_related_lookups
        ]
        self.assertIn('tags', prefetch_lookups)
        self.assertIn('comment_set', prefetch_lookups)

    def test_list_queryset_preloads_relations(self):
        """列表查询应预加载 author / category / tags。"""
        from djangoblog.mixins import OptimizedArticleQueryMixin

        class DummyView(OptimizedArticleQueryMixin):
            pass

        queryset = DummyView().get_optimized_article_queryset()
        self.assertIn('author', queryset.query.select_related)
        self.assertIn('category', queryset.query.select_related)
        self.assertIn('tags', queryset._prefetch_related_lookups)

    def test_detail_queryset_preloads_relations(self):
        """详情页查询应预加载 author / category / tags。"""
        from blog.views import ArticleDetailView

        queryset = ArticleDetailView().get_queryset()
        self.assertIn('author', queryset.query.select_related)
        self.assertIn('category', queryset.query.select_related)
        self.assertIn('tags', queryset._prefetch_related_lookups)


# ============================================================
# 五、测试基础设施自检：测试配置能脱离 MySQL 独立运行
# ============================================================

class TestSettingsTest(BaseTestCase):
    """确认 djangoblog/test_settings.py 生效（组员无需本地 MySQL 即可跑测试）。"""

    def test_uses_sqlite_in_test_mode(self):
        self.assertEqual(settings.DATABASES['default']['ENGINE'],
                         'django.db.backends.sqlite3')

    def test_expensive_features_disabled_by_default_in_tests(self):
        self.assertFalse(settings.PAGE_CACHE_ENABLED)
        self.assertFalse(settings.RATE_LIMIT_ENABLED)
        self.assertTrue(settings.TESTING)

    def test_base_case_fixtures_created(self):
        self.assertIsNotNone(self.user)
        self.assertIsNotNone(self.article)
        self.assertEqual(
            self.article.__class__.objects.filter(pk=self.article.pk).count(), 1)
