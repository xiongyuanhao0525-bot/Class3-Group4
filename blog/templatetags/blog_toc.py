# -*- coding: utf-8 -*-
# ============================================================
# blog/templatetags/blog_toc.py
# 功能点1：文章 TOC 自动生成（陈汉佳 #chj，2415304339）
# 作用：从文章 Markdown 正文里解析 #/##/### 标题，生成侧边目录 + 锚点
# 模板用法：{% load blog_toc %}{{ article.body|markdown_toc }}
# ============================================================
import re

from django import template
from django.utils.safestring import mark_safe

register = template.Library()

# 匹配 Markdown 标题行：开头 1~3 个 #，空格后是标题文字
# MULTILINE 让 ^/$ 匹配每一行而不是整个字符串
HEADING_RE = re.compile(r'^(#{1,3})\s+(.+?)\s*#*\s*$', re.MULTILINE)


def build_toc(body):
    """
    把 Markdown 正文解析成目录结构。
    返回：[(level, text, anchor), ...]
      level  —— 1/2/3 对应 #/##/###
      text   —— 标题文字（去掉前后空格）
      anchor —— 锚点 id，形如 toc-1、toc-2，保证唯一
    """
    toc = []
    if not body:
        return toc
    for match in HEADING_RE.finditer(body):
        level = len(match.group(1))
        text = match.group(2).strip()
        # 用序号当锚点，简单且不会重复
        anchor = 'toc-%d' % (len(toc) + 1)
        toc.append((level, text, anchor))
    return toc


@register.filter(is_safe=True)
def markdown_toc(body):
    """
    模板过滤器：把 Markdown 正文渲染成侧边目录 HTML。
    没有标题时返回空字符串，模板自动不显示目录块。
    """
    items = build_toc(body)
    if not items:
        return ''
    lines = ['<ul class="chj-toc">']
    for level, text, anchor in items:
        # class 带层级，方便 CSS 控制缩进
        lines.append(
            '<li class="chj-toc-lv%d"><a href="#%s">%s</a></li>' % (level, anchor, text)
        )
    lines.append('</ul>')
    return mark_safe('\n'.join(lines))
