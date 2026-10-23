# ============================================================
# blog/models.py —— 博客应用的数据模型（整个站点的“数据地基”）
# 作用：用 Django ORM（对象关系映射，即用 Python 类描述数据库表，一个类=一张表、
#       一个属性=一列）定义博客里所有实体；视图、模板、后台 admin 都建立在这些模型之上。
#       改这里的字段等于改数据库结构，必须配合 migrations（迁移文件）才能生效。
# 本文件包含：
#   LinkShowType —— 友情链接显示位置的枚举（首页 / 列表页 / 详情页 / 全部 / 轮播）
#   BaseModel    —— 抽象基类：主键、创建与修改时间、slug 自动生成、绝对 URL
#   Article      —— 文章（正文、状态、类型、浏览量、作者、分类、标签 + 列表查询索引）
#   Category     —— 文章分类（自关联成树，支持父子级，用于导航与面包屑）
#   Tag          —— 文章标签（多对多，一篇文章可挂多个标签）
#   Links        —— 友情链接
#   SideBar      —— 侧边栏自定义 HTML 区块（广告、公告等）
#   BlogSettings —— 全站唯一一份站点配置（单例表）
# 注释人：翟旌超（软件工程 3 班 2415304340，#zjc）
# 说明：本次任务只添加中文注释，没有改动任何一行原有代码逻辑
# ============================================================
# —— Python 标准库 ——
# logging：按模块名输出日志，便于定位是哪个文件出的问题；
# re：正则表达式，后面用来从 Markdown 正文里抠出第一张图片地址；
# abstractmethod：声明“抽象方法”，子类不实现就不允许实例化，用于强制约定接口
import logging
import re
from abc import abstractmethod

# —— Django 框架自带模块 ——
# settings：项目全局配置，这里主要用 AUTH_USER_MODEL 拿到“用户模型”，
#           不写死 User，方便项目以后换成自定义用户表；
# ValidationError：在模型校验阶段抛错，让后台表单直接显示错误提示；
# models：ORM 核心，所有字段类型（CharField/TextField/DateTimeField...）都从这里取；
# reverse：用“URL 名称 + 参数”反查出真实路径，避免在代码里硬编码 URL（改路由不用改代码）；
# now：带时区的“当前时间”，作为时间字段默认值，比 datetime.now() 更安全（不会出现 naive 时间）；
# gettext_lazy：懒翻译，字符串等到真正渲染时才翻译，字段名在后台可显示中/英文；
# MDTextField：Markdown 编辑器字段，数据库里仍是 text，但后台带上了富文本编辑界面；
# slugify：来自 uuslug 库，比 Django 自带的强一点——中文标题也能转成拼音形式的 URL 别名
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from mdeditor.fields import MDTextField
from uuslug import slugify

# —— 本项目自己的模块 ——
# cache_decorator：方法级缓存装饰器（缓存 10 小时等）；
# cache：底层缓存对象，可直接 get/set/clear；
# get_current_site：取当前站点（带缓存），拼完整网址时用；
# CacheTimeout / CacheKey：缓存过期时间与缓存键模板的常量表，避免到处手写字符串
from djangoblog.utils import cache_decorator, cache
from djangoblog.utils import get_current_site
from djangoblog.constants import CacheTimeout, CacheKey

# 本模块的日志记录器：logger.info(...) 会带上 blog.models 前缀，方便排查问题
logger = logging.getLogger(__name__)


# ============================================================
# 友情链接的“显示位置”枚举
# 说明：TextChoices 是 Django 提供的“带翻译的字符串枚举”，格式是
#       (存进数据库的值, 后台显示给人看的名字)。用枚举而不是散落的魔术字符串，
#       好处是写错名字会立刻报错，后台还能自动渲染成下拉框。
# ============================================================
class LinkShowType(models.TextChoices):
    # i=index 首页、l=list 列表页、p=post 文章详情页、a=all 全部页面、s=slide 轮播图
    I = ('i', _('index'))
    L = ('l', _('list'))
    P = ('p', _('post'))
    A = ('a', _('all'))
    S = ('s', _('slide'))


