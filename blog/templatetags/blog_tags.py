# ============================================================
# blog/templatetags/blog_tags.py —— 博客前台的“模板标签库”，模板里 {% xxx %} / {{ x|xxx }} 用的自定义标签与过滤器都在这里
# 作用：Django 模板语法只提供 if / for 这类基础能力，模板里不能写 Python、也不能直接查数据库。
#       凡是“渲染页面时才需要的数据”（侧边栏聚合、面包屑、分页链接、上一篇下一篇、插件内容）
#       都先在这里包成一个标签（tag）或过滤器（filter），模板里用一行就能调用。
#       视图负责准备主数据，这个文件负责“渲染时的二次加工”，是 view 与 template 之间的粘合层。
# 本文件包含：
#   - 注册入口：register = template.Library()
#   - simple_tag（直接返回一段字符串/对象）：head_meta、timeformat、datetimeformat、
#     render_article_content、get_markdown_toc、current_nav_item、query、
#     render_plugin_widgets、plugin_*_resources、plugin_widget
#   - filter（配合 | 管道使用）：custom_markdown、sidebar_markdown、comment_markdown、
#     to_json、truncatechars_content、truncate、highlight_search_term、highlight_content、
#     gravatar_url、gravatar、addstr、get_reactions_for_user
#   - inclusion_tag（自带子模板的标签，返回值就是子模板的上下文）：load_breadcrumb、
#     load_articletags、load_sidebar、load_article_metas、load_pagination_info、
#     load_article_detail、load_article_detail_with_highlight、plugin_compressed_css / js
# 注释人：翟旌超（软件工程 3 班 2415304340，#zjc）
# 说明：本次任务只添加中文注释，没有改动任何一行原有代码逻辑
# ============================================================
# —— Python 标准库 ——
# hashlib：算哈希摘要（缓存键、签名用），本文件当前未直接调用，保留给标签扩展
# json：把 Python 对象序列化成 JSON 文本，模板里塞进 data- 属性交给前端 JS
# logging：输出日志，标签里出异常时记一笔，不让整个页面 500
# random：给标签徽章随机挑一种 bootstrap 颜色
# urllib：URL 处理工具（本文件暂未直接使用）
import hashlib
import json
import logging
import random
import urllib

# —— Django 框架自带模块 ——
# template：template.Library() 是注册自定义标签的唯一入口
# settings：读项目配置（时间格式、徽章色板）
# Q：构造 OR 条件（友情链接既要当前页类型，也要“全部页面”类型）
# get_object_or_404：按名字查标签/分类，查不到直接返回 404 页
# stringfilter：过滤器装饰器，先强制把入参转成字符串再进函数，避免 None 报错
# static：把静态文件相对路径拼成 STATIC_URL 下的完整地址（默认头像用）
# reverse：用路由名反查真实 URL，分页链接靠它生成
# mark_safe：把字符串标记为“可信 HTML”，模板渲染时不再转义尖括号
from django import template
from django.conf import settings
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.template.defaultfilters import stringfilter
from django.templatetags.static import static
from django.urls import reverse
from django.utils.safestring import mark_safe

# —— 本项目自己的模块 ——
# 数据模型：Article 文章、Category 分类、Tag 标签、Links 友情链接、
#           SideBar 后台可配置的自定义侧边栏块、LinkShowType 链接显示类型枚举
from blog.models import Article, Category, Tag, Links, SideBar, LinkShowType
# 评论模型，侧边栏“最新评论”和评论表情统计要用
from comments.models import Comment
# CommonMarkdown：Markdown 文本转 HTML；sanitize_html：过滤危险标签防 XSS
from djangoblog.utils import CommonMarkdown, sanitize_html
# cache：统一的缓存读写封装（底层可能是本地内存，也可能是 Redis）
from djangoblog.utils import cache
# get_current_site：取当前站点对象（django.contrib.sites），面包屑“首页”链接要用它的 domain
from djangoblog.utils import get_current_site
# OAuthUser：第三方登录用户表，同一个邮箱可能绑定了多个平台，头像比邮箱更真实
from oauth.models import OAuthUser
# hooks：插件钩子机制，允许插件在页面渲染流程中间插入自己的 HTML
from djangoblog.plugin_manage import hooks

# 本模块的日志记录器，按模块名输出，方便定位是哪个标签出的问题
logger = logging.getLogger(__name__)

# 注册器：Django 启动时会扫描每个 app 下的 templatetags 包，
# 把这里的 Library 实例收集起来；模板里写 {% load blog_tags %} 就是把本文件注册的
# 标签/过滤器全部导入当前模板，之后才能用 {% load_sidebar ... %} 这类写法。
register = template.Library()


# ------------------------------------------------------------
# —— 页面头部 / 时间格式化 ——
# ------------------------------------------------------------

# 【head_meta】—— 输出 <head> 里由插件提供的 meta 标签（SEO 描述、canonical、统计脚本等）
# 参数：context（Context）：takes_context=True 时 Django 自动传入当前渲染上下文，
#       插件可以从中拿到 request、当前文章等做判断
# 返回：str：插件拼接出的 HTML，已 mark_safe
# 说明：被 share_layout/base.html 的 <head> 调用，写法 {% head_meta %}。
#       apply_filters 是“过滤器式钩子”：初始值 '' 依次交给每个插件处理，插件返回新字符串。
#       mark_safe 是必须的：否则 <meta ...> 会被模板转义成 &lt;meta&gt;，在页面上显示成源码。
@register.simple_tag(takes_context=True)
def head_meta(context):
    return mark_safe(hooks.apply_filters('head_meta', '', context))


# 【timeformat】—— 按站点配置的“时间格式”把 datetime 格式化成时分
# 参数：data：一般是 datetime/date 对象，模板里传的是 article.pub_time 之类
# 返回：str：格式化后的时间字符串，失败返回空串
# 说明：格式串取自 settings.TIME_FORMAT（随语言设置变化），不写死 "%H:%M"，
#       这样切到英文站点时格式也跟着变。加 try/except 是因为模板标签抛异常会让整页 500，
#       而这里只是展示用，宁可显示空白也不要打断页面。
@register.simple_tag
def timeformat(data):
    try:
        return data.strftime(settings.TIME_FORMAT)
    except Exception as e:
        # 兜底：data 为 None 或没有 strftime 方法时走到这里，记日志后返回空串
        logger.error(e)
        return ""


# 【datetimeformat】—— 按站点配置输出“完整日期+时间”
# 参数：data（datetime）：要格式化的时间
# 返回：str：形如 2024年5月1日 10:30 的文本，失败返回空串
# 说明：被 blog/tags/article_meta_info.html 用在 <time datetime="..."> 上，
#       给搜索引擎读的机器时间与给人看的时间都靠它，同样是失败不报错只留空。
@register.simple_tag
def datetimeformat(data):
    try:
        return data.strftime(settings.DATE_TIME_FORMAT)
    except Exception as e:
        logger.error(e)
        return ""


