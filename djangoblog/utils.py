#!/usr/bin/env python
# encoding: utf-8
"""
公共工具模块（标注人：熊圆好）
作用：汇集全站复用的基础能力——缓存装饰器、站点配置读取、
     Markdown 渲染、邮件发送入口、签名/验证码生成、
     HTML 安全清洗（XSS 防护）等，供各 app 的 views/models 引用。
"""

# xyh：模块级说明 —— 全站公共工具箱，共六类能力：
# xyh：  1) 签名与随机码：get_sha256（HMAC-SHA256 防篡改）、generate_code（数字验证码）
# xyh：  2) 缓存：cache_decorator 通用结果缓存装饰器，expire_view_cache /
# xyh：     delete_view_cache / delete_sidebar_cache 三类缓存失效入口
# xyh：  3) 站点配置：get_current_site、get_blog_setting（BlogSettings 单例，缺库自动建默认）
# xyh：  4) 内容渲染：CommonMarkdown（extra/codehilite/toc/tables 四扩展）
# xyh：  5) 邮件：send_email —— 只派发信号，真正发信在 blog_signals.py，实现解耦与发送留痕
# xyh：  6) XSS 防护：sanitize_html + ALLOWED_TAGS / ALLOWED_ATTRIBUTES /
# xyh：     ALLOWED_CLASSES / ALLOWED_PROTOCOLS 四张白名单
# xyh：注释标识统一为 "# xyh："，便于质量分析报告的小组分工表按标识统计行数。

import logging
import os
import random
import string
import uuid
import hashlib
import hmac

import bleach
import markdown
import requests
from django.conf import settings
from django.contrib.sites.models import Site
from django.core.cache import cache
from django.templatetags.static import static

logger = logging.getLogger(__name__)


# xyh：取文章/评论最大主键，供压测造数
def get_max_articleid_commentid():
    """返回当前文章与评论的最大主键 ID（压测脚本生成测试数据用）。"""
    from blog.models import Article
    from comments.models import Comment
    return (Article.objects.latest().pk, Comment.objects.latest().pk)


# xyh：HMAC-SHA256 签名入口，防链接/参数被伪造
def get_sha256(value):
    """用 SECRET_KEY 对入参做 HMAC-SHA256 签名。

    用途：注册激活链接、图床上传 sign 参数等场景，
    保证链接/参数不可被伪造篡改。
    """
    key = settings.SECRET_KEY.encode('utf-8')  # xyh：密钥取全局 SECRET_KEY
    msg = str(value).encode('utf-8')  # xyh：入参统一转字符串再编码，保证可签名
    return hmac.new(key, msg, hashlib.sha256).hexdigest()  # xyh：输出十六进制摘要作为签名


# xyh：通用结果缓存装饰器工厂（默认 3 分钟）
def cache_decorator(expiration=3 * 60):
    """通用结果缓存装饰器（默认 3 分钟）。

    缓存键优先取对象的 get_cache_key()，否则用
    「函数+参数」的 SHA256 摘要生成；None 结果以哨兵值
    __default_cache_value__ 缓存，避免缓存穿透。
    典型用法：@cache_decorator(10h) 标注分类树、标签计数等
    高频低变的查询方法。
    """
    def wrapper(func):   # xyh：装饰器第二层：持有被装饰函数，返回带缓存的替代函数
        def news(*args, **kwargs):
            try:
                view = args[0]
                key = view.get_cache_key()
            except:
                key = None   # xyh：对象无 get_cache_key() 时走"函数+参数"摘要分支
            if not key:
                unique_str = repr((func, args, kwargs))   # xyh：用函数对象与实参做唯一串

                m = hashlib.sha256(unique_str.encode('utf-8'))
                key = m.hexdigest()
            value = cache.get(key)
            if value is not None:
                # logger.info('cache_decorator get cache:%s key:%s' % (func.__name__, key))
                if str(value) == '__default_cache_value__':
                    return None   # xyh：哨兵值表示"上次结果就是 None"，避免把 None 当未命中重复查库
                else:
                    return value
            else:
                logger.debug(
                    'cache_decorator set cache:%s key:%s' %
                    (func.__name__, key))
                value = func(*args, **kwargs)   # xyh：未命中时真正执行被装饰函数
                if value is None:
                    cache.set(key, '__default_cache_value__', expiration)   # xyh：None 结果也用哨兵缓存，防穿透
                else:
                    cache.set(key, value, expiration)
                return value

        return news

    return wrapper


