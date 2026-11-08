# -*- coding: utf-8 -*-
"""#jxr comments app 敏感词过滤模块（纯函数实现，不依赖数据库）。

设计目标：
1. 词库可配置：优先读取 settings.COMMENT_SENSITIVE_WORDS，未配置时使用内置最小词库；
2. 抗简单绕过：匹配前统一做 NFKC 归一化 + 大小写折叠 + 去空白/标点，
   因此“广 告”“广*告”“ＧＵＡＮＧＧＡＯ”这类拆字、插符号的写法同样能命中；
3. 两种处置策略（settings.COMMENT_SENSITIVE_WORD_MODE）：
   - block（默认）：拦截提交，由表单抛错让用户修改；
   - mask：放行，但把命中词替换为等长的 *，落库前完成脱敏；
4. 只处理文本，不碰模型/视图，方便单测复用，也方便后续做历史数据清洗。

#jxr 说明：词库只放“广告/诈骗/违禁交易”这类通用垃圾信息关键词，
#jxr 不放入人身攻击词，避免把正常讨论误伤为违规。
"""

import re
import unicodedata

from django.conf import settings

# #jxr 内置最小词库：仅作兜底，生产环境应在 settings 中按站点实际情况配置
DEFAULT_SENSITIVE_WORDS = (
    '广告',
    '加微信',
    '加qq',
    '代开发票',
    '刷单',
    '刷信誉',
    '网赚',
    '博彩',
    '赌博',
    '办证',
    '贷款',
    '传销',
    '诈骗',
    '色情',
    '枪支',
    '毒品',
    'spam',
    'casino',
    'porn',
)

# #jxr 处置模式常量
MODE_BLOCK = 'block'   # 拦截：不落库，返回表单错误
MODE_MASK = 'mask'     # 替换：落库前把命中词换成 *
VALID_MODES = (MODE_BLOCK, MODE_MASK)

# #jxr 词库字符串分隔符：英文逗号/中文逗号/顿号/空白，方便在 settings 里写一行配置
_WORD_SPLIT_RE = re.compile(r'[,，、\s]+')


def get_sensitive_words():
    """#jxr 读取当前生效的词库。

    支持三种配置形态：
    - list/tuple/set：直接逐项使用；
    - str：按逗号/顿号/空白切分；
    - 未配置或配置为空：回退到 DEFAULT_SENSITIVE_WORDS。

    :return: tuple[str, ...] 去重后的词库（保持配置顺序）
    """
    configured = getattr(settings, 'COMMENT_SENSITIVE_WORDS', None)
    if configured is None:
        configured = DEFAULT_SENSITIVE_WORDS
    elif isinstance(configured, str):
        configured = _WORD_SPLIT_RE.split(configured)

    # #jxr dict.fromkeys 既去重又保持原顺序；strip 后再过滤空串
    words = [str(word).strip() for word in configured if str(word).strip()]
    # #jxr 配置成空列表/空串时回退内置词库：宁可多拦，也不要因为一处配置失误让过滤失效
    if not words:
        words = [str(word).strip() for word in DEFAULT_SENSITIVE_WORDS if str(word).strip()]
    return tuple(dict.fromkeys(words))


def get_filter_mode():
    """#jxr 读取处置模式；非法值一律回退为 block，保证“默认拦截”不会被误配成放行。"""
    mode = str(getattr(settings, 'COMMENT_SENSITIVE_WORD_MODE', MODE_BLOCK)).strip().lower()
    return mode if mode in VALID_MODES else MODE_BLOCK


def _normalize_word(word):
    """#jxr 单词归一化：与正文使用同一套规则，保证“词”和“文”在同一坐标系里比较。"""
    return _normalize_with_map(word)[0]