# ============================================================
# BaseModel —— 所有业务模型的抽象基类
# 把“每张表都要有”的东西抽出来：自增主键、创建/修改时间、slug 自动生成、完整 URL。
# 注意 abstract = True：它本身不会建表，只是把字段和方法“复制”给子类。
# ============================================================
class BaseModel(models.Model):
    # 显式声明自增主键：Django 默认也会加，但写出来更直观，也方便被外键引用时明确类型
    id = models.AutoField(primary_key=True)
    # 创建时间：default=now 是“插入时取当前时间”，不是建表时间；用 now 而非 now()，避免所有行共享同一时刻
    creation_time = models.DateTimeField(_('creation time'), default=now)
    # 最后修改时间：同样默认 now；真正“自动刷新”靠下面的 save() 逻辑与业务代码显式赋值
    last_modify_time = models.DateTimeField(_('modify time'), default=now)

    # 【save】—— 保存模型时的统一入口，处理“只 +1 浏览量”这个高频特例
    # 参数：*args / **kwargs（透传给 models.Model.save，例如 update_fields、force_insert）
    # 返回：None（Django 的 save 不返回值）
    # 说明：浏览量是最高频的写操作，若走正常 save 会把整行（可能几百 KB 的正文）重新写一遍，
    #       还会顺手刷新时间字段、重算 slug。所以这里先判断“这次是不是单纯改 views”，
    #       是就退化成一条精简的 UPDATE，只改这一列。
    def save(self, *args, **kwargs):
        # 判定条件：当前对象是文章，且调用方明确说“只更新 views 这一个字段”
        is_update_views = isinstance(
            self,
            Article) and 'update_fields' in kwargs and kwargs['update_fields'] == ['views']
        if is_update_views:
            # QuerySet.update() 直接发 SQL：UPDATE blog_article SET views=? WHERE id=?，
            # 不经过模型的 save 钩子，因此不会覆盖正文、不会改 last_modify_time
            Article.objects.filter(pk=self.pk).update(views=self.views)
        else:
            # 只有带 slug 字段的模型（分类、标签）才需要重算 URL 别名
            if 'slug' in self.__dict__:
                # 分类/标签用 name，文章用 title —— 即“URL 别名跟着名字走”
                slug = getattr(
                    self, 'title') if 'title' in self.__dict__ else getattr(
                    self, 'name')
                # slugify 会把中文名转成拼音、把空格转成横线，保证 URL 里只有合法字符
                setattr(self, 'slug', slugify(slug))
            # 真正的落库动作交给父类
            super().save(*args, **kwargs)

    # 【get_full_url】—— 拼出带协议和域名的完整网址
    # 返回：str，形如 https://example.com/article/2024/5/1/3/
    # 说明：站内跳转用相对路径就够，但 RSS、分享到微信/微博、SEO 的 canonical 标签
    #       都要求绝对地址，所以统一在这里拼；域名取自站点表，支持一个项目挂多个域名。
    def get_full_url(self):
        # get_current_site() 本身带缓存，不会每次请求都查库
        site = get_current_site().domain
        url = "https://{site}{path}".format(site=site,
                                            path=self.get_absolute_url())
        return url

    # 【Meta】—— 抽象基类：不建 blog_basemodel 表，字段只被子类继承
    class Meta:
        abstract = True

    # 【get_absolute_url】—— 抽象方法，强制每个子类说明“自己的详情页在哪”
    # 说明：Django 后台的“在站点上查看”按钮、模板里的 {{ obj.get_absolute_url }} 都靠它；
    #       文章、分类、标签的 URL 规则不同，所以这里只留声明，具体由子类实现。
    @abstractmethod
    def get_absolute_url(self):
        pass


