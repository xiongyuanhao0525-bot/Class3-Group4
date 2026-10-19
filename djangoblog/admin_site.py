# xyh：自定义 AdminSite 模块——项目后台唯一入口实例。
# xyh：配合 settings.INSTALLED_APPS 的 SimpleAdminConfig（禁用默认自动发现），
# xyh：全站后台模型统一注册到本文件的 admin_site 单例；准入收紧为仅 superuser。
from django.contrib.admin import AdminSite
from django.contrib.admin.models import LogEntry
from django.contrib.sites.admin import SiteAdmin
from django.contrib.sites.models import Site

# xyh：星号导入各 app 的 Admin 类与模型——注册清单集中于此，避免分散 register
from accounts.admin import *
from blog.admin import *
from blog.models import *
from comments.admin import *
from comments.models import *
from djangoblog.logentryadmin import LogEntryAdmin
from oauth.admin import *
from oauth.models import *
from servermanager.admin import *
from servermanager.models import *


# xyh：博客定制后台站点：改写标题文案 + 收紧访问准入
class DjangoBlogAdminSite(AdminSite):
    site_header = 'djangoblog administration'  # xyh：后台顶栏大标题
    site_title = 'djangoblog site admin'  # xyh：浏览器标签页标题

    def __init__(self, name='admin'):
        super().__init__(name)   # xyh：保留父类构造（注册 registry 等），name 决定 URL 命名空间

    def has_permission(self, request):
        # xyh：安全收紧点——覆盖默认的 is_staff 判定，仅超级管理员可进后台
        return request.user.is_superuser

    # def get_urls(self):
    #     urls = super().get_urls()
    #     from django.urls import path
    #     from blog.views import refresh_memcache
    #
    #     my_urls = [
    #         path('refresh/', self.admin_view(refresh_memcache), name="refresh"),
    #     ]
    #     return urls + my_urls


# xyh：全局唯一的后台实例；djangoblog/urls.py 以 admin_site.urls 挂载 /admin/
admin_site = DjangoBlogAdminSite(name='admin')

# xyh——blog 内容管理域
admin_site.register(Article, ArticlelAdmin)
admin_site.register(Category, CategoryAdmin)
admin_site.register(Tag, TagAdmin)
admin_site.register(Links, LinksAdmin)
admin_site.register(SideBar, SideBarAdmin)
admin_site.register(BlogSettings, BlogSettingsAdmin)

# xyh——servermanager 运维域（微信机器人指令与发信日志）
admin_site.register(commands, CommandsAdmin)
admin_site.register(EmailSendLog, EmailSendLogAdmin)

# xyh——accounts 用户域
admin_site.register(BlogUser, BlogUserAdmin)

# xyh——comments 评论域
admin_site.register(Comment, CommentAdmin)

# xyh——oauth 第三方登录域（授权用户与站点配置）
admin_site.register(OAuthUser, OAuthUserAdmin)
admin_site.register(OAuthConfig, OAuthConfigAdmin)

# xyh——sites 框架与后台操作日志（日志用定制 LogEntryAdmin，只读可追溯）
admin_site.register(Site, SiteAdmin)

admin_site.register(LogEntry, LogEntryAdmin)
