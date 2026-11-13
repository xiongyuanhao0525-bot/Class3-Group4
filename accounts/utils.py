import logging
import math
import re
import typing
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from djangoblog.utils import send_email

logger = logging.getLogger(__name__)

_code_ttl = timedelta(minutes=5)

# ---------------------------------------------------------------------------
# 一、密码强度校验
#
# 注册、修改密码（找回密码）时统一走 check_password_strength，规则如下：
#   1. 长度 8 ~ 64 个字符
#   2. 至少包含 3 类字符：小写字母 / 大写字母 / 数字 / 特殊符号
#   3. 不能是常见弱口令（123456、password 之类）
#   4. 不能包含用户名（邮箱相似度由 Django 自带的 UserAttributeSimilarityValidator 负责）
#   5. 不能出现 4 位以上的连续字符（1234、abcd、qwerty）或重复字符（aaaa）
# ---------------------------------------------------------------------------

PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 64
PASSWORD_MIN_CHAR_TYPES = 3
PASSWORD_MIN_REPEAT_RUN = 4
PASSWORD_MIN_SEQUENCE_LEN = 4

# 字符类型 -> 中文名称，用于拼装提示语
CHAR_TYPE_LABELS = {
    'lower': '小写字母',
    'upper': '大写字母',
    'digit': '数字',
    'special': '特殊符号',
}

# 常见弱口令（统一小写比较）
WEAK_PASSWORDS = {
    '12345678', '123456789', '1234567890', '11111111', '00000000',
    'password', 'password1', 'password123', 'p@ssw0rd', 'passw0rd',
    'qwertyuiop', 'qwerty123', '1qaz2wsx', 'qwer1234', 'asdf1234',
    'abc12345', 'abcd1234', 'a1234567', 'aa123456', 'admin123',
    'admin888', 'iloveyou', 'woaini1314', 'zxcvbnm123',
}

# 键盘行与字母表，用于识别连续字符
_SEQUENCES = (
    '0123456789',
    'abcdefghijklmnopqrstuvwxyz',
    'qwertyuiop',
    'asdfghjkl',
    'zxcvbnm',
)

# 表单上展示给用户的规则说明
PASSWORD_RULES_TEXT = (
    '密码需 8-64 个字符，且至少包含 3 类字符（小写字母、大写字母、数字、特殊符号）；'
    '不能是常见弱口令，不能包含用户名，不能出现 4 位以上连续或重复的字符。'
)


def password_char_types(password: str) -> typing.List[str]:
    """返回密码中出现的字符类型列表，取值 lower/upper/digit/special

    Args:
        password: 待检查的密码
    Returns:
        出现的字符类型列表（可能为空）
    """
    types = []
    if not password:
        return types
    if re.search(r'[a-z]', password):
        types.append('lower')
    if re.search(r'[A-Z]', password):
        types.append('upper')
    if re.search(r'\d', password):
        types.append('digit')
    if re.search(r'[^0-9a-zA-Z]', password):
        types.append('special')
    return types


def has_sequential_chars(password: str, length: int = PASSWORD_MIN_SEQUENCE_LEN) -> bool:
    """密码中是否含有 length 位以上的顺序字符（正序或倒序）

    例如 1234、abcd、qwerty、4321。
    """
    if not password:
        return False
    lowered = password.lower()
    for seq in _SEQUENCES:
        for start in range(len(seq) - length + 1):
            chunk = seq[start:start + length]
            if chunk in lowered or chunk[::-1] in lowered:
                return True
    return False


def has_repeated_chars(password: str, length: int = PASSWORD_MIN_REPEAT_RUN) -> bool:
    """密码中是否含有 length 个以上连续重复的同一字符，例如 aaaa

    比较时忽略大小写，因此 Aaaa 同样视为 4 个连续重复字符。
    """
    if not password:
        return False
    return re.search(r'(.)\1{%d,}' % (length - 1), password,
                     re.IGNORECASE) is not None