# ------------------------------------------------------------
# —— Markdown 渲染类过滤器 ——
# ------------------------------------------------------------

# 【custom_markdown】—— 把 Markdown 正文转成 HTML，并交给插件做二次加工
# 参数：content（str）：Markdown 源码
# 返回：SafeString：可直接输出的 HTML
# 说明：两个装饰器叠加使用，顺序有意义：
#       @register.filter() 先把函数注册成模板过滤器（模板里 {{ article.body|custom_markdown }}）；
#       @stringfilter 再包一层，保证传进来的值先被转成字符串（None 会变 "None" 之前先变 ''）。
#       先 CommonMarkdown 转 HTML，再跑文章内容插件的钩子（比如代码高亮、目录注入），
#       最后 mark_safe —— 编辑器的 Markdown 渲染结果本身就是 HTML，不标记会被转义成纯文本。
@register.filter()
@stringfilter
def custom_markdown(content):
    """
    通用markdown过滤器，应用文章内容插件
    主要用于文章内容处理
    """
    html_content = CommonMarkdown.get_markdown(content)
    
    # 然后应用插件过滤器优化HTML
    # 函数内 import 是为了避免循环依赖：djangoblog.utils / plugin_manage 会反向 import blog 的模型，
    # 放到模块顶层导入会形成 import 环，Django 启动阶段就会报错
    from djangoblog.plugin_manage import hooks
    from djangoblog.plugin_manage.hook_constants import ARTICLE_CONTENT_HOOK_NAME
    optimized_html = hooks.apply_filters(ARTICLE_CONTENT_HOOK_NAME, html_content)
    
    return mark_safe(optimized_html)


# 【sidebar_markdown】—— 侧边栏自定义 HTML 块的 Markdown 渲染
# 参数：content（str）：后台 SideBar 表里填的 Markdown 文本
# 返回：SafeString：渲染后的 HTML
# 说明：和 custom_markdown 的区别是这里不跑文章插件 —— 侧边栏不是文章正文，
#       插件里的“版权声明 / 相关推荐”放到侧边栏没有意义。
#       模板里用法：{{ sidebar.content|sidebar_markdown|safe }}（模板再加 |safe 是双保险）。
@register.filter()
@stringfilter
def sidebar_markdown(content):
    html_content = CommonMarkdown.get_markdown(content)
    return mark_safe(html_content)


# 【render_article_content】—— 渲染文章正文（本项目最核心的标签）
# 参数：context（Context）：takes_context=True 自动注入，供插件读取 request / 当前页信息
#       article（Article）：要渲染的文章对象
#       is_summary（bool）：True 表示列表页只要摘要，False 表示详情页要全文
# 返回：SafeString：渲染好的 HTML，出错时返回空串
# 说明：为什么不直接用一个 filter？因为插件（版权声明、推荐位）需要知道“这是列表页还是详情页”、
#       需要 request 判断用户是否登录，普通 filter 只能拿到一个字符串参数，拿不到这些上下文。
#       模板里两种用法：
#         列表页 / 摘要：{% render_article_content article True %}
#         详情页 / 全文：{% render_article_content article False %}
#       分别出现在 blog/tags/article_info.html、blog/tags/article_info_highlight.html 和
#       blog/article_detail.html 里。
@register.simple_tag(takes_context=True)
def render_article_content(context, article, is_summary=False):
    """
    渲染文章内容，包含完整的上下文信息供插件使用
    
    Args:
        context: 模板上下文
        article: 文章对象
        is_summary: 是否为摘要模式（首页使用）
    """
    # 防御性判断：独立单页、异常数据可能没有 body 字段，直接返回空串，
    # 否则下面访问 article.body 会抛 AttributeError 让整页崩掉
    if not article or not hasattr(article, 'body'):
        return ''
    
    # 先转换Markdown为HTML
    html_content = CommonMarkdown.get_markdown(article.body)
    
    # 如果是摘要模式，先截断内容再应用插件
    if is_summary:
        # 从配置中获取摘要长度
        from djangoblog.utils import get_blog_setting
        from django.template.defaultfilters import truncatechars_html

        blogsetting = get_blog_setting()
        # 摘要长度由后台“站点设置”控制，改配置就能改首页摘要长短，不用改代码
        summary_length = blogsetting.article_sub_length

        # 使用truncatechars_html保留HTML标签结构，正确截断HTML内容
        # 注意是“先 Markdown 转 HTML 再截断”：如果对 Markdown 源码直接切片，
        # 可能把 ``` 代码块或 ** 加粗符号截成半个，HTML 就会残缺；
        # truncatechars_html 会按字符数截断并自动补全未闭合的标签
        html_content = truncatechars_html(html_content, summary_length)
    
    # 然后应用插件过滤器，传递完整的上下文
    from djangoblog.plugin_manage import hooks
    from djangoblog.plugin_manage.hook_constants import ARTICLE_CONTENT_HOOK_NAME
    
    # 获取request对象
    # 用 .get 而不是下标：某些渲染场景（如 sitemap、邮件模板）上下文里没有 request
    request = context.get('request')
    
    # 应用所有文章内容相关的插件
    # 注意：摘要模式下某些插件（如版权声明）可能不适用
    # 这里把 article / request / context / is_summary 一起传下去，
    # 插件据此判断“列表页就跳过版权声明”“登录用户才显示编辑按钮”等
    optimized_html = hooks.apply_filters(
        ARTICLE_CONTENT_HOOK_NAME,
        html_content,
        article=article,
        request=request,
        context=context,
        is_summary=is_summary  # 传递摘要标志，插件可以据此调整行为
    )

    # 如果有搜索查询，应用高亮
    # 只在摘要模式下高亮：详情页显示全文，关键词已经能从标题看出来，
    # 全文高亮反而会让页面花掉，也影响阅读
    query = context.get('query')
    if query and is_summary:
        optimized_html = highlight_content(optimized_html, query)

    return mark_safe(optimized_html)


# 【get_markdown_toc】—— 只取文章目录（Table Of Contents），不取正文
# 参数：content（str）：Markdown 源码
# 返回：SafeString：目录的 <ul>/<a> 结构 HTML
# 说明：模板里用 as 语法把结果存进变量：{% get_markdown_toc article.body as toc %}，
#       再由模板决定目录放在文章开头还是右侧悬浮栏（blog/tags/article_info_highlight.html）。
#       返回两个值的 get_markdown_with_toc 顺手丢掉了正文 body，因为正文另外由
#       render_article_content 渲染，重复渲染没有意义。
@register.simple_tag
def get_markdown_toc(content):
    from djangoblog.utils import CommonMarkdown
    body, toc = CommonMarkdown.get_markdown_with_toc(content)
    return mark_safe(toc)