def _normalize_with_map(text):
    """#jxr 归一化正文，并保留“归一化字符 → 原文下标”的映射。

    归一化步骤：逐字符 NFKC（全角转半角、兼容字符归一）→ casefold（大小写折叠）
    → 只保留字母/数字/汉字（去掉空格、标点、符号、emoji）。

    :param text: 原始文本
    :return: (归一化字符串, 每个字符对应的原文下标列表)
    """
    normalized_chars = []
    index_map = []
    for position, char in enumerate(text or ''):
        folded = unicodedata.normalize('NFKC', char).casefold()
        for piece in folded:
            # #jxr isalnum() 对中文、英文字母、数字都为真，正好覆盖需要保留的字符
            if piece.isalnum():
                normalized_chars.append(piece)
                index_map.append(position)
    return ''.join(normalized_chars), index_map


def find_sensitive_words(text):
    """#jxr 找出正文中命中的敏感词（含拆字/插符号的变体）。

    :param text: 待检测正文
    :return: list[str] 命中的词（按词库顺序，去重）
    """
    normalized_text = _normalize_with_map(text)[0]
    if not normalized_text:
        return []

    hits = []
    for word in get_sensitive_words():
        normalized_word = _normalize_word(word)
        # #jxr 归一化后为空的词（例如只由符号组成）直接跳过，避免“空串匹配一切”
        if normalized_word and normalized_word in normalized_text:
            hits.append(word)
    return hits


def contains_sensitive_words(text):
    """#jxr 布尔版检测，供视图/管理命令做快速判断。"""
    return bool(find_sensitive_words(text))


def _merge_spans(spans):
    """#jxr 合并重叠/相邻的原文区间，避免同一段文字被重复打星号。"""
    if not spans:
        return []
    spans.sort()
    merged = [list(spans[0])]
    for start, end in spans[1:]:
        if start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return merged


def mask_sensitive_words(text):
    """#jxr 把命中的敏感词替换为等长的 *。

    采用“归一化定位 + 原文区间替换”的方式：即使原文写成“广 告”，
    也会把“广 告”这三个字符整体替换为“***”，不会只替换其中一部分。

    :param text: 原始正文
    :return: 脱敏后的正文；未命中时原样返回
    """
    if not text:
        return text

    normalized_text, index_map = _normalize_with_map(text)
    if not normalized_text:
        return text

    spans = []
    for word in get_sensitive_words():
        normalized_word = _normalize_word(word)
        if not normalized_word:
            continue
        start = normalized_text.find(normalized_word)
        while start != -1:
            raw_start = index_map[start]
            raw_end = index_map[start + len(normalized_word) - 1] + 1
            spans.append((raw_start, raw_end))
            # #jxr 从下一个字符继续找，允许同一句话里多次出现同一个词
            start = normalized_text.find(normalized_word, start + len(normalized_word))

    merged = _merge_spans(spans)
    if not merged:
        return text

    pieces = []
    cursor = 0
    for start, end in merged:
        pieces.append(text[cursor:start])
        pieces.append('*' * (end - start))
        cursor = end
    pieces.append(text[cursor:])
    return ''.join(pieces)


def describe_sensitive_hits(hits, keep_first=True):
    """#jxr 生成给用户看的命中提示：保留首字、其余打码，避免把违禁词原样回显。

    :param hits: find_sensitive_words 的返回值
    :param keep_first: 是否保留首字（True 时“广告”→“广*”）
    :return: str 形如“广*、加****”的提示文案
    """
    if not hits:
        return ''
    described = []
    for word in hits:
        if keep_first and len(word) > 1:
            described.append(word[0] + '*' * (len(word) - 1))
        else:
            described.append('*' * len(word))
    return '、'.join(described)


def check_comment_body(body):
    """#jxr 评论正文的统一检查入口（表单和后续清洗任务都调它）。

    :param body: 用户提交的原始正文
    :return: (是否放行, 处置后的正文, 命中词列表, 生效模式)
             - block 模式命中：返回 (False, 原文, 命中词, 'block')
             - mask 模式命中：返回 (True, 脱敏后的正文, 命中词, 'mask')
             - 未命中：返回 (True, 原文, [], mode)
    """
    mode = get_filter_mode()
    hits = find_sensitive_words(body)

    if not hits:
        return True, body, [], mode

    if mode == MODE_MASK:
        return True, mask_sensitive_words(body), hits, mode

    return False, body, hits, mode
