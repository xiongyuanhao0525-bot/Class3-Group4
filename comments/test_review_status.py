# -*- coding: utf-8 -*-
"""#jxr 评论审核三态（功能2）测试。

覆盖四层：
1. 模型层：默认待审、通过/拒绝/打回、三态与 is_enable 的双向同步（含 update_fields 路径）；
2. 提交层：站点“先审后发”开关决定初始状态；
3. 展示层：只有“通过”的评论进入 Article.comment_list()；
4. 后台层：三个批量动作真正落库，并且把文章评论缓存清掉（这是旧实现 update() 的漏洞）。
"""

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import BlogUser
from blog.models import Article, BlogSettings, Category
from comments.models import Comment


class ReviewStatusTestBase(TestCase):
    """#jxr 公共夹具：一个用户 + 一个分类 + 一篇文章 + 站点配置。"""

    def setUp(self):
        # #jxr locmem 缓存在同一进程内跨用例共享，先清空避免上一个用例的数据/配置串味
        cache.clear()

        self.user = BlogUser.objects.create_user(
            username='jxr_review', email='jxr_review@test.com', password='testpass123')
        self.category = Category.objects.create(
            name='审核测试分类', creation_time=timezone.now(), last_modify_time=timezone.now())
        self.article = Article.objects.create(
            title='审核测试文章', body='正文', author=self.user,
            category=self.category, type='a', status='p')

        self.blog_settings, _ = BlogSettings.objects.get_or_create(
            id=1, defaults={'site_name': '测试博客', 'comment_need_review': True})
        self.blog_settings.comment_need_review = True
        self.blog_settings.save()
        cache.delete('get_blog_setting')  # #jxr 站点配置整行有缓存，改完必须清

    def make_comment(self, body='待审评论', **kwargs):
        """#jxr 造一条评论，默认走“待审”状态。"""
        return Comment.objects.create(
            body=body, author=self.user, article=self.article, **kwargs)


class CommentReviewStatusModelTest(ReviewStatusTestBase):
    """#jxr 模型层：三态字段与同步规则。"""

    def test_default_is_pending(self):
        """#jxr 新建评论默认待审、不展示"""
        comment = self.make_comment()
        self.assertEqual(comment.review_status, Comment.REVIEW_STATUS_PENDING)
        self.assertFalse(comment.is_enable)
        self.assertFalse(comment.is_approved)

    def test_approve_syncs_enable(self):
        """#jxr approve()：状态=通过，同时对外可见"""
        comment = self.make_comment()
        comment.approve()
        self.assertEqual(comment.review_status, Comment.REVIEW_STATUS_APPROVED)
        self.assertTrue(comment.is_enable)
        self.assertTrue(comment.is_approved)

    def test_reject_syncs_enable(self):
        """#jxr reject()：状态=拒绝，同时对外隐藏"""
        comment = self.make_comment()
        comment.approve()
        comment.reject()
        self.assertEqual(comment.review_status, Comment.REVIEW_STATUS_REJECTED)
        self.assertFalse(comment.is_enable)

    def test_reset_to_pending(self):
        """#jxr 打回待审：状态=待审，同时对外隐藏"""
        comment = self.make_comment()
        comment.approve()
        comment.reset_to_pending()
        self.assertEqual(comment.review_status, Comment.REVIEW_STATUS_PENDING)
        self.assertFalse(comment.is_enable)

    def test_legacy_enable_true_derives_approved(self):
        """#jxr 兼容老写法：只改 is_enable=True，保存后状态自动变 approved"""
        comment = self.make_comment()
        comment.is_enable = True
        comment.save()
        comment.refresh_from_db()
        self.assertEqual(comment.review_status, Comment.REVIEW_STATUS_APPROVED)

    def test_legacy_enable_false_derives_pending(self):
        """#jxr 兼容老写法：撤销展示后状态回到待审，而不是停在 approved"""
        comment = self.make_comment()
        comment.approve()
        comment.is_enable = False
        comment.save()
        comment.refresh_from_db()
        self.assertEqual(comment.review_status, Comment.REVIEW_STATUS_PENDING)

    def test_status_wins_when_both_changed(self):
        """#jxr 两个字段同时改时以 review_status 为准"""
        comment = self.make_comment()
        comment.review_status = Comment.REVIEW_STATUS_REJECTED
        comment.is_enable = True   # 故意写反，验证状态优先生效
        comment.save()
        comment.refresh_from_db()
        self.assertFalse(comment.is_enable)

    def test_update_fields_path_keeps_fields_in_sync(self):
        """#jxr save(update_fields=['is_enable']) 也要把 review_status 一起写进去"""
        comment = self.make_comment()
        comment.is_enable = True
        comment.save(update_fields=['is_enable'])
        comment.refresh_from_db()
        self.assertEqual(comment.review_status, Comment.REVIEW_STATUS_APPROVED)
        self.assertTrue(comment.is_enable)


