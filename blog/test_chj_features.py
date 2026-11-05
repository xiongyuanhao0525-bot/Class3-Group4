# -*- coding: utf-8 -*-
# ============================================================
# blog/test_chj_features.py
# 陈汉佳 #chj（2415304339）负责的 blog 三个功能点测试
#   功能点1：TOC 自动生成        —— TocTest
#   功能点2：草稿/定时发布        —— ScheduledPublishTest
#   功能点3：搜索关键词高亮       —— SearchHighlightTest
# 运行：python manage.py test blog.test_chj_features
# ============================================================
from datetime import timedelta

from django.utils import timezone

from djangoblog.test_base import BaseTestCase

from blog.templatetags.blog_toc import build_toc, markdown_toc
from blog.templatetags.blog_search import search_highlight


class TocTest(BaseTestCase):
    """功能点1：从 Markdown 正文解析目录"""

    def test_parse_three_levels(self):
        """一级/二级/三级标题都能解析出来"""
        body = '# 第一章\n正文段落\n## 小节A\n### 子节\n## 小节B'
        toc = build_toc(body)
        self.assertEqual(len(toc), 4)
        self.assertEqual(toc[0][0], 1)   # 第一章是一级
        self.assertEqual(toc[1][0], 2)   # 小节A是二级
        self.assertEqual(toc[2][0], 3)   # 子节是三级
        self.assertEqual(toc[3][1], '小节B')

    def test_anchor_unique(self):
        """每条目录的锚点 id 必须唯一"""
        body = '# A\n## B\n## C'
        toc = build_toc(body)
        anchors = [item[2] for item in toc]
        self.assertEqual(len(anchors), len(set(anchors)))

    def test_empty_body(self):
        """空正文不报错，目录为空"""
        self.assertEqual(build_toc(''), [])
        self.assertEqual(build_toc(None), [])

    def test_filter_renders_html(self):
        """过滤器输出带 <ul>/<a> 的 HTML"""
        out = markdown_toc('# 标题')
        self.assertIn('<ul', out)
        self.assertIn('<a href="#toc-1">标题</a>', out)


class ScheduledPublishTest(BaseTestCase):
    """功能点2：草稿不公开；定时发布时间未到不公开"""

    def setUp(self):
        # 测试基类会建好 user/category/article，这里补一个未来时间
        self.future = timezone.now() + timedelta(days=1)

    def test_scheduled_article_anonymous_404(self):
        """定时文章（pub_time 在未来）匿名访问应 404"""
        article = self.create_article(title='定时发布的文章')
        article.pub_time = self.future
        article.save()
        resp = self.client.get(article.get_absolute_url())
        self.assertEqual(resp.status_code, 404)

    def test_past_published_article_visible(self):
        """已发布且发布时间已过，正常访问 200"""
        article = self.create_article(title='已经发布的文章')
        article.pub_time = timezone.now() - timedelta(hours=1)
        article.save()
        resp = self.client.get(article.get_absolute_url())
        self.assertEqual(resp.status_code, 200)

    def test_draft_404(self):
        """草稿文章匿名访问 404"""
        article = self.create_article(title='草稿文章', status='d')
        resp = self.client.get(article.get_absolute_url())
        self.assertEqual(resp.status_code, 404)


class SearchHighlightTest(BaseTestCase):
    """功能点3：搜索结果关键词高亮"""

    def test_highlight_wraps_mark(self):
        """命中关键词被包成 <mark>"""
        out = search_highlight('这是一个测试内容', '测试')
        self.assertIn('<mark', out)
        self.assertIn('测试', out)

    def test_highlight_case_insensitive(self):
        """英文不区分大小写"""
        out = search_highlight('Hello World', 'hello')
        self.assertIn('<mark', out)

    def test_empty_query_no_mark(self):
        """搜索词为空时不输出 <mark>"""
        out = search_highlight('正文内容', '')
        self.assertNotIn('<mark', out)
