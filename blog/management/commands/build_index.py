# ============================================================
# blog/management/commands/build_index.py —— 重建 Elasticsearch 搜索索引的 management command
# 作用：站内搜索由 haystack 驱动，文档结构定义在 blog/documents.py。当 ES 里还没有索引、
#       索引字段结构改过、或者数据被批量导入/直接改库导致索引与数据库不一致时，跑
#       python manage.py build_index 把 blog（文章）索引删掉后全量重建一遍。
#       没配置 ES（settings 里没有 ELASTICSEARCH_DSL）时本命令什么都不做。
# 本文件包含：
#   Command —— 命令类；handle() 先确保 performance 索引存在，再删掉并重建 blog 索引
# 注释人：翟旌超（软件工程 3 班 2415304340，#zjc）
# 说明：本次任务只添加中文注释，没有改动任何一行原有代码逻辑
# ============================================================

# —— Django 框架 ——
# BaseCommand：management command 的基类，python manage.py build_index 最终执行 Command.handle()
from django.core.management.base import BaseCommand

# —— 项目内模块 ——
# ElapsedTimeDocument：页面耗时统计（性能监控）的索引文档；ElaspedTimeDocumentManager 是它的建索引工具
#   （类名里的 Elasped 是历史拼写，外部已有代码按这个名字 import，为保持兼容不能改名）
# ArticleDocumentManager：文章索引管理器，提供 delete_index() / rebuild() 做全量重建
# ELASTICSEARCH_ENABLED：settings 里有 ELASTICSEARCH_DSL 才为 True；否则站内搜索走 Whoosh，不需要本命令
from blog.documents import ElapsedTimeDocument, ArticleDocumentManager, ElaspedTimeDocumentManager, \
    ELASTICSEARCH_ENABLED


# 【Command】—— 重建搜索索引
# 用法：python manage.py build_index
# 说明：management command 就是“用 python manage.py <文件名> 调起的 Django 脚本”，
#       命令名取自本文件名 build_index；类必须叫 Command，Django 只调用它的 handle()。
# TODO 参数化
class Command(BaseCommand):
    # help 会出现在 python manage.py help 的命令列表与说明里
    help = 'build search index'

    # 【handle】—— 命令执行入口：全量重建搜索索引
    # 参数：*args / **options：命令行参数（本命令没有自定义参数）
    # 返回：None
    # 说明：只对 ES 后端生效；Whoosh 后端靠 haystack 的实时信号处理器增量更新，
    #       没有对应的全量重建流程，所以这里用开关直接跳过
    def handle(self, *args, **options):
        if ELASTICSEARCH_ENABLED:
            # 先确保 performance（页面耗时统计）索引存在：build_index 内部是幂等的，
            # 索引已在就跳过，不影响后面的文章索引
            ElaspedTimeDocumentManager.build_index()
            # 再实例化性能监控文档并调一次 init()：init() 是 elasticsearch_dsl 的“不存在才创建”，
            # 这里再兜一次，保证监控索引随时可写
            manager = ElapsedTimeDocument()
            manager.init()
            # 文章索引：构造管理器时会自动 create_index（同样是不存在才建），然后删掉旧索引
            manager = ArticleDocumentManager()
            manager.delete_index()
            # 先删后建：清空旧的字段映射，避免改了 ArticleDocument 的结构后新字段写不进去；
            # rebuild() 会重新遍历数据库里的文章、转换成文档并批量写进 ES
            manager.rebuild()