# ============================================================
# Article —— 文章模型（本文件最核心的一张表，前台的绝大部分页面都在读它）
# 一篇文章 = 标题 + Markdown 正文 + 状态 + 分类 + 作者 + 若干标签
# ============================================================
class Article(BaseModel):
    """文章"""
    # 三组 choices（可选值表）：数据库里只存一个字符，后台表单渲染成下拉框，
    # 显示时用 get_status_display() 拿到 “Draft/Published” 这样的人话
    STATUS_CHOICES = (
        ('d', _('Draft')),      # d代表草稿状态
        ('p', _('Published')),  # p代表已发布状态
    )
    COMMENT_STATUS = (
        ('o', _('Open')),    # o代表开启评论
        ('c', _('Close')),   # c代表关闭评论
    )
    TYPE = (
        ('a', _('Article')),  # a代表普通文章
        ('p', _('Page')),     # p代表独立页面
    )
    # 标题：char 定长比 text 更适合加唯一索引；unique=True 让标题成为业务上的“唯一标识”，
    # 既防止同站两篇同名文章把 slug 冲掉，也让详情页可以按标题查
    title = models.CharField(_('title'), max_length=200, unique=True)  # 文章标题，唯一，最大长度200
    # 正文：用 MDTextField 而不是普通 TextField，是为了后台获得 Markdown 编辑器；
    # 数据库层面它依然是 text，渲染时由 djangoblog.utils.CommonMarkdown 转成 HTML 再进模板
    body = MDTextField(_('body'))    # 文章Markdown正文内容

    # 文章发布时间
    # blank=False/null=False：不允许空，因为列表页要按它排序；
    # default=now：新建文章默认“就是现在”，避免前台立刻出现 1970 年的时间；
    # 用 null=False 而不是允许 NULL，是因为 NULL 参与排序时行为反直觉（升序排最前）
    pub_time = models.DateTimeField(
        _('publish time'), blank=False, null=False, default=now)

    # 文章状态：草稿/已发布
    # max_length=1 是因为值只有单字符；default='p' 表示新建即发布（本站是个人博客，很少存草稿）
    status = models.CharField(
        _('status'),
        max_length=1,
        choices=STATUS_CHOICES,
        default='p')

    # 评论开关状态：开启/关闭
    # 默认 'o' 开启，符合博客“先让人评论”的预期；单篇关评论常用于公告类内容
    comment_status = models.CharField(
        _('comment status'),
        max_length=1,
        choices=COMMENT_STATUS,
        default='o')

    # 内容类型：文章或者独立页面
    # 'a' 普通文章会进列表、归档、RSS；'p' 独立页面（关于我、友情链接）只按 URL 单独访问，不进列表
    type = models.CharField(_('type'), max_length=1, choices=TYPE, default='a')

    # 文章浏览计数
    # PositiveIntegerField 在数据库层带“非负”约束，天然挡住 0 以下的值；
    # 用 Positive 而不是普通 Integer，是让约束落在数据库而不是靠代码自觉
    views = models.PositiveIntegerField(_('views'), default=0)

    # 外键，关联文章作者用户，删除用户时级联删除文章
    # settings.AUTH_USER_MODEL 是字符串形式的用户模型引用，避免和自定义用户表循环导入；
    # CASCADE：作者账号注销时其文章一并清理，不留没有作者的孤儿文章
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_('author'),
        blank=False,
        null=False,
        on_delete=models.CASCADE)

    # 文章排序权重，数值越大越靠前
    # 用 Integer 而不是 Positive，是为了允许负值把文章压到列表末尾；
    # 与 Meta.ordering 的第一个排序键配合，实现“手动置顶”
    article_order = models.IntegerField(
        _('order'), blank=False, null=False, default=0)

    # 是否展示文章目录TOC
    # 默认 False：短文章硬塞目录反而干扰阅读，只有长文在后台手动打开
    show_toc = models.BooleanField(_('show toc'), blank=False, null=False, default=False)

    # 外键，关联文章所属分类，删除分类级联删除文章
    # blank/null 都为 False：每篇文章必须归属一个分类，否则导航、面包屑无从生成；
    # 外键列在数据库里会自动建索引，所以“按分类查文章”天生就快
    category = models.ForeignKey(
        'Category',
        verbose_name=_('category'),
        on_delete=models.CASCADE,
        blank=False,
        null=False)

    # 多对多关系，一篇文章可以拥有多个标签
    # ManyToManyField 会自动生成中间表 blog_article_tags(article_id, tag_id)；
    # blank=True 表示标签可以一个都不选，它是“锦上添花”的分类维度
    tags = models.ManyToManyField('Tag', verbose_name=_('tag'), blank=True)

    # 【body_to_string】—— 把正文当纯字符串返回
    # 用途：模板或摘要逻辑只需要文本时统一走这个方法，将来若正文结构变化，只改这里即可
    def body_to_string(self):
        return self.body

    # 【__str__】—— 后台列表、日志里显示文章标题，而不是冷冰冰的 Article object (3)
    def __str__(self):
        return self.title

    # 【Meta】—— 表的元信息：默认排序、后台显示名、索引
    class Meta:
        # 全局默认排序：负号=降序。先按置顶权重，权重相同再按发布时间新的在前；
        # 有了它，Article.objects.all() 不用每次手写 order_by，列表页也不容易漏排序
        ordering = ['-article_order', '-pub_time']
        # 后台里这张表显示成“文章”（单数/复数）
        verbose_name = _('article')
        verbose_name_plural = verbose_name
        # 让 latest()/earliest() 以 id 为“最新”的判定依据
        get_latest_by = 'id'
        # 索引：查询加速的核心。字段顺序遵循“最左前缀原则”——
        # 等值过滤的列放前面，范围或排序的列放后面；负号表示按该列降序建索引。
        # 下面四个索引都由 blog/migrations/0007 迁移创建
        indexes = [
            # 优化列表查询：type + status + pub_time组合索引
            # 对应首页/归档的 SELECT ... WHERE type='a' AND status='p' ORDER BY pub_time DESC，
            # 走这条索引可以同时完成过滤和排序，省掉一次额外排序（filesort）
            models.Index(fields=['type', 'status', '-pub_time'], name='idx_type_status_pub'),
            # 优化热门文章查询：status + views组合索引
            # 对应侧边栏“最多阅读” SELECT ... WHERE status='p' ORDER BY views DESC LIMIT 10，
            # 用到索引后只读前 10 行就停，不必全表排序
            models.Index(fields=['status', '-views'], name='idx_status_views'),
            # 优化作者文章查询：author + status + type组合索引
            # 对应作者主页 SELECT ... WHERE author_id=? AND status='p' AND type='a'
            models.Index(fields=['author', 'status', 'type'], name='idx_author_status_type'),
            # 优化分类查询：category + status组合索引
            # 对应分类页 SELECT ... WHERE category_id=? AND status='p'
            models.Index(fields=['category', 'status'], name='idx_category_status'),
        ]

    # 【get_absolute_url】—— 文章详情页地址
    # 返回：str，形如 /article/2024/5/1/3/（年/月/日/文章id）
    # 说明：URL 里带日期层级，一是利于搜索引擎判断发布时间，二是方便按日期做归档；
    #       路径最后用 id 而不是 slug，所以标题改了旧链接也不会 404。
    def get_absolute_url(self):
        return reverse('blog:detailbyid', kwargs={
            'article_id': self.id,
            'year': self.creation_time.year,
            'month': self.creation_time.month,
            'day': self.creation_time.day
        })

    # 【get_category_tree】—— 取本文所属分类的整条父级链
    # 返回：list[tuple[str, str]]，[(分类名, 分类链接), ...]，从自己一直排到最顶层
    # 说明：详情页面包屑用；分类结构几乎不变，所以整体缓存 10 小时。
    #       装饰器优先尝试用实例的 get_cache_key() 当缓存键，模型没有这个方法时
    #       会退化为“函数 + 参数”摘要出的哈希键。
    @cache_decorator(CacheTimeout.HOUR_10)
    def get_category_tree(self):
        tree = self.category.get_category_tree()
        # 传 Category 对象给模板还得再调方法，先转成 (名字, 链接) 元组，模板里直接解包使用
        names = list(map(lambda c: (c.name, c.get_absolute_url()), tree))

        return names

    # 【save】—— 文章保存
    # 说明：这里直接转调父类，实际工作（以及“只改浏览量”的特判、slug 计算）都在 BaseModel.save 里；
    #       保留这个入口是为了让 Article 拥有自己的保存时机，将来要在存文章前后加点业务动作时在此扩展。
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

    # 【viewed】—— 浏览量 +1
    # 说明：update_fields=['views'] 是关键，配合 BaseModel.save 的特判，
    #       最终只发一条只改 views 列的 UPDATE，不会把整篇正文重新写盘。
    def viewed(self):
        self.views += 1
        self.save(update_fields=['views'])

    # 【comment_list】—— 取本文下“审核通过”的评论（带 10 小时缓存）
    # 返回：QuerySet（Django 的惰性查询结果集，只有真正遍历时才发 SQL）
    # 说明：评论列表在详情页每次都要渲染，但变化频率低，所以缓存起来；
    #       缓存键用 CacheKey 模板拼，统一前缀便于将来按前缀批量清理。
    def comment_list(self):
        cache_key = CacheKey.ARTICLE_COMMENTS.format(article_id=self.id)
        value = cache.get(cache_key)
        if value:
            # 打日志是为了在线上能直接看出缓存到底有没有命中
            logger.info(f'Cache HIT: article comments (id={self.id})')
            return value
        else:
            # is_enable=True 只取审核通过的评论；-id 表示最新评论排最前
            comments = self.comment_set.filter(is_enable=True).order_by('-id')
            cache.set(cache_key, comments, CacheTimeout.HOUR_10)
            logger.info(f'Cache MISS: article comments (id={self.id})')
            return comments

    # 【get_admin_url】—— 这篇文章在后台的编辑页地址
    # 返回：str，形如 /admin/blog/article/3/change/
    # 说明：app_label + model_name 从模型的 _meta 里取，所以改模型名也不会写错；
    #       前台页面上给管理员显示“编辑此文”的快捷入口就靠它。
    def get_admin_url(self):
        info = (self._meta.app_label, self._meta.model_name)
        return reverse('admin:%s_%s_change' % info, args=(self.pk,))

    # 【next_article】—— 下一篇文章（id 更大的第一篇已发布文章）
    # 返回：Article 或 None
    # 说明：只查 status='p'，草稿不能通过“下一篇”被读者翻到；
    #       order_by('id').first() 等价于 LIMIT 1，避免把整批结果都取回来
    @cache_decorator(expiration=CacheTimeout.HOUR_10)
    def next_article(self):
        # 下一篇
        return Article.objects.filter(
            id__gt=self.id, status='p').order_by('id').first()

    # 【prev_article】—— 上一篇文章（id 更小的最新一篇已发布文章）
    # 说明：默认排序是 -id（由 Meta.ordering 决定），所以 first() 直接就是 id 最大的那篇
    @cache_decorator(expiration=CacheTimeout.HOUR_10)
    def prev_article(self):
        # 前一篇
        return Article.objects.filter(id__lt=self.id, status='p').first()

    # 【get_first_image_url】—— 从 Markdown 正文里取出第一张图片的地址
    # 返回：str，图片 URL；没有图片则返回空字符串（模板里 if 判断很方便，不用处理 None）
    # 说明：列表页缩略图、微信分享卡片的封面都靠它；
    #       正则 !\[.*?\]\((.+?)\) 对应 Markdown 的 ![说明](地址) 语法，
    #       两处 .+? 都是非贪婪匹配，保证只吃到最近的右括号，不会把后面的文字一起吞进来。
    def get_first_image_url(self):
        """
        Get the first image url from article.body.
        :return:
        """
        match = re.search(r'!\[.*?\]\((.+?)\)', self.body)
        if match:
            return match.group(1)
        return ""