# 【current_nav_item】—— 根据当前 URL 判断“顶部导航哪一项该高亮”
# 参数：request（HttpRequest）：模板里传 request 对象
# 返回：str：'index' / 'archives' / 'links' / 'category' / ''（都不匹配）
# 说明：模板里用 as 存成变量再比较，见 share_layout/nav.html：
#         {% current_nav_item request as nav_active %}
#         {% if nav_active == 'index' %}active{% endif %}
#       为什么返回字符串而不是布尔值：一个标签要服务 5 个导航项，
#       返回“当前是哪一项”比写 5 个布尔标签更省事，模板只做字符串比较。
#       注意 /page/2 也算首页（分页后的首页），标签页和分类页共用 'category' 高亮，
#       因为在导航上它们同属一个下拉菜单。
@register.simple_tag
def current_nav_item(request):
    """Determine the active navigation item based on the current URL path."""
    path = request.path
    if path == '/' or path.startswith('/page/'):
        return 'index'
    elif path.startswith('/archives'):
        return 'archives'
    elif path.startswith('/links'):
        return 'links'
    elif path.startswith('/category/'):
        return 'category'
    elif path.startswith('/tag/'):
        return 'category'
    return ''


# 【comment_markdown】—— 评论内容的 Markdown 渲染（带安全过滤）
# 参数：content（str）：评论正文
# 返回：SafeString：清洗后的 HTML
# 说明：和 custom_markdown 的关键区别是多了一步 sanitize_html。
#       文章正文是管理员/作者写的，可以信任；评论是任何访客提交的，
#       如果有人在评论里写 <script> 或 <img onerror=...>，直接 mark_safe 就会造成 XSS。
#       所以先 Markdown 转 HTML，再过一遍白名单清洗，最后才标记为安全。
@register.filter()
@stringfilter
def comment_markdown(content):
    content = CommonMarkdown.get_markdown(content)
    return mark_safe(sanitize_html(content))


# 【to_json】—— 把 Python 对象序列化成 JSON 字符串，方便写进 HTML 的 data-* 属性
# 参数：value（任意）：一般是从数据库算出来的 dict / list
# 返回：SafeString：JSON 文本，出错时返回 '{}'
# 说明：is_safe=True 表示“返回值可以直接放进 HTML，不用再转义”。
#       ensure_ascii=False 让中文、emoji 原样输出，而不是 \u4e2d 这种转义码 ——
#       否则 data 属性里全是编码，调试时完全看不懂。
#       bug 兜底：模板里这个过滤器常和 get_reactions_for_user 串联
#       （data-reactions='{{ comment_item|get_reactions_for_user:user|to_json }}'），
#       万一拿到不可序列化的对象，返回 '{}' 让前端按“无表情数据”处理，页面不至于崩。
@register.filter(is_safe=True)
def to_json(value):
    """
    将 Python 对象转换为 JSON 字符串，用于模板中传递给 JavaScript
    使用 ensure_ascii=False 以支持 emoji 等 unicode 字符
    """
    try:
        return mark_safe(json.dumps(value, ensure_ascii=False))
    except (TypeError, ValueError):
        return mark_safe('{}')


# 【get_reactions_for_user】—— 取某条评论的表情回应统计（含“当前用户点了哪个”）
# 参数：comment（Comment）：评论对象
#       user（User）：当前登录用户，未登录时是 AnonymousUser
# 返回：dict：{'👍': {'count': 3, 'reacted': True}, ...} 之类的结构
# 说明：用法 {{ comment|get_reactions_for_user:user }}，配合 |to_json 写进 data 属性，
#       前端 JS 才能把“我已经点过的那个表情”标成高亮状态。
#       未登录时传 None 而不是 AnonymousUser，让模型层少做一次身份判断；
#       try/except 包住是因为它在一个 for 循环里被调用几十次，
#       某一条评论的数据异常不能让整个评论列表都渲染失败。
@register.filter
def get_reactions_for_user(comment, user):
    """
    获取评论的 reactions 数据（过滤器方式）
    用法: {{ comment|get_reactions_for_user:user }}
    """
    try:
        return comment.get_reactions_summary(user if user.is_authenticated else None)
    except Exception as e:
        logger.error(f"Error getting reactions for comment {comment.id}: {e}")
        return {}




# 【truncatechars_content】—— 按后台配置的长度截断 HTML 正文，得到摘要
# 参数：content（str）：已经是 HTML 的正文
# 返回：str：截断并补全标签后的 HTML
# 说明：is_safe=True 是因为 truncatechars_html 会自己处理标签闭合，输出仍可当 HTML 用；
#       @stringfilter 防止传进来的是 None。
#       摘要长度读的是“站点设置”里的 article_sub_length，和后台改配置联动。
#       函数内 import 同样是为了避开循环依赖（utils 会引用 blog 的模型）。
@register.filter(is_safe=True)
@stringfilter
def truncatechars_content(content):
    """
    获得文章内容的摘要
    :param content:
    :return:
    """
    from django.template.defaultfilters import truncatechars_html
    from djangoblog.utils import get_blog_setting
    blogsetting = get_blog_setting()
    return truncatechars_html(content, blogsetting.article_sub_length)


# 【truncate】—— 去掉所有 HTML 标签后取前 150 个字符
# 参数：content（str）：带标签的 HTML
# 返回：str：纯文本片段
# 说明：和 truncatechars_content 的差别是它“先剥标签再切”：
#       适合用在 meta description、分享卡片的纯文本摘要这类不能出现标签的地方；
#       而 truncatechars_content 是“保留标签地切”，适合直接显示在页面上。
#       这里是简单的字符切片，英文单词可能被截一半，中文场景影响不大。
@register.filter(is_safe=True)
@stringfilter
def truncate(content):
    from django.utils.html import strip_tags

    return strip_tags(content)[:150]


# ------------------------------------------------------------
# —— inclusion_tag：自带子模板的标签 ——
# 这类标签的返回值不是 HTML 字符串，而是一个 dict，Django 拿它当上下文
# 去渲染装饰器里写死的那个子模板，最终把渲染结果插到调用处。
# 好处是模板结构可以单独维护，Python 侧只负责查数据。
# ------------------------------------------------------------

# 【load_breadcrumb】—— 文章详情页顶部的面包屑（首页 > 父分类 > 子分类 > 当前文章）
# 参数：article（Article）：当前文章
# 返回：dict：names（[(名称, 链接), ...] 从首页到当前分类）、title（文章标题）、count（分隔符数量）
# 说明：子模板是 blog/tags/breadcrumb.html，调用写法 {% load_breadcrumb article %}。
#       get_category_tree() 由模型层返回“从顶级分类到当前分类”的列表，顺序是父 -> 子；
#       这里 append 站点名（链接写 '/'，即首页），再 [::-1] 反转成 首页 -> 父 -> 子；
#       count 是元素个数 +1，模板用它决定画几个 '>' 分隔符（标题也算一级）。
@register.inclusion_tag('blog/tags/breadcrumb.html')
def load_breadcrumb(article):
    """
    获得文章面包屑
    :param article:
    :return:
    """
    names = article.get_category_tree()
    from djangoblog.utils import get_blog_setting
    blogsetting = get_blog_setting()
    # 站点域名只用于拼绝对地址，sites 框架支持一个项目挂多个域名
    site = get_current_site().domain
    # 首页固定在面包屑最左边，所以追加后再整体反转
    names.append((blogsetting.site_name, '/'))
    names = names[::-1]

    return {
        'names': names,
        'title': article.title,
        'count': len(names) + 1
    }


