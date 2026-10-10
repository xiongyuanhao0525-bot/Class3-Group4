import logging
import re
from abc import abstractmethod

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from mdeditor.fields import MDTextField
from uuslug import slugify

from djangoblog.utils import cache_decorator, cache
from djangoblog.utils import get_current_site
from djangoblog.constants import CacheTimeout, CacheKey

logger = logging.getLogger(__name__)


class LinkShowType(models.TextChoices):
    """友情链接展示位置枚举。

    用于在后台配置每个友链出现在前台哪些页面，
    避免无关友链在所有页面全站曝光，支持按页面类型投放。
    """
    I = ('i', _('index'))    # index：仅首页轮播/侧边栏展示
    L = ('l', _('list'))     # list：仅文章列表页展示
    P = ('p', _('post'))     # post：仅文章详情页展示
    A = ('a', _('all'))      # all：所有页面都展示
    S = ('s', _('slide'))    # slide：仅首页轮播图位展示


class BaseModel(models.Model):
    """所有业务模型的抽象基类（Django abstract=True，不建表）。

    统一提供三个公共能力：
    1. id 主键：自动自增；
    2. creation_time / last_modify_time：记录创建与最后修改时间；
    3. save() 重写：保存时自动根据 title/name 生成 slug URL别名；
       当仅更新文章浏览量 views 时，绕过完整 save 流程，直接用 QuerySet.update()
       更新数据库，避免每次浏览都触发 slug 重新生成和信号。
    """
    id = models.AutoField(primary_key=True)
    creation_time = models.DateTimeField(_('creation time'), default=now)       # 记录创建时间，默认当前时间
    last_modify_time = models.DateTimeField(_('modify time'), default=now)     # 最后修改时间，每次保存自动刷新

    def save(self, *args, **kwargs):
        """重写 Model.save()：

        分支1：如果是 Article 且 update_fields=['views']，说明这是"浏览量+1"
               的高频写操作，直接走 QuerySet.filter().update()，不触发 slug
               生成、不发信号、不做全字段写入，性能更好。
        分支2：普通保存——若模型有 slug 字段，则用 title（无 title 则用 name）
               经 uuslug.slugify 转成 URL 友好的别名（中文转拼音/连字符）。
        """
        is_update_views = isinstance(
            self,
            Article) and 'update_fields' in kwargs and kwargs['update_fields'] == ['views']
        if is_update_views:
            # 仅更新浏览量，不走完整save流程，避免重复触发slug生成
            Article.objects.filter(pk=self.pk).update(views=self.views)
        else:
            if 'slug' in self.__dict__:
                slug = getattr(
                    self, 'title') if 'title' in self.__dict__ else getattr(
                    self, 'name')
                setattr(self, 'slug', slugify(slug))
            super().save(*args, **kwargs)

    def get_full_url(self):
        """返回带域名的完整绝对URL，用于RSS、邮件、SEO分享等场景。

        从 django_site 表取当前站点 domain，拼接 get_absolute_url() 的路径。
        """
        site = get_current_site().domain
        url = "https://{site}{path}".format(site=site,
                                            path=self.get_absolute_url())
        return url

    class Meta:
        abstract = True

    @abstractmethod
    def get_absolute_url(self):
        """子类必须实现：返回该对象在前台的访问路径（路由 reverse）。"""
        pass