# ============================================================
# Category —— 文章分类
# 通过 parent_category 自关联形成“分类树”（如：技术 -> Python -> Django），
# 前台左侧导航与详情页面包屑都基于它。
# ============================================================
class Category(BaseModel):
    """文章分类"""
    # 分类名：要出现在导航和 URL 里，30 字符够用；unique=True 保证不会出现两个同名分类
    name = models.CharField(_('category name'), max_length=30, unique=True)
    # 父分类：'self' 表示外键指向本表自己，从而形成树形结构；
    # blank/null 必须为 True —— 顶级分类没有父级，数据库只能存 NULL；
    # CASCADE：删父分类时子分类一并删除，避免出现“挂在已删父级下面”的孤儿节点
    parent_category = models.ForeignKey(
        'self',
        verbose_name=_('parent category'),
        blank=True,
        null=True,
        on_delete=models.CASCADE)
    # URL 别名：SlugField 在后台会做合法性校验（只允许字母数字横线下划线）；
    # 下面的 BaseModel.save 会用 name 自动重算它（uuslug 能把中文转成拼音），
    # default='no-slug' 是给数据库里已存在的老数据一个兜底值，避免迁移时非空校验失败
    slug = models.SlugField(default='no-slug', max_length=60, blank=True)
    # 排序权重：后台手工调整导航里分类的先后，数值大的排前面（见 Meta.ordering）
    index = models.IntegerField(default=0, verbose_name=_('index'))

    # 【Meta】—— 默认按 index 降序，后台显示名为“分类”
    class Meta:
        ordering = ['-index']
        verbose_name = _('category')
        verbose_name_plural = verbose_name

    # 【get_absolute_url】—— 分类页地址，形如 /category/python/
    # 注意用 slug 而不是 id：URL 里出现可读单词对搜索引擎更友好
    def get_absolute_url(self):
        return reverse(
            'blog:category_detail', kwargs={
                'category_name': self.slug})

    # 【__str__】—— 后台与模板里显示分类名
    def __str__(self):
        return self.name

    # 【get_category_tree】—— 递归向上收集所有祖先
    # 返回：list[Category]，[自己, 父分类, 祖父分类, ...]（顶级分类只有自己）
    # 说明：面包屑要从当前分类一路展示到根，所以自下而上爬；
    #       分类树变动极少，缓存 10 小时可显著减少递归查库。
    @cache_decorator(CacheTimeout.HOUR_10)
    def get_category_tree(self):
        """
        递归获得分类目录的父级
        :return:
        """
        categorys = []

        # 内部函数 parse：把当前节点塞进列表，再对父节点重复同一动作（递归）
        def parse(category):
            categorys.append(category)
            if category.parent_category:
                parse(category.parent_category)

        parse(self)
        return categorys

    # 【get_sub_categorys】—— 递归向下收集所有子孙分类
    # 返回：list[Category]，[自己, 子分类, 孙分类, ...]
    # 说明：分类页要显示“该分类及其所有子分类下的文章”，所以需要整棵子树；
    #       先把 Category.objects.all() 一次性取到内存，再在内存里 filter，
    #       避免递归过程中一层层查库（否则就是典型的 N+1 查询问题，分类越深查得越多）。
    @cache_decorator(CacheTimeout.HOUR_10)
    def get_sub_categorys(self):
        """
        获得当前分类目录所有子集
        :return:
        """
        categorys = []
        all_categorys = Category.objects.all()

        # 内部函数 parse：取当前节点的直接子分类，逐个加入结果并继续向下递归
        def parse(category):
            if category not in categorys:
                categorys.append(category)
            childs = all_categorys.filter(parent_category=category)
            for child in childs:
                # 判重：同一分类在多层递归中可能被再次遇到，避免结果里出现重复项
                if category not in categorys:
                    categorys.append(child)
                parse(child)

        parse(self)
        return categorys


