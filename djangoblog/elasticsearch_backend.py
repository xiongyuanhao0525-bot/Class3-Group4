from django.utils.encoding import force_str
from elasticsearch_dsl import Q
from haystack.backends import BaseEngine, BaseSearchBackend, BaseSearchQuery, log_query
from haystack.forms import ModelSearchForm
from haystack.models import SearchResult
from haystack.utils import log as logging

from blog.documents import ArticleDocument, ArticleDocumentManager
from blog.models import Article

# xyh：模块级说明 —— Haystack 搜索的 Elasticsearch 后端实现，与 whoosh_cn_backend.py 互为替代。
# xyh：  选用条件见 djangoblog/settings.py：设置环境变量 DJANGO_ELASTICSEARCH_HOST 后，
# xyh：  HAYSTACK_CONNECTIONS['default']['ENGINE'] 指向本文件的 ElasticSearchEngine；
# xyh：  未设置时默认回落 Whoosh（本地文件索引）。
# xyh：四个类的分工：ElasticSearchBackend（索引读写 + 查询执行）、
# xyh：  ElasticSearchQuery（Haystack 查询片段翻译）、
# xyh：  ElasticSearchModelSearchForm（表单入口，决定是否启用推荐词）、
# xyh：  ElasticSearchEngine（把上述三者绑定成一个引擎）。
# xyh：注意：索引结构不在本文件定义，而是复用 blog/documents.py 的 ArticleDocument /
# xyh：  ArticleDocumentManager，因此本后端只服务博客文章，不是通用 ES 封装。

logger = logging.getLogger(__name__)


# xyh：搜索后端主体：负责索引的增删重建，以及把关键词查询翻译成 ES DSL 并组装结果
class ElasticSearchBackend(BaseSearchBackend):
    # xyh：初始化：持有 ArticleDocumentManager 作为索引操作代理；开启拼写/推荐纠错能力
    def __init__(self, connection_alias, **connection_options):
        super(
            ElasticSearchBackend,
            self).__init__(
            connection_alias,
            **connection_options)
        self.manager = ArticleDocumentManager()  # xyh：索引生命周期由 documents.py 的管理器统一处理
        self.include_spelling = True  # xyh：允许返回 spelling_suggestion，支撑"是否要找…"提示

    # xyh：把模型对象批量转成 ES 文档；空集合时退化为全量文章（用于 clear/重建场景）
    def _get_models(self, iterable):
        models = iterable if iterable and iterable[0] else Article.objects.all()  # xyh：falsy 判断避免空列表触发全表扫描以外的歧义
        docs = self.manager.convert_to_doc(models)  # xyh：模型 -> Document 实例，字段映射规则在 ArticleDocument
        return docs

    # xyh：建索引：先确保索引存在，再全量写入文档（对应 rebuild_index 命令路径）
    def _create(self, models):
        self.manager.create_index()  # xyh：幂等创建 ES 索引与 mapping
        docs = self._get_models(models)
        self.manager.rebuild(docs)  # xyh：整批重建，非增量

    # xyh：删除文档：逐个删除传入模型对应的索引条目，恒返回 True（不校验实际删除数）
    def _delete(self, models):
        for m in models:
            m.delete()  # xyh：走 Document 实例的 delete，按 _id 精确移除
        return True

    # xyh：增量重建：把变更后的模型重新转换并更新到索引（RealtimeSignalProcessor 触发的主要路径）
    def _rebuild(self, models):
        models = models if models else Article.objects.all()  # xyh：无参调用即全量刷新
        docs = self.manager.convert_to_doc(models)
        self.manager.update_docs(docs)  # xyh：批量 upsert，已存在的 _id 直接覆盖

    # xyh：Haystack 标准接口：写入/更新索引。commit 参数在本实现中忽略（update_docs 内部即时提交）
    def update(self, index, iterable, commit=True):

        models = self._get_models(iterable)
        self.manager.update_docs(models)

    # xyh：Haystack 标准接口：从索引移除单个对象（对象或 "app.Model.pk" 字符串均可）
    def remove(self, obj_or_string):
        models = self._get_models([obj_or_string])
        self._delete(models)

    # xyh：Haystack 标准接口：清空索引。此处直接复用 remove(None)，由 _get_models 展开为全量文章后逐条删除
    def clear(self, models=None, commit=True):
        self.remove(None)

    # xyh：ES term suggest 取"纠错/推荐词"：命中则用建议词，未命中回退原词，保证搜索永不空转
    @staticmethod
    def get_suggestion(query: str) -> str:
        """获取推荐词, 如果没有找到添加原搜索词"""

        search = ArticleDocument.search() \
            .query("match", body=query) \
            .suggest('suggest_search', query, term={'field': 'body'}) \
            .execute()  # xyh：基于 body 字段做词条级建议（term suggester），需索引侧预先配置 suggest 字段

        keywords = []
        for suggest in search.suggest.suggest_search:
            if suggest["options"]:
                keywords.append(suggest["options"][0]["text"])  # xyh：只取排名第一的建议词，不做多候选合并
            else:
                keywords.append(suggest["text"])  # xyh：无建议项时保留用户原始输入

        return ' '.join(keywords)

    # xyh：核心查询入口：把关键词翻译成 bool/match DSL，过滤已发布文章，可选高亮，返回 Haystack 标准结果字典
    @log_query
    def search(self, query_string, **kwargs):
        logger.info('search query_string:' + query_string)

        start_offset = kwargs.get('start_offset')  # xyh：Haystack 分页起点（切片左边界）
        end_offset = kwargs.get('end_offset')  # xyh：Haystack 分页终点（切片右边界）
        highlight = kwargs.get('highlight', True)  # 默认启用高亮

        # 推荐词搜索
        if getattr(self, "is_suggest", None):
            suggestion = self.get_suggestion(query_string)  # xyh：由表单开关控制是否先走纠错
        else:
            suggestion = query_string

        q = Q('bool',
              should=[Q('match', body=suggestion), Q('match', title=suggestion)],
              minimum_should_match=1)  # 至少匹配1个should子句
        # xyh：正文或标题任一 match 即命中；放 filter 内不参与打分排序，行为偏"过滤"而非"加权"

        search = ArticleDocument.search() \
                     .query('bool', filter=[q]) \
                     .filter('term', status='p') \
                     .filter('term', type='a')  # xyh：status=p 仅已发布、type=a 仅文章，草稿与普通页面不进搜索结果

        # 添加高亮配置
        if highlight:
            search = search.highlight('title', 'body',
                                    fragment_size=150,  # 片段大小
                                    number_of_fragments=3,  # 片段数量
                                    pre_tags=['<mark>'],  # 高亮开始标签
                                    post_tags=['</mark>'])  # 高亮结束标签
            # xyh：<mark> 标签由前端样式着色；片段数上限 3 控制响应体积

        search = search.source(False)[start_offset: end_offset]
        # xyh：source(False) 不返回 _source，列表页只需 id+score，减少网络开销；切片实现分页

        results = search.execute()
        # ES 8.x: total 现在是对象 {'value': 123, 'relation': 'eq'}
        hits_total = results['hits']['total']
        hits = hits_total['value'] if isinstance(hits_total, dict) else hits_total  # xyh：兼容 ES 7/8 两种 total 结构
        raw_results = []
        for raw_result in results['hits']['hits']:
            app_label = 'blog'  # xyh：本后端只索引 blog.Article，故硬编码归属
            model_name = 'Article'
            additional_fields = {}

            # 添加高亮内容
            if highlight and 'highlight' in raw_result:
                highlighted = {}
                if 'title' in raw_result['highlight']:
                    highlighted['title'] = raw_result['highlight']['title']
                if 'body' in raw_result['highlight']:
                    highlighted['body'] = raw_result['highlight']['body']

                if highlighted:
                    additional_fields['highlighted'] = highlighted  # xyh：作为额外属性挂到 SearchResult，模板可直接渲染

            result_class = SearchResult

            result = result_class(
                app_label,
                model_name,
                raw_result['_id'],
                raw_result['_score'],
                **additional_fields)  # xyh：组装 Haystack SearchResult；因 source=False，正文字段需模板再回查 DB
            raw_results.append(result)
        facets = {}  # xyh：本实现未做聚合，保持空字典以符合 Haystack 返回契约
        spelling_suggestion = None if query_string == suggestion else suggestion
        # xyh：推荐词与原词相同则视为无需提示，避免每次搜索都显示"您要找的是不是"

        return {
            'results': raw_results,
            'hits': hits,
            'facets': facets,
            'spelling_suggestion': spelling_suggestion,
        }


