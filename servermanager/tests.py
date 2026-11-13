from django.test import Client, RequestFactory, TestCase, override_settings
from django.utils import timezone
from werobot.messages.messages import TextMessage

from accounts.models import BlogUser
from blog.models import Category, Article
from servermanager.alarm import AlarmNotifier
from servermanager.api.commonapi import ChatGPT
from .models import commands
from .robot import MessageHandler, CommandHandler
from .robot import search, category, recents


class _FakeCache:
    """内存缓存后端，便于在测试中隔离告警状态（不污染 Django locmem 缓存）。"""

    def __init__(self):
        self.store = {}

    def get(self, key, default=None):
        return self.store.get(key, default)

    def set(self, key, value, timeout=None):
        self.store[key] = value

    def delete(self, key):
        self.store.pop(key, None)


class AlarmNotifierTest(TestCase):
    """#wxy 告警通道：重复报警合并 + 发送限频。"""

    def setUp(self):
        self.cache = _FakeCache()
        self.sent = []
        self.now = [1000.0]

        def fake_sender(recipients, title, content):
            self.sent.append((list(recipients), title, content))

        self.notifier = AlarmNotifier(
            coalesce_window=300,
            rate_limit_window=600,
            max_per_window=2,
            cache_backend=self.cache,
            sender=fake_sender,
            clock=lambda: self.now[0],
        )

    def _advance(self, seconds):
        self.now[0] += seconds

    def test_first_report_is_sent(self):
        status = self.notifier.report('openai_error', '连接超时')
        self.assertEqual(status, 'sent')
        self.assertEqual(len(self.sent), 1)
        self.assertIn('openai_error', self.sent[0][1])

    def test_duplicate_within_coalesce_window_is_merged(self):
        self.notifier.report('openai_error', '连接超时')
        status = self.notifier.report('openai_error', '连接超时')
        self.assertEqual(status, 'merged')
        self.assertEqual(len(self.sent), 1)  # 合并窗口内不重复发信

    def test_different_kinds_are_sent_separately(self):
        self.notifier.report('openai_error', '连接超时')
        status = self.notifier.report('command_error', 'ls 失败')
        self.assertEqual(status, 'sent')
        self.assertEqual(len(self.sent), 2)

    def test_message_case_and_space_normalized_to_same_fingerprint(self):
        self.notifier.report('openai_error', 'Connection  Timeout')
        status = self.notifier.report('openai_error', 'connection timeout')
        self.assertEqual(status, 'merged')

    def test_rate_limit_suppresses_after_max_per_window(self):
        self.notifier.report('openai_error', '错误 A')  # sent 1
        self.notifier.report('openai_error', '错误 A')  # merged（合并窗口内）
        self._advance(301)  # 越过合并窗口，再次触发 -> sent 2
        self.notifier.report('openai_error', '错误 A')
        # 限频窗口内已发 2 封（达上限），第三封被抑制
        status = self.notifier.report('openai_error', '错误 A')
        self.assertEqual(status, 'suppressed')
        self.assertEqual(len(self.sent), 2)

    def test_window_expiry_allows_new_send(self):
        self.notifier.report('openai_error', '错误 A')
        self._advance(601)  # 越过限频窗口
        status = self.notifier.report('openai_error', '错误 A')
        self.assertEqual(status, 'sent')
        self.assertEqual(len(self.sent), 2)

    @override_settings(ADMINS=[])
    def test_no_admin_recipient_does_not_raise(self):
        notifier = AlarmNotifier(
            coalesce_window=300, rate_limit_window=600, max_per_window=2,
            cache_backend=self.cache, sender=lambda *a: self.sent.append(a),
            clock=lambda: self.now[0],
        )
        status = notifier.report('openai_error', '无收件人场景')
        self.assertEqual(status, 'sent')  # 流程不抛异常，仅记录日志
        self.assertEqual(len(self.sent), 0)


# Create your tests here.
class ServerManagerTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.factory = RequestFactory()

    def test_chat_gpt(self):
        content = ChatGPT.chat("你好")
        self.assertIsNotNone(content)

    def test_validate_comment(self):
        user = BlogUser.objects.create_superuser(
            email="liangliangyy1@gmail.com",
            username="liangliangyy1",
            password="liangliangyy1")

        self.client.login(username='liangliangyy1', password='liangliangyy1')

        c = Category()
        c.name = "categoryccc"
        c.save()

        article = Article()
        article.title = "nicetitleccc"
        article.body = "nicecontentccc"
        article.author = user
        article.category = c
        article.type = 'a'
        article.status = 'p'
        article.save()
        s = TextMessage([])
        s.content = "nice"
        rsp = search(s, None)
        rsp = category(None, None)
        self.assertIsNotNone(rsp)
        rsp = recents(None, None)
        self.assertTrue(rsp != '暂时还没有文章')

        cmd = commands()
        cmd.title = "test"
        cmd.command = "ls"
        cmd.describe = "test"
        cmd.save()

        cmdhandler = CommandHandler()
        rsp = cmdhandler.run('test')
        self.assertIsNotNone(rsp)
        s.source = 'u'
        s.content = 'test'
        msghandler = MessageHandler(s, {})

        # msghandler.userinfo.isPasswordSet = True
        # msghandler.userinfo.isAdmin = True
        msghandler.handler()
        s.content = 'y'
        msghandler.handler()
        s.content = 'idcard:12321233'
        msghandler.handler()
        s.content = 'weather:上海'
        msghandler.handler()
        s.content = 'admin'
        msghandler.handler()
        s.content = '123'
        msghandler.handler()

        s.content = 'exit'
        msghandler.handler()