# ============================================================
# Tag —— 文章标签
# 与文章是多对多关系：一篇文章可挂多个标签，一个标签下也有多篇文章；
# 比起分类的“树”，标签是扁平的、更细粒度的横向归类。
# ============================================================
class Tag(BaseModel):
    """文章标签"""
    # 标签名：唯一，防止同名标签把文章拆到两处；30 字符对标签这种短词足够
    name = models.CharField(_('tag name'), max_length=30, unique=True)
    # URL 别名：保存时由 BaseModel.save 依据 name 自动生成（中文会转拼音）
    slug = models.SlugField(default='no-slug', max_length=60, blank=True)

    # 【__str__】—— 后台与模板里显示标签名
    def __str__(self):
        return self.name

    # 【get_absolute_url】—— 标签页地址，形如 /tag/python/
    def get_absolute_url(self):
        return reverse('blog:tag_detail', kwargs={'tag_name': self.slug})

    # 【get_article_count】—— 统计这个标签下有多少篇已关联文章
    # 说明：跨表查询 tags__name 会 JOIN 中间表，一篇含多个标签的文章可能被 JOIN 出多行，
    #       所以必须 distinct() 去重再 count()，否则数字会虚高；
    #       侧边栏标签云每个标签都要算一次，因此缓存 10 小时。
    @cache_decorator(CacheTimeout.HOUR_10)
    def get_article_count(self):
        return Article.objects.filter(tags__name=self.name).distinct().count()

    # 【Meta】—— 标签按名字升序排列，后台显示名为“标签”
    class Meta:
        ordering = ['name']
        verbose_name = _('tag')
        verbose_name_plural = verbose_name


