#!/usr/bin/env python
# encoding: utf-8

"""
Django Blog 全局常量定义
包含缓存超时时间、缓存键模板等配置
"""


# xyh：全局常量模块——缓存超时、缓存键模板、HTTP 状态码、分页参数四类集中定义。
# xyh：目的：消除散落在各 app 的魔法数字与手拼字符串，缓存键改格式只需动这里一处。


# ===== 缓存过期时间（秒）=====
# xyh：缓存 TTL 档位表——业务代码只允许从这些档位选择超时时长
class CacheTimeout:
    """
    缓存超时时间常量
    集中管理所有缓存过期时间，便于统一调整缓存策略
    """
    # 分钟级
    MINUTE_1 = 60  # xyh：1 分钟——高频易变数据（如验证码倒计时场景）
    MINUTE_5 = 60 * 5  # xyh：5 分钟——短时防抖/热统计
    MINUTE_10 = 60 * 10  # xyh：10 分钟——准实时列表
    MINUTE_30 = 60 * 30  # xyh：30 分钟——半小时级聚合数据

    # 小时级
    HOUR_1 = 60 * 60  # xyh：1 小时——低频页面片段
    HOUR_2 = 60 * 60 * 2  # xyh：2 小时——侧边栏类组件
    HOUR_10 = 60 * 60 * 10  # xyh：10 小时——默认档，覆盖一个访问高峰日
    HOUR_24 = 60 * 60 * 24  # xyh：24 小时——按天过期的归档/统计

    # 天级
    DAY_7 = 60 * 60 * 24 * 7  # xyh：7 天——周榜类稳定数据
    DAY_30 = 60 * 60 * 24 * 30  # xyh：30 天——月榜/几乎静态的配置

    # 默认缓存时间
    DEFAULT = HOUR_10  # 10小时  # xyh：未显式指定 TTL 时的兜底档位


# ===== 缓存键前缀 =====
# xyh：缓存键统一模板——用 .format() 填充占位符，杜绝各 app 手拼 key 造成读写不一致
class CacheKey:
    """
    缓存键模板
    使用字符串格式化模板，避免缓存键拼写错误
    """
    # 文章相关
    ARTICLE_COMMENTS = 'article_comments_{article_id}'  # xyh：某文章的评论列表缓存
    ARTICLE_NEXT = 'article_next_{article_id}'  # xyh：文章详情页"下一篇"导航
    ARTICLE_PREV = 'article_prev_{article_id}'  # xyh：文章详情页"上一篇"导航
    ARTICLE_CATEGORY_TREE = 'article_category_tree_{article_id}'  # xyh：文章所属分类的层级树

    # 列表页缓存
    INDEX_LIST = 'index_{page}'  # xyh：首页第 N 页列表（信号里清 index_1 即此键）
    CATEGORY_LIST = 'category_list_{name}_{page}'  # xyh：分类列表页第 N 页
    TAG_LIST = 'tag_{name}_{page}'  # xyh：标签列表页第 N 页
    AUTHOR_LIST = 'author_{name}_{page}'  # xyh：作者归档页第 N 页
    ARCHIVES = 'archives'  # xyh：按时间归档页整体缓存

    # 分类和标签
    CATEGORY_TREE = 'category_tree_{category_id}'  # xyh：指定分类的子树结构
    SUB_CATEGORIES = 'sub_categories_{category_id}'  # xyh：指定分类的直接子分类
    TAG_ARTICLE_COUNT = 'tag_article_count_{tag_id}'  # xyh：标签下文章计数（云图/列表用）

    # 全局设置
    BLOG_SETTINGS = 'blog_settings'  # xyh：站点配置单例（BlogSettings）缓存
    CURRENT_SITE = 'current_site'  # xyh：当前站点对象（django.contrib.sites）缓存
    SIDEBAR = 'sidebar_{type}'  # xyh：侧边栏组件按类型分键

    # 侧边栏相关
    SIDEBAR_LATEST_ARTICLES = 'sidebar_latest_articles'  # xyh：最新文章列表
    SIDEBAR_HOT_ARTICLES = 'sidebar_hot_articles'  # xyh：热门文章榜
    SIDEBAR_LATEST_COMMENTS = 'sidebar_latest_comments'  # xyh：最新评论列表


# ===== HTTP 状态码 =====
# xyh：常用状态码别名——接口返回时替代裸数字，可读且防笔误
class HttpStatus:
    """HTTP 状态码常量"""
    OK = 200  # xyh：请求成功
    CREATED = 201  # xyh：资源创建成功
    NO_CONTENT = 204  # xyh：成功但无响应体

    BAD_REQUEST = 400  # xyh：请求参数/格式非法
    UNAUTHORIZED = 401  # xyh：未认证
    FORBIDDEN = 403  # xyh：已认证但无权限
    NOT_FOUND = 404  # xyh：资源不存在

    INTERNAL_SERVER_ERROR = 500  # xyh：服务器内部错误
    BAD_GATEWAY = 502  # xyh：上游网关应答无效
    SERVICE_UNAVAILABLE = 503  # xyh：服务暂不可用


# ===== 分页配置 =====
# xyh：分页统一口径——与 mixins.py 分页基类、blog_tags 分页组件共用
class Pagination:
    """分页相关常量"""
    DEFAULT_PAGE_SIZE = 10  # xyh：默认每页条数
    MAX_PAGE_SIZE = 100  # xyh：单页上限，防调用方传超大 size 拖垮查询
    PAGE_QUERY_PARAM = 'page'  # xyh：页码查询参数名（URL 里的 ?page=）
