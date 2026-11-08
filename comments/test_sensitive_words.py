# -*- coding: utf-8 -*-
"""#jxr 敏感词过滤（功能1）测试。

覆盖三层：
1. 纯函数层：命中判定（直写/拆字/插符号/全角/大小写）、脱敏替换、提示文案；
2. 表单层：block 模式抛校验错误，mask 模式返回脱敏正文；
3. 视图层：block 模式评论不落库，mask 模式落库的是脱敏文本。

注意：词库与模式都从 settings 实时读取，测试用 override_settings 注入，
不依赖 default 词库的具体内容，避免以后改词库把测试改崩。
"""

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import BlogUser
from blog.models import Article, BlogSettings, Category
from comments.forms import CommentForm
from comments.models import Comment
from comments.sensitive_words import (
    MODE_BLOCK,
    MODE_MASK,
    check_comment_body,
    contains_sensitive_words,
    describe_sensitive_hits,
    find_sensitive_words,
    get_filter_mode,
    get_sensitive_words,
    mask_sensitive_words,
)

TEST_WORDS = ['广告', '加微信', 'spam', '赌博']


@override_settings(COMMENT_SENSITIVE_WORDS=TEST_WORDS, COMMENT_SENSITIVE_WORD_MODE=MODE_BLOCK)
class SensitiveWordUnitTest(TestCase):
    """#jxr 纯函数层测试：不建库表，只验证匹配与脱敏算法。"""

    def test_get_sensitive_words_from_settings(self):
        """#jxr 词库从 settings 读取，且能去重"""
        self.assertEqual(get_sensitive_words(), tuple(TEST_WORDS))

    @override_settings(COMMENT_SENSITIVE_WORDS='广告，加微信、spam')
    def test_get_sensitive_words_from_string(self):
        """#jxr 支持在 settings 里写一行逗号分隔的配置"""
        self.assertEqual(get_sensitive_words(), ('广告', '加微信', 'spam'))

    @override_settings(COMMENT_SENSITIVE_WORDS='')
    def test_get_sensitive_words_fallback(self):
        """#jxr 配置为空时回退到内置词库，保证过滤不会裸奔"""
        self.assertTrue(get_sensitive_words())
        self.assertIn('广告', get_sensitive_words())

    def test_get_filter_mode_default_block(self):
        """#jxr 未配置/非法配置都回退为 block"""
        self.assertEqual(get_filter_mode(), MODE_BLOCK)
        with override_settings(COMMENT_SENSITIVE_WORD_MODE='whatever'):
            self.assertEqual(get_filter_mode(), MODE_BLOCK)

    def test_find_direct_word(self):
        """#jxr 直接命中"""
        self.assertEqual(find_sensitive_words('这条就是广告'), ['广告'])

    def test_find_obfuscated_with_space_and_symbol(self):
        """#jxr 拆字/插符号也能命中：广 告、广*告、广-告"""
        for body in ('广 告', '广*告', '广-告', '广　告'):
            with self.subTest(body=body):
                self.assertIn('广告', find_sensitive_words(body))

    def test_find_fullwidth_and_case_insensitive(self):
        """#jxr 全角字符与大小写不影响命中"""
        self.assertIn('spam', find_sensitive_words('ＳＰＡＭ'))
        self.assertIn('spam', find_sensitive_words('SpAm'))

    def test_find_multiple_words(self):
        """#jxr 一句话命中多个词时按词库顺序返回"""
        hits = find_sensitive_words('广告：加微信，还有 SPAM')
        self.assertEqual(hits, ['广告', '加微信', 'spam'])

    def test_no_false_positive(self):
        """#jxr 正常讨论不应被误伤"""
        self.assertEqual(find_sensitive_words('这篇文章的思路很清楚，值得学习。'), [])
        self.assertFalse(contains_sensitive_words('Django 的 ORM 很好用'))

    def test_mask_keeps_length(self):
        """#jxr 脱敏替换成等长星号，长度不变"""
        body = '这里是一条广告内容'
        masked = mask_sensitive_words(body)
        self.assertEqual(len(masked), len(body))
        self.assertEqual(masked, '这里是一条**内容')
        self.assertNotIn('广告', masked)

    def test_mask_obfuscated_span(self):
        """#jxr 拆字写法把整段（含插入的空格）一起打码"""
        masked = mask_sensitive_words('广 告')
        self.assertEqual(masked, '***')

    def test_mask_without_hit_returns_original(self):
        """#jxr 未命中时原样返回，不做任何改写"""
        body = '正常评论内容'
        self.assertIs(mask_sensitive_words(body), body)

    def test_mask_multiple_occurrences(self):
        """#jxr 同一个词出现多次都要打码"""
        masked = mask_sensitive_words('广告广告')
        self.assertEqual(masked, '****')

    def test_check_block_mode(self):
        """#jxr block 模式：不放行，正文保持原样"""
        allowed, body, hits, mode = check_comment_body('加微信领福利')
        self.assertFalse(allowed)
        self.assertEqual(body, '加微信领福利')
        self.assertEqual(hits, ['加微信'])
        self.assertEqual(mode, MODE_BLOCK)

    @override_settings(COMMENT_SENSITIVE_WORD_MODE=MODE_MASK)
    def test_check_mask_mode(self):
        """#jxr mask 模式：放行，但正文已脱敏"""
        allowed, body, hits, mode = check_comment_body('加微信领福利')
        self.assertTrue(allowed)
        self.assertEqual(body, '***领福利')
        self.assertEqual(hits, ['加微信'])
        self.assertEqual(mode, MODE_MASK)

    def test_describe_hits(self):
        """#jxr 提示文案只保留首字，其余打码"""
        self.assertEqual(describe_sensitive_hits(['广告', '加微信']), '广*、加**')
        self.assertEqual(describe_sensitive_hits([]), '')