# ============================================================
# Links —— 友情链接
# 注意它直接继承 models.Model 而不是 BaseModel：友链不需要 slug 和“详情页地址”，
# 所以不走那套基类，id 由 Django 自动补上（隐式 AutoField 主键）。
# ============================================================
class Links(models.Model):
    """友情链接"""

    # 链接名称：unique 便于后台定位和去重
    name = models.CharField(_('link name'), max_length=30, unique=True)
    # URLField 比 CharField 多了“必须是合法网址”的校验，后台填错会直接提示
    link = models.URLField(_('link'))
    # 显示顺序：unique 保证不会出现两个同序号，排序结果永远稳定，不会忽上忽下
    sequence = models.IntegerField(_('order'), unique=True)
    # 是否启用：站长想临时下线某条友链时改这里即可，不必删除记录（保留历史）
    is_enable = models.BooleanField(
        _('is show'), default=True, blank=False, null=False)
    # 显示位置：取值来自上面的 LinkShowType 枚举；
    # 默认 LinkShowType.I 表示只在首页展示，其他页面不重复出现
    show_type = models.CharField(
        _('show type'),
        max_length=1,
        choices=LinkShowType.choices,
        default=LinkShowType.I)
    # 创建时间 / 修改时间：这里字段名是 last_mod_time（不是基类里的 last_modify_time），
    # 因为没继承 BaseModel，需要自己声明这两列
    creation_time = models.DateTimeField(_('creation time'), default=now)
    last_mod_time = models.DateTimeField(_('modify time'), default=now)

    # 【Meta】—— 按 sequence 升序展示，后台显示名为“友情链接”
    class Meta:
        ordering = ['sequence']
        verbose_name = _('link')
        verbose_name_plural = verbose_name

    # 【__str__】—— 后台列表显示友链名称
    def __str__(self):
        return self.name