# xyh：精确失效某 path 的整页视图缓存（评论审核通过/文章更新后调用）
def expire_view_cache(path, servername, serverport, key_prefix=None):
    '''
    刷新视图缓存
    :param path:url路径
    :param servername:host
    :param serverport:端口
    :param key_prefix:前缀
    :return:是否成功
    '''
    from django.http import HttpRequest
    from django.utils.cache import get_cache_key

    request = HttpRequest()   # xyh：伪造一个请求对象，让 Django 按同样规则推算缓存键
    request.META = {'SERVER_NAME': servername, 'SERVER_PORT': serverport}
    request.path = path

    key = get_cache_key(request, key_prefix=key_prefix, cache=cache)   # xyh：用 Django 视图缓存键算法反推
    if key:
        logger.info('expire_view_cache:get key:{path}'.format(path=path))
        if cache.get(key):
            cache.delete(key)   # xyh：删除该路径的整页缓存
        return True
    return False


# xyh：当前站点对象（多站点部署用于拼完整 URL），结果带缓存避免每请求查库
@cache_decorator()
def get_current_site():
    """获取当前站点对象（多站点部署时用于拼完整 URL），结果带缓存。"""
    site = Site.objects.get_current()
    return site


# xyh：Markdown 渲染器——正文 HTML 与目录 TOC 一次解析产出（文章详情页使用）
class CommonMarkdown:
    """Markdown 渲染器。

    启用 extra/codehilite/toc/tables 扩展：
    - get_markdown：只返回渲染后的 HTML 正文；
    - get_markdown_with_toc：同时返回正文与目录（TOC），
      供文章详情页"目录"侧栏使用（配合 Article.show_toc）。
    """

    # xyh：统一转换入口：一次 md.convert 同时拿到正文 HTML 与 TOC
    @staticmethod
    def _convert_markdown(value):
        md = markdown.Markdown(
            extensions=[
                'extra',   # xyh：额外语法（表格/脚注/缩写等）
                'codehilite',   # xyh：代码块语法高亮
                'toc',   # xyh：标题自动生成目录锚点
                'tables',   # xyh：表格支持
            ]
        )
        body = md.convert(value)
        toc = md.toc   # xyh：扩展生成的目录 HTML
        return body, toc

    # xyh：正文 + 目录（详情页"文章目录"侧栏）
    @staticmethod
    def get_markdown_with_toc(value):
        body, toc = CommonMarkdown._convert_markdown(value)
        return body, toc

    # xyh：只要正文（列表页摘要、RSS 输出等场景）
    @staticmethod
    def get_markdown(value):
        body, toc = CommonMarkdown._convert_markdown(value)
        return body


# xyh：邮件统一出口——只派发信号不直连 SMTP（见 blog_signals.py 接收器落库+发送）
def send_email(emailto, title, content):
    """发送邮件的统一入口。

    并不直接 SMTP，而是派发 Django 信号 send_email_signal，
    由 blog_signals.py 中的接收器真正发信并写 EmailSendLog，
    实现解耦与发送留痕（注册激活/找回密码/评论审核通知）。
    """
    from djangoblog.blog_signals import send_email_signal
    send_email_signal.send(
        send_email.__class__,
        emailto=emailto,
        title=title,
        content=content)


# xyh：6 位数字验证码（random.sample 不放回抽样）
def generate_code() -> str:
    """生成随机数验证码"""
    return ''.join(random.sample(string.digits, 6))


# xyh：字典 → URL 查询串，键值均做 URL 编码
def parse_dict_to_url(dict):
    """把字典序列化为 URL 查询串（键值均做 URL 编码）。"""
    from urllib.parse import quote
    url = '&'.join(['{}={}'.format(quote(k, safe='/'), quote(v, safe='/'))
                    for k, v in dict.items()])
    return url