class Article(BaseModel):
    """博客文章实体——系统核心表。

    既承载普通博文（type='a'），也承载"关于页/友情链接页"等独立页面（type='p'）。
    草稿(d)不对外展示，只有已发布(p)会出现在前台列表、搜索和上下篇导航中。
    """
    STATUS_CHOICES = (
        ('d', _('Draft')),  # d=Draft 草稿：作者未完成，前台不可见
        ('p', _('Published')),   # p=Published 已发布：前台可见
    )
    COMMENT_STATUS = (
        ('o', _('Open')),   # o=Open 开放：读者可评论
        ('c', _('Close')),  # c=Close 关闭：即使全站开放也禁止此文章评论
    )
    TYPE = (
        ('a', _('Article')),   # a=Article 普通博文，出现在列表/归档
        ('p', _('Page')),      # p=Page 独立页面（如关于页），不进列表
    )
    # 文章标题，全局唯一，最长200字符；unique约束防止重名文章
    title = models.CharField(_('title'), max_length=200, unique=True)

    body = MDTextField(_('body'))       # 正文，MDTextField是mdeditor提供的Markdown编辑器字段
    pub_time = models.DateTimeField(
        _('publish time'), blank=False, null=False, default=now)   # 发布时间，前台按此排序；blank=False强制必填
    status = models.CharField(
        _('status'),
        max_length=1,
        choices=STATUS_CHOICES,
        default='p')                                              # 文章状态：默认已发布，后台可改草稿
    comment_status = models.CharField(
        _('comment status'),
        max_length=1,
        choices=COMMENT_STATUS,
        default='o')                                              # 评论开关，单篇文章级别，优先级高于全站配置
    type = models.CharField(_('type'), max_length=1, choices=TYPE, default='a')  # 文章/独立页面，控制前台入口
    views = models.PositiveIntegerField(_('views'), default=0)     # 浏览量，非负整数；通过 viewed() 方法高频+1
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_('author'),
        blank=False,
        null=False,
        on_delete=models.CASCADE)                               # 作者外键，关联accounts.BlogUser；用户删除则文章级联删除
    article_order = models.IntegerField(
        _('order'), blank=False, null=False, default=0)          # 排序权重，越大越靠前；置顶文章设大值
    show_toc = models.BooleanField(_('show toc'), blank=False, null=False, default=False)  # 是否在正文旁显示章节目录
    category = models.ForeignKey(
        'Category',
        verbose_name=_('category'),
        on_delete=models.CASCADE,
        blank=False,
        null=False)                                             # 所属分类，多对一；一篇文章只能属于一个分类
    tags = models.ManyToManyField('Tag', verbose_name=_('tag'), blank=True)  # 标签多对多，一篇文章可打多个标签

    def body_to_string(self):
        """正文取纯文本（当前直接返回Markdown原文，预留做HTML转纯文本）。"""
        return self.body

    def __str__(self):
        # 后台admin列表中显示文章标题，而非 "Article object (1)"
        return self.title

    class Meta:
        # 默认排序：先按权重降序（置顶优先），同权重再按发布时间倒序
        ordering = ['-article_order', '-pub_time']
        verbose_name = _('article')
        verbose_name_plural = verbose_name
        get_latest_by = 'id'   # latest() 方法默认按 id 倒序
        indexes = [
            # 组合索引：前台"已发布文章列表"查询最频繁，按 type+status 过滤后按 pub_time 排序
            models.Index(fields=['type', 'status', '-pub_time'], name='idx_type_status_pub'),
            # 热门文章排行：按 status 过滤后按 views 倒序，走此索引避免filesort
            models.Index(fields=['status', '-views'], name='idx_status_views'),
            # 作者主页"我的文章"：按 author+status+type 过滤
            models.Index(fields=['author', 'status', 'type'], name='idx_author_status_type'),
            # 分类页：按 category+status 过滤该分类下已发布文章
            models.Index(fields=['category', 'status'], name='idx_category_status'),
        ]

    def get_absolute_url(self):
        """生成文章详情页URL，格式：/article/{id}/{年}/{月}/{日}/。

        带年/月/日是早期SEO友好设计，也便于按日期归档。
        """
        return reverse('blog:detailbyid', kwargs={
            'article_id': self.id,
            'year': self.creation_time.year,
            'month': self.creation_time.month,
            'day': self.creation_time.day
        })

    @cache_decorator(CacheTimeout.HOUR_10)
    def get_category_tree(self):
        """返回当前文章所属分类的面包屑路径 [(分类名, URL), ...]，缓存10小时。

        前台文章页面包屑导航用：首页 > 分类A > 子分类B > 当前文章。
        """
        tree = self.category.get_category_tree()
        names = list(map(lambda c: (c.name, c.get_absolute_url()), tree))

        return names

    def save(self, *args, **kwargs):
        """Article自己的save：先调用父类save（BaseModel里已处理slug）。"""
        super().save(*args, **kwargs)

    def viewed(self):
        """文章被浏览一次：views+1，并用 update_fields=['views'] 只更新该字段。

        这个调用频率极高（每次打开文章页一次），所以BaseModel.save()专门为此优化。
        """
        self.views += 1
        self.save(update_fields=['views'])

    def comment_list(self):
        """返回当前文章已启用的评论列表，带10小时缓存。

        缓存key按文章id区分；缓存命中打日志，未命中查库后回填缓存。
        只取 is_enable=True 的评论（后台可屏蔽不当评论）。
        """
        cache_key = CacheKey.ARTICLE_COMMENTS.format(article_id=self.id)
        value = cache.get(cache_key)
        if value:
            logger.info(f'Cache HIT: article comments (id={self.id})')
            return value
        else:
            comments = self.comment_set.filter(is_enable=True).order_by('-id')
            cache.set(cache_key, comments, CacheTimeout.HOUR_10)
            logger.info(f'Cache MISS: article comments (id={self.id})')
            return comments

    def get_admin_url(self):
        """返回该文章在Django admin后台的编辑页URL。"""
        info = (self._meta.app_label, self._meta.model_name)
        return reverse('admin:%s_%s_change' % info, args=(self.pk,))

    @cache_decorator(expiration=CacheTimeout.HOUR_10)
    def next_article(self):
        """下一篇（id更大的已发布文章），用于文章页"下一篇"导航，缓存10小时。"""
        return Article.objects.filter(
            id__gt=self.id, status='p').order_by('id').first()

    @cache_decorator(expiration=CacheTimeout.HOUR_10)
    def prev_article(self):
        """上一篇（id更小的已发布文章），用于文章页"上一篇"导航，缓存10小时。"""
        return Article.objects.filter(id__lt=self.id, status='p').first()

    def get_first_image_url(self):
        """从Markdown正文中用正则提取第一张图片的URL。

        用于列表页摘要缩略图：文章没设封面时自动取正文首图。
        正则：匹配 ![任意文字](图片URL) 的Markdown图片语法。
        """
        match = re.search(r'!\[.*?\]\((.+?)\)', self.body)
        if match:
            return match.group(1)
        return ""


