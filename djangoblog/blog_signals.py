# xyh：博客全局信号模块——集中定义并监听项目内所有 Django 信号。
# xyh：职责一：自定义信号（发邮件、第三方登录）的声明与接收器实现；
# xyh：职责二：监听 ORM 通用 post_save 信号，按模型类型执行缓存失效与搜索引擎推送；
# xyh：职责三：监听用户登录/登出信号刷新侧边栏缓存。
# xyh：本模块由 djangoblog/apps.py 的 ready() 导入以完成信号注册（全局约定）。
import _thread
import logging

import django.dispatch
from django.conf import settings
from django.contrib.admin.models import LogEntry
from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.core.mail import EmailMultiAlternatives
from django.db.models.signals import post_save
from django.dispatch import receiver

from comments.models import Comment
from comments.utils import send_comment_email
from djangoblog.spider_notify import SpiderNotify
from djangoblog.utils import cache, expire_view_cache, delete_sidebar_cache, delete_view_cache
from djangoblog.utils import get_current_site
from oauth.models import OAuthUser

logger = logging.getLogger(__name__)

# xyh：自定义信号——第三方用户登录成功后触发，携带参数 id（OAuthUser 主键）
oauth_user_login_signal = django.dispatch.Signal(['id'])
# xyh：自定义信号——请求发送邮件时触发，携带收件人列表、标题、正文三个参数
send_email_signal = django.dispatch.Signal(
    ['emailto', 'title', 'content'])


# xyh：接收 send_email_signal：任何模块只要 send_email_signal.send(...) 即异步走此处发信
@receiver(send_email_signal)
def send_email_signal_handler(sender, **kwargs):
    emailto = kwargs['emailto']  # xyh：收件人列表（可多人）
    title = kwargs['title']  # xyh：邮件主题
    content = kwargs['content']  # xyh：邮件正文（HTML）

    msg = EmailMultiAlternatives(
        title,
        content,
        from_email=settings.DEFAULT_FROM_EMAIL,  # xyh：发件地址取自全局配置
        to=emailto)
    msg.content_subtype = "html"  # xyh：声明正文为 HTML 子类型

    from servermanager.models import EmailSendLog  # xyh：延迟导入避免循环依赖
    log = EmailSendLog()  # xyh：每次发信都落一条发送日志供后台审计
    log.title = title
    log.content = content
    log.emailto = ','.join(emailto)

    try:
        result = msg.send()  # xyh：真正调用 SMTP 发送
        log.send_result = result > 0  # xyh：记录发送是否成功
    except Exception as e:
        logger.error(f"失败邮箱号: {emailto}, {e}")  # xyh：发送异常只记日志不上抛，保证业务不被邮件拖垮
        log.send_result = False
    log.save()


# xyh：接收 oauth_user_login_signal：oauth/views.py 在第三方授权登录成功后触发
# xyh：副作用——把外链头像转存到本站并清理侧边栏缓存（头像变化影响"最新评论"展示）
@receiver(oauth_user_login_signal)
def oauth_user_login_signal_handler(sender, **kwargs):
    id = kwargs['id']  # xyh：OAuthUser 记录主键
    oauthuser = OAuthUser.objects.get(id=id)
    site = get_current_site().domain
    # xyh：头像仍是外部域名时才需要转存（已在本站则跳过）
    if oauthuser.picture and not oauthuser.picture.find(site) >= 0:
        from djangoblog.utils import save_user_avatar  # xyh：延迟导入防循环依赖
        oauthuser.picture = save_user_avatar(oauthuser.picture)  # xyh：下载外链头像存入 MEDIA 目录
        oauthuser.save()

    delete_sidebar_cache()  # xyh：头像更新后侧边栏展示过期，整组清除