# ============================================================
# SideBar —— 侧边栏自定义区块
# 除了“最新文章/热门文章”这些程序生成的内容，站长还可以自己塞一段 HTML
# （公告、广告位、统计代码），每段就是一个 SideBar 记录。
# ============================================================
class SideBar(models.Model):
    """侧边栏,可以展示一些html内容"""
    # 区块标题：只作后台识别和前台小标题，不要求唯一（可以有两块同名）
    name = models.CharField(_('title'), max_length=100)
    # 区块内容：TextField 存大段 HTML；用 TextField 而非 CharField 是因为长度不可预估
    content = models.TextField(_('content'))
    # 排序序号：unique 保证侧边栏顺序确定，不会因序号相同而随机排列
    sequence = models.IntegerField(_('order'), unique=True)
    # 是否启用：下线广告位时保留内容、只关开关，方便随时再开
    is_enable = models.BooleanField(_('is enable'), default=True)
    # 与 Links 同理：未继承 BaseModel，时间字段自行声明
    creation_time = models.DateTimeField(_('creation time'), default=now)
    last_mod_time = models.DateTimeField(_('modify time'), default=now)

    # 【Meta】—— 按 sequence 升序展示，后台显示名为“侧边栏”
    class Meta:
        ordering = ['sequence']
        verbose_name = _('sidebar')
        verbose_name_plural = verbose_name

    # 【__str__】—— 后台列表显示区块标题
    def __str__(self):
        return self.name