class CommentReviewStatusSubmitTest(ReviewStatusTestBase):
    """#jxr 提交层：站点配置决定新评论的初始状态。"""

    def setUp(self):
        super().setUp()
        self.client.login(username='jxr_review', password='testpass123')
        self.url = reverse('comments:postcomment', kwargs={'article_id': self.article.id})

    def test_need_review_creates_pending(self):
        """#jxr 开启先审后发：新评论待审 + 不展示"""
        response = self.client.post(self.url, {'body': '先审后发的评论'})
        self.assertEqual(response.status_code, 302)
        comment = Comment.objects.get(body='先审后发的评论')
        self.assertEqual(comment.review_status, Comment.REVIEW_STATUS_PENDING)
        self.assertFalse(comment.is_enable)

    def test_no_review_creates_approved(self):
        """#jxr 关闭先审后发：新评论直接通过 + 展示"""
        self.blog_settings.comment_need_review = False
        self.blog_settings.save()
        cache.delete('get_blog_setting')

        response = self.client.post(self.url, {'body': '免审直接通过的评论'})
        self.assertEqual(response.status_code, 302)
        comment = Comment.objects.get(body='免审直接通过的评论')
        self.assertEqual(comment.review_status, Comment.REVIEW_STATUS_APPROVED)
        self.assertTrue(comment.is_enable)

    def test_pending_comment_not_in_article_list(self):
        """#jxr 待审评论不出现在文章评论列表里"""
        self.client.post(self.url, {'body': '先审后发的评论'})
        self.assertFalse(list(self.article.comment_list()))

    def test_approved_comment_in_article_list(self):
        """#jxr 审核通过后出现在文章评论列表里"""
        self.client.post(self.url, {'body': '先审后发的评论'})
        comment = Comment.objects.get(body='先审后发的评论')
        comment.approve()
        self.assertEqual([item.pk for item in self.article.comment_list()], [comment.pk])


class CommentReviewStatusAdminTest(ReviewStatusTestBase):
    """#jxr 后台层：三个批量动作的落库与缓存失效。"""

    def setUp(self):
        super().setUp()
        self.admin_user = BlogUser.objects.create_superuser(
            username='jxr_admin', email='jxr_admin@test.com', password='testpass123')
        self.client.login(username='jxr_admin', password='testpass123')
        self.changelist_url = reverse('admin:comments_comment_changelist')

    def _run_action(self, action_name, comments):
        """#jxr 模拟后台下拉框 + 勾选 + 提交的请求。"""
        return self.client.post(self.changelist_url, {
            'action': action_name,
            '_selected_action': [str(comment.pk) for comment in comments],
            'index': '0',
            'select_across': '0',
        })

    def test_approve_action(self):
        """#jxr 批量通过：状态 approved + 可见 + 清缓存后可查到"""
        comment = self.make_comment()
        response = self._run_action('approve_comments', [comment])
        self.assertEqual(response.status_code, 302)
        comment.refresh_from_db()
        self.assertEqual(comment.review_status, Comment.REVIEW_STATUS_APPROVED)
        self.assertTrue(comment.is_enable)
        self.assertEqual([item.pk for item in self.article.comment_list()], [comment.pk])

    def test_reject_action_clears_cached_list(self):
        """#jxr 批量拒绝：状态 rejected + 隐藏 + 旧缓存被清掉（这是 update() 做不到的）"""
        comment = self.make_comment()
        comment.approve()
        # #jxr 先把“已通过”的评论列表读进缓存，制造一个典型的陈旧缓存场景
        self.assertEqual([item.pk for item in self.article.comment_list()], [comment.pk])

        response = self._run_action('reject_comments', [comment])
        self.assertEqual(response.status_code, 302)
        comment.refresh_from_db()
        self.assertEqual(comment.review_status, Comment.REVIEW_STATUS_REJECTED)
        self.assertFalse(comment.is_enable)
        # #jxr 若缓存没清，这里仍会拿到旧列表；清掉后应为空
        self.assertFalse(list(self.article.comment_list()))

    def test_reset_action(self):
        """#jxr 批量打回待审：状态 pending + 隐藏"""
        comment = self.make_comment()
        comment.approve()
        response = self._run_action('reset_comments_to_pending', [comment])
        self.assertEqual(response.status_code, 302)
        comment.refresh_from_db()
        self.assertEqual(comment.review_status, Comment.REVIEW_STATUS_PENDING)
        self.assertFalse(comment.is_enable)

    def test_status_column_rendered(self):
        """#jxr 列表页渲染状态徽标（验证 admin 配置真的生效）"""
        self.make_comment(body='列表页状态徽标')
        response = self.client.get(self.changelist_url)
        self.assertEqual(response.status_code, 200)
        # #jxr 状态徽标文本取自 get_review_status_display()，默认语言下是 Pending review
        self.assertContains(response, 'Pending review')
        self.assertContains(response, 'border-radius:10px')