# 【load_articletags】—— 文章底部“标签”徽章列表
# 参数：article（Article）：当前文章
# 返回：dict：article_tags_list，元素是 (标签链接, 该标签下文章数, 标签对象, 随机颜色)
# 说明：子模板 blog/tags/article_tag_list.html，调用写法 {% load_articletags article %}。
#       这里先把数据整理成元组列表再交给模板，是为了让模板里只写一个 for 循环，
#       不用在模板里反复调用 tag.get_absolute_url / get_article_count（模板里每调一次都可能查库）。
#       random.choice(settings.BOOTSTRAP_COLOR_TYPES) 从配置的色板里随机取色，
#       同一个标签每次刷新颜色可能不同，纯粹是视觉效果，不影响功能。
@register.inclusion_tag('blog/tags/article_tag_list.html')
def load_articletags(article):
    """
    文章标签
    :param article:
    :return:
    """
    tags = article.tags.all()
    tags_list = []
    for tag in tags:
        # 标签的详情页地址（按 slug 生成，比中文名字做 URL 更稳）
        url = tag.get_absolute_url()
        # 该标签下已发布文章数，模板里显示成 “标签名(3)”
        count = tag.get_article_count()
        tags_list.append((
            url, count, tag, random.choice(settings.BOOTSTRAP_COLOR_TYPES)
        ))
    return {
        'article_tags_list': tags_list
    }


# 【load_sidebar】—— 加载整块侧边栏（全站最重的标签，一次聚合 8 类数据）
# 参数：user（User）：当前用户，只用于“评论框显示谁的头像/昵称”，不进缓存
#       linktype（str）：'i' 首页/其它页、'p' 文章详情页、'l' 列表页，决定侧边栏里显示哪类友情链接
# 返回：dict：侧边栏子模板所需的全部上下文
# 说明：子模板 blog/tags/sidebar.html，调用写法 {% load_sidebar user 'p' %}，
#       在首页、文章详情、归档、友链、搜索、错误页里都会调用，是“每页都要渲染”的标签。
#       所以这里做了整块缓存：侧边栏内容对同一类页面是固定的，
#       每个访客都重新查 8 次库太浪费，缓存后命中时只剩一次 cache.get。
@register.inclusion_tag('blog/tags/sidebar.html')
def load_sidebar(user, linktype):
    """
    加载侧边栏
    :return:
    """
    # 缓存键 = "sidebar" + linktype。为什么要把 linktype 拼进键里：
    # 三种页面的侧边栏只差“友情链接来源”这一块，其余内容都一样，
    # 用 linktype 区分即可，既不会串数据，也不必为每个页面存一份完整副本
    value = cache.get("sidebar" + linktype)
    if value:
        # 命中缓存：把当前请求的 user 塞回去再返回。
        # user 是“每个请求都不一样”的对象，绝对不能进缓存 ——
        # 否则 A 用户的登录态会被下一个访客读到
        value['user'] = user
        return value
    else:
        logger.info('load sidebar')
        from djangoblog.utils import get_blog_setting
        blogsetting = get_blog_setting()

        # 优化：添加select_related/prefetch_related减少查询
        # 最新文章：只要已发布（status='p'）的；select_related 让 author/category 两个外键
        # 用一条 JOIN 一起查回来，避免模板里 for 循环访问 article.author 时每篇再查一次库（N+1 问题）；
        # [:n] 这种切片会让 SQL 直接带 LIMIT，不会把整表取回内存再切
        recent_articles = Article.objects.filter(
            status='p'
        ).select_related('author', 'category')[:blogsetting.sidebar_article_count]

        # 全部分类，模板里按父子关系渲染成树
        sidebar_categorys = Category.objects.all()

        # 后台“自定义侧边栏”块：只取启用的，按 sequence 字段排序（后台可拖顺序）
        extra_sidebars = SideBar.objects.filter(
            is_enable=True
        ).order_by('sequence')

        # 热门文章：同一批已发布文章，改按阅读量 -views 倒序取前 n 篇
        most_read_articles = Article.objects.filter(
            status='p'
        ).select_related('author', 'category').order_by(
            '-views'
        )[:blogsetting.sidebar_article_count]

        # 归档月份列表：datetimes() 让数据库自己做“按月截断 + 去重”，
        # 只返回“有文章的月份”；如果自己用 Python 遍历全部文章再 set 去重，
        # 文章一多就会把所有行都读进内存
        dates = Article.objects.datetimes('creation_time', 'month', order='DESC')

        # 友情链接：既要当前页面类型的，也要“所有页面都显示”的（A = All），
        # 所以用 Q 对象拼 OR 条件；show_type 字段存的是字符串，故把 linktype 也转成 str 再比
        links = Links.objects.filter(is_enable=True).filter(
            Q(show_type=str(linktype)) | Q(show_type=LinkShowType.A)
        )

        # 最新评论：只取审核通过（is_enable=True）的，-id 倒序等价于“最新在前”；
        # select_related('author') 同样是为了避免模板循环里反复查用户表
        commment_list = Comment.objects.filter(
            is_enable=True
        ).select_related('author').order_by('-id')[:blogsetting.sidebar_comment_count]
        # 标签云 — 按文章数排序，取 top 20，size = (count/avg)*5+10
        # 思路：先给每个标签算出文章数，丢掉 0 篇的（if t[1] 为假），
        # 按数量倒序取前 20 个，再算这 20 个的平均数 dd 作为“基准字号”
        increment = 5
        tags = Tag.objects.all()
        sidebar_tags = None
        if tags and len(tags) > 0:
            s = sorted(
                [t for t in [(t, t.get_article_count()) for t in tags] if t[1]],
                key=lambda x: x[1], reverse=True
            )[:20]
            count = sum([t[1] for t in s])
            # dd 是平均值；用 1 兜底防止除零（标签总数为 0 或列表为空时）
            dd = 1 if (count == 0 or not len(s)) else count / len(s)
            # 字号公式：(该标签文章数 / 平均值) * 5 + 10，文章越多的标签字越大，最小 10px
            sidebar_tags = list(
                map(lambda x: (x[0], x[1], (x[1] / dd) * increment + 10), s))

        # 一次性打包成 dict，键名就是 sidebar.html 里用的变量名；
        # 站点设置里的开关（谷歌广告、评论开关、公安备案号）也一起缓存，
        # 否则每个访客都要再查一次 BlogSettings
        value = {
            'recent_articles': recent_articles,
            'sidebar_categorys': sidebar_categorys,
            'most_read_articles': most_read_articles,
            'article_dates': dates,
            'sidebar_comments': commment_list,
            'sidabar_links': links,
            'show_google_adsense': blogsetting.show_google_adsense,
            'google_adsense_codes': blogsetting.google_adsense_codes,
            'open_site_comment': blogsetting.open_site_comment,
            'show_gongan_code': blogsetting.show_gongan_code,
            'sidebar_tags': sidebar_tags,
            'extra_sidebars': extra_sidebars
        }
        # 有效期按 60*60*60*3 秒计算（约 7.5 天）。侧边栏数据变化不频繁，
        # 长缓存能省掉大量重复查询；后台发新文章后靠“清缓存”接口主动失效
        cache.set("sidebar" + linktype, value, 60 * 60 * 60 * 3)
        logger.info('set sidebar cache.key:{key}'.format(key="sidebar" + linktype))
        # 缓存里存的是不含 user 的公共数据，返回前才补上本次请求的用户
        value['user'] = user
        return value


