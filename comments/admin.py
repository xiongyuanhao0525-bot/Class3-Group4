from django.contrib import admin  # Django 后台管理框架
from django.urls import reverse  # 反向解析后台 URL
from django.utils.html import format_html  # 构造安全的 HTML 片段（自动转义）
from django.utils.translation import gettext_lazy as _

from .models import Comment, CommentReaction
from .utils import invalidate_article_comment_cache

# #jxr 本文件为 comments app 的后台管理配置：
# #jxr - 三个批量动作：审核通过 / 审核拒绝 / 打回待审（对应三态审核状态）
# #jxr - CommentAdmin：评论列表页配置，含状态徽标、跳转作者/文章的链接列
# #jxr - CommentReactionAdmin：表情反应列表页配置
# #jxr 注意：批量动作用逐条 save() 而不是 queryset.update()。
# #jxr update() 不会触发 post_save 信号，文章评论缓存不会失效，管理员“通过”后前台仍看不到。


def _change_review_status(modeladmin, request, queryset, action_name):
    """#jxr 批量改审核状态的公共实现：逐条保存 + 逐条清缓存。

    :param action_name: 'approve' / 'reject' / 'reset'
    :return: 实际处理的评论条数（Django admin 会忽略返回值）
    """
    handled = 0
    # #jxr select_related 预取文章，避免每条评论再查一次文章
    for comment in queryset.select_related('article'):
        if action_name == 'approve':
            comment.approve()
        elif action_name == 'reject':
            comment.reject()
        else:
            comment.reset_to_pending()
        # #jxr 逐条失效该文章的评论缓存/页面缓存：状态变化必须让前台立即生效
        invalidate_article_comment_cache(comment.article)
        handled += 1
    return handled


def approve_comments(modeladmin, request, queryset):
    """#jxr 后台批量动作：审核通过（三态置为 approved，前台可见）"""
    _change_review_status(modeladmin, request, queryset, 'approve')


def reject_comments(modeladmin, request, queryset):
    """#jxr 后台批量动作：审核拒绝（三态置为 rejected，前台隐藏）"""
    _change_review_status(modeladmin, request, queryset, 'reject')


def reset_comments_to_pending(modeladmin, request, queryset):
    """#jxr 后台批量动作：打回待审（三态置为 pending，前台隐藏）"""
    _change_review_status(modeladmin, request, queryset, 'reset')


approve_comments.short_description = _('Approve selected comments')
reject_comments.short_description = _('Reject selected comments')
reset_comments_to_pending.short_description = _('Reset selected comments to pending')


# #jxr 状态徽标配色：待审=琥珀、通过=绿、拒绝=红；用低饱和色，避免后台列表过于刺眼
REVIEW_STATUS_STYLES = {
    Comment.REVIEW_STATUS_PENDING: ('#92400e', '#fef3c7'),
    Comment.REVIEW_STATUS_APPROVED: ('#166534', '#dcfce7'),
    Comment.REVIEW_STATUS_REJECTED: ('#991b1b', '#fee2e2'),
}


class CommentAdmin(admin.ModelAdmin):
    list_per_page = 20  # #jxr 每页显示20条，控制后台列表页体积
    list_display = (
        'id',
        'body',
        'link_to_userinfo',
        'link_to_article',
        'review_status_badge',
        'is_enable',
        'creation_time')
    list_display_links = ('id', 'body', 'review_status_badge')
    list_filter = ('review_status', 'is_enable')  # #jxr 三态 + 展示开关双维度筛选
    exclude = ('creation_time', 'last_modify_time')
    actions = [approve_comments, reject_comments, reset_comments_to_pending]  # #jxr 注册三态审核动作
    raw_id_fields = ('author', 'article')  # #jxr 外键用原始ID输入，避免大数据量下拉卡顿
    search_fields = ('body',)  # #jxr 支持按正文搜索
    # #jxr is_enable 由 review_status 派生，后台只读展示，避免两个开关互相打架
    readonly_fields = ('is_enable',)

    def review_status_badge(self, obj):
        """#jxr 审核状态列：带底色的徽标，管理员一眼能看出待审/通过/拒绝。"""
        foreground, background = REVIEW_STATUS_STYLES.get(
            obj.review_status, ('#374151', '#e5e7eb'))
        return format_html(
            '<span style="display:inline-block;padding:1px 8px;border-radius:10px;'
            'font-size:12px;color:{};background:{};">{}</span>',
            foreground, background, obj.get_review_status_display())

    review_status_badge.short_description = _('Review status')
    review_status_badge.admin_order_field = 'review_status'  # #jxr 允许点表头按状态排序

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

    # #jxr 后台删除评论（单条删除或列表批量删除）同样要清缓存：
    # #jxr post_delete 信号不在 blog_signals 的处理范围里，删除已通过的评论后
    # #jxr 详情页评论数与侧边栏“近期评论”会继续显示旧数据，所以在这里补一刀。
    def delete_model(self, request, obj):
        article = obj.article
        super().delete_model(request, obj)
        invalidate_article_comment_cache(article)

    def delete_queryset(self, request, queryset):
        articles = {comment.article for comment in queryset.select_related('article')}
        super().delete_queryset(request, queryset)
        for article in articles:
            invalidate_article_comment_cache(article)


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