class Category(BaseModel):
    """文章分类，支持无限级层级（自引用外键 parent_category）。

   业务上区分"分类"与"标签"：分类是粗粒度树状结构（如：技术/前端/Vue），
    一篇文章只属于一个分类；标签是扁平的自由词（如：vue3, composition-api）。
    """
    name = models.CharField(_('category name'), max_length=30, unique=True)   # 分类名，唯一，最长30字
    parent_category = models.ForeignKey(
        'self',
        verbose_name=_('parent category'),
        blank=True,
        null=True,
        on_delete=models.CASCADE)      # 父分类自引用；顶级分类该字段为null；删父分类则子分类级联删除
    slug = models.SlugField(default='no-slug', max_length=60, blank=True)    # URL别名，中文自动转拼音，用于分类页URL
    index = models.IntegerField(default=0, verbose_name=_('index'))          # 排序权重，越大越靠前

    class Meta:
        ordering = ['-index']
        verbose_name = _('category')
        verbose_name_plural = verbose_name

    def get_absolute_url(self):
        """分类详情页URL：/category/{slug}/"""
        return reverse(
            'blog:category_detail', kwargs={
                'category_name': self.slug})

    def __str__(self):
        return self.name

    @cache_decorator(CacheTimeout.HOUR_10)
    def get_category_tree(self):
        """从当前分类沿 parent_category 向上递归，返回到顶级分类的路径列表。

        例如：(前端) -> (技术) -> (根)，用于面包屑。缓存10小时。
        """
        categorys = []

        def parse(category):
            categorys.append(category)
            if category.parent_category:
                parse(category.parent_category)

        parse(self)
        return categorys

    @cache_decorator(CacheTimeout.HOUR_10)
    def get_sub_categorys(self):
        """返回当前分类及其所有子孙分类（向下递归），用于在分类页列出子分类文章。

        与 get_category_tree 方向相反：本方法向下，get_category_tree 向上。
        缓存10小时。
        """
        categorys = []
        all_categorys = Category.objects.all()

        def parse(category):
            if category not in categorys:
                categorys.append(category)
            childs = all_categorys.filter(parent_category=category)
            for child in childs:
                if category not in categorys:
                    categorys.append(child)
                parse(child)

        parse(self)
        return categorys