# 【load_article_metas】—— 文章标题下方的 meta 信息条（作者、发布时间、分类、阅读数）
# 参数：article（Article）：当前文章；user（User）：当前用户（决定是否显示编辑按钮）
# 返回：dict：原样透传 article / user
# 说明：子模板 blog/tags/article_meta_info.html，调用写法 {% load_article_metas article user %}。
#       这个标签本身不查库，只是把两个对象转交给子模板 ——
#       用 inclusion_tag 是为了让“作者头像怎么拼、时间用哪种格式”这类展示细节
#       收在一个模板文件里，详情页和搜索页都能复用同一段 HTML。
@register.inclusion_tag('blog/tags/article_meta_info.html')
def load_article_metas(article, user):
    """
    获得文章meta信息
    :param article:
    :return:
    """
    return {
        'article': article,
        'user': user
    }


# 【load_pagination_info】—— 列表页底部的分页条（上一页 / 页码 / 省略号 / 下一页）
# 参数：page_obj（Page）：Django Paginator 当前页对象
#       page_type（str）：页面类型的中文标识，视图类里定义的 page_type 原样传进来
#       tag_name（str）：分类名 / 标签名 / 作者名，生成 URL 时用
# 返回：dict：previous_url、next_url、page_obj、page_range（页码或省略号的列表）
# 说明：子模板 blog/tags/article_pagination.html，调用写法
#       {% load_pagination_info page_obj page_type tag_name %}。
#       难点在于“同一个分页条要服务 4 种不同的路由”：首页、标签、分类、作者，
#       它们的 URL 名字和参数都不一样，所以这里按 page_type 分派。
@register.inclusion_tag('blog/tags/article_pagination.html')
def load_pagination_info(page_obj, page_type, tag_name):
    previous_url = ''
    next_url = ''

    # Pre-resolve slug for tag/category to avoid repeated DB queries
    # 标签/分类的详情地址用的是 slug 而不是中文 name，
    # 所以在拼链接之前先查一次 slug 存起来；如果放到 _build_url 里查，
    # 页码循环每拼一个链接就要多打一次数据库
    _slug = None
    if page_type == '分类标签归档':
        _slug = get_object_or_404(Tag, name=tag_name).slug
    elif page_type == '分类目录归档':
        _slug = get_object_or_404(Category, name=tag_name).slug

    def _build_url(page_number):
        """Build URL for a given page number based on page_type."""
        # 内部函数（闭包）：直接用到外层的 page_type / _slug / tag_name，
        # 这样调用方只需要关心“第几页”，不用每次都把上下文传一遍
        if page_type == '':
            # 首页分页：/page/2/
            return reverse('blog:index_page', kwargs={'page': page_number})
        elif page_type == '分类标签归档':
            return reverse('blog:tag_detail_page',
                           kwargs={'page': page_number, 'tag_name': _slug})
        elif page_type == '作者文章归档':
            # 作者页用 username 做路径参数，这里直接拿 tag_name 传进去
            return reverse('blog:author_detail_page',
                           kwargs={'page': page_number, 'author_name': tag_name})
        elif page_type == '分类目录归档':
            return reverse('blog:category_detail_page',
                           kwargs={'page': page_number, 'category_name': _slug})
        return ''

    # 必须先 has_next()/has_previous() 判断再取页码：
    # 在最后一页调用 next_page_number() 会抛 EmptyPage 异常，整个列表页就 500 了
    if page_obj.has_next():
        next_url = _build_url(page_obj.next_page_number())
    if page_obj.has_previous():
        previous_url = _build_url(page_obj.previous_page_number())

    # Build page range with URLs for numbered pagination
    # 页码窗口：页数很多时不能把 200 个页码全画出来，只画“首页 + 当前页附近 + 末页”
    current_page = page_obj.number
    total_pages = page_obj.paginator.num_pages
    page_range = []

    if total_pages > 1:
        # Show at most 5 page numbers centered around current page
        # with ellipsis indicators
        if total_pages <= 7:
            # 页数少，全部列出最直观
            nums = range(1, total_pages + 1)
        else:
            # 用 set 收集是因为“首页/末页”可能与“当前页 ±2”重叠，去重后再排序
            nums = set()
            nums.add(1)
            nums.add(total_pages)
            # max/min 保证不会越界到 0 或 total_pages+1
            for i in range(max(1, current_page - 2), min(total_pages + 1, current_page + 3)):
                nums.add(i)
            nums = sorted(nums)

        # last_num 记录上一个画出来的页码，两个页码之间断开（差 > 1）就补一个省略号
        last_num = 0
        for num in nums:
            if num - last_num > 1:
                # {'type': 'ellipsis'} 让子模板渲染成 “…” 而不是可点的页码
                page_range.append({'type': 'ellipsis'})
            page_range.append({
                'type': 'page',
                'number': num,
                'url': _build_url(num),
                'is_current': num == current_page,
            })
            last_num = num

    return {
        'previous_url': previous_url,
        'next_url': next_url,
        'page_obj': page_obj,
        'page_range': page_range,
    }


# 【load_article_detail】—— 列表页/搜索页里“一张文章卡片”的渲染
# 参数：article（Article）：文章对象
#       isindex（bool）：True 表示列表页，子模板只显示摘要，不显示全文
#       user（User）：当前用户
#       query（str|None）：搜索关键词，传给子模板做标题高亮
# 返回：dict：子模板上下文
# 说明：子模板 blog/tags/article_info.html，调用写法 {% load_article_detail article True user %}
#       （搜索页多传一个 query：{% load_article_detail result.object True user query %}）。
#       读取 open_site_comment 是让卡片底部决定“要不要显示评论入口”，
#       这样全站评论开关一改，所有列表页同时生效。
@register.inclusion_tag('blog/tags/article_info.html')
def load_article_detail(article, isindex, user, query=None):
    """
    加载文章详情
    :param article:
    :param isindex:是否列表页，若是列表页只显示摘要
    :param query: 搜索查询词（用于高亮）
    :return:
    """
    from djangoblog.utils import get_blog_setting
    blogsetting = get_blog_setting()

    return {
        'article': article,
        'isindex': isindex,
        'user': user,
        'query': query,  # 传递查询词
        'open_site_comment': blogsetting.open_site_comment,
    }


