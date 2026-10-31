from django.contrib import admin  # Django 后台管理框架
from django.urls import reverse  # 反向解析后台 URL
from django.utils.html import format_html  # 构造安全的 HTML 片段（自动转义）
from django.utils.translation import gettext_lazy as _

from .models import Comment, CommentReaction

# #jxr 本文件为 comments app 的后台管理配置：
# #jxr - 两个批量动作：批量禁用/启用评论（用于管理员审核）
# #jxr - CommentAdmin：评论列表页配置，含跳转作者/文章的链接列
# #jxr - CommentReactionAdmin：表情反应列表页配置


def disable_commentstatus(modeladmin, request, queryset):
    # #jxr 后台批量动作：将选中的评论统一置为 is_enable=False（下架/不展示）
    queryset.update(is_enable=False)


def enable_commentstatus(modeladmin, request, queryset):
    # #jxr 后台批量动作：将选中的评论统一置为 is_enable=True（审核通过/展示）
    queryset.update(is_enable=True)


disable_commentstatus.short_description = _('Disable comments')
enable_commentstatus.short_description = _('Enable comments')


class CommentAdmin(admin.ModelAdmin):
    list_per_page = 20  # #jxr 每页显示20条，控制后台列表页体积
    list_display = (
        'id',
        'body',
        'link_to_userinfo',
        'link_to_article',
        'is_enable',
        'creation_time')
    list_display_links = ('id', 'body', 'is_enable')
    list_filter = ('is_enable',)  # #jxr 按审核状态过滤，方便管理员挑出待审评论
    exclude = ('creation_time', 'last_modify_time')
    actions = [disable_commentstatus, enable_commentstatus]  # #jxr 注册批量审核动作
    raw_id_fields = ('author', 'article')  # #jxr 外键用原始ID输入，避免大数据量下拉卡顿
    search_fields = ('body',)  # #jxr 支持按正文搜索

    def link_to_userinfo(self, obj):
        # #jxr 构造"作者"列的超链接：点击跳转到该用户的后台编辑页
        info = (obj.author._meta.app_label, obj.author._meta.model_name)
        link = reverse('admin:%s_%s_change' % info, args=(obj.author.id,))
        return format_html(
            u'<a href="%s">%s</a>' %
            (link, obj.author.nickname if obj.author.nickname else obj.author.email))

    def link_to_article(self, obj):
        # #jxr 构造"文章"列的超链接：点击跳转到该文章的后台编辑页
        info = (obj.article._meta.app_label, obj.article._meta.model_name)
        link = reverse('admin:%s_%s_change' % info, args=(obj.article.id,))
        return format_html(
            u'<a href="%s">%s</a>' % (link, obj.article.title))

    link_to_userinfo.short_description = _('User')
    link_to_article.short_description = _('Article')


class CommentReactionAdmin(admin.ModelAdmin):
    list_display = ('id', 'reaction_type', 'link_to_comment', 'link_to_user', 'created_at')
    list_display_links = ('id', 'reaction_type')
    list_filter = ('reaction_type', 'created_at')  # #jxr 按表情类型/时间过滤统计
    raw_id_fields = ('comment', 'user')
    search_fields = ('comment__body', 'user__username')  # #jxr 跨表搜索：评论正文或用户名
    date_hierarchy = 'created_at'  # #jxr 后台时间层级钻取（年→月→日）

    def link_to_comment(self, obj):
        # #jxr 构造"评论"列超链接：跳转到对应评论的后台编辑页
        info = (obj.comment._meta.app_label, obj.comment._meta.model_name)
        link = reverse('admin:%s_%s_change' % info, args=(obj.comment.id,))
        return format_html(
            u'<a href="%s">Comment #%s</a>' % (link, obj.comment.id))

    def link_to_user(self, obj):
        # #jxr 构造"用户"列超链接：跳转到点表情用户的后台编辑页
        info = (obj.user._meta.app_label, obj.user._meta.model_name)
        link = reverse('admin:%s_%s_change' % info, args=(obj.user.id,))
        return format_html(
            u'<a href="%s">%s</a>' %
            (link, obj.user.nickname if obj.user.nickname else obj.user.username))

    link_to_comment.short_description = _('Comment')
    link_to_user.short_description = _('User')


admin.site.register(Comment, CommentAdmin)
admin.site.register(CommentReaction, CommentReactionAdmin)
