# accounts/forms.py
# 用户模块表单层：登录 / 注册 / 找回密码 表单
# 注释人：陈汉佳 #chj （只加注释，不改逻辑）
from django import forms
from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.core.exceptions import ValidationError
from django.forms import widgets
from django.utils.translation import gettext_lazy as _
from . import utils
from .models import BlogUser


class LoginForm(AuthenticationForm):
    # #chj 登录表单：继承 Django 内置认证表单，只美化输入框样式
    def __init__(self, *args, **kwargs):
        super(LoginForm, self).__init__(*args, **kwargs)
        # #chj 用户名输入框加上 Bootstrap 样式和占位提示
        self.fields['username'].widget = widgets.TextInput(
            attrs={'placeholder': "username", "class": "form-control"})
        # #chj 密码框使用 PasswordInput 密文显示
        self.fields['password'].widget = widgets.PasswordInput(
            attrs={'placeholder': "password", "class": "form-control"})


class RegisterForm(UserCreationForm):
    # #chj 注册表单：用户名 + 邮箱 + 两次密码
    def __init__(self, *args, **kwargs):
        super(RegisterForm, self).__init__(*args, **kwargs)
        # #chj 各字段统一套 Bootstrap 样式
        self.fields['username'].widget = widgets.TextInput(
            attrs={'placeholder': "username", "class": "form-control"})
        self.fields['email'].widget = widgets.EmailInput(
            attrs={'placeholder': "email", "class": "form-control"})
        self.fields['password1'].widget = widgets.PasswordInput(
            attrs={'placeholder': "password", "class": "form-control"})
        self.fields['password2'].widget = widgets.PasswordInput(
            attrs={'placeholder': "repeat password", "class": "form-control"})

    def clean_email(self):
        # #chj 校验邮箱是否已被注册，重复则报错
        email = self.cleaned_data['email']
        if get_user_model().objects.filter(email=email).exists():
            raise ValidationError(_("email already exists"))
        return email

    class Meta:
        model = get_user_model()
        fields = ("username", "email")


class ForgetPasswordForm(forms.Form):
    # #chj 找回密码表单：新密码 + 确认密码 + 邮箱 + 验证码
    new_password1 = forms.CharField(
        label=_("New password"),
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                'placeholder': _("New password")
            }
        ),
    )

    new_password2 = forms.CharField(
        label="确认密码",
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                'placeholder': _("Confirm password")
            }
        ),
    )

    email = forms.EmailField(
        label='邮箱',
        widget=forms.TextInput(
            attrs={
                'class': 'form-control',
                'placeholder': _("Email")
            }
        ),
    )

    code = forms.CharField(
        label=_('Code'),
        widget=forms.TextInput(
            attrs={
                'class': 'form-control',
                'placeholder': _("Code")
            }
        ),
    )

    def clean_new_password2(self):
        # #chj 确认两次密码一致，并通过 Django 密码强度校验
        password1 = self.data.get("new_password1")
        password2 = self.data.get("new_password2")
        if password1 and password2 and password1 != password2:
            raise ValidationError(_("passwords do not match"))
        password_validation.validate_password(password2)

        return password2

    def clean_email(self):
        # #chj 校验邮箱必须已注册（防止给陌生邮箱发验证码）
        user_email = self.cleaned_data.get("email")
        if not BlogUser.objects.filter(
                email=user_email
        ).exists():
            # todo 这里的报错提示可以判断一个邮箱是不是注册过，如果不想暴露可以修改
            raise ValidationError(_("email does not exist"))
        return user_email

    def clean_code(self):
        # #chj 校验邮箱验证码是否正确（查缓存）
        code = self.cleaned_data.get("code")
        error = utils.verify(
            email=self.cleaned_data.get("email"),
            code=code,
        )
        if error:
            raise ValidationError(error)
        return code


class ForgetPasswordCodeForm(forms.Form):
    # #chj 仅含邮箱字段的表单，用于请求发送验证码
    email = forms.EmailField(
        label=_('Email'),
    )
