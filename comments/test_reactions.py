# -*- coding: utf-8 -*-
"""#jxr 表情回应（功能3）测试。

覆盖三类“已知问题”：
1. 汇总查询的 N+1 与用户预览顺序不稳定 → 用 assertNumQueries + 顺序断言锁死；
2. 评论不存在时返回 HTML 404、参数错误时缺 success 字段 → 校验 JSON 契约；
3. 切换表情的并发竞态/返回体缺可用表情列表 → 校验切换语义与 available_reactions。
"""

from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import BlogUser
from blog.models import Article, BlogSettings, Category
from comments.models import Comment, CommentReaction


class CommentReactionTestBase(TestCase):
    """#jxr 公共夹具：登录用户 + 已通过审核的评论。"""

    def setUp(self):
        self.user = BlogUser.objects.create_user(
            username='jxr_react', email='jxr_react@test.com', password='testpass123')
        self.category = Category.objects.create(
            name='表情测试分类', creation_time=timezone.now(), last_modify_time=timezone.now())
        self.article = Article.objects.create(
            title='表情测试文章', body='正文', author=self.user,
            category=self.category, type='a', status='p')
        BlogSettings.objects.get_or_create(
            id=1, defaults={'site_name': '测试博客', 'comment_need_review': False})

        self.comment = Comment.objects.create(
            body='表情测试评论', author=self.user, article=self.article)
        self.comment.approve()  # #jxr 只有已通过审核的评论才能被回应
        self.url = reverse('comments:comment_react', kwargs={'comment_id': self.comment.pk})

    def make_user(self, username):
        return BlogUser.objects.create_user(
            username=username, email=f'{username}@test.com', password='testpass123')

    def add_reaction(self, user, reaction_type='👍'):
        return CommentReaction.objects.create(
            comment=self.comment, user=user, reaction_type=reaction_type)


class ReactionSummaryQueryTest(CommentReactionTestBase):
    """#jxr 汇总方法的查询次数与顺序。"""

    def test_anonymous_summary_uses_single_query(self):
        """#jxr 未登录：无论多少种表情、多少用户，只发 1 条 SQL"""
        alice = self.make_user('jxr_alice')
        bob = self.make_user('jxr_bob')
        self.add_reaction(alice, '👍')
        self.add_reaction(bob, '👍')
        self.add_reaction(alice, '❤️')
        self.add_reaction(bob, '🎉')

        with self.assertNumQueries(1):
            summary = self.comment.get_reactions_summary()

        self.assertEqual(summary['👍']['count'], 2)
        self.assertEqual(summary['❤️']['count'], 1)
        self.assertEqual(summary['🎉']['count'], 1)
        self.assertFalse(summary['👍']['has_reacted'])

    def test_authenticated_summary_uses_two_queries(self):
        """#jxr 登录用户：在总量查询之外只补 1 条“我点过哪些”"""
        alice = self.make_user('jxr_alice')
        self.add_reaction(alice, '👍')
        self.add_reaction(self.user, '👍')
        self.add_reaction(self.user, '🚀')

        with self.assertNumQueries(2):
            summary = self.comment.get_reactions_summary(self.user)

        self.assertTrue(summary['👍']['has_reacted'])
        self.assertTrue(summary['🚀']['has_reacted'])
        self.assertFalse(summary['❤️']['has_reacted'])

    def test_user_preview_order_is_stable(self):
        """#jxr 用户预览按“先点的在前”，不再依赖数据库默认返回顺序"""
        base_time = timezone.now() - timedelta(minutes=20)
        users = []
        for index in range(3):
            user = self.make_user('jxr_order_%d' % index)
            users.append(user)
            reaction = self.add_reaction(user, '👍')
            # #jxr auto_now_add 无法指定时间，创建后回写 created_at 来固定先后
            CommentReaction.objects.filter(pk=reaction.pk).update(
                created_at=base_time + timedelta(minutes=index))

        summary = self.comment.get_reactions_summary()
        self.assertEqual(summary['👍']['users'], ['jxr_order_0', 'jxr_order_1', 'jxr_order_2'])

    def test_user_preview_limited_to_ten(self):
        """#jxr 每种表情最多回传 10 个用户名"""
        base_time = timezone.now() - timedelta(minutes=30)
        for index in range(12):
            user = self.make_user('jxr_many_%02d' % index)
            reaction = self.add_reaction(user, '👍')
            CommentReaction.objects.filter(pk=reaction.pk).update(
                created_at=base_time + timedelta(seconds=index))

        summary = self.comment.get_reactions_summary()
        self.assertEqual(summary['👍']['count'], 12)
        self.assertEqual(len(summary['👍']['users']), CommentReaction.USER_PREVIEW_LIMIT)

    def test_empty_summary(self):
        """#jxr 没有任何回应时仍返回全部表情键，计数为 0（前端不用判空）"""
        summary = self.comment.get_reactions_summary()
        self.assertEqual(set(summary.keys()), set(CommentReaction.available_reaction_types()))
        self.assertTrue(all(item['count'] == 0 for item in summary.values()))
        self.assertTrue(all(item['users'] == [] for item in summary.values()))


