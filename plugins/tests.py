# -*- coding: utf-8 -*-
"""#wxy plugins 模块功能测试。

覆盖本轮两个插件的新增功能：
  - image_lazy_loading：占位图（data-src + 骨架占位）与加载失败兜底；
  - seo_optimizer：Twitter/X 卡片标签与 sitemap 入口链接。

plugins 不是 Django INSTALLED_APPS，可通过显式标签运行：
    python manage.py test plugins.tests
"""
from types import SimpleNamespace
from unittest.mock import patch

from django.test import RequestFactory, TestCase

from accounts.models import BlogUser
from blog.models import Article, Category
from plugins.image_lazy_loading.plugin import plugin as image_plugin
from plugins.seo_optimizer.plugin import SeoOptimizerPlugin


class ImageLazyLoadingPluginTest(TestCase):
    """图片懒加载占位图 + 失败兜底。"""

    def setUp(self):
        self.factory = RequestFactory()
        # 保存单例原始配置，避免用例间互相污染
        self._original_config = dict(image_plugin.config)

    def tearDown(self):
        image_plugin.config = self._original_config

    def test_second_image_gets_placeholder_and_fallback(self):
        html = (
            '<p><img src="/media/first.png" alt="首图"></p>'
            '<p><img src="/media/second.png"></p>'
        )
        out = image_plugin.optimize_images(html)

        # 第二张（非首图）：真实地址进 data-src，src 换骨架占位，带兜底
        self.assertIn('data-src="/media/second.png"', out)
        self.assertIn('lazy-img', out)
        self.assertIn('data-fallback=', out)
        self.assertIn('onerror=', out)
        # 占位图为内联 SVG data URI
        self.assertIn('data:image/svg+xml', out)

    def test_first_image_keeps_real_src_for_lcp(self):
        html = '<p><img src="/media/first.png" alt="首图"></p>'
        out = image_plugin.optimize_images(html)

        # 首图作为 LCP 资源保持真实 src，不做 data-src 占位
        self.assertIn('src="/media/first.png"', out)
        self.assertNotIn('data-src=', out)
        self.assertIn('fetchpriority="high"', out)

    def test_placeholder_disabled_keeps_real_src(self):
        image_plugin.config['add_loading_placeholder'] = False
        html = '<p><img src="/media/second.png"></p>'
        out = image_plugin.optimize_images(html)

        self.assertNotIn('data-src=', out)
        self.assertIn('src="/media/second.png"', out)

    def test_js_files_registered(self):
        self.assertEqual(image_plugin.get_js_files(), ['js/lazyload.js'])


class SeoOptimizerPluginTest(TestCase):
    """SEO 插件：Twitter 卡片标签 + sitemap 入口。"""

    def setUp(self):
        self.factory = RequestFactory()
        self.seo = SeoOptimizerPlugin()
        self.blog_setting = SimpleNamespace(
            site_name='测试站点', site_description='这是一个测试站点描述')

    def _make_article(self):
        user = BlogUser.objects.create_superuser(
            email='seo@example.com', username='seouser', password='seo12345')
        category = Category.objects.create(name='测试分类')
        article = Article.objects.create(
            title='SEO 测试文章',
            body='正文内容，用于生成描述。',
            author=user,
            category=category,
            type='a',
            status='p',
        )
        return article

    def test_default_page_twitter_summary_card(self):
        request = self.factory.get('/')
        with patch('plugins.seo_optimizer.plugin.get_blog_setting',
                   return_value=self.blog_setting):
            data = self.seo._get_default_seo_data({}, request, self.blog_setting)

        meta = data['meta_tags']
        self.assertIn('twitter:card" content="summary"', meta)
        self.assertIn('twitter:title', meta)
        self.assertIn('twitter:description', meta)

    def test_article_page_twitter_large_card(self):
        article = self._make_article()
        request = self.factory.get(article.get_full_url())
        context = {'article': article, 'request': request}

        with patch('plugins.seo_optimizer.plugin.get_blog_setting',
                   return_value=self.blog_setting):
            data = self.seo._get_article_seo_data(context, request, self.blog_setting)

        meta = data['meta_tags']
        self.assertIn('twitter:card" content="summary_large_image"', meta)
        self.assertIn('twitter:title', meta)
        self.assertIn('twitter:description', meta)

    def test_dispatch_outputs_sitemap_link(self):
        request = self.factory.get('/')
        request.resolver_match = SimpleNamespace(view_name='blog:index')
        context = {'request': request}

        with patch('plugins.seo_optimizer.plugin.get_blog_setting',
                   return_value=self.blog_setting):
            html = self.seo.dispatch_seo_generation('', context)

        self.assertIn('rel="sitemap"', html)
        self.assertIn('/sitemap.xml', html)
