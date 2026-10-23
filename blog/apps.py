# ============================================================
# blog/apps.py —— blog 应用的启动配置（AppConfig）
# 作用：Django 启动时会为 INSTALLED_APPS 里的每个应用找一个 AppConfig 子类，用来说明
#   “这个应用叫什么、启动时要做什么”。本文件就是 blog 应用的这份配置，并在 ready() 里
#   插入一个启动钩子：检查搜索引擎的索引是否就绪，缺了就顺手建出来，
#   避免上线后第一次搜索才因为“索引不存在”报错。
# 本文件包含：
#   - BlogConfig：应用配置类，name = 'blog'；ready() 在启动阶段调用下面的检查
#   - check_search_index：分别检查 Elasticsearch 索引与 Whoosh 索引目录，
#     已存在就跳过、缺失就创建或提示“首次搜索时会自动建”
# 注释人：翟旌超（软件工程 3 班 2415304340，#zjc）
# 说明：本次任务只添加中文注释，没有改动任何一行原有代码逻辑
# ============================================================

# —— Django 框架自带模块 ——
# AppConfig：应用配置基类，每个 app 写一个子类即可定制启动行为
from django.apps import AppConfig

# —— Python 标准库 ——
# logging：启动检查的结果只写日志（成功 / 跳过 / 失败），不打断服务启动
import logging

# 本模块的日志记录器，启动阶段的提示都带模块名，便于定位
logger = logging.getLogger(__name__)


