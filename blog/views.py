# ============================================================
# blog/views.py —— 博客前台所有页面的“视图”都集中在这个文件里
# 什么是视图：浏览器发来请求 -> 视图去数据库取数据 -> 交给模板渲染成 HTML 页面返回
# 本文件包含：首页、文章详情、分类/标签/作者归档、归档页、友情链接页、
#            站内搜索页、图片上传接口（简易图床）、清缓存接口
# 注释人：翟旌超（软件工程 3 班 2415304340）
# 说明：本次任务只添加中文注释，没有改动任何一行原有代码逻辑
# ============================================================
# —— Python 标准库 ——
# logging：输出日志；os：文件与路径处理；uuid：生成随机文件名
import logging
import os
import uuid

# —— Django 框架自带模块 ——
# settings 项目配置、Paginator 分页器、HttpResponse/HttpResponseForbidden 响应、
# get_object_or_404 查不到就返回 404、render 渲染模板、static 静态文件地址、
# timezone 时区、_ 翻译、csrf_exempt 免除 CSRF 校验、DetailView/ListView 通用视图
from django.conf import settings
from django.core.paginator import Paginator
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404
from django.shortcuts import render
from django.templatetags.static import static
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.csrf import csrf_exempt
from django.views.generic.detail import DetailView
from django.views.generic.list import ListView
# Haystack（全文检索）的搜索视图，站内搜索页面基于它实现
from haystack.views import SearchView

# —— 本项目自己的模块 ——
# 数据模型：Article 文章、Category 分类、Tag 标签、Links 友情链接、LinkShowType 链接显示类型
from blog.models import Article, Category, LinkShowType, Links, Tag
# 评论表单对象，用来渲染文章详情页底部的评论输入框
from comments.forms import CommentForm
# 插件钩子机制：让插件能在页面渲染流程中插入自己的逻辑
from djangoblog.plugin_manage import hooks
# 钩子名称常量（用常量代替手写字符串，避免名字写错）
from djangoblog.plugin_manage.hook_constants import ARTICLE_CONTENT_HOOK_NAME
# 通用工具：cache 缓存操作、get_blog_setting 读取博客站点设置、get_sha256 计算签名（图床上传校验用）
from djangoblog.utils import cache, get_blog_setting, get_sha256
# 自定义 Mixin（混入类）：把“整页缓存、文章查询优化、分页、按 slug 查分类/标签”
# 这些重复逻辑抽出来，视图只要继承就能复用，不必每个页面重抄一遍
from djangoblog.mixins import (
    SlugCachedMixin,
    ArticleListMixin,
    OptimizedArticleQueryMixin,
    CachedListViewMixin,
    PageNumberMixin
)

# 本模块的日志记录器，出错时按模块名输出日志，便于定位问题
logger = logging.getLogger(__name__)


# ============================================================
# 文章列表视图基类 ArticleListView
# 首页 / 分类 / 标签 / 作者 / 归档 等“文章列表页”的公共父类，统一负责：
#   1) 用哪个模板   2) 分页   3) 整页缓存   4) 页面底部显示哪类友情链接
# 子类只需要实现 get_queryset_data()（要显示哪些文章）和
# get_queryset_cache_key()（缓存键怎么取）这两个方法
# ============================================================
class ArticleListView(CachedListViewMixin, PageNumberMixin, ListView):
    """
    文章列表视图基类（重构版）

    使用 Mixin 简化代码，消除重复逻辑
    子类只需实现 get_queryset_data() 和 get_queryset_cache_key() 方法
    """
    # template_name属性用于指定使用哪个模板进行渲染
    # 列表页默认使用的模板（子类可以覆盖）
    template_name = 'blog/article_index.html'

    # context_object_name属性用于给上下文变量取名（在模板中使用该名字）
    context_object_name = 'article_list'

    # 页面类型，分类目录或标签列表等
    # 页面类型文字，会显示在列表页顶部，用来告诉用户当前在看哪一类列表
    page_type = ''
    # 每页显示多少篇文章，取自项目配置 settings.PAGINATE_BY
    paginate_by = settings.PAGINATE_BY
    # 页码参数名，对应浏览器地址栏里的 ?page=2
    page_kwarg = 'page'
    # 本页面底部展示哪一类友情链接（L = 列表页）
    link_type = LinkShowType.L

    # 整页缓存的缓存键：默认取请求参数中的 pages
    # （子类一般会用 get_queryset_cache_key() 提供更精确的键，见下面各子类）
    def get_view_cache_key(self):
        return self.request.get['pages']

    def get_context_data(self, **kwargs):
        # 把友情链接类型放进模板上下文，模板据此决定底部显示哪些链接
        kwargs['linktype'] = self.link_type
        return super(ArticleListView, self).get_context_data(**kwargs)