def check_password_strength(password: str, username: str = '') -> typing.List[str]:
    """校验密码强度

    Args:
        password: 待校验密码
        username: 用户名，用于检查密码是否包含用户名
    Returns:
        错误信息列表；为空列表表示密码强度合格
    """
    errors = []

    if not password:
        return ['密码不能为空']

    if len(password) < PASSWORD_MIN_LENGTH:
        errors.append('密码长度不能少于 %d 个字符（当前 %d 个）' % (
            PASSWORD_MIN_LENGTH, len(password)))
    if len(password) > PASSWORD_MAX_LENGTH:
        errors.append('密码长度不能超过 %d 个字符（当前 %d 个）' % (
            PASSWORD_MAX_LENGTH, len(password)))

    types = password_char_types(password)
    if len(types) < PASSWORD_MIN_CHAR_TYPES:
        missing = '、'.join(
            label for key, label in CHAR_TYPE_LABELS.items() if key not in types)
        errors.append(
            '密码至少需要包含 %d 类字符（小写字母、大写字母、数字、特殊符号），'
            '当前 %d 类，还缺少：%s' % (
                PASSWORD_MIN_CHAR_TYPES, len(types), missing))

    if password.lower() in WEAK_PASSWORDS:
        errors.append('该密码属于常见弱口令，容易被猜解，请更换')

    if username and len(username) >= 3 and username.lower() in password.lower():
        errors.append('密码不能包含用户名')

    if has_sequential_chars(password):
        errors.append('密码不能包含 4 位以上连续字符（如 1234、abcd、qwerty）')

    if has_repeated_chars(password):
        errors.append('密码不能包含 %d 个以上连续重复的字符（如 aaaa）' % PASSWORD_MIN_REPEAT_RUN)

    return errors


def password_strength_level(password: str) -> str:
    """粗略评估密码强度等级，供前端展示强度条

    Returns:
        'empty'（未填写）/ 'weak' / 'medium' / 'strong'
    """
    if not password:
        return 'empty'

    score = 0
    if len(password) >= PASSWORD_MIN_LENGTH:
        score += 1
    if len(password) >= 12:
        score += 1
    if len(password) >= 16:
        score += 1
    types = len(password_char_types(password))
    if types >= 2:
        score += 1
    if types >= 3:
        score += 1
    if types >= 4:
        score += 1

    if score <= 2:
        return 'weak'
    if score <= 4:
        return 'medium'
    return 'strong'


# ---------------------------------------------------------------------------
# 二、登录失败锁定（防暴力破解）
#
# 同一账号连续失败 LOGIN_FAILURE_LIMIT 次后锁定 LOGIN_LOCK_SECONDS 秒；
# 存在用户走数据库字段（可在 admin 里看到），不存在的用户名走缓存（同样计数，
# 避免撞库试探），锁定后即使密码正确也不允许登录。
# ---------------------------------------------------------------------------

LOGIN_FAILURE_LIMIT = 5
LOGIN_LOCK_SECONDS = 15 * 60
LOGIN_FAILURE_WINDOW_SECONDS = 15 * 60

_LOGIN_LOCK_CACHE_PREFIX = 'accounts:login-lock:'


def get_login_failure_limit() -> int:
    return int(getattr(settings, 'LOGIN_FAILURE_LIMIT', LOGIN_FAILURE_LIMIT))


def get_login_lock_seconds() -> int:
    return int(getattr(settings, 'LOGIN_LOCK_SECONDS', LOGIN_LOCK_SECONDS))


def get_login_failure_window_seconds() -> int:
    return int(getattr(
        settings, 'LOGIN_FAILURE_WINDOW_SECONDS', LOGIN_FAILURE_WINDOW_SECONDS))


def _lock_cache_key(username: str) -> str:
    return '%s%s' % (_LOGIN_LOCK_CACHE_PREFIX, (username or '').strip().lower())


def _cached_lock_remaining(username: str, now=None) -> int:
    """读取缓存里（用户不存在的情况）的锁定剩余秒数"""
    now = now or timezone.now()
    state = cache.get(_lock_cache_key(username)) or {}
    lock_until = state.get('lock_until')
    if not lock_until:
        return 0
    remaining = lock_until - now.timestamp()
    return int(math.ceil(remaining)) if remaining > 0 else 0