# 【BlogConfig】—— blog 应用的 AppConfig：告诉 Django“这个应用怎么启动”
# 说明：三个关键属性的含义（本类只显式写了 name，其余用默认值）：
#   name：应用的 Python 包路径，必须能 import 到，且要和 INSTALLED_APPS 里的 'blog' 对应
#       （djangoblog/settings.py 第 57 行写的就是 'blog'）；
#   verbose_name：后台 admin 里显示的名字；本类没写 → Django 默认取 name 的最后一段，即 'blog'；
#   default_auto_field：Django 3.2+ 引入，指定模型主键默认用哪种自增字段；本类没写 →
#       跟随项目全局设置 djangoblog/settings.py 第 448 行的 DEFAULT_AUTO_FIELD
#       = 'django.db.models.BigAutoField'（64 位自增主键，容量足够大不会用完）。
# 怎么被用起来：INSTALLED_APPS 里写 'blog'，Django 会自动到 blog/apps.py 找唯一的
#   AppConfig 子类并采用它（blog/__init__.py 是空文件，没有老式的 default_app_config 写法）。
class BlogConfig(AppConfig):
    # 应用包路径；写错 Django 启动就会报 ImproperlyConfigured
    name = 'blog'

    # 【ready】—— 应用启动完成后的回调，Django 启动流程里每个进程调用一次
    # 参数：无
    # 返回：无
    # 说明：调用时机是“所有应用都加载完、模型都已注册”之后。它会在每个进程各跑一遍
    #       （runserver 的自动重载子进程、每个 gunicorn / uwsgi worker 都会调），
    #       所以这里的事必须“可重复执行、代价小、不依赖别的 app 的启动顺序”。
    #       本方法只做一次索引存在性检查，不写数据库。
    def ready(self):
        """应用启动时的初始化"""
        # 检查并创建搜索索引（如果需要）
        self.check_search_index()

    # 【check_search_index】—— 检查搜索索引是否就绪；缺失就建，出任何异常都只记日志
    # 参数：无
    # 返回：无
    # 说明：本项目的站内搜索有两条链路（Elasticsearch 和 Whoosh），这里两条都检查一遍；
    #       但整段都包在 try/except 里 —— 引擎没装、连不上、配置不全，都只 warning，
    #       绝不能因为“搜索暂时用不了”就让整个网站起不来。
    def check_search_index(self):
        """检查搜索索引是否存在，不存在则创建空索引"""
        # 局部导入 settings：把配置的读取推迟到真正执行检查时，模块导入期少一层依赖
        from django.conf import settings

        # 1. 检查Elasticsearch索引
        # 只有 settings 里存在 ELASTICSEARCH_DSL 才说明配了 ES
        # （settings.py 里只有设置了环境变量 DJANGO_ELASTICSEARCH_HOST 才会生成这一项），
        # 没配就整段跳过，不会去连一个根本不存在的 ES
        if hasattr(settings, 'ELASTICSEARCH_DSL'):
            try:
                # ELASTICSEARCH_ENABLED：documents.py 里“是否启用 ES”的总开关；
                # ArticleDocumentManager：文章索引管理器，实例化时就会把 blog 索引建出来
                from blog.documents import ELASTICSEARCH_ENABLED, ArticleDocumentManager
                if ELASTICSEARCH_ENABLED:
                    from elasticsearch import Elasticsearch
                    # 取默认那一组连接配置
                    es_config = settings.ELASTICSEARCH_DSL['default']
                    # verify_certs=False：开发环境的 ES 多用自签证书，关掉证书校验才连得上
                    es = Elasticsearch(hosts=[es_config['hosts']], verify_certs=False)

                    # 检查blog索引是否存在
                    # 先用客户端的 indices.exists 问一句：索引在就什么都不做，
                    # 保证这段代码反复执行（每个进程都跑一次）也是安全的
                    if not es.indices.exists(index='blog'):
                        logger.info("Elasticsearch blog index not found, creating empty index...")
                        # ArticleDocumentManager 的 __init__ 里就调了 create_index()，
                        # 所以“实例化”这一步已经把空索引建好了（见 blog/documents.py 第 315 行）
                        manager = ArticleDocumentManager()
                        logger.info("Elasticsearch blog index created successfully")
                    else:
                        logger.debug("Elasticsearch blog index already exists")
            except Exception as e:
                # 兜底：ES 没启动 / 认证失败 / elasticsearch 包没装，都只记 warning 继续启动，
                # 让站点至少能正常浏览（此时只是站内搜索不可用）
                logger.warning(f"Failed to check/create Elasticsearch index: {e}")

        # 2. 检查Whoosh索引
        # Whoosh 是纯 Python 的轻量索引库，也是本项目没配 ES 时的默认引擎
        # （settings.py 的 HAYSTACK_CONNECTIONS 里 ENGINE 为 djangoblog.whoosh_cn_backend.WhooshEngine）；
        # 这里用“引擎名里有没有 whoosh”来判断当前是不是这条路，lower() 是为了忽略大小写差异
        haystack_engine = settings.HAYSTACK_CONNECTIONS.get('default', {}).get('ENGINE', '')
        if 'whoosh' in haystack_engine.lower():
            try:
                import os
                # PATH：索引目录（settings.py 里配的是 BASE_DIR/whoosh_index）
                whoosh_path = settings.HAYSTACK_CONNECTIONS['default'].get('PATH')
                if whoosh_path and not os.path.exists(whoosh_path):
                    # 目录还不存在：这里故意不建 —— Whoosh 在第一次建索引时自己会创建目录，
                    # 现在动手建还得额外处理权限、空目录判断，收益不大
                    logger.info(f"Whoosh index directory not found at {whoosh_path}, will be created on first search")
                    # Whoosh会在第一次搜索时自动创建，这里只记录日志
                elif whoosh_path and os.path.exists(whoosh_path):
                    # 检查是否有索引文件
                    # Whoosh 的索引由 .seg 段文件等组成（外加写入锁文件 _MAIN_WRITELOCK）：
                    # 目录存在但一个 .seg 都没有，说明只是个空目录、还没真正建过索引
                    index_files = [f for f in os.listdir(whoosh_path) if f.endswith('.seg') or f == '_MAIN_WRITELOCK']
                    if not index_files:
                        logger.info("Whoosh index directory exists but empty, will be initialized on first search")
                    else:
                        logger.debug("Whoosh index already exists")
            except Exception as e:
                # 兜底同上：索引目录不可读、配置里没有 PATH，都只 warning，不影响服务启动
                logger.warning(f"Failed to check Whoosh index: {e}")