# xyh：站点配置单例：缓存优先，缺库自动建默认行（评论开关/摘要长度等业务规则都从这里读）
def get_blog_setting():
    """读取站点全局配置单例（BlogSettings），带缓存。

    全站唯一配置对象：首次调用若库中不存在，则自动创建一条
    默认配置（站点名、摘要、SEO 关键词、文章摘要长度、侧栏
    条数、评论开关、是否先审后发等）。评论开关、摘要长度等
    业务规则都从这里取值。
    """
    value = cache.get('get_blog_setting')
    if value:
        return value
    else:
        from blog.models import BlogSettings
        if not BlogSettings.objects.count():
            setting = BlogSettings()   # xyh：库中无配置则补一条默认值，保证首启动可用
            setting.site_name = 'djangoblog'
            setting.site_description = '基于Django的博客系统'
            setting.site_seo_description = '基于Django的博客系统'
            setting.site_keywords = 'Django,Python'
            setting.article_sub_length = 300
            setting.sidebar_article_count = 10
            setting.sidebar_comment_count = 5
            setting.show_google_adsense = False
            setting.open_site_comment = True
            setting.analytics_code = ''
            setting.beian_code = ''
            setting.show_gongan_code = False
            setting.comment_need_review = False
            setting.save()
        value = BlogSettings.objects.first()
        logger.info('set cache get_blog_setting')
        cache.set('get_blog_setting', value)   # xyh：缓存整行对象（不设 TTL，改动侧须主动清）
        return value


# xyh：第三方头像落地：下载 → UUID 重命名存 static/avatar/，任何异常回退默认头像
def save_user_avatar(url):
    '''
    保存用户头像
    :param url:头像url
    :return: 本地路径

    第三方登录（oauth）建号时调用：把平台头像下载到
    static/avatar/ 目录并以 UUID 重命名；任何异常都
    回退为默认头像，保证注册流程不因头像失败而中断。
    '''
    logger.info(url)

    try:
        basedir = os.path.join(settings.STATICFILES, 'avatar')   # xyh：存放目录 static/avatar/
        rsp = requests.get(url, timeout=2)   # xyh：外链下载，2 秒超时防拖慢注册
        if rsp.status_code == 200:
            if not os.path.exists(basedir):
                os.makedirs(basedir)

            image_extensions = ['.jpg', '.png', 'jpeg', '.gif']
            isimage = len([i for i in image_extensions if url.endswith(i)]) > 0   # xyh：按扩展名粗判是否为图片
            ext = os.path.splitext(url)[1] if isimage else '.jpg'
            save_filename = str(uuid.uuid4().hex) + ext   # xyh：UUID 重命名，杜绝路径穿越与重名覆盖
            logger.info('保存用户头像:' + basedir + save_filename)
            with open(os.path.join(basedir, save_filename), 'wb+') as file:
                file.write(rsp.content)
            return static('avatar/' + save_filename)   # xyh：返回可直接用于 <img> 的静态 URL
    except Exception as e:
        logger.error(e)
        return static('blog/img/avatar.png')   # xyh：兜底默认头像，注册流程不中断


# xyh：按 LinkShowType 各取值清 sidebar 前缀键（友链/侧栏内容变更后调用）
def delete_sidebar_cache():
    """清空侧边栏缓存（友链/侧栏内容变更后调用）。

    侧边栏按 LinkShowType 各取值分别缓存（键形如 sidebar+i/l/p/a/s），
    逐一删除以让前台立即看到新配置。
    """
    from blog.models import LinkShowType
    keys = ["sidebar" + x for x in LinkShowType.values]
    for k in keys:
        logger.info('delete sidebar key:' + k)
        cache.delete(k)


# xyh：删除模板片段缓存（{% cache %} 产生键）
def delete_view_cache(prefix, keys):
    """删除模板片段缓存（{% cache %} 标签产生的键）。"""
    from django.core.cache.utils import make_template_fragment_key
    key = make_template_fragment_key(prefix, keys)   # xyh：按 Django 模板缓存键规则构造
    cache.delete(key)


# xyh：静态资源前缀 URL 兜底（无 STATIC_URL 时拼站点域名）
def get_resource_url():
    """返回静态资源前缀 URL（优先 STATIC_URL，否则拼当前站点域名）。"""
    if settings.STATIC_URL:
        return settings.STATIC_URL
    else:
        site = get_current_site()
        return 'http://' + site.domain + '/static/'


