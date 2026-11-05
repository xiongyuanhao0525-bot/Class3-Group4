"""
accounts 模块安全功能测试

覆盖功能：密码强度校验（注册、找回密码时校验长度 / 字符类型等强度并给出提示）
"""
from django.test import TestCase
from django.urls import reverse

from accounts import utils
from accounts.forms import ForgetPasswordForm, RegisterForm
from accounts.models import BlogUser

# 一个符合强度规则的密码：4 类字符、13 位、无连续/重复片段
STRONG_PASSWORD = 'Blog@2026#Sec'
# 明显的弱密码：只有小写字母 + 数字，且有重复字符
WEAK_PASSWORD = 'aaaa1111'


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
