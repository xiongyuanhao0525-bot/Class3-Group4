# xyh：RSS 订阅源模块 —— Django Feed 框架实现全站文章订阅，
# xyh：/feed/ 与 /rss/ 两个路由共用本类（见 djangoblog/urls.py），
# xyh：输出 RSS 2.0（rev2）格式，条目取最新 5 篇已发布普通文章。
from django.contrib.auth import get_user_model
from django.contrib.syndication.views import Feed
from django.utils import timezone
from django.utils.feedgenerator import Rss201rev2Feed

from blog.models import Article
from djangoblog.utils import CommonMarkdown


class DjangoBlogFeed(Feed):   # xyh：站点级唯一订阅源
    feed_type = Rss201rev2Feed   # xyh：显式指定 RSS2.0 生成器（默认 Atom）

    description = '大巧无工,重剑无锋.'
    title = "且听风吟 大巧无工,重剑无锋. "
    link = "/feed/"   # xyh：订阅源自指 URL

    def author_name(self):
        return get_user_model().objects.first().nickname   # xyh：取首个注册用户为站点作者名（硬编码约定）

    def author_link(self):
        return get_user_model().objects.first().get_absolute_url()   # xyh：作者主页地址

    def items(self):
        return Article.objects.filter(type='a', status='p').order_by('-pub_time')[:5]   # xyh：type='a' 普通文章、status='p' 已发布，按发布时间倒序取前 5 条

    def item_title(self, item):
        return item.title   # xyh：条目标题

    def item_description(self, item):
        return CommonMarkdown.get_markdown(item.body)   # xyh：正文 Markdown 渲染成 HTML 后作为摘要输出

    def feed_copyright(self):
        now = timezone.now()
        return "Copyright© {year} 且听风吟".format(year=now.year)   # xyh：版权年份动态取当前时间

    def item_link(self, item):
        return item.get_absolute_url()   # xyh：条目原文链接

    def item_guid(self, item):
        return   # xyh：不提供 GUID，由框架回退用链接充当唯一标识
