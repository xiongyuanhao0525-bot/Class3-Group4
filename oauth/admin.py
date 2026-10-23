"""
oauth/admin.py
==============
#yjh 本模块注册 oauth 应用的 Django Admin 后台管理：
    - OAuthUserAdmin   第三方用户列表（只读，禁新增），带头像预览和本地账号跳转链接
    - OAuthConfigAdmin 第三方应用配置管理（增删改查）
"""
import logging

from django.contrib import admin
# Register your models here.
from django.urls import reverse
from django.utils.html import format_html

logger = logging.getLogger(__name__)


class OAuthUserAdmin(admin.ModelAdmin):
    # yjh: 第三方用户后台：按昵称/邮箱搜索，每页 20 条
    search_fields = ('nickname', 'email')
    list_per_page = 20
    list_display = (
        'id',
        'nickname',
        'link_to_usermodel',
        'show_user_image',
        'type',
        'email',
    )
    list_display_links = ('id', 'nickname')
    list_filter = ('author', 'type',)
    readonly_fields = []

    def get_readonly_fields(self, request, obj=None):
        # yjh: 动态把所有字段（含多对多）都设为只读——第三方用户信息
        # 由登录流程自动写入，不应在后台手工编辑
        return list(self.readonly_fields) + \
               [field.name for field in obj._meta.fields] + \
               [field.name for field in obj._meta.many_to_many]

    def has_add_permission(self, request):
        # yjh: 禁止后台手动新增第三方用户（数据只能来自真实登录流程）
        return False

    def link_to_usermodel(self, obj):
        # yjh: 列表页渲染"本地账号"列：点击跳转到对应用户的编辑页
        if obj.author:
            info = (obj.author._meta.app_label, obj.author._meta.model_name)
            link = reverse('admin:%s_%s_change' % info, args=(obj.author.id,))
            return format_html(
                u'<a href="%s">%s</a>' %
                (link, obj.author.nickname if obj.author.nickname else obj.author.email))

    def show_user_image(self, obj):
        # yjh: 列表页渲染"头像"列：用 format_html 输出 50x50 图片
        img = obj.picture
        return format_html(
            u'<img src="%s" style="width:50px;height:50px"></img>' %
            (img))

    link_to_usermodel.short_description = '用户'
    show_user_image.short_description = '用户头像'


class OAuthConfigAdmin(admin.ModelAdmin):
    # yjh: 配置后台：列表直接暴露 appkey/appsecret 方便核对（仅管理员可见）
    list_display = ('type', 'appkey', 'appsecret', 'is_enable')
    list_filter = ('type',)
