from django import forms
from django.forms import ModelForm
from django.utils.translation import gettext_lazy as _

from .models import Comment
from .sensitive_words import check_comment_body, describe_sensitive_hits

# #jxr 评论提交表单：基于 Comment 模型自动生成
# #jxr 只暴露 body 字段给用户输入，其余字段（作者/文章/审核状态/父评论）由视图层逻辑填充
# #jxr 敏感词过滤放在表单 clean_body 中：拦截模式下直接抛表单错误，替换模式下改写正文再落库


class CommentForm(ModelForm):
    """评论提交表单：基于 Comment 模型生成，只让用户填写正文"""
    parent_comment_id = forms.IntegerField(
        widget=forms.HiddenInput, required=False)  # 隐藏字段：回复的父评论ID（楼中楼用）

    class Meta:
        model = Comment      # 绑定的模型
        fields = ['body']    # 只暴露正文字段让用户输入

    def clean_body(self):
        """#jxr 校验正文：非空校验 + 敏感词过滤（拦截或替换）。

        过滤逻辑全部委托给 comments.sensitive_words.check_comment_body，
        表单只负责把结果翻译成 Django 的校验错误或改写后的正文。
        """
        body = (self.cleaned_data.get('body') or '').strip()

        # #jxr 全空白内容按空评论处理，避免“三个空格”绕过非空校验
        if not body:
            raise forms.ValidationError(_('评论内容不能为空。'))

        allowed, filtered_body, hits, mode = check_comment_body(body)

        if not allowed:
            # #jxr 报错里只回显打码后的词，避免把敏感词原样弹回页面
            raise forms.ValidationError(
                _('评论包含敏感词：%(words)s，请修改后再提交。')
                % {'words': describe_sensitive_hits(hits)})

        # #jxr 替换模式：返回脱敏后的正文，后续 save 落库的就是这份文本
        return filtered_body