# ============================================================
# 【首页视图 IndexView】—— 分工表中由翟旌超负责注释的类
# 作用：用户打开网站首页（/）时，取出最新的已发布文章，渲染成首页的文章列表
# 继承：OptimizedArticleQueryMixin 提供优化过的文章查询（少打数据库查询）
#       ArticleListView 提供列表页的公共属性、分页和整页缓存
# ============================================================
class IndexView(OptimizedArticleQueryMixin, ArticleListView):
    """
    首页视图（重构版）

    继承 OptimizedArticleQueryMixin 获得优化的查询方法
    """
    # ------------------------------------------------------------
    # 首页做的事情，一句话：把「已发布」的文章按时间倒序分页显示出来
    #   type='a'   -> 这条记录是文章（而不是独立单页）
    #   status='p' -> 状态是 published（已发布），草稿不会被首页显示
    # 渲染模板：blog/article_index.html
    # 访问地址：http://127.0.0.1:8000/
    # ------------------------------------------------------------
    # 友情链接类型
    # 首页底部展示“首页专用”的友情链接（I = Index）
    link_type = LinkShowType.I
    # 下面这个方法回答一个核心问题：首页到底要显示哪些文章？

    def get_queryset_data(self):
        # 使用 Mixin 提供的优化查询方法
        # 下面调用的 get_optimized_article_queryset() 来自 OptimizedArticleQueryMixin，
        # 它已经帮我们把作者、分类、标签等关联数据一次性取好，
        # 避免“查出 10 篇文章却打了 100 次数据库”的性能问题
        return self.get_optimized_article_queryset().filter(
            type='a', status='p'
            # 只保留“文章”类型 + “已发布”状态（草稿 'd' 不会出现在首页）
        )

    def get_queryset_cache_key(self):
        # 缓存键：用页码区分，第 1 页缓存为 index_1、第 2 页为 index_2 ……
        # 这样翻页时缓存互不覆盖，命中缓存就不用再查数据库
        return f'index_{self.page_number}'

    def get_context_data(self, **kwargs):
        # get_context_data()：往模板上下文里追加数据，供 article_index.html 使用
        context = super().get_context_data(**kwargs)
        blog_setting = get_blog_setting()
        # 首页的 SEO（搜索引擎优化）信息：网页标题、描述、关键词
        # 这些内容会输出到 HTML 的 <head> 标签里，方便被搜索引擎收录
        # 提供基础SEO数据
        context['seo_title'] = f"{blog_setting.site_name} | {blog_setting.site_description}"
        # 网页标题 = 站点名称 | 站点描述
        context['seo_description'] = blog_setting.site_seo_description
        # 网页描述：给搜索引擎看的摘要
        context['seo_keywords'] = blog_setting.site_keywords
        # 网页关键词：逗号分隔的关键词列表
        return context