def get_login_lock_remaining(username: str, user=None, now=None) -> int:
    """获取账号剩余锁定秒数，0 表示未锁定

    Args:
        username: 本次登录提交的用户名
        user: 用户名对应的用户对象；不存在时传 None
        now: 当前时间，测试时可注入
    """
    now = now or timezone.now()
    if user is not None:
        return user.get_lock_remaining_seconds(now)
    return _cached_lock_remaining(username, now)


def register_login_failure(username: str, user=None, now=None) -> typing.Tuple[int, int]:
    """记录一次登录失败

    Args:
        username: 本次登录提交的用户名
        user: 用户名对应的用户对象；不存在时传 None
        now: 当前时间，测试时可注入
    Returns:
        (累计失败次数, 剩余锁定秒数)，剩余锁定秒数大于 0 表示本次失败触发了锁定
    """
    now = now or timezone.now()
    limit = get_login_failure_limit()
    lock_seconds = get_login_lock_seconds()
    window_seconds = get_login_failure_window_seconds()

    if user is not None:
        count = user.register_login_failure(
            limit=limit,
            lock_seconds=lock_seconds,
            window_seconds=window_seconds,
            now=now)
        remaining = user.get_lock_remaining_seconds(now)
        if remaining:
            logger.warning('账号 %s 连续登录失败 %d 次，锁定 %d 秒', username, count, remaining)
        return count, remaining

    # 用户名不存在：用缓存按用户名计数，超过次数同样锁定
    key = _lock_cache_key(username)
    state = cache.get(key) or {}
    count = int(state.get('count') or 0)
    last_at = state.get('last_at')
    if last_at and (now.timestamp() - last_at) > window_seconds:
        count = 0
    count += 1

    new_state = {'count': count, 'last_at': now.timestamp(), 'lock_until': None}
    remaining = 0
    if count >= limit:
        new_state['lock_until'] = (now + timedelta(seconds=lock_seconds)).timestamp()
        new_state['count'] = 0
        remaining = lock_seconds
        logger.warning('用户名 %s 连续登录失败 %d 次，锁定 %d 秒', username, limit, lock_seconds)

    cache.set(key, new_state, max(lock_seconds, window_seconds) * 2)
    return count, remaining


def reset_login_failures(user, username: str = '') -> None:
    """登录成功后清空失败计数与锁定状态"""
    if user is not None:
        user.reset_login_failures()
    cache.delete(_lock_cache_key(username or getattr(user, 'username', '')))


def build_login_lock_message(remaining_seconds: int) -> str:
    """构造锁定提示文案

    get_lock_remaining_seconds() 会把剩余秒数向上取整 1 秒（避免刚锁定时显示 0），
    这里若再用 ceil 换算分钟，第一次提示就会把 15 分钟说成 16 分钟，因此先四舍五入。
    """
    minutes = max(1, int(round(remaining_seconds / 60.0)))
    return '该账号因连续登录失败已被临时锁定，请约 %d 分钟后再试' % minutes


# ---------------------------------------------------------------------------
# 三、找回密码验证码的发送节流（重发倒计时 + 发送次数限制）
#
#   * 两次发送之间至少间隔 CODE_RESEND_INTERVAL 秒（重发倒计时）
#   * 同一邮箱在 CODE_SEND_WINDOW 秒内最多发送 CODE_SEND_LIMIT 次
# ---------------------------------------------------------------------------

CODE_RESEND_INTERVAL = 60
CODE_SEND_LIMIT = 5
CODE_SEND_WINDOW = 60 * 60

_CODE_STATE_CACHE_PREFIX = 'accounts:code-state:'


def get_code_resend_interval() -> int:
    return int(getattr(settings, 'CODE_RESEND_INTERVAL', CODE_RESEND_INTERVAL))


