import logging  # 标准日志模块

from django.core.cache import cache  # #jxr 缓存操作入口（清文章评论缓存用）
from django.utils.translation import gettext_lazy as _

from djangoblog.utils import get_current_site  # 获取当前站点域名
from djangoblog.utils import (  # #jxr 复用公共缓存工具，和 blog_signals 保持同一套清理口径
    delete_sidebar_cache,
    delete_view_cache,
    expire_view_cache,
)
from djangoblog.utils import send_email  # 复用公共邮件发送工具

logger = logging.getLogger(__name__)  # #jxr 模块级 logger，用于记录异常

# #jxr 本文件为 comments app 的工具函数：
# #jxr 1) invalidate_article_comment_cache：审核状态变化后主动失效相关缓存；
# #jxr 2) send_comment_email：评论提交后触发两类邮件——①感谢评论者；②通知被回复的父评论作者


def invalidate_article_comment_cache(article):
    """#jxr 让某篇文章的评论相关缓存立即失效。

    为什么要单独写这个函数：项目的评论缓存分散在四处——
    ①文章详情页整页缓存（key_prefix=blogdetail）；②Article.comment_list() 的
    article_comments_{id}；③模板片段缓存 article_comments；④侧边栏“最新评论”。
    后台批量审核如果直接用 queryset.update()，不会触发 post_save 信号，
    这四处缓存就全部留在旧状态，管理员会看到“已经通过了但前台还没有”。

    :param article: 评论所属文章（可为 None，内部会直接返回 False）
    :return: bool 是否完成清理（异常时记日志并返回 False，不影响审核主流程）
    """
    if article is None:
        return False

    try:
        path = article.get_absolute_url()
        site = get_current_site().domain
        # #jxr 域名带端口时截掉端口，与 blog_signals 的处理保持一致
        if site.find(':') > 0:
            site = site[0:site.find(':')]

        expire_view_cache(path, servername=site, serverport=80, key_prefix='blogdetail')
        cache.delete('article_comments_{id}'.format(id=article.id))
        delete_view_cache('article_comments', [str(article.pk)])
        delete_sidebar_cache()
        cache.delete('seo_processor')
        return True
    except Exception as error:
        # #jxr 缓存清理失败只记日志：审核状态已经落库，不能因为缓存问题把后台操作变成 500
        logger.error('invalidate comment cache failed: article=%s error=%s',
                     getattr(article, 'pk', None), error)
        return False


def send_comment_email(comment):
    """#jxr 发送评论相关邮件：感谢评论者 + 通知被回复的父评论作者。

    整个函数体都在 try 里：邮件属于“锦上添花”的旁路逻辑，任何异常
    （邮件服务不可用、发信日志表缺失、对象在子线程里取关联字段失败……）
    都只记日志，绝不把异常抛回评论保存流程或后台线程。
    """
    try:
        # #jxr 组装当前站点域名与文章绝对 URL，拼出可点击的评论链接
        site = get_current_site().domain
        subject = _('Thanks for your comment')
        article_url = f"https://{site}{comment.article.get_absolute_url()}"

        # #jxr 第一封邮件：感谢评论者本人，附上其评论所在文章的可点击链接
        html_content = _("""<p>Thank you very much for your comments on this site</p>
                        You can visit <a href="%(article_url)s" rel="bookmark">%(article_title)s</a>
                        to review your comments,
                        Thank you again!
                        <br />
                        If the link above cannot be opened, please copy this link to your browser.
                        %(article_url)s""") % {'article_url': article_url, 'article_title': comment.article.title}
        tomail = comment.author.email  # #jxr 收件人：评论作者
        send_email([tomail], subject, html_content)

        if comment.parent_comment:  # #jxr 若该评论是"楼中楼"回复，则再通知父评论作者
            html_content = _("""Your comment on <a href="%(article_url)s" rel="bookmark">%(article_title)s</a><br/> has 
                   received a reply. <br/> %(comment_body)s
                    <br/>   
                    go check it out!
                     <br/>
                     If the link above cannot be opened, please copy this link to your browser.
                     %(article_url)s
                    """) % {'article_url': article_url, 'article_title': comment.article.title,
                            'comment_body': comment.parent_comment.body}
            tomail = comment.parent_comment.author.email  # #jxr 收件人：父评论作者
            send_email([tomail], subject, html_content)
    except Exception as error:
        # #jxr 邮件发送失败只记录日志，不阻断评论主流程（评论已保存成功）
        logger.error('send comment email failed: comment=%s error=%s',
                     getattr(comment, 'pk', None), error)
