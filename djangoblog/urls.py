# xyh：项目根 URLConf —— 全站路由入口：i18n 前缀、后台 admin、六个业务 app 分发、
# xyh：sitemap/RSS/搜索聚合路由，以及 404/500/403 自定义错误页绑定。
"""djangoblog URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/1.10/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  url(r'^$', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  url(r'^$', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.conf.urls import url, include
    2. Add a URL to urlpatterns:  url(r'^blog/', include('blog.urls'))
"""
from django.conf import settings
from django.conf.urls.i18n import i18n_patterns
from django.conf.urls.static import static
from django.contrib.sitemaps.views import sitemap
from django.urls import path, include
from django.urls import re_path
from haystack.views import search_view_factory
from django.http import JsonResponse
import time

from blog.views import EsSearchView
from djangoblog.admin_site import admin_site
from djangoblog.elasticsearch_backend import ElasticSearchModelSearchForm
from djangoblog.feeds import DjangoBlogFeed
from djangoblog.sitemap import ArticleSiteMap, CategorySiteMap, StaticViewSitemap, TagSiteMap, UserSiteMap

sitemaps = {   # xyh：五类页面地图注册表，键名进 sitemap.xml 索引，值见 djangoblog/sitemap.py

    'blog': ArticleSiteMap,           # xyh：已发布文章
    'Category': CategorySiteMap,      # xyh：分类页
    'Tag': TagSiteMap,                # xyh：标签页
    'User': UserSiteMap,              # xyh：作者归档页
    'static': StaticViewSitemap       # xyh：首页等静态视图
}

handler404 = 'blog.views.page_not_found_view'        # xyh：404 → 博客自定义缺省页
handler500 = 'blog.views.server_error_view'          # xyh：500 → 服务器错误页
handle403 = 'blog.views.permission_denied_view'      # xyh：注意拼写为 handle403，Django 约定名应为 handler403，此绑定实际不生效（质量问题，报告可引用）


def health_check(request):
    """
    健康检查接口
    简单返回服务健康状态
    """
    return JsonResponse({
        'status': 'healthy',
        'timestamp': time.time()
    })   # xyh：供负载均衡/容器探针轮询，无鉴权、无 DB 依赖

urlpatterns = [
    path('i18n/', include('django.conf.urls.i18n')),           # xyh：语言切换接口（set_language）
    path('health/', health_check, name='health_check'),        # xyh：健康检查，置于 i18n 之外免语言前缀
]
urlpatterns += i18n_patterns(   # xyh：以下路由纳入国际化 URLConf（可带 /en/、/zh-hans/ 前缀；prefix_default_language=False 使默认语言免前缀）
    re_path(r'^admin/', admin_site.urls),                      # xyh：后台管理，走自定义 admin_site（准入收紧为 is_superuser）
    re_path(r'', include('blog.urls', namespace='blog')),      # xyh：博客前台全部路由（首页/文章/分类/标签/归档/友链…）
    re_path(r'mdeditor/', include('mdeditor.urls')),           # xyh：Markdown 编辑器的上传/预览接口
    re_path(r'', include('comments.urls', namespace='comment')),   # xyh：评论发表/回复/表情回应接口
    re_path(r'', include('accounts.urls', namespace='account')),   # xyh：注册/登录/登出/找回密码
    re_path(r'', include('oauth.urls', namespace='oauth')),        # xyh：第三方授权登录回调入口
    re_path(r'^sitemap\.xml$', sitemap, {'sitemaps': sitemaps},
            name='django.contrib.sitemaps.views.sitemap'),     # xyh：聚合五类地图输出 /sitemap.xml
    re_path(r'^feed/$', DjangoBlogFeed()),                     # xyh：RSS 订阅源（feed 别名一）
    re_path(r'^rss/$', DjangoBlogFeed()),                      # xyh：RSS 订阅源（feed 别名二，与上重复挂载）
    re_path('^search', search_view_factory(view_class=EsSearchView, form_class=ElasticSearchModelSearchForm),
            name='search'),                                    # xyh：搜索页——haystack 工厂组装 ES 视图+表单；注意 r'^search' 缺 $，会前缀吞并后续同名路径（质量问题）
    re_path(r'', include('servermanager.urls', namespace='servermanager'))
    , prefix_default_language=False) + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)   # xyh：运维机器人路由；末尾拼接静态文件路由（开发服务器下直出 collectstatic 产物）
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL,
                          document_root=settings.MEDIA_ROOT)   # xyh：仅调试模式由 Django 直出用户上传媒体文件