class Tag(BaseModel):
    """文章标签——扁平的自由关键词，与文章多对多。

    与Category区别：标签无层级、自由输入、一篇文章可多标签；
    用于标签云、相关文章推荐。
    """
    name = models.CharField(_('tag name'), max_length=30, unique=True)   # 标签名唯一，最长30字
    slug = models.SlugField(default='no-slug', max_length=60, blank=True)  # URL别名

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        """标签详情页URL：/tag/{slug}/"""
        return reverse('blog:tag_detail', kwargs={'tag_name': self.slug})

    @cache_decorator(CacheTimeout.HOUR_10)
    def get_article_count(self):
        """返回该标签下已打标签的文章数（去重），用于标签云显示文章数。缓存10小时。"""
        return Article.objects.filter(tags__name=self.name).distinct().count()

    class Meta:
        ordering = ['name']
        verbose_name = _('tag')
        verbose_name_plural = verbose_name


class Links(models.Model):
    """友情链接——前台页脚/侧边栏展示的外部站点链接。

    注意：本模型不继承BaseModel，自定义了 creation_time/last_mod_time 字段名。
    """

    name = models.CharField(_('link name'), max_length=30, unique=True)    # 链接显示名，唯一
    link = models.URLField(_('link'))                                      # 目标URL，URLField自带格式校验
    sequence = models.IntegerField(_('order'), unique=True)                # 排序序号，唯一约束保证不重复
    is_enable = models.BooleanField(
        _('is show'), default=True, blank=False, null=False)              # 软删除开关：False则前台不显示，但记录保留
    show_type = models.CharField(
        _('show type'),
        max_length=1,
        choices=LinkShowType.choices,
        default=LinkShowType.I)                                          # 显示位置，关联LinkShowType枚举
    creation_time = models.DateTimeField(_('creation time'), default=now)  # 创建时间
    last_mod_time = models.DateTimeField(_('modify time'), default=now)    # 修改时间（注意命名与BaseModel不同）

    class Meta:
        ordering = ['sequence']
        verbose_name = _('link')
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.name


class SideBar(models.Model):
    """侧边栏——可在前台侧栏投放自定义HTML块（公告、广告、markdown等）。

    不继承BaseModel，自定义时间字段。通过 sequence 控制展示顺序，
    is_enable=False 可临时停用某个侧边栏而不删除。
    """
    name = models.CharField(_('title'), max_length=100)                    # 侧边栏标题
    content = models.TextField(_('content'))                              # HTML内容，后台直接渲染
    sequence = models.IntegerField(_('order'), unique=True)               # 排序序号，唯一
    is_enable = models.BooleanField(_('is enable'), default=True)          # 是否启用显示
    creation_time = models.DateTimeField(_('creation time'), default=now)  # 创建时间
    last_mod_time = models.DateTimeField(_('modify time'), default=now)    # 最后修改时间

    class Meta:
        ordering = ['sequence']
        verbose_name = _('sidebar')
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.name


