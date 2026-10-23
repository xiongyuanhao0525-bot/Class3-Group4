# ============================================================
# blog/search_indexes.py —— Haystack 全文检索的“索引入口 / 注册表”
# 作用：Haystack（Django 生态的全文检索抽象层，底层引擎可换 Whoosh / Elasticsearch / Solr）
#   启动时会自动扫描每个已安装 app 根目录下名为 search_indexes.py 的文件，
#   把其中继承 SearchIndex 的类收集成一张“索引注册表（Register）”。
#   之后 manage.py rebuild_index / update_index 建索引、SearchView（views.py 的站内搜索页）
#   发起查询，都按这张表判断“哪些模型可以被搜、搜哪些字段”。
#   所以这个文件的名字和位置都不能改：一旦改名或挪目录，Haystack 就扫描不到，
#   站内搜索会提示“没有任何可搜字段”（No fields were found in any search_indexes）。
#   单独放一个文件而不是写进 models.py，是 Haystack 的约定：它按固定文件名做自动发现，
#   这样检索配置与模型定义解耦，换索引字段不用动 model。
# 本文件包含：
#   - ArticleIndex：声明文章怎么被检索 —— text 主文档字段的内容由模板拼出、
#     index_queryset 只索引已发布文章、get_model 指定模型、title/body 作为可读取的存储字段
# 注释人：翟旌超（软件工程 3 班 2415304340，#zjc）
# 说明：本次任务只添加中文注释，没有改动任何一行原有代码逻辑
# ============================================================

# —— 第三方库：Haystack ——
# indexes：提供 SearchIndex（索引定义基类，地位类似 Model 之于数据库）、
#   Indexable（声明“本索引服务于哪个模型”）、CharField 等索引字段类型
from haystack import indexes

# —— 本项目自己的模块 ——
# 要索引的数据模型：Article 文章（见 blog/models.py）
from blog.models import Article


# 【ArticleIndex】—— 文章的 Haystack 索引定义：告诉 Haystack 文章有哪些可搜字段、索引哪些文章
# 说明：SearchIndex 管“字段从哪来、怎么被搜到”，Indexable 管“索引哪个模型”，两个都要继承。
#       它不需要注册到任何地方 —— 只要类定义在本文件里，Haystack 启动扫描时就会自动发现
class ArticleIndex(indexes.SearchIndex, indexes.Indexable):
    # text：主文档字段（document=True）。Haystack 要求每个索引有且只有一个 document=True 的字段，
    #   搜索时默认就在这个字段里做全文匹配 —— 也就是说“拼进 text 的内容才是能被搜到的内容”。
    # use_template=True：值不直接从模型属性取，而是用一个模板渲染出来。模板路径规则是
    #   templates/search/indexes/<app_label>/<model_name>_text.txt，
    #   本项目就是 templates/search/indexes/blog/article_text.txt，里面写的是
    #   {{ object.title }} / {{ object.author.username }} / {{ object.body }}，
    #   建索引时按文章逐条渲染，把标题、作者名、正文拼成一段文本交给引擎切词。
    #   —— 若某字段的值需要额外计算（拼接、取关联对象、做映射），Haystack 会优先调用
    #   prepare_<字段名>(self, obj) 方法，用它的返回值当该字段的值；本文件没写 prepare_xxx，
    #   正是因为“拼检索文本”这件事已经交给模板完成了。
    # 注意：text 的内容只进索引、不存回数据库，搜索结果里读不到 text 本身。
    text = indexes.CharField(document=True, use_template=True)
    # title / body：普通索引字段。model_attr='title' 表示值直接取 article.title；
    # stored=True 表示这个值同时“存”在索引里，搜索结果可以直接 result.title 取到，
    # 不必再回数据库查一次（fields / stored_fields 的区别就在这里：
    # 非 stored 字段只用于检索、取不回原值；stored 字段是既能检索又能原样读出的“存储字段”）。
    title = indexes.CharField(model_attr='title', stored=True)
    body = indexes.CharField(model_attr='body', stored=True)

    # 【get_model】—— 返回本索引对应的模型类；Haystack 靠它知道去 Article 表取数据、
    #   以及模板路径里的 model_name 该用哪个
    # 返回：Article（type）：文章的 Django 模型类
    # 说明：Indexable 接口要求必须实现，返回的是“类”而不是实例
    def get_model(self):
        return Article

    # 【index_queryset】—— 决定“哪些文章会被写进索引”，也就决定了搜索结果的范围
    # 参数：using（str | None）：Haystack 传入的“使用哪个搜索连接 / 别名”，这里不需要区分，直接忽略
    # 返回：QuerySet：状态为 p 的文章集合（QuerySet 是 Django 的惰性查询结果集，真正遍历时才发 SQL）
    # 说明：只索引已发布（p = published）的文章 —— 草稿（d = draft）和私密内容不该被外人搜到，
    #       在“建索引”这一步就过滤掉，比在搜索页里再筛更安全，也更省索引体积。
    #       rebuild_index / update_index 以及实时信号更新索引时，都会调这个方法取数据源。
    def index_queryset(self, using=None):
        return self.get_model().objects.filter(status='p')
