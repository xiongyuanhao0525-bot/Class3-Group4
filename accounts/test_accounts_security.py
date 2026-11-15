"""
accounts 模块安全功能测试

覆盖三类功能：
1. 密码强度校验（注册、找回密码时校验长度 / 字符类型等强度并给出提示）
2. 登录失败锁定（连续 N 次失败后锁定一段时间，防暴力破解）
3. 找回密码验证码（重发倒计时 + 发送次数限制）
"""
from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts import utils
from accounts.forms import ForgetPasswordForm, RegisterForm
from accounts.models import BlogUser


def warm_up_site_setting():
    """预热站点配置缓存，避免首次渲染页面时的 cache.clear() 冲掉统计状态

    说明：模板里的 seo 上下文处理器会调用 djangoblog.utils.get_blog_setting()，
    测试库第一次渲染页面时该函数会新建 BlogSettings 记录，而 BlogSettings.save()
    里有一句 cache.clear()，会把本次测试写进缓存的数据一起清空——导致「按用户名
    累计失败次数」只在第一个请求里生效。先预热一次，把记录建好，再清缓存即可。
    真实环境里这条记录早已存在，不会触发该问题。
    """
    from djangoblog.utils import get_blog_setting
    get_blog_setting()

# 一个符合强度规则的密码：4 类字符、13 位、无连续/重复片段
STRONG_PASSWORD = 'Blog@2026#Sec'
# 明显的弱密码：只有小写字母 + 数字，且有重复字符
WEAK_PASSWORD = 'aaaa1111'
# 验证码节流测试专用邮箱：不要用 admin@admin.com，避免与既有用例互相影响
CODE_EMAIL = 'code-throttle@example.com'


# ---------------------------------------------------------------------------
# 一、密码强度校验
# ---------------------------------------------------------------------------

class PasswordStrengthUtilsTest(TestCase):
    """utils.check_password_strength 的规则细节"""

    def test_strong_password_passes(self):
        """合规密码不应返回任何错误"""
        errors = utils.check_password_strength(STRONG_PASSWORD, username='zhaisjc')
        self.assertEqual(errors, [])

    def test_empty_password(self):
        """空密码直接返回提示"""
        self.assertEqual(utils.check_password_strength(''), ['密码不能为空'])

    def test_too_short_password(self):
        """长度不足 8 位应被拒绝"""
        errors = utils.check_password_strength('Ab1@')
        self.assertTrue(any('长度不能少于 8' in e for e in errors), errors)

    def test_too_long_password(self):
        """长度超过 64 位应被拒绝"""
        errors = utils.check_password_strength('Aa1@' + 'x' * 64)
        self.assertTrue(any('不能超过 64' in e for e in errors), errors)

    def test_missing_char_types(self):
        """只有小写字母 + 数字（2 类）不满足 3 类字符要求"""
        errors = utils.check_password_strength('abcdefghij12')
        self.assertTrue(any('至少需要包含 3 类字符' in e for e in errors), errors)

    def test_common_weak_password(self):
        """常见弱口令应被拒绝"""
        errors = utils.check_password_strength('Password123')
        self.assertTrue(any('常见弱口令' in e for e in errors), errors)

    def test_password_contains_username(self):
        """密码包含用户名应被拒绝"""
        errors = utils.check_password_strength(
            'Zhaisjc@2026', username='zhaisjc')
        self.assertTrue(any('用户名' in e for e in errors), errors)

    def test_sequential_chars(self):
        """连续键盘/数字序列应被拒绝"""
        errors = utils.check_password_strength('Qwer@2026')
        self.assertTrue(any('连续字符' in e for e in errors), errors)

    def test_repeated_chars(self):
        """连续重复字符（aaaa）应被拒绝"""
        errors = utils.check_password_strength('Aaaa@2026')
        self.assertTrue(any('重复' in e for e in errors), errors)

    def test_password_char_types(self):
        """字符类型识别应覆盖四类字符"""
        self.assertEqual(
            utils.password_char_types('aA1@'),
            ['lower', 'upper', 'digit', 'special'])
        self.assertEqual(utils.password_char_types(''), [])

    def test_strength_level(self):
        """强度分级：空 / 弱 / 中 / 强"""
        self.assertEqual(utils.password_strength_level(''), 'empty')
        self.assertEqual(utils.password_strength_level('abcdefgh'), 'weak')
        self.assertEqual(utils.password_strength_level('Abc12345'), 'medium')
        self.assertEqual(
            utils.password_strength_level('Blog@2026#SecurityYard'), 'strong')


