from django import forms
from django.forms import ModelForm

from .models import Comment

class CommentForm(ModelForm):
    """评论提交表单：基于 Comment 模型生成，只让用户填写正文"""
    parent_comment_id = forms.IntegerField(
        widget=forms.HiddenInput, required=False)  # 隐藏字段：回复的父评论ID（楼中楼用）

    class Meta:
        model = Comment      # 绑定的模型
        fields = ['body']    # 只暴露正文字段让用户输入