# xyh：查询片段翻译层：把 Haystack 的 (field, filter_type, value) 三元组转成后端可执行形式
class ElasticSearchQuery(BaseSearchQuery):
    # xyh：日期条件格式化为 ES 可比较的字符串；无时分秒的日期补齐为当天零点
    def _convert_datetime(self, date):
        if hasattr(date, 'hour'):
            return force_str(date.strftime('%Y%m%d%H%M%S'))
        else:
            return force_str(date.strftime('%Y%m%d000000'))

    # xyh：清洗用户输入：保留字转小写，含特殊字符的词整体加引号，防止语法注入
    def clean(self, query_fragment):
        """
        Provides a mechanism for sanitizing user input before presenting the
        value to the backend.

        Whoosh 1.X differs here in that you can no longer use a backslash
        to escape reserved characters. Instead, the whole word should be
        quoted.
        """
        words = query_fragment.split()
        cleaned_words = []

        for word in words:
            if word in self.backend.RESERVED_WORDS:
                word = word.replace(word, word.lower())  # xyh：命中保留字则降级为普通小写词

            for char in self.backend.RESERVED_CHARACTERS:
                if char in word:
                    word = "'%s'" % word  # xyh：整词加单引号包裹，替代反斜杠转义
                    break

            cleaned_words.append(word)

        return ' '.join(cleaned_words)

    # xyh：本后端不使用字段级过滤语法，直接透传上层拼好的 query_string（简化实现）
    def build_query_fragment(self, field, filter_type, value):
        return value.query_string

    # xyh：结果计数：取本次查询结果长度，空结果按 0 计
    def get_count(self):
        results = self.get_results()
        return len(results) if results else 0

    # xyh：返回后端在 search() 中算出的推荐词，供模板展示纠错提示
    def get_spelling_suggestion(self, preferred_query=None):
        return self._spelling_suggestion

    # xyh：组装查询参数：沿用父类逻辑并注入 start/end offset，使分页落到 Backend.search()
    def build_params(self, spelling_query=None):
        kwargs = super(ElasticSearchQuery, self).build_params(spelling_query=spelling_query)
        return kwargs


# xyh：搜索表单：在标准 ModelSearchForm 上增加"是否启用推荐词"开关
class ElasticSearchModelSearchForm(ModelSearchForm):

    # xyh：把前端 is_suggest 参数写回 backend，决定本次是否先走 term suggest 纠错
    def search(self):
        # 是否建议搜索
        self.searchqueryset.query.backend.is_suggest = self.data.get("is_suggest") != "no"
        sqs = super().search()
        return sqs


# xyh：引擎装配：Haystack 通过该类的 backend/query 两个类属性识别可用后端
class ElasticSearchEngine(BaseEngine):
    backend = ElasticSearchBackend  # xyh：索引读写与查询执行
    query = ElasticSearchQuery  # xyh：查询串构造与清洗