class PasswordStrengthFormTest(TestCase):
    """注册 / 找回密码表单接入强度校验"""

    def test_register_form_accepts_strong_password(self):
        form = RegisterForm(data={
            'username': 'newuser01',
            'email': 'newuser01@example.com',
            'password1': STRONG_PASSWORD,
            'password2': STRONG_PASSWORD,
        })
        self.assertTrue(form.is_valid(), form.errors)

    def test_register_form_rejects_weak_password(self):
        form = RegisterForm(data={
            'username': 'newuser02',
            'email': 'newuser02@example.com',
            'password1': WEAK_PASSWORD,
            'password2': WEAK_PASSWORD,
        })
        self.assertFalse(form.is_valid())
        messages = ' '.join(form.errors['password2'])
        self.assertIn('类字符', messages)

    def test_register_form_shows_strength_rules(self):
        """密码输入框下方应展示强度规则提示"""
        form = RegisterForm()
        self.assertEqual(
            str(form.fields['password1'].help_text), utils.PASSWORD_RULES_TEXT)

    def test_register_view_rejects_weak_password(self):
        """走注册视图时弱密码不会创建用户"""
        response = self.client.post(reverse('account:register'), {
            'username': 'weakuser',
            'email': 'weakuser@example.com',
            'password1': WEAK_PASSWORD,
            'password2': WEAK_PASSWORD,
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            BlogUser.objects.filter(username='weakuser').exists())

    def test_forget_password_rejects_weak_password(self):
        """找回密码（改密）时弱密码被拒绝，原密码保持不变"""
        user = BlogUser.objects.create_user(
            username='resetuser', email='resetuser@example.com',
            password=STRONG_PASSWORD)
        code = '123456'
        utils.set_code(user.email, code)

        form = ForgetPasswordForm(data={
            'email': user.email,
            'code': code,
            'new_password1': 'abcdefgh12',
            'new_password2': 'abcdefgh12',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('类字符', ' '.join(form.errors['new_password2']))

        user.refresh_from_db()
        self.assertTrue(user.check_password(STRONG_PASSWORD))

    def test_forget_password_accepts_strong_password(self):
        user = BlogUser.objects.create_user(
            username='resetuser2', email='resetuser2@example.com',
            password=STRONG_PASSWORD)
        utils.set_code(user.email, '654321')

        form = ForgetPasswordForm(data={
            'email': user.email,
            'code': '654321',
            'new_password1': 'Zjc@2026#Reset',
            'new_password2': 'Zjc@2026#Reset',
        })
        self.assertTrue(form.is_valid(), form.errors)

# ---------------------------------------------------------------------------
# 二、登录失败锁定
# ---------------------------------------------------------------------------

class LoginLockUtilsTest(TestCase):
    """utils 层的失败计数与锁定逻辑"""

    def setUp(self):
        cache.clear()
        self.user = BlogUser.objects.create_user(
            username='lockuser', email='lockuser@example.com',
            password=STRONG_PASSWORD)

    def test_failure_counter_and_auto_lock(self):
        """连续失败达到上限后自动写入锁定时间"""
        limit = utils.get_login_failure_limit()
        for _ in range(limit - 1):
            count, remaining = utils.register_login_failure(
                self.user.username, user=self.user)
            self.assertEqual(remaining, 0)

        count, remaining = utils.register_login_failure(
            self.user.username, user=self.user)
        self.assertEqual(count, limit)
        self.assertGreater(remaining, 0)

        self.user.refresh_from_db()
        self.assertTrue(self.user.is_login_locked())

    def test_reset_after_success(self):
        """登录成功后计数与锁定状态被清空"""
        utils.register_login_failure(self.user.username, user=self.user)
        self.user.refresh_from_db()
        self.assertEqual(self.user.failed_login_count, 1)

        utils.reset_login_failures(self.user, self.user.username)
        self.user.refresh_from_db()
        self.assertEqual(self.user.failed_login_count, 0)
        self.assertIsNone(self.user.lock_until)
        self.assertEqual(utils.get_login_lock_remaining(
            self.user.username, user=self.user), 0)

    def test_lock_message(self):
        """锁定提示文案包含分钟数"""
        message = utils.build_login_lock_message(900)
        self.assertIn('锁定', message)
        self.assertIn('15 分钟', message)

    def test_lock_message_rounds_extra_second(self):
        """剩余秒数向上取整的 1 秒不应把 15 分钟显示成 16 分钟"""
        self.assertIn('15 分钟', utils.build_login_lock_message(901))
        self.assertIn('1 分钟', utils.build_login_lock_message(30))

    @override_settings(LOGIN_FAILURE_LIMIT=3, LOGIN_LOCK_SECONDS=60)
    def test_settings_override(self):
        """阈值可通过 settings 配置"""
        self.assertEqual(utils.get_login_failure_limit(), 3)
        self.assertEqual(utils.get_login_lock_seconds(), 60)

        for _ in range(2):
            _, remaining = utils.register_login_failure(
                self.user.username, user=self.user)
            self.assertEqual(remaining, 0)

        _, remaining = utils.register_login_failure(
            self.user.username, user=self.user)
        self.assertGreater(remaining, 0)

    def test_unknown_username_uses_cache(self):
        """不存在的用户名同样被计数并锁定（防止撞库试探）"""
        limit = utils.get_login_failure_limit()
        remaining = 0
        for _ in range(limit):
            _, remaining = utils.register_login_failure('ghost-user')
        self.assertGreater(remaining, 0)
        self.assertGreater(
            utils.get_login_lock_remaining('ghost-user'), 0)


class LoginLockViewTest(TestCase):
    """登录视图接入失败锁定"""

    def setUp(self):
        # 顺序很重要：先清空缓存，让预热真的落库建记录；再清一次，避免上一个
        # 用例留下的（已随事务回滚的）站点配置残留在缓存里。
        cache.clear()
        warm_up_site_setting()
        cache.clear()
        self.user = BlogUser.objects.create_user(
            username='viewuser', email='viewuser@example.com',
            password=STRONG_PASSWORD)
        self.url = reverse('account:login')

    def _login(self, password):
        return self.client.post(self.url, {
            'username': self.user.username,
            'password': password,
        })

    def _fail_until_locked(self):
        """连续用错误密码登录，直到触发锁定，返回最后一次响应"""
        limit = utils.get_login_failure_limit()
        response = None
        for _ in range(limit):
            response = self._login('Wrong@Pass2026')
        return response

    def test_failed_login_shows_remaining_attempts(self):
        """失败一次后提示还可以再试几次"""
        response = self._login('Wrong@Pass2026')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '再失败')

        self.user.refresh_from_db()
        self.assertEqual(self.user.failed_login_count, 1)

    def test_lock_after_limit_failures(self):
        """连续失败达到上限后锁定并返回 429"""
        response = self._fail_until_locked()
        self.assertEqual(response.status_code, 429)
        self.assertContains(response, '锁定', status_code=429)

        self.user.refresh_from_db()
        self.assertTrue(self.user.is_login_locked())

    def test_locked_user_rejected_even_with_correct_password(self):
        """锁定期内即使密码正确也无法登录"""
        self._fail_until_locked()
        self.client.post(reverse('account:logout'))

        response = self._login(STRONG_PASSWORD)
        self.assertEqual(response.status_code, 429)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_successful_login_resets_failure_count(self):
        """失败几次后登录成功，计数归零"""
        for _ in range(2):
            self._login('Wrong@Pass2026')

        response = self._login(STRONG_PASSWORD)
        self.assertIn(response.status_code, [301, 302])

        self.user.refresh_from_db()
        self.assertEqual(self.user.failed_login_count, 0)
        self.assertIsNone(self.user.lock_until)

    def test_lock_expires_and_allows_login(self):
        """锁定时间过期后可以正常登录"""
        self._fail_until_locked()
        self.user.refresh_from_db()

        # 把锁定时间改成过去，模拟锁定期已过
        self.user.lock_until = timezone.now() - timedelta(seconds=1)
        self.user.save(update_fields=['lock_until'])

        response = self._login(STRONG_PASSWORD)
        self.assertIn(response.status_code, [301, 302])

    def test_unknown_username_locked_via_cache(self):
        """不存在的用户名连续失败后同样返回锁定提示"""
        limit = utils.get_login_failure_limit()
        response = None
        for _ in range(limit):
            response = self.client.post(self.url, {
                'username': 'ghost-user',
                'password': 'Wrong@Pass2026',
            })
        self.assertEqual(response.status_code, 429)

# ---------------------------------------------------------------------------
# 三、找回密码验证码节流
# ---------------------------------------------------------------------------

class VerificationCodeThrottleUtilsTest(TestCase):
    """验证码发送节流的工具函数（重发倒计时 + 发送次数限制）"""

    def setUp(self):
        cache.clear()
        utils.reset_code_send_state(CODE_EMAIL)

    def test_first_send_is_allowed(self):
        """没发过的时候既不用等，也没到次数上限"""
        self.assertEqual(utils.get_code_resend_remaining(CODE_EMAIL), 0)
        self.assertFalse(utils.is_code_send_limited(CODE_EMAIL))

    def test_resend_needs_countdown(self):
        """发过一次后要等满间隔才能再发"""
        now = timezone.now()
        interval = utils.get_code_resend_interval()
        utils.record_code_sent(CODE_EMAIL, now=now)

        self.assertEqual(
            utils.get_code_resend_remaining(CODE_EMAIL, now=now), interval)
        self.assertGreater(utils.get_code_resend_remaining(
            CODE_EMAIL, now=now + timedelta(seconds=interval - 1)), 0)
        self.assertEqual(utils.get_code_resend_remaining(
            CODE_EMAIL, now=now + timedelta(seconds=interval)), 0)

    @override_settings(CODE_SEND_LIMIT=3, CODE_SEND_WINDOW=3600,
                       CODE_RESEND_INTERVAL=0)
    def test_send_count_limit(self):
        """一个窗口内发满次数后被限制"""
        now = timezone.now()
        for _ in range(3):
            utils.record_code_sent(CODE_EMAIL, now=now)

        self.assertTrue(utils.is_code_send_limited(CODE_EMAIL, now=now))
        self.assertGreater(
            utils.get_code_send_window_remaining(CODE_EMAIL, now=now), 0)

    @override_settings(CODE_SEND_LIMIT=3, CODE_SEND_WINDOW=60,
                       CODE_RESEND_INTERVAL=0)
    def test_window_expiry_resets_count(self):
        """窗口过去后次数自动清零，可以重新发"""
        now = timezone.now()
        for _ in range(3):
            utils.record_code_sent(CODE_EMAIL, now=now)

        later = now + timedelta(seconds=61)
        self.assertFalse(utils.is_code_send_limited(CODE_EMAIL, now=later))
        self.assertEqual(
            utils.get_code_send_state(CODE_EMAIL, now=later)['count'], 0)
        self.assertEqual(
            utils.get_code_send_window_remaining(CODE_EMAIL, now=later), 0)

    def test_reset_code_send_state(self):
        """清空状态后可以立刻重新发送"""
        utils.record_code_sent(CODE_EMAIL)
        utils.reset_code_send_state(CODE_EMAIL)

        self.assertEqual(utils.get_code_resend_remaining(CODE_EMAIL), 0)
        self.assertFalse(utils.is_code_send_limited(CODE_EMAIL))


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class VerificationCodeThrottleViewTest(TestCase):
    """发送验证码接口接入节流"""

    def setUp(self):
        cache.clear()
        utils.reset_code_send_state(CODE_EMAIL)
        self.url = reverse('account:forget_password_code')

    def _post_code(self, email=CODE_EMAIL):
        return self.client.post(self.url, {'email': email})

    def test_first_request_sends_code(self):
        """首次请求正常发送，并告知前端倒计时秒数"""
        response = self._post_code()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b'ok')
        self.assertEqual(
            response['X-Code-Resend-After'],
            str(utils.get_code_resend_interval()))

    def test_second_request_is_throttled(self):
        """倒计时内重复请求被拒绝（429 + retry_after）"""
        self._post_code()
        response = self._post_code()

        self.assertEqual(response.status_code, 429)
        data = response.json()
        self.assertEqual(data['status'], 'too_frequent')
        self.assertGreater(data['retry_after'], 0)

    @override_settings(CODE_SEND_LIMIT=2, CODE_SEND_WINDOW=3600,
                       CODE_RESEND_INTERVAL=0)
    def test_send_count_limit_returns_limited(self):
        """超过次数上限后返回 limited"""
        self.assertEqual(self._post_code().status_code, 200)
        self.assertEqual(self._post_code().status_code, 200)

        response = self._post_code()
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json()['status'], 'limited')

    def test_invalid_email_keeps_old_contract(self):
        """邮箱非法时仍然返回原来的纯文本提示"""
        response = self._post_code('not-an-email')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode(), '错误的邮箱')
