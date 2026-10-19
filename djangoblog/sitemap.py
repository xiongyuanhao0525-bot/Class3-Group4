# xyh：SEO 站点地图模块 —— 五个 Sitemap 子类分别向搜索引擎声明
# xyh：首页/文章/分类/标签/作者页五类 URL 的更新频率与权重；
# xyh：在 djangoblog/urls.py 组装成 sitemaps 字典后经 /sitemap.xml 输出。
from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from blog.models import Article, Category, Tag


class StaticViewSitemap(Sitemap):   # xyh：静态页面地图（当前仅首页）
    priority = 0.5                  # xyh：权重 0-1，首页中等
    changefreq = 'daily'            # xyh：建议爬虫每日抓取

    def items(self):
        return ['blog:index', ]     # xyh：返回 URL name 列表而非对象

    def location(self, item):
        return reverse(item)        # xyh：把 URL name 反解析成实际路径


class ArticleSiteMap(Sitemap):   # xyh：已发布文章的地图
    changefreq = "monthly"
    priority = "0.6"              # xyh：文章是核心内容，权重最高

    def items(self):
        return Article.objects.filter(status='p')   # xyh：status='p' 只收录已发布，草稿不进 sitemap

    def lastmod(self, obj):
        return obj.last_modify_time                 # xyh：以最后修改时间提示爬虫增量抓取


class CategorySiteMap(Sitemap):   # xyh：分类页地图，收录全部分类
    changefreq = "Weekly"
    priority = "0.6"

    def items(self):
        return Category.objects.all()   # xyh：收录全部分类

    def lastmod(self, obj):
        return obj.last_modify_time   # xyh：同理以最后修改时间提示增量抓取


class TagSiteMap(Sitemap):   # xyh：标签页地图，收录全部标签
    changefreq = "Weekly"
    priority = "0.3"         # xyh：标签页权重低于正文与分类

    def items(self):
        return Tag.objects.all()   # xyh：收录全部标签

    def lastmod(self, obj):
        return obj.last_modify_time   # xyh：以最后修改时间提示增量抓取


class UserSiteMap(Sitemap):   # xyh：作者归档页地图
    changefreq = "Weekly"
    priority = "0.3"

    def items(self):
        return list(set(map(lambda x: x.author, Article.objects.all())))   # xyh：从文章集合提取去重后的作者列表

    def lastmod(self, obj):
        return obj.date_joined   # xyh：用户模型无更新时间字段，用注册时间近似