class BlogSettings(models.Model):
    """博客全局配置（单例模式）。

    全站只有一条配置记录，clean() 方法在保存时校验"不能存在第二条"。
    保存后会清空整个缓存（cache.clear()），让前台读到新配置。
    涵盖：站点名/SEO/广告/备案号/主题色/统计代码/评论审核开关等。
    """

    COLOR_SCHEMES = (
        ('purple', _('紫色主题 - Purple Dream')),
        ('blue', _('蓝色主题 - Ocean Blue')),
        ('green', _('绿色主题 - Forest Green')),
        ('orange', _('橙色主题 - Sunset Orange')),
        ('pink', _('粉色主题 - Cherry Blossom')),
        ('red', _('红色主题 - Ruby Red')),
        ('indigo', _('靛蓝主题 - Midnight Indigo')),
        ('teal', _('青色主题 - Teal Wave')),
    )

    site_name = models.CharField(
        _('site name'),
        max_length=200,
        null=False,
        blank=False,
        default='')                                       # 站点名，显示在浏览器标题和页脚
    site_description = models.TextField(
        _('site description'),
        max_length=1000,
        null=False,
        blank=False,
        default='')                                       # 站点一句话描述，用于meta description
    site_seo_description = models.TextField(
        _('site seo description'), max_length=1000, null=False, blank=False, default='')  # SEO专用描述，给搜索引擎看
    site_keywords = models.TextField(
        _('site keywords'),
        max_length=1000,
        null=False,
        blank=False,
        default='')                                       # SEO关键词，逗号分隔
    article_sub_length = models.IntegerField(_('article sub length'), default=300)        # 列表页摘要截取长度（字符数）
    sidebar_article_count = models.IntegerField(_('sidebar article count'), default=10)   # 侧边栏"热门文章"显示条数
    sidebar_comment_count = models.IntegerField(_('sidebar comment count'), default=5)    # 侧边栏"最新评论"显示条数
    article_comment_count = models.IntegerField(_('article comment count'), default=5)    # 文章页底部显示评论条数
    show_google_adsense = models.BooleanField(_('show adsense'), default=False)          # 是否启用Google AdSense广告
    google_adsense_codes = models.TextField(
        _('adsense code'), max_length=2000, null=True, blank=True, default='')          # AdSense广告位代码
    open_site_comment = models.BooleanField(_('open site comment'), default=True)        # 全站评论总开关，优先级低于单篇文章comment_status
    color_scheme = models.CharField(
        _('配色方案'),
        max_length=20,
        choices=COLOR_SCHEMES,
        default='purple',
        help_text=_('选择网站的主题配色方案'))            # 前端主题色，8套内置配色
    global_header = models.TextField("公共头部", null=True, blank=True, default='')      # 注入到<head>的自定义HTML（统计/验证标签）
    global_footer = models.TextField("公共尾部", null=True, blank=True, default='')      # 注入到</body>前的自定义HTML
    beian_code = models.CharField(
        '备案号',
        max_length=2000,
        null=True,
        blank=True,
        default='')                                       # ICP备案号（国内站点必需），显示在页脚
    analytics_code = models.TextField(
        "网站统计代码",
        max_length=1000,
        null=False,
        blank=False,
        default='')                                       # 百度/Google统计脚本
    show_gongan_code = models.BooleanField(
        '是否显示公安备案号', default=False, null=False)   # 是否在页脚显示公安备案号
    gongan_beiancode = models.TextField(
        '公安备案号',
        max_length=2000,
        null=True,
        blank=True,
        default='')                                       # 公安联网备案号（国内站点必需）
    comment_need_review = models.BooleanField(
        '评论是否需要审核', default=False, null=False)    # True时新评论需后台审核后才显示

    class Meta:
        verbose_name = _('Website configuration')
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.site_name

    def clean(self):
        """Django模型校验：保证全站只有一条BlogSettings记录。

        exclude(id=self.id) 排除当前正在编辑的这条，如果还有其他记录就抛错。
        """
        if BlogSettings.objects.exclude(id=self.id).count():
            raise ValidationError(_('There can only be one configuration'))

    def save(self, *args, **kwargs):
        """保存配置后清空全站缓存，让前台立即生效新配置。"""
        super().save(*args, **kwargs)
        from djangoblog.utils import cache
        cache.clear()