# 【load_article_detail_with_highlight】—— 搜索页专用：渲染“已带高亮”的文章卡片
# 参数：article（Article）：文章对象
#       highlighted（dict）：Haystack 已经算好的高亮片段，形如 {'title': [...], 'body': [...]}
#       isindex（bool）：是否列表页
#       user（User）：当前用户
# 返回：dict：子模板上下文
# 说明：子模板是 blog/tags/article_info_highlight.html，与 article_info.html 的区别是
#       它不再自己算关键词位置，而是直接用搜索引擎返回的高亮片段 ——
#       全文检索库知道“哪个字段命中了、周围上下文是什么”，比自己写正则更准，
#       也不会因为关键词出现在无关地方而高亮错。
@register.inclusion_tag('blog/tags/article_info_highlight.html')
def load_article_detail_with_highlight(article, highlighted, isindex, user):
    """
    加载文章详情（带搜索高亮）
    :param article: 文章对象
    :param highlighted: 高亮数据字典 {'title': [...], 'body': [...]}
    :param isindex: 是否列表页，若是列表页只显示摘要
    :param user: 当前用户
    :return:
    """
    from djangoblog.utils import get_blog_setting
    blogsetting = get_blog_setting()

    return {
        'article': article,
        'highlighted': highlighted,
        'isindex': isindex,
        'user': user,
        'open_site_comment': blogsetting.open_site_comment,
    }


# ------------------------------------------------------------
# —— 搜索关键词高亮 ——
# ------------------------------------------------------------

# 【highlight_search_term】—— 在“纯文本”里高亮搜索词（主要给文章标题用）
# 参数：text（str）：原始文本，模板里传的是 article.title，本身不含 HTML
#       query（str）：用户输入的搜索词，可能包含空格分隔的多个词
# 返回：SafeString：把命中词包上 <mark> 的文本
# 说明：用法 {{ article.title|highlight_search_term:query }}。
#       几个细节都有原因：
#       - 先 split：搜索支持“Django 缓存”这种多关键词，逐词标；
#       - 跳过长度 < 2 的词：否则搜“的”“a”会把整页文字标满，反而看不清；
#       - re.escape：用户输入里可能有 . * ( ) 这类正则元字符，
#         不转义会当成正则语法，轻则标错，重则让 re.compile 抛异常；
#       - re.IGNORECASE + \1：忽略大小写匹配，但替换回去的是“原文的大小写”，
#         这样 DJANGO 还是显示成 DJANGO，不会被改成查询词的小写形式；
#       - mark_safe：结果里有 <mark> 标签，不标记会被转义成文字。
@register.filter
def highlight_search_term(text, query):
    """
    在文本中高亮搜索关键词
    :param text: 原始文本
    :param query: 搜索查询词
    :return: 高亮后的HTML
    """
    if not query or not text:
        return text

    import re
    # 分词处理（支持空格分隔的多个词）
    terms = query.split()

    for term in terms:
        if len(term) < 2:  # 忽略单字符
            continue
        # 使用正则替换，不区分大小写，但保留原文本的大小写
        pattern = re.compile(r'(' + re.escape(term) + r')', re.IGNORECASE)
        text = pattern.sub(r'<mark>\1</mark>', text)

    return mark_safe(text)


# 【highlight_content】—— 在“HTML 正文”里高亮搜索词（给摘要用）
# 参数：html_content（str）：Markdown 转出来的 HTML
#       query（str）：搜索词
# 返回：SafeString：去标签后的纯文本 + <mark> 标记
# 说明：为什么不能像标题那样直接在 HTML 上做正则替换 ——
#       关键词可能正好出现在 class="xxx"、href="/tag/django" 这类属性里，
#       替换进去会把标签结构破坏掉（<a href="/tag/<mark>django</mark>"> 直接坏页）。
#       所以这里先用 BeautifulSoup 解析成 DOM，删掉 code/pre/script/style
#       （代码块里高亮会把代码标得乱七八糟，还容易撑破布局），
#       再 get_text() 取纯文本，最后在纯文本上做替换。
#       代价是：高亮后的摘要不再有链接、图片等 HTML 结构，只剩文字。
@register.filter
def highlight_content(html_content, query):
    """
    对HTML内容提取纯文本并进行搜索高亮
    会去除HTML标签，只保留文本内容，并高亮搜索关键词
    跳过代码块中的内容
    :param html_content: HTML内容
    :param query: 搜索查询词
    :return: 高亮后的纯文本（包含mark标签）
    """
    if not query or not html_content:
        return html_content

    from bs4 import BeautifulSoup
    import re

    # 使用BeautifulSoup解析HTML
    soup = BeautifulSoup(html_content, 'html.parser')

    # 移除代码块、脚本等标签（不要它们的内容）
    # decompose() 是连内容带标签一起删除，而不是只删标签保留文字
    for tag in soup.find_all(['code', 'pre', 'script', 'style']):
        tag.decompose()

    # 提取纯文本
    # separator=' ' 保证相邻块级元素之间留空格，否则“段落一”和“段落二”会粘成一个词
    # strip=True 去掉首尾空白
    text = soup.get_text(separator=' ', strip=True)

    # 分词处理（支持空格分隔的多个词）
    terms = [term for term in query.split() if len(term) >= 2]

    if not terms:
        # 没有合格的关键词（比如用户只搜了一个字母），直接返回纯文本，不做标记
        return text

    # 对纯文本进行高亮
    for term in terms:
        # 使用正则替换，不区分大小写
        pattern = re.compile(r'(' + re.escape(term) + r')', re.IGNORECASE)
        text = pattern.sub(r'<mark>\1</mark>', text)

    return mark_safe(text)


# 返回用户头像URL
# 模板使用方法:  {{ email|gravatar_url:150 }}
# ------------------------------------------------------------
# —— 用户头像 ——
# ------------------------------------------------------------