class CommentReviewStatusChangeFormTest(ReviewStatusTestBase):
    """#jxr 后台修改表单：逐条改 review_status 也必须让前台缓存立即失效。

    这是用户手工验收时报出的缺陷：批量动作能刷新，但打开某条评论、在表单里
    把“通过”改成“拒绝/待审”再保存时，文章页评论数不变、侧边栏“近期评论”
    仍显示该评论。根因是 blog_signals 只在 is_enable=True 时清缓存。
    """

    def setUp(self):
        super().setUp()
        self.admin_user = BlogUser.objects.create_superuser(
            username='jxr_admin_form', email='jxr_admin_form@test.com', password='testpass123')
        self.client.login(username='jxr_admin_form', password='testpass123')

    def _change_form_post(self, comment, review_status):
        """#jxr 模拟在后台评论编辑页修改“审核状态”并保存。"""
        url = reverse('admin:comments_comment_change', args=[comment.pk])
        return self.client.post(url, {
            'body': comment.body,
            'author': str(comment.author_id),
            'article': str(comment.article_id),
            'parent_comment': '',
            'review_status': review_status,
            '_save': 'Save',
        })

    def _warm_caches(self):
        """#jxr 制造陈旧缓存场景：评论列表 + 侧边栏“近期评论”都写进缓存。"""
        list(self.article.comment_list())
        cache.set('sidebarp', {'sidebar_comments': ['陈旧数据']}, 60)

    def test_change_form_reject_clears_comment_list_cache(self):
        """#jxr 表单里由“通过”改成“拒绝”：评论列表缓存必须被清，前台不再显示"""
        comment = self.make_comment(body='表单改成拒绝的评论')
        comment.approve()
        self._warm_caches()
        self.assertEqual([item.pk for item in self.article.comment_list()], [comment.pk])

        response = self._change_form_post(comment, Comment.REVIEW_STATUS_REJECTED)

        self.assertEqual(response.status_code, 302)
        comment.refresh_from_db()
        self.assertEqual(comment.review_status, Comment.REVIEW_STATUS_REJECTED)
        self.assertFalse(comment.is_enable)
        self.assertFalse(list(self.article.comment_list()))
        self.assertIsNone(cache.get('sidebarp'))  # #jxr 侧边栏“近期评论”缓存同时被清

    def test_change_form_pending_clears_comment_list_cache(self):
        """#jxr 表单里由“通过”改成“待审”：同样要立即从前台消失"""
        comment = self.make_comment(body='表单改成待审的评论')
        comment.approve()
        self._warm_caches()

        response = self._change_form_post(comment, Comment.REVIEW_STATUS_PENDING)

        self.assertEqual(response.status_code, 302)
        comment.refresh_from_db()
        self.assertEqual(comment.review_status, Comment.REVIEW_STATUS_PENDING)
        self.assertFalse(list(self.article.comment_list()))

    def test_change_form_approve_makes_comment_visible(self):
        """#jxr 表单里由“待审”改成“通过”：刷新缓存后前台能查到"""
        comment = self.make_comment(body='表单改成通过的评论')

        response = self._change_form_post(comment, Comment.REVIEW_STATUS_APPROVED)

        self.assertEqual(response.status_code, 302)
        comment.refresh_from_db()
        self.assertTrue(comment.is_enable)
        self.assertEqual([item.pk for item in self.article.comment_list()], [comment.pk])

    def test_delete_approved_comment_clears_cache(self):
        """#jxr 后台删除已通过评论：删除后列表缓存也要失效，评论数才会跟着减少"""
        comment = self.make_comment(body='待删除的已通过评论')
        comment.approve()
        self._warm_caches()
        self.assertEqual([item.pk for item in self.article.comment_list()], [comment.pk])

        url = reverse('admin:comments_comment_delete', args=[comment.pk])
        response = self.client.post(url, {'post': 'yes'})

        self.assertEqual(response.status_code, 302)
        self.assertFalse(Comment.objects.filter(pk=comment.pk).exists())
        self.assertFalse(list(self.article.comment_list()))