# ============================================================
# 文章详情视图：点开一篇文章后看到的页面（地址形如 /article/<文章id>/）
# 除了文章正文，还要准备：评论表单、评论分页列表、上一篇/下一篇、相关 SEO 数据
# ============================================================
class ArticleDetailView(DetailView):
    '''
    文章详情页面
    '''
    # 本页面使用的模板文件
    template_name = 'blog/article_detail.html'
    # 本视图操作的数据模型：文章
    model = Article
    # URL 中文章主键的参数名（与 urls.py 里的写法一一对应）
    pk_url_kwarg = 'article_id'
    # 在模板中用 {{ article }} 这个名字访问当前文章
    context_object_name = "article"

    def get_context_data(self, **kwargs):
        # 1) 评论表单：渲染页面底部的“写评论”输入框
        comment_form = CommentForm()

        # 优化：直接查询父评论，减少数据库查询
        # 2) 查评论：只查“顶级评论”（parent_comment 为空，即不是回复别人的），
        #    is_enable=True 表示这条评论没有被管理员禁用
        from comments.models import Comment
        parent_comments = Comment.objects.filter(
            article=self.object,
            parent_comment=None,
            is_enable=True
        ).select_related('author').prefetch_related(
            'comment_set__author'  # 预加载子评论及其作者
        ).order_by('-id')

        # 3) 再取一次全部评论，只用于页面上显示“共 N 条评论”
        # 获取所有评论用于总数显示
        article_comments = self.object.comment_list()

        blog_setting = get_blog_setting()
        # 4) 评论分页：每页显示多少条由后台“博客设置”里的 article_comment_count 决定
        paginator = Paginator(parent_comments, blog_setting.article_comment_count)
        # 从地址栏的 ?comment_page=N 取评论页码，默认第 1 页
        page = self.request.GET.get('comment_page', '1')
        # 容错处理：页码不是数字就按第 1 页算；小于 1 或超过总页数也要修正，避免程序报错
        if not page.isnumeric():
            page = 1
        else:
            page = int(page)
            if page < 1:
                page = 1
            if page > paginator.num_pages:
                page = paginator.num_pages
                # 页码超过总页数时，取最后一页

        # 取出当前这一页的评论（p_comments 就是本页的评论列表）
        p_comments = paginator.page(page)
        # 计算“下一页评论 / 上一页评论”的页码，没有则为 None
        next_page = p_comments.next_page_number() if p_comments.has_next() else None
        prev_page = p_comments.previous_page_number() if p_comments.has_previous() else None

        # 拼接评论翻页链接；#commentlist-container 是锚点，跳转后直接定位到评论区
        if next_page:
            kwargs[
                'comment_next_page_url'] = self.object.get_absolute_url() + f'?comment_page={next_page}#commentlist-container'
        if prev_page:
            kwargs[
                'comment_prev_page_url'] = self.object.get_absolute_url() + f'?comment_page={prev_page}#commentlist-container'
        # 5) 把评论相关的数据（表单、当前页评论、评论总数）交给模板使用
        kwargs['form'] = comment_form
        kwargs['article_comments'] = article_comments
        kwargs['p_comments'] = p_comments
        kwargs['comment_count'] = len(
            article_comments) if article_comments else 0

        # 6) 上一篇 / 下一篇文章（由 Article 模型对应属性算出来）
        kwargs['next_article'] = self.object.next_article
        kwargs['prev_article'] = self.object.prev_article

        # 7) 先让父类把上面准备的数据组装好，下面再补充 SEO 信息
        context = super(ArticleDetailView, self).get_context_data(**kwargs)
        article = self.object
        # article 就是当前正在浏览的这篇文章对象
        
        # 8) 生成 SEO 数据：标题、描述、关键词，让搜索引擎更好地收录这篇文章
        # 添加基础SEO数据
        blog_setting = get_blog_setting()
        # 下面要用到三个工具：去掉 HTML 标签、截断过长文本、把 Markdown 转成 HTML
        from django.utils.html import strip_tags
        from django.utils.text import Truncator
        from djangoblog.utils import CommonMarkdown
        
        # 9) SEO 描述：文章正文 -> Markdown 转 HTML -> 去掉标签 -> 压缩多余空白 -> 截断 150 字，
        #    这样得到的都是纯文字，适合放进 meta 描述里
        # 处理description：markdown -> HTML -> 纯文本，彻底去除格式
        html_content = CommonMarkdown.get_markdown(article.body)
        description = strip_tags(html_content)
        description = ' '.join(description.split())  # 规范化空白字符
        description = Truncator(description).chars(150, truncate='...')
        
        # 10) SEO 关键词：取这篇文章的全部标签名；如果文章没有标签，就用站点默认关键词
        # 处理keywords：去除空格，用逗号分隔
        tags = [tag.name.strip() for tag in article.tags.all()]
        keywords = ", ".join(tags) if tags else blog_setting.site_keywords
        
        context['seo_title'] = f"{article.title} | {blog_setting.site_name}"
        # 网页标题：文章标题 | 站点名称
        context['seo_description'] = description
        context['seo_keywords'] = keywords
        
        # 11) 运行插件钩子：插件可以往上下文里再添加数据，或对文章正文做二次加工
        # 触发文章详情加载钩子，让插件可以添加额外的上下文数据
        from djangoblog.plugin_manage.hook_constants import ARTICLE_DETAIL_LOAD
        hooks.run_action(ARTICLE_DETAIL_LOAD, article=article, context=context, request=self.request)
        
        # 12) 再触发一个“正文已获取”的钩子，插件通常在这里统计阅读量、清理正文等
        # Action Hook, 通知插件"文章详情已获取"
        hooks.run_action('after_article_body_get', article=article, request=self.request)
        # 最后把整理好的上下文数据返回给模板去渲染成网页
        return context


