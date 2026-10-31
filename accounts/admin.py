# accounts/admin.py
# 用户模块 Django 后台管理配置
# 注释人：陈汉佳 #chj （只加注释，不改逻辑）
from django import forms
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserChangeForm
from django.contrib.auth.forms import UsernameField
from django.utils.translation import gettext_lazy as _

# Register your models here.
from .models import BlogUser


class BlogUserCreationForm(forms.ModelForm):
    # #chj 后台"新增用户"专用表单：需要手动输入两次密码
    password1 = forms.CharField(label=_('password'), widget=forms.PasswordInput)
    password2 = forms.CharField(label=_('Enter password again'), widget=forms.PasswordInput)

    class Meta:
        model = BlogUser
        fields = ('email',)

    def clean_password2(self):
        # Check that the two password entries match
        # #chj 校验两次密码输入一致
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError(_("passwords do not match"))
        return password2

    def save(self, commit=True):
        # Save the provided password in hashed format
        # #chj 密码哈希化后再入库，并标记来源为后台创建
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.source = 'adminsite'
            user.save()
        return user


class BlogUserChangeForm(UserChangeForm):
    # #chj 后台"修改用户"表单：复用 Django 默认的 UserChangeForm
    class Meta:
        model = BlogUser
        fields = '__all__'
        field_classes = {'username': UsernameField}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class BlogUserAdmin(UserAdmin):
    # #chj 用户后台管理：绑定增改表单，配置列表展示字段
    form = BlogUserChangeForm
    add_form = BlogUserCreationForm
    # #chj 列表页展示的列
    list_display = (
        'id',
        'nickname',
        'username',
        'email',
        'last_login',
        'date_joined',
        'source')
    # #chj 可点击进入详情页的列
    list_display_links = ('id', 'username')
    # #chj 默认按 id 倒序
    ordering = ('-id',)
    # #chj 支持按用户名/昵称/邮箱搜索
    search_fields = ('username', 'nickname', 'email')
