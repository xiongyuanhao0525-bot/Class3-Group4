# ============================================================
# blog/urls.py —— 博客应用的路由表（URL 分发中心）
# 作用：用户在浏览器输入网址后，Django 根据这里的规则，
#       决定"这个地址交给哪个视图去处理"。
# 相当于饭店前台：客人报菜名（网址），前台决定送到哪个后厨（视图）。
# 注释人：翟旌超（软件工程 3 班 2415304340，#zjc）
# 补充注释：翟旌超（#zjc）—— 本文件此前已有一版注释（分工表记为 xyh 跟进），本次只补缺、不改原文
# ============================================================

# —— Django 框架自带模块 ——
# path：把一条"URL 规则 → 视图"登记进路由表；cache_page：给整页响应套一层缓存
from django.urls import path                       # path：注册一条"网址 → 视图"的规则
from django.views.decorators.cache import cache_page  # 页面缓存装饰器（给不常变的页面提速用）

# —— 本项目自己的模块 ——
from . import views                               # 从本应用(blog)导入视图：真正的页面逻辑都在 views.py 里

# 【app_name】—— 给这组路由起一个"姓"，也就是 URL 命名空间（namespace，同名路由的分组前缀）
# 根路由 djangoblog/urls.py:62 用 include('blog.urls', namespace='blog') 把它挂到网站根路径，
# 所以本文件里的 name 都要写成 "blog:index" 这种带前缀的形式才能反查；
# 好处：不同应用可以有同名路由互不打架，而且路径改了只改这里，模板/代码里的反查名不用动。
app_name = "blog"                                 # 本应用的路由命名空间：其他地方用 "blog:index" 这样的名字引用网址

