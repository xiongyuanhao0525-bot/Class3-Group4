#!/usr/bin/env python
# encoding: utf-8
"""
公共工具模块（标注人：熊圆好）
作用：汇集全站复用的基础能力——缓存装饰器、站点配置读取、
     Markdown 渲染、邮件发送入口、签名/验证码生成、
     HTML 安全清洗（XSS 防护）等，供各 app 的 views/models 引用。
"""


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


def get_max_articleid_commentid():
    """返回当前文章与评论的最大主键 ID（压测脚本生成测试数据用）。"""
    from blog.models import Article
    from comments.models import Comment
    return (Article.objects.latest().pk, Comment.objects.latest().pk)


def get_sha256(value):
    """用 SECRET_KEY 对入参做 HMAC-SHA256 签名。

    用途：注册激活链接、图床上传 sign 参数等场景，
    保证链接/参数不可被伪造篡改。
    """
    key = settings.SECRET_KEY.encode('utf-8')
    msg = str(value).encode('utf-8')
    return hmac.new(key, msg, hashlib.sha256).hexdigest()


def cache_decorator(expiration=3 * 60):
    """通用结果缓存装饰器（默认 3 分钟）。

    缓存键优先取对象的 get_cache_key()，否则用
    「函数+参数」的 SHA256 摘要生成；None 结果以哨兵值
    __default_cache_value__ 缓存，避免缓存穿透。
    典型用法：@cache_decorator(10h) 标注分类树、标签计数等
    高频低变的查询方法。
    """
    def wrapper(func):
        def news(*args, **kwargs):
            try:
                view = args[0]
                key = view.get_cache_key()
            except:
                key = None
            if not key:
                unique_str = repr((func, args, kwargs))

                m = hashlib.sha256(unique_str.encode('utf-8'))
                key = m.hexdigest()
            value = cache.get(key)
            if value is not None:
                # logger.info('cache_decorator get cache:%s key:%s' % (func.__name__, key))
                if str(value) == '__default_cache_value__':
                    return None
                else:
                    return value
            else:
                logger.debug(
                    'cache_decorator set cache:%s key:%s' %
                    (func.__name__, key))
                value = func(*args, **kwargs)
                if value is None:
                    cache.set(key, '__default_cache_value__', expiration)
                else:
                    cache.set(key, value, expiration)
                return value

        return news

    return wrapper


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

    request = HttpRequest()
    request.META = {'SERVER_NAME': servername, 'SERVER_PORT': serverport}
    request.path = path

    key = get_cache_key(request, key_prefix=key_prefix, cache=cache)
    if key:
        logger.info('expire_view_cache:get key:{path}'.format(path=path))
        if cache.get(key):
            cache.delete(key)
        return True
    return False


@cache_decorator()
def get_current_site():
    """获取当前站点对象（多站点部署时用于拼完整 URL），结果带缓存。"""
    site = Site.objects.get_current()
    return site


class CommonMarkdown:
    """Markdown 渲染器。

    启用 extra/codehilite/toc/tables 扩展：
    - get_markdown：只返回渲染后的 HTML 正文；
    - get_markdown_with_toc：同时返回正文与目录（TOC），
      供文章详情页"目录"侧栏使用（配合 Article.show_toc）。
    """

    @staticmethod
    def _convert_markdown(value):
        md = markdown.Markdown(
            extensions=[
                'extra',
                'codehilite',
                'toc',
                'tables',
            ]
        )
        body = md.convert(value)
        toc = md.toc
        return body, toc

    @staticmethod
    def get_markdown_with_toc(value):
        body, toc = CommonMarkdown._convert_markdown(value)
        return body, toc

    @staticmethod
    def get_markdown(value):
        body, toc = CommonMarkdown._convert_markdown(value)
        return body


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


def generate_code() -> str:
    """生成随机数验证码"""
    return ''.join(random.sample(string.digits, 6))


def parse_dict_to_url(dict):
    """把字典序列化为 URL 查询串（键值均做 URL 编码）。"""
    from urllib.parse import quote
    url = '&'.join(['{}={}'.format(quote(k, safe='/'), quote(v, safe='/'))
                    for k, v in dict.items()])
    return url


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
            setting = BlogSettings()
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
        cache.set('get_blog_setting', value)
        return value


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
        basedir = os.path.join(settings.STATICFILES, 'avatar')
        rsp = requests.get(url, timeout=2)
        if rsp.status_code == 200:
            if not os.path.exists(basedir):
                os.makedirs(basedir)

            image_extensions = ['.jpg', '.png', 'jpeg', '.gif']
            isimage = len([i for i in image_extensions if url.endswith(i)]) > 0
            ext = os.path.splitext(url)[1] if isimage else '.jpg'
            save_filename = str(uuid.uuid4().hex) + ext
            logger.info('保存用户头像:' + basedir + save_filename)
            with open(os.path.join(basedir, save_filename), 'wb+') as file:
                file.write(rsp.content)
            return static('avatar/' + save_filename)
    except Exception as e:
        logger.error(e)
        return static('blog/img/avatar.png')


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


def delete_view_cache(prefix, keys):
    """删除模板片段缓存（{% cache %} 标签产生的键）。"""
    from django.core.cache.utils import make_template_fragment_key
    key = make_template_fragment_key(prefix, keys)
    cache.delete(key)


def get_resource_url():
    """返回静态资源前缀 URL（优先 STATIC_URL，否则拼当前站点域名）。"""
    if settings.STATIC_URL:
        return settings.STATIC_URL
    else:
        site = get_current_site()
        return 'http://' + site.domain + '/static/'


# 允许的HTML标签白名单 - 支持markdown常用元素
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
ALLOWED_CLASSES = [
    'codehilite', 'highlight', 'hll', 'c', 'err', 'k', 'l', 'n', 'o', 'p', 'cm', 'cp', 'c1', 'cs',
    'gd', 'ge', 'gr', 'gh', 'gi', 'go', 'gp', 'gs', 'gu', 'gt', 'kc', 'kd', 'kn', 'kp', 'kr', 'kt',
    'ld', 'm', 'mf', 'mh', 'mi', 'mo', 'na', 'nb', 'nc', 'no', 'nd', 'ni', 'ne', 'nf', 'nl', 'nn',
    'nt', 'nv', 'ow', 'w', 'mb', 'mh', 'mi', 'mo', 'sb', 'sc', 'sd', 'se', 'sh', 'si', 'sx', 's2',
    's1', 'ss', 'bp', 'vc', 'vg', 'vi', 'il'
]

def class_filter(tag, name, value):
    """自定义class属性过滤器"""
    if name == 'class':
        # 只允许预定义的安全class值
        allowed_classes = [cls for cls in value.split() if cls in ALLOWED_CLASSES]
        return ' '.join(allowed_classes) if allowed_classes else False
    return value

# 安全的属性白名单
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
ALLOWED_PROTOCOLS = ['http', 'https', 'mailto']

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
    cleaned = re.sub(r'\s*style\s*=\s*["\'][\s]*["\']', '', cleaned)
    
    return cleaned
