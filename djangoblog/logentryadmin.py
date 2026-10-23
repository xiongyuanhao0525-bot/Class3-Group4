# xyh：LogEntry 后台定制 Admin——把 Django 操作审计日志做成可筛选、可跳转的只读台账。
# xyh：设计要点：禁增删改（日志不可篡改），object/user 列渲染成回跳原对象的链接，
# xyh：列表按内容类型过滤、支持按对象标识与变更描述搜索；由 admin_site.py 注册生效。
from django.contrib import admin
from django.contrib.admin.models import DELETION
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse, NoReverseMatch
from django.utils.encoding import force_str
from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _


# xyh：操作日志只读台账视图
class LogEntryAdmin(admin.ModelAdmin):
    list_filter = [
        'content_type'  # xyh：右侧过滤器——按被操作对象的类型（文章/评论/用户…）筛选日志
    ]

    search_fields = [
        'object_repr',  # xyh：搜索框——匹配对象标识串
        'change_message'  # xyh：搜索框——匹配变更内容描述
    ]

    list_display_links = [
        'action_time',  # xyh：点时间列也可进详情
        'get_change_message',
    ]
    list_display = [
        'action_time',  # xyh：操作发生时间
        'user_link',  # xyh：操作人（可点击跳转其编辑页，见下方 user_link）
        'content_type',  # xyh：被操作对象所属模型
        'object_link',  # xyh：被操作对象（可点击跳转，删除类记录除外）
        'get_change_message',  # xyh：变更说明（Django 内置方法格式化字段 diff）
    ]

    def has_add_permission(self, request):
        return False  # xyh：禁止手工伪造日志条目

    def has_change_permission(self, request, obj=None):
        # xyh：仅 superuser 或被显式授权者可"查看"（Django 用 change 权限控制列表可见性），
        # xyh：且拒绝 POST——实际等于完全只读
        return (
                request.user.is_superuser or
                request.user.has_perm('admin.change_logentry')
        ) and request.method != 'POST'

    def has_delete_permission(self, request, obj=None):
        return False  # xyh：禁止删除日志，保证审计完整

    # xyh：列表列——被操作对象名渲染为超链接；删除类记录不建链（原对象已不存在）
    def object_link(self, obj):
        object_link = escape(obj.object_repr)  # xyh：先转义防 XSS
        content_type = obj.content_type

        if obj.action_flag != DELETION and content_type is not None:  # xyh：非删除且类型仍在才尝试建链
            # try returning an actual link instead of object repr string
            try:
                url = reverse(  # xyh：按 app_label_model_change 约定反查编辑页 URL
                    'admin:{}_{}_change'.format(content_type.app_label,
                                                content_type.model),
                    args=[obj.object_id]
                )
                object_link = '<a href="{}">{}</a>'.format(url, object_link)
            except NoReverseMatch:
                pass  # xyh：模型已从后台注销等情况则退回纯文本
        return mark_safe(object_link)  # xyh：声明为安全 HTML 供列表渲染

    object_link.admin_order_field = 'object_repr'  # xyh：该列支持点击排序
    object_link.short_description = _('object')  # xyh：列标题（国际化）

    # xyh：列表列——操作人同样渲染为可跳转链接，便于追查是谁改的
    def user_link(self, obj):
        content_type = ContentType.objects.get_for_model(type(obj.user))  # xyh：取用户模型的内容类型
        user_link = escape(force_str(obj.user))  # xyh：转义显示名
        try:
            # try returning an actual link instead of object repr string
            url = reverse(
                'admin:{}_{}_change'.format(content_type.app_label,
                                            content_type.model),
                args=[obj.user.pk]
            )
            user_link = '<a href="{}">{}</a>'.format(url, user_link)
        except NoReverseMatch:
            pass
        return mark_safe(user_link)

    user_link.admin_order_field = 'user'
    user_link.short_description = _('user')

    def get_queryset(self, request):
        queryset = super(LogEntryAdmin, self).get_queryset(request)
        return queryset.prefetch_related('content_type')  # xyh：预取内容类型表，避免每行一次查询（N+1 优化）

    def get_actions(self, request):
        actions = super(LogEntryAdmin, self).get_actions(request)
        if 'delete_selected' in actions:
            del actions['delete_selected']  # xyh：移除批量删除动作，与 has_delete_permission 双重保险
        return actions