# 【gravatar_url】—— 根据邮箱取用户头像地址（优先第三方登录头像，其次本地默认头像）
# 参数：email（str）：用户邮箱，模板里传 comment.author.email
#       size（int）：头像边长，仅用于和 gravatar 保持同样的调用写法，本地图片不按尺寸裁剪
# 返回：str：头像 URL
# 说明：头像要出现在每条评论上，同一个用户会在列表里重复出现，
#       所以先查缓存 'avatar/' + email，命中就直接返回，不再查 OAuthUser 表。
#       为什么不走 gravatar.com：国外站点在国内访问经常超时，
#       图片加载失败会让评论区一片空白，所以项目把默认头像放在本地静态目录里。
#       用法：{{ comment_item.author.email|gravatar_url:150 }}。
@register.filter
def gravatar_url(email, size=40):
    """获得用户头像 - 优先使用OAuth头像，否则使用默认头像"""
    # 缓存键按邮箱区分：一个邮箱对应一个头像，和用户 id 无关
    cachekey = 'avatar/' + email
    url = cache.get(cachekey)
    if url:
        return url
    
    # 检查OAuth用户是否有自定义头像
    usermodels = OAuthUser.objects.filter(email=email)
    if usermodels:
        # 过滤出有头像的用户
        # 同一邮箱可能绑定了 GitHub / Google 等多个账号，picture 为空的记录跳过
        users_with_picture = list(filter(lambda x: x.picture is not None, usermodels))
        if users_with_picture:
            # 获取默认头像路径用于比较
            default_avatar_path = static('blog/img/avatar.png')
            
            # 优先选择非默认头像的用户，否则选择第一个
            # 判断条件写两个是因为部署时 STATIC_URL 可能带前缀，
            # 存进库里的可能是 "/static/blog/img/avatar.png" 也可能带 CDN 域名，
            # 用 endswith('/avatar.png') 兜住“路径不同但都是默认头像”的情况
            non_default_users = [u for u in users_with_picture if u.picture != default_avatar_path and not u.picture.endswith('/avatar.png')]
            selected_user = non_default_users[0] if non_default_users else users_with_picture[0]
            
            url = selected_user.picture
            cache.set(cachekey, url, 60 * 60 * 24)  # 缓存24小时
            

            # 日志里区分 default / non-default，排查“头像怎么不更新”时有据可查
            avatar_type = 'non-default' if non_default_users else 'default'
            logger.info('Using {} OAuth avatar for {} from {}'.format(avatar_type, email, selected_user.type))
            return url
    
    # 使用默认头像
    # 没有任何 OAuth 记录（本地注册用户）时也走这里，兜底保证页面一定有图
    url = static('blog/img/avatar.png')
    cache.set(cachekey, url, 60 * 60 * 24)  # 缓存24小时
    logger.info('Using default avatar for {}'.format(email))
    return url


# 【gravatar】—— 直接输出一个 <img> 头像标签
# 参数：email（str）：用户邮箱；size（int）：宽高像素
# 返回：SafeString：<img ...> 标签
# 说明：地址部分复用 gravatar_url，避免两套逻辑；height/width 同时写上，
#       是为了图片加载出来之前就占好位置，防止评论区在加载时“跳动”。
#       目前模板里主要用 gravatar_url（因为需要 srcset 支持二倍图），
#       这个过滤器保留给“只想快速放个头像”的地方用。
@register.filter
def gravatar(email, size=40):
    """获得用户头像HTML标签"""
    url = gravatar_url(email, size)
    return mark_safe(
        '<img src="%s" height="%d" width="%d" class="avatar" alt="用户头像">' %
        (url, size, size))


# ------------------------------------------------------------
# —— 模板里的小工具 ——
# ------------------------------------------------------------

# 【query】—— 在模板里对 QuerySet 做 filter，相当于“模板版的 .filter()”
# 参数：qs（QuerySet）：视图传进来的原始查询集
#       **kwargs：任意查询条件，支持 __isnull / __gt 这类双下划线写法
# 返回：QuerySet：过滤后的查询集
# 说明：Django 模板里不能写 qs.filter(...)，所以用这个标签补上。
#       模板写法（as 语法会把结果存成变量）：
#         {% query nav_category_list parent_category__isnull=True as nav_top_cats %}
#         {% query nav_category_list parent_category=category as nav_children %}
#       为什么需要：导航栏要按父子关系画多级菜单，视图里一次性把全部分类取出来，
#       模板里按需过滤成“顶级分类”“某分类的子分类”，
#       避免为每种情况在视图里单写一个查询。
#       kwargs 原样透传给 filter，所以查询语法和 models 里完全一致。
@register.simple_tag
def query(qs, **kwargs):
    """ template tag which allows queryset filtering. Usage:
          {% query books author=author as mybooks %}
          {% for book in mybooks %}
            ...
          {% endfor %}
    """
    return qs.filter(**kwargs)


# 【addstr】—— 字符串拼接
# 参数：arg1 / arg2（任意）：会被 str() 转成字符串
# 返回：str：拼接结果
# 说明：模板自带的 + 只能做数字加法，|add 也是数字相加，
#       要拼字符串（比如“第 3 页”这种）就得有专门的过滤器。
#       两边都套 str() 是为了容错：传进来 int、None 也不会抛 TypeError。
@register.filter
def addstr(arg1, arg2):
    """concatenate arg1 & arg2"""
    return str(arg1) + str(arg2)


# ------------------------------------------------------------
# —— 插件系统模板标签 ——
# 插件（plugin_manage 目录下）是一套“可插拔”的功能模块：
# 它们在启动时被 loader 加载，然后通过下面这些标签把
# CSS/JS/HTML 组件注入到页面的固定位置，不改主模板代码就能加功能。
# ------------------------------------------------------------

# === 插件系统模板标签 ===

# 【render_plugin_widgets】—— 渲染某个“位置”上所有插件注册的组件
# 参数：context（Context）：takes_context=True 自动注入
#       position（str）：位置标识，比如 'article_bottom'（文章末尾）、'sidebar'（侧边栏）
#       **kwargs：额外传给插件的参数，如 article=article
# 返回：SafeString：按优先级拼好的 HTML
# 说明：调用写法 {% render_plugin_widgets 'article_bottom' article=article %}，
#       出现在 blog/article_detail.html 和 blog/tags/article_info_highlight.html 的文章底部。
#       模板只声明“这里有个插槽”，具体插什么由插件决定 —— 这就是插件化的意义：
#       新增一个“相关推荐”插件，不需要改任何页面模板。
@register.simple_tag(takes_context=True)
def render_plugin_widgets(context, position, **kwargs):
    """
    渲染指定位置的所有插件组件
    
    Args:
        context: 模板上下文
        position: 位置标识
        **kwargs: 传递给插件的额外参数
    
    Returns:
        按优先级排序的所有插件HTML内容
    """
    from djangoblog.plugin_manage.loader import get_loaded_plugins
    
    widgets = []
    
    for plugin in get_loaded_plugins():
        try:
            # 每个插件单独 try：一个第三方插件写错不能连累整页，
            # 记下日志、跳过它，其余插件照常渲染
            widget_data = plugin.render_position_widget(
                position=position,
                context=context,
                **kwargs
            )
            if widget_data:
                widgets.append(widget_data)
        except Exception as e:
            logger.error(f"Error rendering widget from plugin {plugin.PLUGIN_NAME}: {e}")
    
    # 按优先级排序（数字越小优先级越高）
    widgets.sort(key=lambda x: x['priority'])
    
    # 合并HTML内容
    html_parts = [widget['html'] for widget in widgets]
    return mark_safe(''.join(html_parts))