@override_settings(COMMENT_SENSITIVE_WORDS=TEST_WORDS, COMMENT_SENSITIVE_WORD_MODE=MODE_BLOCK)
class CommentFormSensitiveWordTest(TestCase):
    """#jxr 表单层测试：确认 clean_body 真正接入了过滤逻辑。"""

    def test_block_mode_raises_validation_error(self):
        """#jxr block 模式：表单不通过，错误信息包含打码后的命中词"""
        form = CommentForm(data={'body': '这里是一条广告'})
        self.assertFalse(form.is_valid())
        self.assertIn('body', form.errors)
        self.assertIn('敏感词', str(form.errors['body']))
        self.assertIn('广*', str(form.errors['body']))

    def test_clean_text_passes(self):
        """#jxr 正常文本照常通过，且去掉首尾空白"""
        form = CommentForm(data={'body': '  这是一条正常评论  '})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['body'], '这是一条正常评论')

    def test_blank_body_rejected(self):
        """#jxr 全空白内容按空评论处理"""
        form = CommentForm(data={'body': '   '})
        self.assertFalse(form.is_valid())
        self.assertIn('body', form.errors)

    @override_settings(COMMENT_SENSITIVE_WORD_MODE=MODE_MASK)
    def test_mask_mode_returns_masked_body(self):
        """#jxr mask 模式：表单通过，cleaned_data 是脱敏正文"""
        form = CommentForm(data={'body': '广告内容，请勿相信'})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['body'], '**内容，请勿相信')


@override_settings(COMMENT_SENSITIVE_WORDS=TEST_WORDS, COMMENT_SENSITIVE_WORD_MODE=MODE_BLOCK)
class CommentPostSensitiveWordViewTest(TestCase):
    """#jxr 视图层测试：走真实 URL + 登录态，验证落库结果。"""

    def setUp(self):
        self.user = BlogUser.objects.create_user(
            username='jxr_sensitive', email='jxr_sensitive@test.com', password='testpass123')
        self.category = Category.objects.create(
            name='敏感词测试分类', creation_time=timezone.now(), last_modify_time=timezone.now())
        self.article = Article.objects.create(
            title='敏感词测试文章', body='正文', author=self.user,
            category=self.category, type='a', status='p')
        self.blog_settings, _ = BlogSettings.objects.get_or_create(
            id=1, defaults={'site_name': '测试博客', 'comment_need_review': False})
        self.blog_settings.comment_need_review = False
        self.blog_settings.save()
        self.client.login(username='jxr_sensitive', password='testpass123')
        self.url = reverse('comments:postcomment', kwargs={'article_id': self.article.id})

    def test_block_mode_does_not_create_comment(self):
        """#jxr block 模式：提交被拦下（200 回显错误），数据库里没有这条评论"""
        response = self.client.post(self.url, {'body': '加微信 领取资料'})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Comment.objects.filter(article=self.article).exists())

    @override_settings(COMMENT_SENSITIVE_WORD_MODE=MODE_MASK)
    def test_mask_mode_stores_masked_body(self):
        """#jxr mask 模式：评论正常保存，但正文已脱敏"""
        response = self.client.post(self.url, {'body': '加微信 领取资料'})
        self.assertEqual(response.status_code, 302)
        comment = Comment.objects.get(article=self.article)
        self.assertNotIn('加微信', comment.body)
        self.assertEqual(comment.body, '*** 领取资料')

    def test_clean_comment_still_works(self):
        """#jxr 不含敏感词的评论行为不变"""
        response = self.client.post(self.url, {'body': '这是一条正常评论'})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Comment.objects.filter(article=self.article, body='这是一条正常评论').exists())