# ============================================================
# 分类目录视图：点某个分类后，显示该分类（含子分类）下的已发布文章
# 地址形如 /category/<分类名>/
# ============================================================
class CategoryDetailView(SlugCachedMixin, OptimizedArticleQueryMixin, ArticleListView):
    """
    分类目录列表（重构版）

    使用 SlugCachedMixin 避免重复查询 Category
    使用 OptimizedArticleQueryMixin 优化文章查询
    """
    page_type = "分类目录归档"
    # 页面类型文字，会显示在列表页顶部
    # URL 中分类名的参数名；slug_model 告诉 SlugCachedMixin 去 Category 表里查
    slug_url_kwarg = 'category_name'
    slug_model = Category

    def get_queryset_data(self):
        # 使用 Mixin 缓存的对象，只查询一次
        # 取出当前分类，并拿到它所有子分类的名字（进入父分类也能看到子分类下的文章）
        category = self.get_slug_object()
        categorynames = [c.name for c in category.get_sub_categorys()]

        return self.get_optimized_article_queryset().filter(
            category__name__in=categorynames, status='p'
        )

    def get_queryset_cache_key(self):
        # 复用缓存的对象，不再重复查询数据库
        # 缓存键带上分类名和页码，保证不同分类、不同页各自独立缓存
        category = self.get_slug_object()
        return f'category_list_{category.name}_{self.page_number}'

    def get_context_data(self, **kwargs):
        category = self.get_slug_object()
        categoryname = category.name

        # 分类名里如果带斜杠（例如“生活/随笔”），只取最后一段作为页面显示名
        try:
            categoryname = categoryname.split('/')[-1]
        except BaseException:
            pass

        # 把页面类型和分类名传给模板，供顶部标题显示
        kwargs['page_type'] = CategoryDetailView.page_type
        kwargs['tag_name'] = categoryname
        
        # 添加基础SEO数据
        blog_setting = get_blog_setting()
        article_count = self.get_queryset().count()
        kwargs['seo_title'] = f"{categoryname} | {blog_setting.site_name}"
        kwargs['seo_description'] = f"浏览 {categoryname} 分类下的所有文章，共 {article_count} 篇文章。"
        kwargs['seo_keywords'] = f"{categoryname}, {blog_setting.site_keywords}"
        
        return super(CategoryDetailView, self).get_context_data(**kwargs)


# ============================================================
# 作者文章归档页：显示某位作者发表的全部已发布文章
# 地址形如 /author/<用户名>/
# ============================================================
class AuthorDetailView(OptimizedArticleQueryMixin, ArticleListView):
    """
    作者详情页（重构版）

    使用 OptimizedArticleQueryMixin 优化文章查询
    """
    page_type = '作者文章归档'

    def get_queryset_cache_key(self):
        # 用户名可能含中文，先用 slugify 转换再拼缓存键，避免中文键名带来的问题
        from uuslug import slugify
        author_name = slugify(self.kwargs['author_name'])
        return f'author_{author_name}_{self.page_number}'

    def get_queryset_data(self):
        # 只查这位作者写的、且已发布的文章
        author_name = self.kwargs['author_name']
        return self.get_optimized_article_queryset().filter(
            author__username=author_name, type='a', status='p'
        )

    def get_context_data(self, **kwargs):
        # 把页面类型和作者名传给模板，供顶部标题显示
        author_name = self.kwargs['author_name']
        kwargs['page_type'] = AuthorDetailView.page_type
        kwargs['tag_name'] = author_name
        
        # 添加基础SEO数据
        blog_setting = get_blog_setting()
        article_count = self.get_queryset().count()
        kwargs['seo_title'] = f"{author_name} 的文章 | {blog_setting.site_name}"
        kwargs['seo_description'] = f"浏览 {author_name} 发表的所有文章，共 {article_count} 篇。"
        kwargs['seo_keywords'] = f"{author_name}, {blog_setting.site_keywords}"
        
        return super(AuthorDetailView, self).get_context_data(**kwargs)