# 【plugin_critical_head_resources】—— 注入“关键 head 资源”（必须在页面渲染前执行）
# 参数：context（Context）：当前模板上下文
# 返回：SafeString：多个插件关键 HTML 用换行拼接
# 说明：被 base.html 的 <head> 最前面调用，写法 {% plugin_critical_head_resources %}。
#       所谓“关键”是指防闪烁脚本、主题色变量这类必须在 CSS 之前同步执行的代码：
#       如果放到页面底部再执行，用户会先看到一瞬间的白色闪屏（FOUC）。
@register.simple_tag(takes_context=True)
def plugin_critical_head_resources(context):
    """
    渲染所有插件的关键head资源（阻塞式加载）

    用于防闪烁脚本等必须在页面渲染前执行的关键代码。
    这些资源会在<head>标签的最开始位置加载，在所有CSS之前。
    """
    from djangoblog.plugin_manage.loader import get_loaded_plugins

    resources = []

    for plugin in get_loaded_plugins():
        try:
            critical_html = plugin.get_critical_head_html(context)
            if critical_html:
                resources.append(critical_html)

        except Exception as e:
            logger.error(f"Error loading critical head resources from plugin {plugin.PLUGIN_NAME}: {e}")

    # 用 '\n' 而不是 '' 连接：万一插件返回的是单行注释 //...，
    # 直接拼接会把下一个插件的代码也注释掉
    return mark_safe('\n'.join(resources))


# 【plugin_head_resources】—— 注入普通 head 资源（meta、站点统计脚本等）
# 参数：context（Context）：当前模板上下文
# 返回：SafeString：拼接后的 HTML
# 说明：CSS 文件不在这里输出 —— 它们已经统一交给下面的 plugin_compressed_css
#       集中输出，避免同一个 CSS 被插件和压缩系统各引一次。
@register.simple_tag(takes_context=True)
def plugin_head_resources(context):
    """渲染所有插件的head资源（仅自定义HTML，CSS已集成到压缩系统）"""
    from djangoblog.plugin_manage.loader import get_loaded_plugins

    resources = []

    for plugin in get_loaded_plugins():
        try:
            # 只处理自定义head HTML（CSS文件已通过压缩系统处理）
            head_html = plugin.get_head_html(context)
            if head_html:
                resources.append(head_html)

        except Exception as e:
            logger.error(f"Error loading head resources from plugin {plugin.PLUGIN_NAME}: {e}")

    return mark_safe('\n'.join(resources))


# 【plugin_body_resources】—— 注入 body 末尾的自定义 HTML/JS
# 参数：context（Context）：当前模板上下文
# 返回：SafeString：拼接后的 HTML
# 说明：放在 </body> 前，此时 DOM 已经解析完，脚本里可以直接操作页面元素，
#       适合“页面加载完再初始化”的插件逻辑（统计、悬浮按钮等）。
@register.simple_tag(takes_context=True)
def plugin_body_resources(context):
    """渲染所有插件的body资源（仅自定义HTML，JS已集成到压缩系统）"""
    from djangoblog.plugin_manage.loader import get_loaded_plugins
    
    resources = []
    
    for plugin in get_loaded_plugins():
        try:
            # 只处理自定义body HTML（JS文件已通过压缩系统处理）
            body_html = plugin.get_body_html(context)
            if body_html:
                resources.append(body_html)
                
        except Exception as e:
            logger.error(f"Error loading body resources from plugin {plugin.PLUGIN_NAME}: {e}")
    
    return mark_safe('\n'.join(resources))


# 【plugin_compressed_css】—— 收集所有插件的 CSS 文件，一次性输出 <link>
# 参数：无
# 返回：dict：css_files，已经拼好的样式表地址列表
# 说明：inclusion_tag，子模板是 plugins/css_includes.html，
#       被 base.html 的 <head> 调用，写法 {% plugin_compressed_css %}。
#       集中收集的好处：插件只需要声明“我有哪些 css 文件”，
#       页面模板里永远只有一行引入，加插件不用改模板；
#       以后要合并压缩样式表，也只需要改这一个地方。
@register.inclusion_tag('plugins/css_includes.html')
def plugin_compressed_css():
    """插件CSS压缩包含模板"""
    from djangoblog.plugin_manage.loader import get_loaded_plugins
    
    css_files = []
    for plugin in get_loaded_plugins():
        for css_file in plugin.get_css_files():
            # get_static_url 会把插件包内的相对路径补成带 STATIC_URL 的完整地址，
            # 这样模板里不用关心插件装在哪个目录
            css_url = plugin.get_static_url(css_file)
            css_files.append(css_url)
    
    return {'css_files': css_files}


# 【plugin_compressed_js】—— 收集所有插件的 JS 文件，一次性输出 <script>
# 参数：无
# 返回：dict：js_files，已经拼好的脚本地址列表
# 说明：子模板 plugins/js_includes.html，被 base.html 放在页面底部调用，
#       写法 {% plugin_compressed_js %}。放在底部是为了不阻塞页面渲染。
@register.inclusion_tag('plugins/js_includes.html')
def plugin_compressed_js():
    """插件JS压缩包含模板"""
    from djangoblog.plugin_manage.loader import get_loaded_plugins
    
    js_files = []
    for plugin in get_loaded_plugins():
        for js_file in plugin.get_js_files():
            js_url = plugin.get_static_url(js_file)
            js_files.append(js_url)
    
    return {'js_files': js_files}




# 【plugin_widget】—— 精确渲染“某一个插件的某一个组件”
# 参数：context（Context）：当前模板上下文
#       plugin_name（str）：插件标识（slug 或名字）
#       widget_type（str）：组件类型，对应插件模板目录下的文件名，默认 'default'
#       **kwargs：额外参数，会和当前上下文一起进入插件模板
# 返回：SafeString：渲染结果，插件不存在或出错时返回空串
# 说明：和 render_plugin_widgets 的区别是它“点名”渲染，不看位置，
#       适合在页面某个具体位置固定放一个组件，比如文章底部的相关推荐：
#         {% plugin_widget 'article_recommendation' 'bottom' article=article count=5 %}
#       context.flatten() 把 Django 的 Context 摊平成普通 dict，
#       再 **kwargs 覆盖，这样插件模板里既能用页面原有变量，又能用调用时传的参数。
@register.simple_tag(takes_context=True)
def plugin_widget(context, plugin_name, widget_type='default', **kwargs):
    """
    渲染指定插件的组件
    
    使用方式：
    {% plugin_widget 'article_recommendation' 'bottom' article=article count=5 %}
    """
    from djangoblog.plugin_manage.loader import get_plugin_by_slug
    
    plugin = get_plugin_by_slug(plugin_name)
    # hasattr 判断：插件可能存在但没实现 render_template，
    # 直接调用会抛 AttributeError，这里优雅跳过
    if plugin and hasattr(plugin, 'render_template'):
        try:
            widget_context = {**context.flatten(), **kwargs}
            # 约定式命名：组件类型直接对应模板文件名，如 bottom.html / default.html，
            # 插件开发者不用额外写配置
            template_name = f"{widget_type}.html"
            return mark_safe(plugin.render_template(template_name, widget_context))
        except Exception as e:
            logger.error(f"Error rendering plugin widget {plugin_name}.{widget_type}: {e}")
    

    # 插件不存在 / 模板渲染失败：返回空串，页面照常显示其他部分
    return ""