# ============================================================
# blog/context_processors.py —— 模板上下文处理器：给所有模板灌注公共变量
# 作用：Django 在渲染页面模板前会先调用这里，把站点名、备案号、导航分类、
#       独立页面列表等变量统一塞进模板上下文，这样 templates/ 下的每个模板
#       都能直接使用，不必每个视图各写一遍。
# 本文件包含：seo_processor（唯一的上下文处理器，返回一份带 10 小时缓存的 dict）
# 注释人：翟旌超（软件工程 3 班 2415304340，#zjc）
# 说明：本次任务只添加中文注释，没有改动任何一行原有代码逻辑
# ============================================================
# —— 上下文处理器是什么（第一次读请先看这段）——
# 上下文处理器（context processor）：一个"接收 request、返回 dict"的函数。
# 渲染模板前，Django 会把 settings.TEMPLATES[0].OPTIONS.context_processors 里
# 列出的函数依次调一遍（本文件对应最后一项 'blog.context_processors.seo_processor'），
# 再把各自返回的 dict 合并进模板上下文。
# 也就是说：这里返回的每个键，在 templates/ 下任何模板里都能当变量直接用；
# 代价是"每渲染一个页面就要执行一次"，所以里面的查库、缓存要格外当心。
# —— Python 标准库 ——
# logging：记录缓存命中 / 未命中的日志，排查"后台改了设置前台没变"这类问题用
import logging

# —— Django 框架自带模块 ——
# timezone：取当前时区的时间，用来算页脚版权的年份
from django.utils import timezone

# —— 本项目自己的模块 ——
# cache：项目封装的缓存对象（默认 LocMemCache，配了 DJANGO_REDIS_URL 就换成 Redis）；
# get_blog_setting：读取站点设置 BlogSettings，它自己内部也带了一层缓存
from djangoblog.utils import cache, get_blog_setting
# 数据模型：Category 分类（做导航菜单用）；Article 文章（这里只取其中的独立页面）
from .models import Category, Article

# 本模块的日志记录器：缓存重建时打一行日志，方便确认缓存有没有按预期生效
logger = logging.getLogger(__name__)


# ------------------------------------------------------------
# 【seo_processor】—— 把站点级公共变量注入所有模板（带 10 小时缓存）
# 参数：requests（HttpRequest）：当前请求；参数名虽然叫复数，实际就是单个请求对象，
#       本文件没有导入 requests 库，所以不存在重名冲突，用它拼站点域名
# 返回：dict：模板上下文变量集合，键名就是模板里可直接使用的变量名
# 说明：站点设置、导航分类、独立页面列表这些数据变得很慢，查库却不便宜，
#       所以整份 dict 缓存 10 小时；只有 SITE_BASE_URL / CURRENT_YEAR 两个
#       跟"这次请求 / 当前时间"相关的值，每次命中缓存都重新算一遍再返回。
# ------------------------------------------------------------
def seo_processor(requests):
    # 缓存键用固定字符串：全站只有一份站点配置，不需要按用户或 URL 区分
    key = 'seo_processor'
    # 先读缓存，命中就跳过下面所有数据库查询（这是它能"每页都跑"还不拖慢页面的原因）
    value = cache.get(key)
    if value:
        # 更新动态值（不需要缓存的内容）
        # 取回的是缓存反序列化出来的副本（LocMemCache 与 Redis 后端都会先 pickle），
        # 所以直接改 value 不会把旧域名写回缓存，是安全的
        value['SITE_BASE_URL'] = requests.scheme + '://' + requests.get_host() + '/'
        # 年份每次现算：跨年时页脚自动变成新一年，不必等缓存过期
        value['CURRENT_YEAR'] = timezone.now().year
        return value
    else:
        # 缓存未命中：走到这里说明真要查库了，日志出现这行代表缓存已被清或已过期
        logger.info('set processor cache.')
        setting = get_blog_setting()

        # 优化查询：预加载关联数据
        # 导航菜单要显示全部分类（父子层级在模板里用 {% query %} 标签再筛），
        # 这里一次取出整张分类表，配合下面的缓存，避免每个页面都重查一遍
        nav_category_list = Category.objects.all()
        # 导航栏里的"独立页面"入口：type='p' 是独立页面（关于我、友情链接这类），
        # status='p' 是已发布；草稿状态（'d'）的页面不应该出现在导航里
        nav_pages = Article.objects.filter(
            type='p',
            status='p'
        )

        # 组装模板上下文：键名与 BlogSettings 的字段基本一一对应，
        # 模板里用 {{ SITE_NAME }}、{{ BEIAN_CODE }} 这种全大写变量取值
        value = {
            'SITE_NAME': setting.site_name,
            'SHOW_GOOGLE_ADSENSE': setting.show_google_adsense,
            'GOOGLE_ADSENSE_CODES': setting.google_adsense_codes,
            'SITE_SEO_DESCRIPTION': setting.site_seo_description,
            'SITE_DESCRIPTION': setting.site_description,
            'SITE_KEYWORDS': setting.site_keywords,
            # 站点根地址用本次请求的 scheme + host 拼，换域名或上 https 都能自适应
            'SITE_BASE_URL': requests.scheme + '://' + requests.get_host() + '/',
            'ARTICLE_SUB_LENGTH': setting.article_sub_length,
            # 保留 QuerySet 而不是转成 list：模板里的 {% query %} 标签要在它基础上再过滤
            'nav_category_list': nav_category_list,  # 保持QuerySet
            'nav_pages': nav_pages,  # 保持QuerySet
            'OPEN_SITE_COMMENT': setting.open_site_comment,
            # 备案号、公安备案、统计代码：国内站点合规与流量统计用的配置项
            'BEIAN_CODE': setting.beian_code,
            'ANALYTICS_CODE': setting.analytics_code,
            "BEIAN_CODE_GONGAN": setting.gongan_beiancode,
            "SHOW_GONGAN_CODE": setting.show_gongan_code,
            # 页脚版权年份（这里是缓存未命中时的初值，命中缓存时会被上面重算覆盖）
            "CURRENT_YEAR": timezone.now().year,
            # 后台可填的全局头 / 尾 HTML 片段，用来插统计脚本、公告横幅
            "GLOBAL_HEADER": setting.global_header,
            "GLOBAL_FOOTER": setting.global_footer,
            # 评论是否需要先审核、站点配色方案，模板据此决定评论展示与主题色
            "COMMENT_NEED_REVIEW": setting.comment_need_review,
            "COLOR_SCHEME": setting.color_scheme,
        }
        # 整份上下文缓存 10 小时（60×60×10 秒）。代价是后台改了站点设置，
        # 前台最长要等 10 小时才生效；等不及就访问 /clean 接口手动清缓存。
        # 另有坑：dict 里装的是 QuerySet，cache.set 时要把整份值 pickle（序列化），
        # 这一步会立刻执行 SQL；所以 10 小时内新增的分类 / 页面不会出现在导航上。
        cache.set(key, value, 60 * 60 * 10)
        return value