# ============================================================
# 标签列表视图：点某个标签后，显示打了这个标签的已发布文章
# 地址形如 /tag/<标签名>/
# ============================================================
class TagDetailView(SlugCachedMixin, OptimizedArticleQueryMixin, ArticleListView):
    """
    标签列表页面（重构版）

    使用 SlugCachedMixin 避免重复查询 Tag
    使用 OptimizedArticleQueryMixin 优化文章查询
    """
    page_type = '分类标签归档'
    slug_url_kwarg = 'tag_name'
    slug_model = Tag

    def get_queryset_data(self):
        # 使用 Mixin 缓存的对象，只查询一次
        # 先取出当前标签对象，再筛选出带这个标签、且已发布的文章
        tag = self.get_slug_object()
        return self.get_optimized_article_queryset().filter(
            tags__name=tag.name, type='a', status='p'
        )

    def get_queryset_cache_key(self):
        # 复用缓存的对象，不再重复查询数据库
        # 同样复用已缓存的标签对象，缓存键 = 标签名 + 页码
        tag = self.get_slug_object()
        return f'tag_{tag.name}_{self.page_number}'

    def get_context_data(self, **kwargs):
        tag = self.get_slug_object()
        # 把页面类型和标签名传给模板，供顶部标题显示
        kwargs['page_type'] = TagDetailView.page_type
        kwargs['tag_name'] = tag.name
        
        # 添加基础SEO数据
        blog_setting = get_blog_setting()
        article_count = self.get_queryset().count()
        kwargs['seo_title'] = f"{tag.name} | {blog_setting.site_name}"
        kwargs['seo_description'] = f"浏览所有关于 {tag.name} 的文章，共 {article_count} 篇内容。"
        kwargs['seo_keywords'] = f"{tag.name}, {blog_setting.site_keywords}"
        
        return super(TagDetailView, self).get_context_data(**kwargs)


# ============================================================
# 文章归档页：把所有已发布文章按时间顺序列出来（/archives.html）
# 和其他列表页不同：这里不分页，一次把全部文章显示完
# ============================================================
class ArchivesView(OptimizedArticleQueryMixin, ArticleListView):
    """
    文章归档页面（重构版）

    使用 OptimizedArticleQueryMixin 优化文章查询
    """
    page_type = '文章归档'
    paginate_by = None
    # 不分页：设为 None 即取消父类的分页行为
    page_kwarg = None
    # 不使用页码参数（因为不分页）
    template_name = 'blog/article_archives.html'

    def get_queryset_data(self):
        # 归档页只筛选已发布的文章，不限制文章类型
        return self.get_optimized_article_queryset().filter(status='p')

    def get_queryset_cache_key(self):
        # 归档页只有一份数据，缓存键固定为 archives
        return 'archives'


# ============================================================
# 友情链接页：显示后台登记、且已启用（is_enable=True）的友情链接
# ============================================================
class LinkListView(ListView):
    model = Links
    # 本视图使用的数据模型：友情链接表
    template_name = 'blog/links_list.html'

    def get_queryset(self):
        # 只显示管理员启用的链接，被停用的链接前台看不到
        return Links.objects.filter(is_enable=True)


