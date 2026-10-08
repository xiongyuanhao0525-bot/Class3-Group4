# -*- coding: utf-8 -*-
# 博客后台管理模块（blog/admin.py）
# 作用：注册 Django 自带的 Admin 后台，管理博客的文章、标签、分类、
#       友链、侧边栏和博客全局设置。
# 说明：以下只添加中文注释，不修改任何代码逻辑。
from django import forms
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

# Register your models here.
# 导入本应用的数据模型：文章、分类、标签、友链、侧边栏、博客设置
from .models import Article, Category, Tag, Links, SideBar, BlogSettings


class ArticleForm(forms.ModelForm):
    # body = forms.CharField(widget=AdminPagedownWidget())
    # 上面这行是被注释掉的富文本编辑器控件，暂时不使用
    class Meta:
        # 表单关联的文章模型
        model = Article
        # 表单包含模型的所有字段
        fields = '__all__'


# 以下 4 个函数是 Admin 后台的"批量操作"动作，
# 用于在文章列表页勾选多篇文章后统一修改状态。


def makr_article_publish(modeladmin, request, queryset):
    # 批量发布：把选中的文章状态改为 'p'（publish 已发布）
    queryset.update(status='p')


def draft_article(modeladmin, request, queryset):
    # 批量转为草稿：把选中的文章状态改为 'd'（draft 草稿）
    queryset.update(status='d')


def close_article_commentstatus(modeladmin, request, queryset):
    # 批量关闭评论：把选中文章的评论状态改为 'c'（close 关闭）
    queryset.update(comment_status='c')


def open_article_commentstatus(modeladmin, request, queryset):
    # 批量开启评论：把选中文章的评论状态改为 'o'（open 开启）
    queryset.update(comment_status='o')


# 为上面 4 个批量操作设置后台列表中显示的英文说明（本地化翻译用）
makr_article_publish.short_description = _('Publish selected articles')
draft_article.short_description = _('Draft selected articles')
close_article_commentstatus.short_description = _('Close article comments')
open_article_commentstatus.short_description = _('Open article comments')


class ArticlelAdmin(admin.ModelAdmin):
    # 文章管理后台配置类：定义文章在 Admin 里的列表展示、搜索、过滤方式
    list_per_page = 20
    # 列表每页显示 20 条
    search_fields = ('body', 'title')
    # 支持按文章正文和标题搜索
    form = ArticleForm
    # 使用上面定义的文章表单
    list_display = (
        'id',
        'title',
        'author',
        'link_to_category',
        'creation_time',
        'views',
        'status',
        'type',
        'article_order')
    # 列表页显示的字段：编号、标题、作者、分类链接、创建时间、浏览量、状态、类型、排序
    list_display_links = ('id', 'title')
    # 点击"编号"或"标题"可进入文章编辑页
    list_filter = ('status', 'type', 'category')
    # 列表右侧的筛选栏：按状态、类型、分类筛选
    date_hierarchy = 'creation_time'
    # 顶部按创建时间提供日期层级导航
    filter_horizontal = ('tags',)
    # 标签字段用横向选择器，方便多选
    exclude = ('creation_time', 'last_modify_time')
    # 隐藏创建时间和最后修改时间字段（系统自动记录）
    view_on_site = True
    # 提供"在网站中查看"按钮
    actions = [
        makr_article_publish,
        draft_article,
        close_article_commentstatus,
        open_article_commentstatus]
    # 列表页可用的批量操作：发布、草稿、关评论、开评论
    raw_id_fields = ('author', 'category',)
    # 作者和分类使用原始 ID 输入框，避免大量选项卡顿

    def link_to_category(self, obj):
        # 自定义列：把文章所属分类显示为可点击的后台链接
        info = (obj.category._meta.app_label, obj.category._meta.model_name)
        # 取分类的应用名和模型名，用于拼后台 URL
        link = reverse('admin:%s_%s_change' % info, args=(obj.category.id,))
        # 生成跳转到该分类编辑页的链接
        return format_html(u'<a href="%s">%s</a>' % (link, obj.category.name))
        # 返回带链接的分类名称

    link_to_category.short_description = _('category')
    # 该列的列头显示为"分类"

    def get_form(self, request, obj=None, **kwargs):
        # 自定义后台表单：限制作者下拉框只显示超级管理员
        form = super(ArticlelAdmin, self).get_form(request, obj, **kwargs)
        # 先调用父类生成标准表单
        form.base_fields['author'].queryset = get_user_model(
        ).objects.filter(is_superuser=True)
        # 把"作者"字段的候选用户过滤为超管，避免普通用户可选
        return form

    def save_model(self, request, obj, form, change):
        # 保存文章时的钩子（当前未附加额外逻辑，仅调用父类保存）
        super(ArticlelAdmin, self).save_model(request, obj, form, change)

    def get_view_on_site_url(self, obj=None):
        # 自定义"在网站中查看"跳转地址：有文章返回文章完整 URL，否则返回站点域名
        if obj:
            url = obj.get_full_url()
            # 文章存在：使用文章的完整链接
            return url
        else:
            from djangoblog.utils import get_current_site
            # 文章不存在：导入工具函数获取当前站点
            site = get_current_site().domain
            # 返回站点域名
            return site