# xyh：监听 Django 全局 post_save（所有模型保存后触发），是本模块核心：
# xyh：按实例类型分发——LogEntry 跳过 / 纯浏览量更新跳过 / 可推送对象通知百度 / Comment 与 Article 等精细化清缓存
@receiver(post_save)
def model_post_save_callback(
        sender,
        instance,
        created,
        raw,
        using,
        update_fields,
        **kwargs):
    if isinstance(instance, LogEntry):  # xyh：后台操作日志入库不引发任何缓存/推送副作用
        return

    # 检查是否只更新了浏览量
    is_update_views = update_fields == {'views'}
    if is_update_views:
        return  # 浏览量更新不需要清理缓存

    # 搜索引擎通知
    if 'get_full_url' in dir(instance):  # xyh：鸭子类型判断——实现了 get_full_url 的模型才视为可推送页面
        if not settings.TESTING:  # xyh：测试环境不发真实 HTTP 请求
            try:
                notify_url = instance.get_full_url()  # xyh：取该对象的完整访问 URL
                SpiderNotify.baidu_notify([notify_url])  # xyh：主动推送给百度收录
            except Exception as ex:
                logger.error("notify sipder", ex)  # xyh：推送失败不影响保存事务

    # 评论相关的缓存清理
    if isinstance(instance, Comment):
        if instance.is_enable:  # xyh：仅审核通过的评论才需要刷新页面缓存
            path = instance.article.get_absolute_url()  # xyh：评论所属文章详情页路径
            site = get_current_site().domain
            if site.find(':') > 0:  # xyh：域名带端口时截掉端口部分
                site = site[0:site.find(':')]

            expire_view_cache(  # xyh：精确失效该文章详情页的整页视图缓存（key_prefix=blogdetail）
                path,
                servername=site,
                serverport=80,
                key_prefix='blogdetail')

            # 清理评论相关缓存
            comment_cache_key = 'article_comments_{id}'.format(
                id=instance.article.id)
            cache.delete(comment_cache_key)  # xyh：删除该文章的评论列表缓存
            delete_view_cache('article_comments', [str(instance.article.pk)])  # xyh：按前缀+参数批量清评论视图缓存
            delete_sidebar_cache()  # xyh：最新评论侧边栏组件失效
            cache.delete('seo_processor')  # xyh：SEO 处理器缓存一并清除

            _thread.start_new_thread(send_comment_email, (instance,))  # xyh：起独立线程发评论通知邮件，避免阻塞保存请求

    # 文章相关的精细化缓存清理
    elif 'get_full_url' in dir(instance):  # xyh：非评论但可推送的模型（Article/Category/Tag 等）走这里
        from blog.models import Article, Category, Tag  # xyh：延迟导入防循环依赖

        if isinstance(instance, Article):
            # 清理文章列表首页缓存
            cache.delete('index_1')  # xyh：新文章/改文章影响首页第一页

            # 清理文章详情缓存
            article_cache_key = f'article_comments_{instance.id}'
            cache.delete(article_cache_key)

            # 清理分类相关缓存
            if instance.category:
                category_name = instance.category.name
                cache.delete(f'category_list_{category_name}_1')  # xyh：该分类列表页第一页失效

            # 清理标签相关缓存
            try:
                for tag in instance.tags.all():
                    cache.delete(f'tag_{tag.name}_1')  # xyh：文章挂的每个标签列表页都要刷新
            except Exception:
                pass  # 可能在创建时tags还未关联

            # 清理作者相关缓存
            if instance.author:
                from uuslug import slugify
                author_slug = slugify(instance.author.username)
                cache.delete(f'author_{author_slug}_1')  # xyh：作者归档页第一页失效

            # 清理归档缓存
            cache.delete('archives')  # xyh：时间归档页整页缓存

            # 清理侧边栏和上下文处理器缓存
            delete_sidebar_cache()
            cache.delete('seo_processor')

        elif isinstance(instance, Category):
            # 清理分类相关缓存
            cache.delete(f'category_list_{instance.name}_1')  # xyh：分类改名/新建只需刷该分类列表与侧栏
            delete_sidebar_cache()
            cache.delete('seo_processor')

        elif isinstance(instance, Tag):
            # 清理标签相关缓存
            cache.delete(f'tag_{instance.name}_1')
            delete_sidebar_cache()

        # 其他模型的缓存清理
        else:
            # 对于其他有get_full_url的模型，清理基础缓存
            delete_sidebar_cache()  # xyh：友链、站点配置等其他对象统一保守清侧栏+SEO
            cache.delete('seo_processor')


# xyh：同时监听用户登录与登出两个内置信号
# xyh：副作用——"记住我/登录态"会影响侧边栏展示内容，切换后必须整组清缓存
@receiver(user_logged_in)
@receiver(user_logged_out)
def user_auth_callback(sender, request, user, **kwargs):
    if user and user.username:  # xyh：匿名请求（无用户名）不处理
        logger.info(user)
        delete_sidebar_cache()
        # cache.clear()
