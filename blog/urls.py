# ============================================================
# blog/urls.py —— 博客应用的路由表（URL 分发中心）
# 作用：用户在浏览器输入网址后，Django 根据这里的规则，
#       决定"这个地址交给哪个视图去处理"。
# 相当于饭店前台：客人报菜名（网址），前台决定送到哪个后厨（视图）。
# ============================================================

from django.urls import path                       # path：注册一条"网址 → 视图"的规则
from django.views.decorators.cache import cache_page  # 页面缓存装饰器（给不常变的页面提速用）

from . import views                               # 从本应用(blog)导入视图：真正的页面逻辑都在 views.py 里

app_name = "blog"                                 # 本应用的路由命名空间：其他地方用 "blog:index" 这样的名字引用网址

urlpatterns = [                                   # 路由表：Django 从上往下匹配，命中第一条就执行

    # ---------- 首页 ----------
    path(
        r'',                                      # 空路径 = 网站根地址 http://127.0.0.1:8000/
        views.IndexView.as_view(),                # 交给首页视图类：负责查文章列表并渲染首页模板
        name='index'),                            # 路由名字：代码里用 reverse('blog:index') 就能拿到这个网址

    # ---------- 首页分页（第2页、第3页…）----------
    path(
        r'page/<int:page>/',                      # <int:page> 是"路径参数"：/page/2/ 里的 2 会被解析成数字
        views.IndexView.as_view(),                # 同一个首页视图，只是换成第 page 页的数据
        name='index_page'),

    # ---------- 文章详情页 ----------
    path(
        r'article/<int:year>/<int:month>/<int:day>/<int:article_id>.html',
        # 文章页地址格式：/article/2026/9/18/1.html
        # 4 个 <int:...> 分别是 年/月/日/文章ID，都会被转成整数传给视图
        views.ArticleDetailView.as_view(),        # 文章详情视图：按 ID 查出这篇文章，渲染正文 + 评论区
        name='detailbyid'),

    # ---------- 分类页（列出某分类下的所有文章）----------
    path(
        r'category/<slug:category_name>.html',    # <slug:...> 参数：分类名的短横线写法，如 /category/guoneiyou.html
        views.CategoryDetailView.as_view(),
        name='category_detail'),

    # ---------- 分类页分页 ----------
    path(
        r'category/<slug:category_name>/<int:page>.html',   # 分类 + 页码：/category/guoneiyou/2.html
        views.CategoryDetailView.as_view(),
        name='category_detail_page'),

    # ---------- 作者页（列出某位作者的文章）----------
    path(
        r'author/<author_name>.html',             # /author/熊圆好.html
        views.AuthorDetailView.as_view(),
        name='author_detail'),

    # ---------- 作者页分页 ----------
    path(
        r'author/<author_name>/<int:page>.html',  # 作者 + 页码
        views.AuthorDetailView.as_view(),
        name='author_detail_page'),

    # ---------- 标签页（列出带某标签的文章）----------
    path(
        r'tag/<slug:tag_name>.html',              # /tag/hai-dao.html（标签名同样转成 slug 格式）
        views.TagDetailView.as_view(),
        name='tag_detail'),

    # ---------- 标签页分页 ----------
    path(
        r'tag/<slug:tag_name>/<int:page>.html',   # 标签 + 页码
        views.TagDetailView.as_view(),
        name='tag_detail_page'),

    # ---------- 归档页（按时间列出全部文章，相当于时间轴）----------
    path(
        'archives.html',
        cache_page(                               # 用缓存装饰器包起来：归档页内容很少变化，
            60 * 60)(                             # 缓存 1 小时（60秒×60），不用每次都查数据库，访问更快
            views.ArchivesView.as_view()),
        name='archives'),

    # ---------- 友情链接页 ----------
    path(
        'links.html',                             # /links.html
        views.LinkListView.as_view(),
        name='links'),

    # ---------- 图片上传接口（后台写文章时上传图片走这里）----------
    path(
        r'upload',                                # 不是页面而是接口：POST 图片过来，返回图片地址
        views.fileupload,
        name='upload'),

    # ---------- 清理缓存接口 ----------
    path(
        r'clean',                                 # 管理用的接口：手动清空页面缓存
        views.clean_cache_view,
        name='clean'),
]