class TagAdmin(admin.ModelAdmin):
    # 标签管理后台：隐藏自动生成的字段，只保留标签名
    exclude = ('slug', 'last_mod_time', 'creation_time')


class CategoryAdmin(admin.ModelAdmin):
    # 分类管理后台：列表显示分类名、父分类、排序索引；隐藏自动字段
    list_display = ('name', 'parent_category', 'index')
    exclude = ('slug', 'last_mod_time', 'creation_time')


class LinksAdmin(admin.ModelAdmin):
    # 友链管理后台：隐藏自动生成的时间字段
    exclude = ('last_mod_time', 'creation_time')


class SideBarAdmin(admin.ModelAdmin):
    # 侧边栏管理后台：列表显示名称、内容、是否启用、排序序号
    list_display = ('name', 'content', 'is_enable', 'sequence')
    exclude = ('last_mod_time', 'creation_time')


class BlogSettingsAdmin(admin.ModelAdmin):
    """单例配置Admin - 直接跳转到编辑页面"""
    # 博客全局设置：只允许存在一条配置，进入列表直接跳到编辑页

    def has_add_permission(self, request):
        """如果已经存在配置，则禁止添加"""
        # 已存在设置记录时，不允许再新增，保证"单例"
        return not BlogSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        """禁止删除配置"""
        # 全局设置不允许删除
        return False

    def changelist_view(self, request, extra_context=None):
        """列表页直接跳转到编辑页面"""
        # 覆写列表页：不再展示列表，而是直接进入编辑/新增页
        from django.http import HttpResponseRedirect
        # 导入重定向响应
        obj = BlogSettings.objects.first()
        # 取第一条（唯一）设置记录
        if obj:
            # 已存在设置：跳转到该记录的编辑页
            return HttpResponseRedirect(
                reverse('admin:blog_blogsettings_change', args=[obj.pk])
            )
        # 如果不存在配置，跳转到添加页面
        return HttpResponseRedirect(
            reverse('admin:blog_blogsettings_add')
        )

    def save_model(self, request, obj, form, change):
        """保存设置时清除缓存"""
        # 保存全局设置后自动清空缓存，让新设置立即生效
        super().save_model(request, obj, form, change)
        # 先调用父类完成保存
        # 确保缓存被清除
        from djangoblog.utils import cache
        # 导入项目缓存对象
        cache.clear()
        # 清空全部缓存，避免旧设置残留
        self.message_user(request, '设置已保存，缓存已清除')
        # 后台弹出保存成功的提示