# ------------------------------------------------------------
# 【urlpatterns】—— 路由表主体，Django 按"从上往下"的顺序逐条匹配
# 命中第一条就把请求交给对应视图，后面的规则不再看，所以规则顺序会影响结果。
# 每条 path(路由规则, 视图, name=反查名)：
#   · 路由规则里 <类型:参数名> 叫路径参数（如 <int:page>），会解析成关键字参数传给视图；
#   · name 是给"反向解析"用的：模板里 {% url 'blog:xxx' %}、代码里 reverse('blog:xxx')
#     都靠它算真实网址，所以改路径时只要 name 不变，引用处就都不用改。
# ------------------------------------------------------------
urlpatterns = [                                   # 路由表：Django 从上往下匹配，命中第一条就执行

    # ---------- 首页 ----------
    # 本模块被挂在根路由 r'' 下，所以这条 r'' 对应的真实网址就是网站根地址 /
    # 反查名 index 的引用处：templates/share_layout/nav.html:34 与 nav.html:197（PC / 手机导航）、
    # templates/share_layout/footer.html:19（页脚）、djangoblog/sitemap.py:12（站点地图）、
    # blog/test_views.py:66 等测试用例（用 reverse 造请求地址）
    path(
        r'',                                      # 空路径 = 网站根地址 http://127.0.0.1:8000/
        views.IndexView.as_view(),                # 交给首页视图类：负责查文章列表并渲染首页模板
        name='index'),                            # 路由名字：代码里用 reverse('blog:index') 就能拿到这个网址

    # ---------- 首页分页（第2页、第3页…）----------
    # 分页地址和根地址"形状"不同，只能单独登记一条规则，但两条规则指向同一个视图类。
    # 视图内部按 page 取第几页数据；页码不合法（比如 0 或超出总页数）时由分页器抛 404。
    # 反查名 index_page 的引用处：blog/templatetags/blog_tags.py:609（拼上一页/下一页链接）
    path(
        r'page/<int:page>/',                      # <int:page> 是"路径参数"：/page/2/ 里的 2 会被解析成数字
        views.IndexView.as_view(),                # 同一个首页视图，只是换成第 page 页的数据
        name='index_page'),

    # ---------- 文章详情页 ----------
    # 结尾的 .html 是写死的普通字符（不是参数），访问时地址必须带 .html，少写就匹配不到；
    # 这样设计是为了让文章地址看起来像"静态页"，对搜索引擎更友好。
    # 年/月/日只用于"地址里体现发布时间"；真正定位文章的是 article_id —— 视图里的
    # pk_url_kwarg = 'article_id' 只按主键查库，年/月/日虽然被接收但不用来查数据。
    # 反查名 detailbyid 的引用处：blog/models.py:274（Article.get_absolute_url 生成文章链接）、
    # plugins/seo_optimizer/plugin.py:184（按视图名给详情页补 SEO 信息）
    path(
        r'article/<int:year>/<int:month>/<int:day>/<int:article_id>.html',
        # 文章页地址格式：/article/2026/9/18/1.html
        # 4 个 <int:...> 分别是 年/月/日/文章ID，都会被转成整数传给视图
        views.ArticleDetailView.as_view(),        # 文章详情视图：按 ID 查出这篇文章，渲染正文 + 评论区
        name='detailbyid'),

    # ---------- 分类页（列出某分类下的所有文章）----------
    # slug 转换器只匹配 字母 / 数字 / 下划线 / 短横线，所以中文分类名必须先转成
    # slug（"国内游记" → guoneiyou）才能出现在地址里，这也是模型里要有 slug 字段的原因。
    # 反查名 category_detail 的引用处：blog/models.py:401（Category.get_absolute_url）、
    # plugins/seo_optimizer/plugin.py:186
    path(
        r'category/<slug:category_name>.html',    # <slug:...> 参数：分类名的短横线写法，如 /category/guoneiyou.html
        views.CategoryDetailView.as_view(),
        name='category_detail'),

    # ---------- 分类页分页 ----------
    # 与上一条只差末尾的 /<page>.html；两条规则都写在同一个视图上，靠 page 是否出现区分。
    # 反查名 category_detail_page 的引用处：blog/templatetags/blog_tags.py:618（拼页码链接）
    path(
        r'category/<slug:category_name>/<int:page>.html',   # 分类 + 页码：/category/guoneiyou/2.html
        views.CategoryDetailView.as_view(),
        name='category_detail_page'),

    # ---------- 作者页（列出某位作者的文章）----------
    # <author_name> 用的是默认的 str 转换器：匹配除斜杠外的任意字符，
    # 所以中文用户名也能访问（浏览器会把中文百分号编码后再发过来）。
    # 反查名 author_detail 的引用处：accounts/models.py:19（BlogUser.get_absolute_url
    # 用 username 拼作者主页地址）、plugins/seo_optimizer/plugin.py:190
    path(
        r'author/<author_name>.html',             # /author/熊圆好.html
        views.AuthorDetailView.as_view(),
        name='author_detail'),

    # ---------- 作者页分页 ----------
    # 与作者页规则只差末尾的 /<page>.html；作者页和分页共用一个 AuthorDetailView。
    # 反查名 author_detail_page 的引用处：blog/templatetags/blog_tags.py:615
    path(
        r'author/<author_name>/<int:page>.html',  # 作者 + 页码
        views.AuthorDetailView.as_view(),
        name='author_detail_page'),

    # ---------- 标签页（列出带某标签的文章）----------
    # <slug:tag_name> 同样只允许 字母 / 数字 / 下划线 / 短横线，标签名里的中文/空格
    # 不能直接出现在地址中，必须先 slug 化（Tag 模型有 slug 字段就是为此）。
    # 反查名 tag_detail 的引用处：blog/models.py:476（Tag.get_absolute_url）、
    # plugins/seo_optimizer/plugin.py:188
    path(
        r'tag/<slug:tag_name>.html',              # /tag/hai-dao.html（标签名同样转成 slug 格式）
        views.TagDetailView.as_view(),
        name='tag_detail'),

    # ---------- 标签页分页 ----------
    # 反查名 tag_detail_page 的引用处：blog/templatetags/blog_tags.py:611（拼页码链接）
    path(
        r'tag/<slug:tag_name>/<int:page>.html',   # 标签 + 页码
        views.TagDetailView.as_view(),
        name='tag_detail_page'),

    # ---------- 归档页（按时间列出全部文章，相当于时间轴）----------
    # 固定路径、不接受任何参数（ArchivesView 里 paginate_by = None，不分页，一次列全部文章）。
    # 【cache_page 的生效范围】它只包住"这一条路由"，别的路由完全不受影响；
    # 缓存的是渲染好的整份响应（连响应头一起），缓存键由请求的完整路径决定，
    # 命中时视图函数根本不会执行 —— 这 1 小时内一次数据库都不查。
    # 【生效条件】只缓存 GET/HEAD 且状态码 200 的响应；POST、404 之类的响应不缓存。
    # 【坑 1】同一网址的所有访客共用一份缓存，页面里绝不能放因人而异的内容
    #        （本页只是纯文章列表，所以敢这么用）。
    # 【坑 2】默认缓存后端是 LocMemCache（每个进程各自一块内存），多进程部署时各进程的
    #        缓存互不可见；下面那个 /clean 接口也只能清掉当前进程的那一份。
    # 【坑 3】改了模板后，前台最长要 1 小时才看到效果，等不及就调 /clean 或重启进程。
    # 【坑 4】ArchivesView 自己还带了一层"按 'archives' 键缓存查询结果"的数据缓存，
    #        两者是嵌套的两层（外层管 HTML、内层管 SQL），清缓存时得一起清才干净。
    path(
        'archives.html',
        cache_page(                               # 用缓存装饰器包起来：归档页内容很少变化，
            60 * 60)(                             # 缓存 1 小时（60秒×60），不用每次都查数据库，访问更快
            views.ArchivesView.as_view()),
        name='archives'),

    # ---------- 友情链接页 ----------
    # 视图 LinkListView 只显示 is_enable=True 的链接；name='links' 全项目没有任何
    # {% url %} / reverse 引用，模板里也没有入口，只能自己输网址 /links.html 访问。
    path(
        'links.html',                             # /links.html
        views.LinkListView.as_view(),
        name='links'),

    # ---------- 图片上传接口（后台写文章时上传图片走这里）----------
    # 注意 r'upload' 结尾没有斜杠：真实地址是 /upload，写成 /upload/ 会 404。
    # 它不是页面而是接口：只接受 POST（非 POST 返回 "only for post"），
    # 且必须带 ?sign=<两次 sha256(SECRET_KEY) 的十六进制> 通过校验，否则返回 403；
    # 视图上有 @csrf_exempt，所以调用方不用带 CSRF token。
    # name='upload' 目前没有任何模板/代码用反查，是留给前端 JS 拼地址用的。
    path(
        r'upload',                                # 不是页面而是接口：POST 图片过来，返回图片地址
        views.fileupload,
        name='upload'),

    # ---------- 清理缓存接口 ----------
    # 真实地址是 /clean（同样没有末尾斜杠），name='clean' 也没有任何地方反查引用。
    # 视图 clean_cache_view 就是一句 cache.clear()：把默认缓存后端整个清空，
    # 上面被 cache_page 包住的归档页缓存、seo_processor 那份整块缓存都会一起失效。
    # ⚠️ 它没有任何登录/权限校验，谁能访问这个网址谁就能清缓存，别在生产环境暴露。
    path(
        r'clean',                                 # 管理用的接口：手动清空页面缓存
        views.clean_cache_view,
        name='clean'),
]
