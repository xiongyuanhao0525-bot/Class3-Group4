# -*- coding: utf-8 -*-
# ============================================================
# blog/templatetags/blog_search.py
# 功能点3：搜索结果关键词高亮（陈汉佳 #chj，2415304339）
# 作用：把正文里出现的搜索词包成 <mark>，用户一眼看到命中位置
# 模板用法：{% load blog_search %}{{ result.object.body|search_highlight:query }}
# ============================================================
import re

from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter(is_safe=True)
def search_highlight(text, query):
    """
    把 text 里出现的 query 关键词包成 <mark>。
    先 escape 正文再高亮，避免把用户输入的 HTML 直接渲染出来（防 XSS）。
    query 为空时直接返回转义后的原文，不加任何标签。
    """
    safe_text = escape(text or '')
    if not query:
        return safe_text
    # 对 query 也先转义再正则转义特殊字符
    safe_query = re.escape(escape(query))
    # IGNORECASE 让"Python"也能命中"python"
    highlighted = re.sub(
        r'(%s)' % safe_query, r'<mark class="chj-hit">\1</mark>',
        safe_text, flags=re.IGNORECASE
    )
    return mark_safe(highlighted)
