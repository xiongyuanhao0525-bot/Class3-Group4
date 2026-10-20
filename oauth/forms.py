"""
oauth/forms.py
==============
#yjh 本模块定义 oauth 应用的表单：
    - RequireEmailForm 第三方登录缺少邮箱时，引导用户补填邮箱的表单
"""
from django.contrib.auth.forms import forms
from django.forms import widgets


class RequireEmailForm(forms.Form):
    # yjh: 补填邮箱表单：email 必填（Django 自动做邮箱格式校验），
    # oauthid 隐藏字段用于提交时定位是哪条 OAuthUser 记录
    email = forms.EmailField(label='电子邮箱', required=True)
    oauthid = forms.IntegerField(widget=forms.HiddenInput, required=False)

    def __init__(self, *args, **kwargs):
        super(RequireEmailForm, self).__init__(*args, **kwargs)
        # yjh: 构造时替换 email 控件：加占位符和 Bootstrap 样式类，美化前端展示
        self.fields['email'].widget = widgets.EmailInput(
            attrs={'placeholder': "email", "class": "form-control"})