# ============================================================
# BlogSettings —— 站点配置（全站唯一的一条记录，即“单例表”）
# 站名、SEO 关键词、摘要长度、评论总开关、配色、备案号等都放这里，
# 改一次等于改整站外观与行为，所以保存时要清空全部页面缓存。
# ============================================================
class BlogSettings(models.Model):
    """blog的配置"""

    # 主题配色可选值：前端模板按这个值切换 CSS 变量，实现“一键换肤”
    # 显示名写成中英双份，后台下拉框里一眼能看懂
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

    # 站名：出现在浏览器标题、页头 Logo、RSS 里，必填
    # 所有字符串字段统一 null=False + default=''：用空串表示“还没填”，
    # 不用 NULL，模板里就不用到处判断 None
    site_name = models.CharField(
        _('site name'),
        max_length=200,
        null=False,
        blank=False,
        default='')
    # 站点描述：给访客看的一句话介绍，也常被搜索引擎当作摘要
    site_description = models.TextField(
        _('site description'),
        max_length=1000,
        null=False,
        blank=False,
        default='')
    # SEO 描述：写进页面 <meta name="description">，影响搜索结果里的那两行字
    site_seo_description = models.TextField(
        _('site seo description'), max_length=1000, null=False, blank=False, default='')
    # SEO 关键词：写进 <meta name="keywords">，用逗号分隔多个词
    site_keywords = models.TextField(
        _('site keywords'),
        max_length=1000,
        null=False,
        blank=False,
        default='')
    # 列表页摘要长度：正文截取多少个字符当摘要，300 约等于一段话，默认值够大多数场景
    article_sub_length = models.IntegerField(_('article sub length'), default=300)
    # 侧边栏“最新文章”显示条数：10 条刚好一屏，不影响首屏加载
    sidebar_article_count = models.IntegerField(_('sidebar article count'), default=10)
    # 侧边栏“最新评论”显示条数：评论一行较短，5 条就够，太多会挤压正文区
    sidebar_comment_count = models.IntegerField(_('sidebar comment count'), default=5)
    # 详情页最多显示多少条评论
    article_comment_count = models.IntegerField(_('article comment count'), default=5)
    # 是否开启 Google 广告：默认关闭（国内站点基本用不上，也避免拖慢加载）
    show_google_adsense = models.BooleanField(_('show adsense'), default=False)
    # 广告代码：只有开启广告才需要，所以允许 null/blank，绝大多数站点留空
    google_adsense_codes = models.TextField(
        _('adsense code'), max_length=2000, null=True, blank=True, default='')
    # 全站评论总开关：默认 True，一键关站内所有评论（比逐篇设置 comment_status 快）
    open_site_comment = models.BooleanField(_('open site comment'), default=True)
    # 当前配色方案：max_length=20 足够放下最长的 'orange'；
    # help_text 会显示在后台表单输入框下面，给运营同学一句说明
    color_scheme = models.CharField(
        _('配色方案'),
        max_length=20,
        choices=COLOR_SCHEMES,
        default='purple',
        help_text=_('选择网站的主题配色方案'))
    # 公共头部 / 尾部：站长自己粘的 HTML（统计脚本、样式），可留空
    global_header = models.TextField("公共头部", null=True, blank=True, default='')
    global_footer = models.TextField("公共尾部", null=True, blank=True, default='')
    # 工信部 ICP 备案号：按法规必须显示在页脚，未备案的站点留空
    beian_code = models.CharField(
        '备案号',
        max_length=2000,
        null=True,
        blank=True,
        default='')
    # 网站统计代码（如百度统计、Google Analytics 的 <script>），直接插进页面底部
    analytics_code = models.TextField(
        "网站统计代码",
        max_length=1000,
        null=False,
        blank=False,
        default='')
    # 是否显示公安备案号：很多站点只在页脚显示 ICP 备案，公安备案可选
    show_gongan_code = models.BooleanField(
        '是否显示公安备案号', default=False, null=False)
    # 公安备案号本身：只有 show_gongan_code 为 True 时才有意义，故可留空
    gongan_beiancode = models.TextField(
        '公安备案号',
        max_length=2000,
        null=True,
        blank=True,
        default='')
    # 评论是否需要审核：默认 False（发出来就展示）；
    # 打开后新评论要等管理员在后台放行，用于防垃圾评论
    comment_need_review = models.BooleanField(
        '评论是否需要审核', default=False, null=False)

    # 【Meta】—— 后台里这张表显示为“网站配置”
    class Meta:
        verbose_name = _('Website configuration')
        verbose_name_plural = verbose_name

    # 【__str__】—— 后台下拉/列表里显示站名，而不是 BlogSettings object (1)
    def __str__(self):
        return self.site_name

    # 【clean】—— 模型级校验，保证“全站只能有一份配置”
    # 说明：Django 在后台表单保存前会先调 clean()；exclude(id=self.id) 是为了
    #       让“编辑自己”这一次能通过校验——否则一改配置就会和自己冲突。
    def clean(self):
        if BlogSettings.objects.exclude(id=self.id).count():
            raise ValidationError(_('There can only be one configuration'))

    # 【save】—— 保存配置后清空全部缓存
    # 说明：站名、导航、配色这些值被整页缓存/片段缓存大量引用，
    #       配置一改必须让旧页面立刻失效，否则前台还是旧名字；
    #       缓存对象在函数内局部 import，是为了避开 utils 与本模块的循环导入。
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        from djangoblog.utils import cache
        cache.clear()