# 允许的HTML标签白名单 - 支持markdown常用元素
# xyh：XSS 白名单①——允许保留的标签集合（markdown 常用元素 + 表格 + 代码块）
ALLOWED_TAGS = [
    'a', 'abbr', 'acronym', 'b', 'blockquote', 'code', 'em', 'i', 'li', 'ol', 'ul', 'pre', 'strong',
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6',  # 标题
    'p', 'span', 'div', 'br', 'hr',  # 段落和分隔
    'table', 'thead', 'tbody', 'tr', 'th', 'td',  # 表格
    'dl', 'dt', 'dd',  # 定义列表
    'img',  # 图片（需配合ALLOWED_ATTRIBUTES限制src）
    'del', 'ins', 'sub', 'sup',  # 文本修饰
]

# 安全的class值白名单 - 只允许代码高亮相关的class
# xyh：XSS 白名单②——class 值限定为 Pygments 代码高亮类名，防止借 class 挂样式
ALLOWED_CLASSES = [
    'codehilite', 'highlight', 'hll', 'c', 'err', 'k', 'l', 'n', 'o', 'p', 'cm', 'cp', 'c1', 'cs',
    'gd', 'ge', 'gr', 'gh', 'gi', 'go', 'gp', 'gs', 'gu', 'gt', 'kc', 'kd', 'kn', 'kp', 'kr', 'kt',
    'ld', 'm', 'mf', 'mh', 'mi', 'mo', 'na', 'nb', 'nc', 'no', 'nd', 'ni', 'ne', 'nf', 'nl', 'nn',
    'nt', 'nv', 'ow', 'w', 'mb', 'mh', 'mi', 'mo', 'sb', 'sc', 'sd', 'se', 'sh', 'si', 'sx', 's2',
    's1', 'ss', 'bp', 'vc', 'vg', 'vi', 'il'
]

# xyh：class 白名单过滤器（bleach 属性回调：返回值即过滤后的属性值）
def class_filter(tag, name, value):
    """自定义class属性过滤器"""
    if name == 'class':
        # 只允许预定义的安全class值
        allowed_classes = [cls for cls in value.split() if cls in ALLOWED_CLASSES]
        return ' '.join(allowed_classes) if allowed_classes else False   # xyh：全被滤掉则删除该属性
    return value

# 安全的属性白名单
# xyh：XSS 白名单③——按标签限定允许属性；span/div/pre/code 的 class 走 class_filter
ALLOWED_ATTRIBUTES = {
    'a': ['href', 'title', 'rel'],  # rel="nofollow" 用于外部链接
    'abbr': ['title'], 
    'acronym': ['title'],
    'img': ['src', 'alt', 'title', 'width', 'height'],  # 图片属性
    'table': ['border', 'cellpadding', 'cellspacing'],
    'th': ['align', 'valign'],
    'td': ['align', 'valign'],
    'span': class_filter,
    'div': class_filter,
    'pre': class_filter,
    'code': class_filter
}

# 安全的协议白名单 - 防止javascript:等危险协议
# xyh：XSS 白名单④——href/src 只允许 http/https/mailto（杜绝 javascript:）
ALLOWED_PROTOCOLS = ['http', 'https', 'mailto']

# xyh：XSS 清洗总入口：标签/属性/协议三张白名单 + 去空 style
def sanitize_html(html):
    """
    安全的HTML清理函数
    使用bleach库进行白名单过滤，防止XSS攻击
    """
    cleaned = bleach.clean(
        html, 
        tags=ALLOWED_TAGS, 
        attributes=ALLOWED_ATTRIBUTES,
        protocols=ALLOWED_PROTOCOLS,  # 限制允许的协议
        strip=True,  # 移除不允许的标签而不是转义
        strip_comments=True  # 移除HTML注释
    )
    
    # 移除空的 style 属性（bleach 有时会保留 style=""）
    import re
    cleaned = re.sub(r'\s*style\s*=\s*["\'][\s]*["\']', '', cleaned)   # xyh：清理残留的空 style="" 
    
    return cleaned