# ============================================================
# 站内搜索视图：基于 Haystack + 搜索引擎（Elasticsearch / Whoosh）做全文检索
# 在父类基础上额外做了两件事：
#   1) 给命中的关键词加高亮   2) 支持“你是不是想搜 XXX”的拼写建议
# ============================================================
class EsSearchView(SearchView):
    def build_form(self, form_kwargs=None):
        """Override to enable highlighting"""
        # 重写父类方法，目的就是给搜索结果开启关键词高亮
        if form_kwargs is None:
            form_kwargs = {}

        # Enable highlighting for search results
        # 如果调用方没有传入查询集，就新建一个并开启高亮（命中的关键词会被包上标记，模板里显示为高亮样式）
        from haystack.query import SearchQuerySet
        if self.searchqueryset is None:
            sqs = SearchQuerySet().highlight()
        else:
            sqs = self.searchqueryset.highlight()

        form_kwargs['searchqueryset'] = sqs
        return super().build_form(form_kwargs=form_kwargs)

    # 组装模板上下文：搜索词、搜索表单、当前页结果、分页器、拼写建议
    def get_context(self):
        paginator, page = self.build_page()
        context = {
            "query": self.query,
            "form": self.form,
            "page": page,
            "paginator": paginator,
            "suggestion": None,
        }
        # 如果搜索引擎支持拼写检查，就取一条“你是不是想搜 XXX”的建议
        if hasattr(self.results, "query") and self.results.query.backend.include_spelling:
            context["suggestion"] = self.results.query.get_spelling_suggestion()
        # 合并额外的上下文数据（子类或插件提供的）
        context.update(self.extra_context())

        return context


# ============================================================
# 图片上传接口（简易图床）：供编辑器把图片上传到服务器
# 安全校验：必须带 sign 参数，且 sign 要等于 SECRET_KEY 连续两次 sha256 的结果
# ============================================================
@csrf_exempt
def fileupload(request):
    """
    该方法需自己写调用端来上传图片，该方法仅提供图床功能
    :param request:
    :return:
    """
    # 只处理 POST 上传请求，其他请求（GET 等）走最后的 else 返回 only for post
    if request.method == 'POST':
        # 取签名参数并校验，签名不对返回 403 禁止访问，防止别人乱传文件
        sign = request.GET.get('sign', None)
        if not sign:
            return HttpResponseForbidden()
        if not sign == get_sha256(get_sha256(settings.SECRET_KEY)):
            return HttpResponseForbidden()
        # 开始逐个处理上传的文件，并把可访问的图片地址收集到 response 里
        response = []
        for filename in request.FILES:
            # 按“年/月/日”分目录存放，避免所有文件挤在一个文件夹里
            timestr = timezone.now().strftime('%Y/%m/%d')
            imgextensions = ['jpg', 'png', 'jpeg', 'bmp']
            fname = u''.join(str(filename))
            # 根据扩展名判断是不是图片（图片后面会走压缩流程）
            isimage = len([i for i in imgextensions if fname.find(i) >= 0]) > 0
            base_dir = os.path.join(settings.STATICFILES, "files" if not isimage else "image", timestr)
            # 目录不存在就先创建出来
            if not os.path.exists(base_dir):
                os.makedirs(base_dir)
            # 用 uuid 生成随机文件名，避免同名覆盖，也避免用原始文件名带来的安全问题
            savepath = os.path.normpath(os.path.join(base_dir, f"{uuid.uuid4().hex}{os.path.splitext(filename)[-1]}"))
            # 安全兜底：如果最终路径跑到了目标目录之外，直接拒绝写入
            if not savepath.startswith(base_dir):
                return HttpResponse("only for post")
            # 分块写入文件内容（大文件也不会一次性占满内存）
            with open(savepath, 'wb+') as wfile:
                for chunk in request.FILES[filename].chunks():
                    wfile.write(chunk)
            # 图片额外压缩一次：质量 20 并开启优化，能明显减小体积
            if isimage:
                from PIL import Image
                image = Image.open(savepath)
                image.save(savepath, quality=20, optimize=True)
            # 转成可访问的静态文件地址并收集起来，最后统一返回
            url = static(savepath)
            response.append(url)
        return HttpResponse(response)

    else:
        return HttpResponse("only for post")


# ===== 错误处理视图 =====
# 下面这三个视图（404 页面不存在、500 服务器错误、403 无权限）本文件不再自己实现，
# 而是从 djangoblog.error_views 导入，方便统一维护和美化错误页面
# 注意：这些函数保留是为了向后兼容
# 实际实现已经移动到 djangoblog.error_views
# 可以在 urls.py 中直接引用新的实现

from djangoblog.error_views import (
    page_not_found_view,
    server_error_view,
    permission_denied_view
)


# 清空缓存的接口：访问这个地址就会把站点缓存全部清掉（一般用于后台手动刷新）
def clean_cache_view(request):
    cache.clear()
    # 调用项目封装的缓存工具，清空所有缓存
    return HttpResponse('ok')
