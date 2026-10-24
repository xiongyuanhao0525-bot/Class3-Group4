import logging  # 标准日志模块

from django.utils.translation import gettext_lazy as _

from djangoblog.utils import get_current_site  # 获取当前站点域名
from djangoblog.utils import send_email  # 复用公共邮件发送工具

logger = logging.getLogger(__name__)  # #jxr 模块级 logger，用于记录异常

# #jxr 本文件为 comments app 的工具函数：
# #jxr send_comment_email：评论提交后触发两类邮件——①感谢评论者；②通知被回复的父评论作者


def send_comment_email(comment):
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
    try:
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
    except Exception as e:
        # #jxr 邮件发送失败只记录日志，不阻断评论主流程（评论已保存成功）
        logger.error(e)