def get_code_send_limit() -> int:
    return int(getattr(settings, 'CODE_SEND_LIMIT', CODE_SEND_LIMIT))


def get_code_send_window() -> int:
    return int(getattr(settings, 'CODE_SEND_WINDOW', CODE_SEND_WINDOW))


def _code_state_key(email: str) -> str:
    return '%s%s' % (_CODE_STATE_CACHE_PREFIX, (email or '').strip().lower())


def get_code_send_state(email: str, now=None) -> dict:
    """读取某个邮箱的验证码发送状态

    Returns:
        {'sent_at': float|None, 'count': int, 'window_start': float|None}
        sent_at 为上次发送时间戳，count 为当前窗口内已发送次数。
    """
    now = now or timezone.now()
    raw = cache.get(_code_state_key(email)) or {}
    if not isinstance(raw, dict):
        raw = {}

    count = int(raw.get('count') or 0)
    window_start = raw.get('window_start')
    if count and (not window_start or (now.timestamp() - window_start) > get_code_send_window()):
        # 计数窗口已过期，重新计数
        count = 0
        window_start = None

    return {'sent_at': raw.get('sent_at'), 'count': count, 'window_start': window_start}


def get_code_resend_remaining(email: str, now=None) -> int:
    """距离可以再次发送验证码还需要等待的秒数，0 表示可以立即发送"""
    now = now or timezone.now()
    sent_at = get_code_send_state(email, now)['sent_at']
    if not sent_at:
        return 0

    interval = get_code_resend_interval()
    elapsed = now.timestamp() - sent_at
    if elapsed >= interval:
        return 0
    return int(math.ceil(interval - elapsed))


def is_code_send_limited(email: str, now=None) -> bool:
    """该邮箱在当前窗口内的发送次数是否已经用完"""
    return get_code_send_state(email, now)['count'] >= get_code_send_limit()


def get_code_send_window_remaining(email: str, now=None) -> int:
    """距离发送次数窗口重置（可以再发满次数）还有多少秒"""
    now = now or timezone.now()
    window_start = get_code_send_state(email, now)['window_start']
    if not window_start:
        return 0
    remaining = get_code_send_window() - (now.timestamp() - window_start)
    return int(math.ceil(remaining)) if remaining > 0 else 0


def record_code_sent(email: str, now=None) -> dict:
    """记录一次验证码发送，返回记录后的状态"""
    now = now or timezone.now()
    state = get_code_send_state(email, now)
    new_state = {
        'sent_at': now.timestamp(),
        'count': state['count'] + 1,
        'window_start': state['window_start'] or now.timestamp(),
    }
    cache.set(
        _code_state_key(email),
        new_state,
        max(get_code_send_window(), get_code_resend_interval()))
    return new_state


def reset_code_send_state(email: str) -> None:
    """清空某个邮箱的发送状态（主要用于测试与排障）"""
    cache.delete(_code_state_key(email))


# ---------------------------------------------------------------------------
# 四、验证码相关（原有逻辑）
# ---------------------------------------------------------------------------


def send_verify_email(to_mail: str, code: str, subject: str = _("Verify Email")):
    """发送重设密码验证码
    Args:
        to_mail: 接受邮箱
        subject: 邮件主题
        code: 验证码
    """
    html_content = _(
        "You are resetting the password, the verification code is：%(code)s, valid within 5 minutes, please keep it "
        "properly") % {'code': code}
    send_email([to_mail], subject, html_content)


def verify(email: str, code: str) -> typing.Optional[str]:
    """验证code是否有效
    Args:
        email: 请求邮箱
        code: 验证码
    Return:
        如果有错误就返回错误str
    Node:
        这里的错误处理不太合理，应该采用raise抛出
        否测调用方也需要对error进行处理
    """
    cache_code = get_code(email)
    if cache_code != code:
        return gettext("Verification code error")


def set_code(email: str, code: str):
    """设置code"""
    cache.set(email, code, _code_ttl.seconds)


def get_code(email: str) -> typing.Optional[str]:
    """获取code"""
    return cache.get(email)