class ReactionApiContractTest(CommentReactionTestBase):
    """#jxr API 契约：状态码、JSON 结构、异常分支。"""

    def test_get_returns_json_with_available_reactions(self):
        """#jxr GET 返回统计 + 可用表情列表"""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])
        self.assertEqual(payload['available_reactions'], CommentReaction.available_reaction_types())
        self.assertEqual(len(payload['available_reactions']), 8)

    def test_get_missing_comment_returns_json_404(self):
        """#jxr 评论不存在时返回 JSON 404，而不是 HTML 错误页"""
        url = reverse('comments:comment_react', kwargs={'comment_id': 999999})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertFalse(response.json()['success'])

    def test_get_pending_comment_returns_404(self):
        """#jxr 待审评论对外不可见，GET 同样返回 JSON 404"""
        pending = Comment.objects.create(
            body='待审评论', author=self.user, article=self.article)
        url = reverse('comments:comment_react', kwargs={'comment_id': pending.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)
        self.assertFalse(response.json()['success'])

    def test_post_requires_login(self):
        """#jxr 未登录 POST 返回 401 JSON"""
        response = self.client.post(self.url, {'reaction_type': '👍'})
        self.assertEqual(response.status_code, 401)
        self.assertFalse(response.json()['success'])

    def test_post_invalid_type_has_success_field(self):
        """#jxr 非法表情返回 400，且必须带 success=False（旧实现漏了这个字段）"""
        self.client.login(username='jxr_react', password='testpass123')
        response = self.client.post(self.url, {'reaction_type': '💩'})
        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload['success'])
        self.assertIn('error', payload)

    def test_post_missing_comment_returns_json_404(self):
        """#jxr 对不存在的评论 POST 也返回 JSON 404"""
        self.client.login(username='jxr_react', password='testpass123')
        url = reverse('comments:comment_react', kwargs={'comment_id': 999999})
        response = self.client.post(url, {'reaction_type': '👍'})
        self.assertEqual(response.status_code, 404)
        self.assertFalse(response.json()['success'])


class ReactionToggleTest(CommentReactionTestBase):
    """#jxr 切换语义：再点一次取消。"""

    def setUp(self):
        super().setUp()
        self.client.login(username='jxr_react', password='testpass123')

    def test_add_then_remove(self):
        """#jxr 第一次点=added，第二次点=removed，计数同步变化"""
        first = self.client.post(self.url, {'reaction_type': '👍'})
        self.assertEqual(first.status_code, 200)
        first_payload = first.json()
        self.assertEqual(first_payload['action'], 'added')
        self.assertEqual(first_payload['reactions']['👍']['count'], 1)
        self.assertTrue(first_payload['reactions']['👍']['has_reacted'])
        self.assertIn('available_reactions', first_payload)

        second = self.client.post(self.url, {'reaction_type': '👍'})
        second_payload = second.json()
        self.assertEqual(second_payload['action'], 'removed')
        self.assertEqual(second_payload['reactions']['👍']['count'], 0)
        self.assertFalse(second_payload['reactions']['👍']['has_reacted'])
        self.assertFalse(CommentReaction.objects.filter(comment=self.comment).exists())

    def test_different_emojis_are_independent(self):
        """#jxr 不同表情互不影响"""
        self.client.post(self.url, {'reaction_type': '👍'})
        self.client.post(self.url, {'reaction_type': '🚀'})
        summary = self.comment.get_reactions_summary(self.user)
        self.assertEqual(summary['👍']['count'], 1)
        self.assertEqual(summary['🚀']['count'], 1)
