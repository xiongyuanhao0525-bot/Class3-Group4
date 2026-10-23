# encoding: utf-8

# xyh：Whoosh 中文分词搜索后端（Haystack backend 实现），本项目 HAYSTACK_CONNECTIONS 的默认引擎。
# xyh：关键类：WhooshHtmlFormatter（高亮标签格式化）、WhooshSearchBackend（索引建立/更新/查询主逻辑）、
# xyh：　　　WhooshSearchQuery（把 Haystack 查询条件翻译成 Whoosh 查询语法）、WhooshEngine（backend+query 注册入口）。
# xyh：与上游 haystack 版的核心差异：TEXT 字段改用 jieba 的 ChineseAnalyzer 做中文分词（见 build_schema），
# xyh：并在 _process_results 中用正则 <mark> 方案实现标题/正文高亮，替代英文 StemmingAnalyzer 路径。

from __future__ import absolute_import, division, print_function, unicode_literals

import json
import os
import re
import shutil
import threading
import warnings

import six
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from datetime import datetime
from django.utils.encoding import force_str
from haystack.backends import BaseEngine, BaseSearchBackend, BaseSearchQuery, EmptyResults, log_query
from haystack.constants import DJANGO_CT, DJANGO_ID, ID
from haystack.exceptions import MissingDependency, SearchBackendError, SkipDocument
from haystack.inputs import Clean, Exact, PythonData, Raw
from haystack.models import SearchResult
from haystack.utils import get_identifier, get_model_ct
from haystack.utils import log as logging
from haystack.utils.app_loading import haystack_get_model
from jieba.analyse import ChineseAnalyzer
from whoosh import index
from whoosh.analysis import StemmingAnalyzer
from whoosh.fields import BOOLEAN, DATETIME, IDLIST, KEYWORD, NGRAM, NGRAMWORDS, NUMERIC, Schema, TEXT
from whoosh.fields import ID as WHOOSH_ID
from whoosh.filedb.filestore import FileStorage, RamStorage
from whoosh.highlight import ContextFragmenter, HtmlFormatter
from whoosh.highlight import highlight as whoosh_highlight
from whoosh.qparser import QueryParser
from whoosh.searching import ResultsPage
from whoosh.writing import AsyncWriter

try:
    import whoosh
except ImportError:
    raise MissingDependency(
        "The 'whoosh' backend requires the installation of 'Whoosh'. Please refer to the documentation.")

# Handle minimum requirement.
if not hasattr(whoosh, '__version__') or whoosh.__version__ < (2, 5, 0):
    raise MissingDependency(
        "The 'whoosh' backend requires version 2.5.0 or greater.")

# Bubble up the correct error.

# xyh：ISO8601 日期时间正则，用于把索引中存的字符串反解析回 datetime（见 _to_python）
DATETIME_REGEX = re.compile(
    '^(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})T(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2})(\.\d{3,6}Z?)?$')
LOCALS = threading.local()  # xyh：线程本地存储，内存模式下保证每个线程独享 RamStorage
LOCALS.RAM_STORE = None


class WhooshHtmlFormatter(HtmlFormatter):  # xyh：高亮片段格式化器，输出 <tag>文本</tag> 形式
    """
    This is a HtmlFormatter simpler than the whoosh.HtmlFormatter.
    We use it to have consistent results across backends. Specifically,
    Solr, Xapian and Elasticsearch are using this formatting.
    """
    template = '<%(tag)s>%(t)s</%(tag)s>'


class WhooshSearchBackend(BaseSearchBackend):  # xyh：搜索后端主体：建索引、增删文档、执行查询、纠错建议
    # Word reserved by Whoosh for special use.
    RESERVED_WORDS = (
        'AND',
        'NOT',
        'OR',
        'TO',
    )  # xyh：Whoosh 查询语法保留词，拼查询前须清洗（见 create_spelling_suggestion）

    # Characters reserved by Whoosh for special use.
    # The '\\' must come first, so as not to overwrite the other slash
    # replacements.
    RESERVED_CHARACTERS = (
        '\\', '+', '-', '&&', '||', '!', '(', ')', '{', '}',
        '[', ']', '^', '"', '~', '*', '?', ':', '.',
    )  # xyh：保留字符集，反斜杠必须排首位避免二次转义覆盖

    def __init__(self, connection_alias, **connection_options):  # xyh：读取 PATH/STORAGE/POST_LIMIT 连接配置
        super(
            WhooshSearchBackend,
            self).__init__(
            connection_alias,
            **connection_options)
        self.setup_complete = False  # xyh：懒初始化标记，首次使用时才真正建索引
        self.use_file_storage = True
        self.post_limit = getattr(
            connection_options,
            'POST_LIMIT',
            128 * 1024 * 1024)  # xyh：单次提交文档量上限（默认 128MB）
        self.path = connection_options.get('PATH')  # xyh：索引文件目录（settings 里 HAYSTACK_CONNECTIONS 配置）

        if connection_options.get('STORAGE', 'file') != 'file':
            self.use_file_storage = False  # xyh：STORAGE=ram 时切换为内存存储

        if self.use_file_storage and not self.path:
            raise ImproperlyConfigured(
                "You must specify a 'PATH' in your settings for connection '%s'." %
                connection_alias)

        self.log = logging.getLogger('haystack')

    def setup(self):  # xyh：延迟加载入口：建目录、选存储、构建 schema、打开/创建索引
        """
        Defers loading until needed.
        """
        from haystack import connections
        new_index = False

        # Make sure the index is there.
        if self.use_file_storage and not os.path.exists(self.path):
            os.makedirs(self.path)
            new_index = True  # xyh：目录不存在则视为全新索引

        if self.use_file_storage and not os.access(self.path, os.W_OK):
            raise IOError(
                "The path to your Whoosh index '%s' is not writable for the current user/group." %
                self.path)

        if self.use_file_storage:
            self.storage = FileStorage(self.path)  # xyh：磁盘存储
        else:
            global LOCALS

            if getattr(LOCALS, 'RAM_STORE', None) is None:
                LOCALS.RAM_STORE = RamStorage()

            self.storage = LOCALS.RAM_STORE  # xyh：线程内共享的内存存储

        self.content_field_name, self.schema = self.build_schema(
            connections[self.connection_alias].get_unified_index().all_searchfields())  # xyh：由 search_indexes 声明的全部字段生成 schema
        self.parser = QueryParser(self.content_field_name, schema=self.schema)  # xyh：默认查询解析器绑定正文(content)字段

        if new_index is True:
            self.index = self.storage.create_index(self.schema)
        else:
            try:
                self.index = self.storage.open_index(schema=self.schema)  # xyh：优先打开已有索引
            except index.EmptyIndexError:
                self.index = self.storage.create_index(self.schema)  # xyh：空目录则回退为新建

        self.setup_complete = True

    def build_schema(self, fields):  # xyh：把 Haystack 字段定义映射为 Whoosh 字段类型
        schema_fields = {
            ID: WHOOSH_ID(stored=True, unique=True),  # xyh：Haystack 全局文档 id，唯一
            DJANGO_CT: WHOOSH_ID(stored=True),  # xyh：内容类型（app.model），用于按模型过滤
            DJANGO_ID: WHOOSH_ID(stored=True),  # xyh：模型主键
        }
        # Grab the number of keys that are hard-coded into Haystack.
        # We'll use this to (possibly) fail slightly more gracefully later.
        initial_key_count = len(schema_fields)  # xyh：内置键数量，用于后面判断是否没配任何搜索字段
        content_field_name = ''

        for field_name, field_class in fields.items():
            if field_class.is_multivalued:  # xyh：多值字段
                if field_class.indexed is False:
                    schema_fields[field_class.index_fieldname] = IDLIST(
                        stored=True, field_boost=field_class.boost)  # xyh：不索引仅存储
                else:
                    schema_fields[field_class.index_fieldname] = KEYWORD(
                        stored=True, commas=True, scorable=True, field_boost=field_class.boost)  # xyh：逗号分隔关键词，可计分
            elif field_class.field_type in ['date', 'datetime']:
                schema_fields[field_class.index_fieldname] = DATETIME(
                    stored=field_class.stored, sortable=True)  # xyh：日期可排序（配合 sortedby）
            elif field_class.field_type == 'integer':
                schema_fields[field_class.index_fieldname] = NUMERIC(
                    stored=field_class.stored, numtype=int, field_boost=field_class.boost)
            elif field_class.field_type == 'float':
                schema_fields[field_class.index_fieldname] = NUMERIC(
                    stored=field_class.stored, numtype=float, field_boost=field_class.boost)
            elif field_class.field_type == 'boolean':
                # Field boost isn't supported on BOOLEAN as of 1.8.2.
                schema_fields[field_class.index_fieldname] = BOOLEAN(
                    stored=field_class.stored)
            elif field_class.field_type == 'ngram':
                schema_fields[field_class.index_fieldname] = NGRAM(
                    minsize=3, maxsize=15, stored=field_class.stored, field_boost=field_class.boost)
            elif field_class.field_type == 'edge_ngram':
                schema_fields[field_class.index_fieldname] = NGRAMWORDS(minsize=2, maxsize=15, at='start',
                                                                        stored=field_class.stored,
                                                                        field_boost=field_class.boost)  # xyh：前缀 ngram，适合自动补全
            else:
                # schema_fields[field_class.index_fieldname] = TEXT(stored=True, analyzer=StemmingAnalyzer(), field_boost=field_class.boost, sortable=True)
                schema_fields[field_class.index_fieldname] = TEXT(
                    stored=True, analyzer=ChineseAnalyzer(), field_boost=field_class.boost, sortable=True)  # xyh：★本项目关键改造——文本字段用 jieba ChineseAnalyzer 替代英文词干分析器，实现中文分词；BM3 评分基于分词后的词项统计
            if field_class.document is True:  # xyh：document=True 的主文本字段，同时开启拼写纠错
                content_field_name = field_class.index_fieldname
                schema_fields[field_class.index_fieldname].spelling = True

        # Fail more gracefully than relying on the backend to die if no fields
        # are found.
        if len(schema_fields) <= initial_key_count:
            raise SearchBackendError(
                "No fields were found in any search_indexes. Please correct this before attempting to search.")

        return (content_field_name, Schema(**schema_fields))

    def update(self, index, iterable, commit=True):  # xyh：批量写入/更新文档到索引
        if not self.setup_complete:
            self.setup()

        self.index = self.index.refresh()  # xyh：刷新以感知外部写入
        writer = AsyncWriter(self.index)  # xyh：异步写线程，避免阻塞请求

        for obj in iterable:
            try:
                doc = index.full_prepare(obj)  # xyh：按 search_indexes 把模型实例摊平成字段字典
            except SkipDocument:
                self.log.debug(u"Indexing for object `%s` skipped", obj)
            else:
                # Really make sure it's unicode, because Whoosh won't have it any
                # other way.
                for key in doc:
                    doc[key] = self._from_python(doc[key])  # xyh：统一转成 Whoosh 可存的字符串

                # Document boosts aren't supported in Whoosh 2.5.0+.
                if 'boost' in doc:
                    del doc['boost']  # xyh：新版 Whoosh 不支持文档级 boost，直接剔除

                try:
                    writer.update_document(**doc)  # xyh：同 id 覆盖旧文档（upsert 语义）
                except Exception as e:
                    if not self.silently_fail:
                        raise

                    # We'll log the object identifier but won't include the actual object
                    # to avoid the possibility of that generating encoding errors while
                    # processing the log message:
                    self.log.error(
                        u"%s while preparing object for update" %
                        e.__class__.__name__,
                        exc_info=True,
                        extra={
                            "data": {
                                "index": index,
                                "object": get_identifier(obj)}})

        if len(iterable) > 0:
            # For now, commit no matter what, as we run into locking issues
            # otherwise.
            writer.commit()  # xyh：无视 commit 参数强制提交——不提交会触发文件锁问题（原作者注）

    def remove(self, obj_or_string, commit=True):  # xyh：按 Haystack id 从索引删除单个文档
        if not self.setup_complete:
            self.setup()

        self.index = self.index.refresh()
        whoosh_id = get_identifier(obj_or_string)  # xyh：拼 app.model.pk 形式的唯一标识

        try:
            self.index.delete_by_query(
                q=self.parser.parse(
                    u'%s:"%s"' %
                    (ID, whoosh_id)))  # xyh：用 ID 精确匹配查询实现删除
        except Exception as e:
            if not self.silently_fail:
                raise

            self.log.error(
                "Failed to remove document '%s' from Whoosh: %s",
                whoosh_id,
                e,
                exc_info=True)

    def clear(self, models=None, commit=True):  # xyh：清空索引：models=None 全清，否则按内容类型删除指定模型
        if not self.setup_complete:
            self.setup()

        self.index = self.index.refresh()

        if models is not None:
            assert isinstance(models, (list, tuple))

        try:
            if models is None:
                self.delete_index()  # xyh：整体重建最快
            else:
                models_to_delete = []

                for model in models:
                    models_to_delete.append(
                        u"%s:%s" %
                        (DJANGO_CT, get_model_ct(model)))  # xyh：每个模型转 dj_content_type 过滤项

                self.index.delete_by_query(
                    q=self.parser.parse(
                        u" OR ".join(models_to_delete)))  # xyh：OR 拼接一次删多类
        except Exception as e:
            if not self.silently_fail:
                raise

            if models is not None:
                self.log.error(
                    "Failed to clear Whoosh index of models '%s': %s",
                    ','.join(models_to_delete),
                    e,
                    exc_info=True)
            else:
                self.log.error(
                    "Failed to clear Whoosh index: %s", e, exc_info=True)

    def delete_index(self):  # xyh：物理删除索引目录后重建（全量清空场景）
        # Per the Whoosh mailing list, if wiping out everything from the index,
        # it's much more efficient to simply delete the index files.
        if self.use_file_storage and os.path.exists(self.path):
            shutil.rmtree(self.path)
        elif not self.use_file_storage:
            self.storage.clean()

        # Recreate everything.
        self.setup()

    def optimize(self):  # xyh：合并段文件、压缩索引，提升查询性能
        if not self.setup_complete:
            self.setup()

        self.index = self.index.refresh()
        self.index.optimize()

    def calculate_page(self, start_offset=0, end_offset=None):  # xyh：把 Haystack 偏移区间换算成 Whoosh 的(页码,每页条数)
        # Prevent against Whoosh throwing an error. Requires an end_offset
        # greater than 0.
        if end_offset is not None and end_offset <= 0:
            end_offset = 1  # xyh：Whoosh 要求 end_offset>0，钳位保护

        # Determine the page.
        page_num = 0

        if end_offset is None:
            end_offset = 1000000  # xyh：未指定终点时给一个大值≈不分页

        if start_offset is None:
            start_offset = 0

        page_length = end_offset - start_offset  # xyh：区间长度即每页条数

        if page_length and page_length > 0:
            page_num = int(start_offset / page_length)  # xyh：起始偏移落在第几页

        # Increment because Whoosh uses 1-based page numbers.
        page_num += 1  # xyh：Whoosh 页码从 1 开始
        return page_num, page_length

    @log_query
    def search(
            self,
            query_string,
            sort_by=None,
            start_offset=0,
            end_offset=None,
            fields='',
            highlight=False,
            facets=None,
            date_facets=None,
            query_facets=None,
            narrow_queries=None,
            spelling_query=None,
            within=None,
            dwithin=None,
            distance_point=None,
            models=None,
            limit_to_registered_models=None,
            result_class=None,
            **kwargs):  # xyh：查询主入口：清洗→排序校验→模型过滤→分页执行→结果加工；相关性由 Whoosh 默认 BM3F 评分器基于 jieba 分词后的词频计算
        if not self.setup_complete:
            self.setup()

        # A zero length query should return no results.
        if len(query_string) == 0:
            return {
                'results': [],
                'hits': 0,
            }  # xyh：空串短路返回

        query_string = force_str(query_string)

        # A one-character query (non-wildcard) gets nabbed by a stopwords
        # filter and should yield zero results.
        if len(query_string) <= 1 and query_string != u'*':
            return {
                'results': [],
                'hits': 0,
            }  # xyh：单字符会被停用词过滤器吞掉，直接判零结果

        reverse = False

        if sort_by is not None:
            # Determine if we need to reverse the results and if Whoosh can
            # handle what it's being asked to sort by. Reversing is an
            # all-or-nothing action, unfortunately.
            sort_by_list = []
            reverse_counter = 0

            for order_by in sort_by:
                if order_by.startswith('-'):
                    reverse_counter += 1  # xyh：统计降序字段个数

            if reverse_counter and reverse_counter != len(sort_by):
                raise SearchBackendError("Whoosh requires all order_by fields"
                                         " to use the same sort direction")  # xyh：★排序方向必须全一致——Whoosh reverse 是整页翻转，混用会错排

            for order_by in sort_by:
                if order_by.startswith('-'):
                    sort_by_list.append(order_by[1:])  # xyh：剥掉负号

                    if len(sort_by_list) == 1:
                        reverse = True  # xyh：以第一个字段定全局方向
                else:
                    sort_by_list.append(order_by)

                    if len(sort_by_list) == 1:
                        reverse = False

            sort_by = sort_by_list[0]  # xyh：Whoosh 仅按首字段排序（多字段能力受限）

        if facets is not None:
            warnings.warn(
                "Whoosh does not handle faceting.",
                Warning,
                stacklevel=2)  # xyh：Whoosh 不支持切面聚合，仅告警不报错

        if date_facets is not None:
            warnings.warn(
                "Whoosh does not handle date faceting.",
                Warning,
                stacklevel=2)

        if query_facets is not None:
            warnings.warn(
                "Whoosh does not handle query faceting.",
                Warning,
                stacklevel=2)

        narrowed_results = None
        self.index = self.index.refresh()

        if limit_to_registered_models is None:
            limit_to_registered_models = getattr(
                settings, 'HAYSTACK_LIMIT_TO_REGISTERED_MODELS', True)

        if models and len(models):
            model_choices = sorted(get_model_ct(model) for model in models)  # xyh：显式指定模型集合
        elif limit_to_registered_models:
            # Using narrow queries, limit the results to only models handled
            # with the current routers.
            model_choices = self.build_models_list()  # xyh：默认只搜已注册索引的模型
        else:
            model_choices = []

        if len(model_choices) > 0:
            if narrow_queries is None:
                narrow_queries = set()

            narrow_queries.add(' OR '.join(
                ['%s:%s' % (DJANGO_CT, rm) for rm in model_choices]))  # xyh：模型白名单转 dj_content_type 窄化查询

        narrow_searcher = None

        if narrow_queries is not None:
            # Potentially expensive? I don't see another way to do it in
            # Whoosh...
            narrow_searcher = self.index.searcher()

            for nq in narrow_queries:
                recent_narrowed_results = narrow_searcher.search(
                    self.parser.parse(force_str(nq)), limit=None)  # xyh：limit=None 取全量命中做交集

                if len(recent_narrowed_results) <= 0:
                    return {
                        'results': [],
                        'hits': 0,
                    }  # xyh：任一窄化条件无命中则整体为空

                if narrowed_results:
                    narrowed_results.filter(recent_narrowed_results)  # xyh：多次窄化求交集
                else:
                    narrowed_results = recent_narrowed_results

        self.index = self.index.refresh()

        if self.index.doc_count():
            searcher = self.index.searcher()
            parsed_query = self.parser.parse(query_string)  # xyh：QueryParser 解析成 Whoosh 查询树（中文经 ChineseAnalyzer 切词）

            # In the event of an invalid/stopworded query, recover gracefully.
            if parsed_query is None:
                return {
                    'results': [],
                    'hits': 0,
                }  # xyh：全是停用词时优雅返回空

            page_num, page_length = self.calculate_page(
                start_offset, end_offset)  # xyh：偏移区间 → 1-based 页码+每页条数

            search_kwargs = {
                'pagelen': page_length,
                'sortedby': sort_by,
                'reverse': reverse,
            }  # xyh：分页与排序参数包

            # Handle the case where the results have been narrowed.
            if narrowed_results is not None:
                search_kwargs['filter'] = narrowed_results  # xyh：把交集结果作为过滤器带入正式搜索

            try:
                raw_page = searcher.search_page(
                    parsed_query,
                    page_num,
                    **search_kwargs
                )  # xyh：执行一次搜索并直接取指定页（BM3 评分排序后）
            except ValueError:
                if not self.silently_fail:
                    raise

                return {
                    'results': [],
                    'hits': 0,
                    'spelling_suggestion': None,
                }

            # Because as of Whoosh 2.5.1, it will return the wrong page of
            # results if you request something too high. :(
            if raw_page.pagenum < page_num:
                return {
                    'results': [],
                    'hits': 0,
                    'spelling_suggestion': None,
                }  # xyh：规避上游 bug——请求页超出总页数时会错返末页，这里判空兜底

            results = self._process_results(
                raw_page,
                highlight=highlight,
                query_string=query_string,
                spelling_query=spelling_query,
                result_class=result_class)
            searcher.close()  # xyh：及时释放 searcher 文件句柄

            if hasattr(narrow_searcher, 'close'):
                narrow_searcher.close()

            return results
        else:
            if self.include_spelling:
                if spelling_query:
                    spelling_suggestion = self.create_spelling_suggestion(
                        spelling_query)
                else:
                    spelling_suggestion = self.create_spelling_suggestion(
                        query_string)  # xyh：索引为空仍尝试给纠错建议
            else:
                spelling_suggestion = None

            return {
                'results': [],
                'hits': 0,
                'spelling_suggestion': spelling_suggestion,
            }

    def more_like_this(
            self,
            model_instance,
            additional_query_string=None,
            start_offset=0,
            end_offset=None,
            models=None,
            limit_to_registered_models=None,
            result_class=None,
            **kwargs):  # xyh：找相似文档（相关推荐）：基于正文词项重合度，Whoosh 用 more_like_this 实现
        if not self.setup_complete:
            self.setup()

        # Deferred models will have a different class ("RealClass_Deferred_fieldname")
        # which won't be in our registry:
        model_klass = model_instance._meta.concrete_model  # xyh：取真实模型类，规避 deferred 代理类不在注册表的问题

        field_name = self.content_field_name  # xyh：以主文本字段做相似度比较
        narrow_queries = set()
        narrowed_results = None
        self.index = self.index.refresh()

        if limit_to_registered_models is None:
            limit_to_registered_models = getattr(
                settings, 'HAYSTACK_LIMIT_TO_REGISTERED_MODELS', True)

        if models and len(models):
            model_choices = sorted(get_model_ct(model) for model in models)
        elif limit_to_registered_models:
            # Using narrow queries, limit the results to only models handled
            # with the current routers.
            model_choices = self.build_models_list()
        else:
            model_choices = []

        if len(model_choices) > 0:
            if narrow_queries is None:
                narrow_queries = set()

            narrow_queries.add(' OR '.join(
                ['%s:%s' % (DJANGO_CT, rm) for rm in model_choices]))  # xyh：同 search：模型白名单窄化

        if additional_query_string and additional_query_string != '*':
            narrow_queries.add(additional_query_string)  # xyh：附加过滤条件并入窄化集合

        narrow_searcher = None

        if narrow_queries is not None:
            # Potentially expensive? I don't see another way to do it in
            # Whoosh...
            narrow_searcher = self.index.searcher()

            for nq in narrow_queries:
                recent_narrowed_results = narrow_searcher.search(
                    self.parser.parse(force_str(nq)), limit=None)

                if len(recent_narrowed_results) <= 0:
                    return {
                        'results': [],
                        'hits': 0,
                    }

                if narrowed_results:
                    narrowed_results.filter(recent_narrowed_results)
                else:
                    narrowed_results = recent_narrowed_results

        page_num, page_length = self.calculate_page(start_offset, end_offset)

        self.index = self.index.refresh()
        raw_results = EmptyResults()  # xyh：先置空结果，索引无文档时直接走空分支

        if self.index.doc_count():
            query = "%s:%s" % (ID, get_identifier(model_instance))  # xyh：先定位目标文档本身
            searcher = self.index.searcher()
            parsed_query = self.parser.parse(query)
            results = searcher.search(parsed_query)

            if len(results):
                raw_results = results[0].more_like_this(
                    field_name, top=end_offset)  # xyh：★核心——由命中文档反查正文词项最相似的 top-N

            # Handle the case where the results have been narrowed.
            if narrowed_results is not None and hasattr(raw_results, 'filter'):
                raw_results.filter(narrowed_results)  # xyh：相似结果再与窄化交集求交

        try:
            raw_page = ResultsPage(raw_results, page_num, page_length)  # xyh：手工切片成页
        except ValueError:
            if not self.silently_fail:
                raise

            return {
                'results': [],
                'hits': 0,
                'spelling_suggestion': None,
            }

        # Because as of Whoosh 2.5.1, it will return the wrong page of
        # results if you request something too high. :(
        if raw_page.pagenum < page_num:
            return {
                'results': [],
                'hits': 0,
                'spelling_suggestion': None,
            }  # xyh：同 search 的越界页兜底

        results = self._process_results(raw_page, result_class=result_class)
        searcher.close()

        if hasattr(narrow_searcher, 'close'):
            narrow_searcher.close()

        return results

    def _process_results(
            self,
            raw_page,
            highlight=False,
            query_string='',
            spelling_query=None,
            result_class=None):  # xyh：把 Whoosh 原始页加工成 Haystack SearchResult 列表，并做本项目自研的中文高亮
        from haystack import connections
        results = []

        # It's important to grab the hits first before slicing. Otherwise, this
        # can cause pagination failures.
        hits = len(raw_page)  # xyh：先取总命中数，后面对未注册模型的扣减不影响分页语义

        if result_class is None:
            result_class = SearchResult

        facets = {}
        spelling_suggestion = None
        unified_index = connections[self.connection_alias].get_unified_index()
        indexed_models = unified_index.get_indexed_models()

        for doc_offset, raw_result in enumerate(raw_page):
            score = raw_page.score(doc_offset) or 0  # xyh：BM3 相关性得分随结果带出
            app_label, model_name = raw_result[DJANGO_CT].split('.')
            additional_fields = {}
            model = haystack_get_model(app_label, model_name)

            if model and model in indexed_models:
                for key, value in raw_result.items():
                    index = unified_index.get_index(model)
                    string_key = str(key)

                    if string_key in index.fields and hasattr(
                            index.fields[string_key], 'convert'):  # xyh：字段声明了 convert 则还原为 Python 原生类型
                        # Special-cased due to the nature of KEYWORD fields.
                        if index.fields[string_key].is_multivalued:
                            if value is None or len(value) == 0:
                                additional_fields[string_key] = []
                            else:
                                additional_fields[string_key] = value.split(
                                    ',')  # xyh：KEYWORD 多值字段按逗号拆回列表
                        else:
                            additional_fields[string_key] = index.fields[string_key].convert(
                                value)
                    else:
                        additional_fields[string_key] = self._to_python(value)  # xyh：无 convert 走通用反序列化

                del (additional_fields[DJANGO_CT])
                del (additional_fields[DJANGO_ID])  # xyh：内部元数据字段不外露给结果对象

                if highlight:
                    # 使用中文分词器
                    ca = ChineseAnalyzer()  # xyh：实例化但未直接使用——实际高亮走下方正则方案（遗留代码）

                    highlighted = {}

                    # 高亮标题（如果存在）
                    if 'title' in additional_fields and additional_fields['title']:
                        import re
                        title_text = additional_fields['title']
                        # 使用正则表达式高亮，不转义HTML
                        for term in query_string.split():
                            if len(term) >= 2:  # xyh：单字词跳过，避免误伤过广
                                # 不区分大小写地替换
                                title_text = re.sub(
                                    r'(' + re.escape(term) + r')',
                                    r'<mark>\1</mark>',
                                    title_text,
                                    flags=re.IGNORECASE
                                )  # xyh：★自研中文高亮：直接正则包裹 <mark>，绕开 Whoosh 英文高亮器不适配中文的问题
                        if '<mark>' in title_text:
                            highlighted['title'] = [title_text]

                    # 高亮正文 - 返回markdown片段，让模板处理
                    if 'body' in additional_fields and additional_fields['body']:
                        import re
                        from djangoblog.utils import CommonMarkdown

                        # 先转换为HTML，便于提取摘要
                        html_content = CommonMarkdown.get_markdown(additional_fields['body'])

                        # 提取纯文本用于搜索匹配的上下文
                        from django.utils.html import strip_tags
                        plain_text = strip_tags(html_content)  # xyh：markdown→HTML→纯文本，得到可定位的正文

                        # 找到关键词的位置，提取上下文
                        match_pos = -1
                        for term in query_string.split():
                            if len(term) >= 2:
                                pos = plain_text.lower().find(term.lower())
                                if pos >= 0:
                                    match_pos = pos
                                    break  # xyh：取第一个命中的词作为摘要锚点

                        if match_pos >= 0:
                            # 提取匹配位置前后的内容
                            start = max(0, match_pos - 150)
                            end = min(len(plain_text), match_pos + 350)  # xyh：锚点前150/后350字符窗口
                            snippet = plain_text[start:end]

                            # 对snippet进行高亮
                            for term in query_string.split():
                                if len(term) >= 2:
                                    snippet = re.sub(
                                        r'(' + re.escape(term) + r')',
                                        r'<mark>\1</mark>',
                                        snippet,
                                        flags=re.IGNORECASE
                                    )  # xyh：摘要片段同样包裹 <mark>

                            highlighted['body'] = [snippet]

                    if highlighted:
                        additional_fields['highlighted'] = highlighted  # xyh：高亮结果挂到附加字段，交给模板渲染

                result = result_class(
                    app_label,
                    model_name,
                    raw_result[DJANGO_ID],
                    score,
                    **additional_fields)
                results.append(result)
            else:
                hits -= 1  # xyh：索引里有但已取消注册的模型，扣减总数保持 hits 准确

        if self.include_spelling:
            if spelling_query:
                spelling_suggestion = self.create_spelling_suggestion(
                    spelling_query)
            else:
                spelling_suggestion = self.create_spelling_suggestion(
                    query_string)  # xyh："你是不是想搜"建议

        return {
            'results': results,
            'hits': hits,
            'facets': facets,
            'spelling_suggestion': spelling_suggestion,
        }

    def create_spelling_suggestion(self, query_string):  # xyh：基于 Whoosh 编辑距离纠错器逐词给拼写建议
        spelling_suggestion = None
        reader = self.index.reader()
        corrector = reader.corrector(self.content_field_name)  # xyh：以正文词库为纠错词典
        cleaned_query = force_str(query_string)

        if not query_string:
            return spelling_suggestion

        # Clean the string.
        for rev_word in self.RESERVED_WORDS:
            cleaned_query = cleaned_query.replace(rev_word, '')  # xyh：剔除语法保留词再纠错

        for rev_char in self.RESERVED_CHARACTERS:
            cleaned_query = cleaned_query.replace(rev_char, '')

        # Break it down.
        query_words = cleaned_query.split()
        suggested_words = []

        for word in query_words:
            suggestions = corrector.suggest(word, limit=1)  # xyh：每词最多取 1 个建议

            if len(suggestions) > 0:
                suggested_words.append(suggestions[0])

        spelling_suggestion = ' '.join(suggested_words)
        return spelling_suggestion

    def _from_python(self, value):  # xyh：写入前把 Python 值序列化为 Whoosh 字符串
        """
        Converts Python values to a string for Whoosh.

        Code courtesy of pysolr.
        """
        if hasattr(value, 'strftime'):
            if not hasattr(value, 'hour'):
                value = datetime(value.year, value.month, value.day, 0, 0, 0)  # xyh：纯 date 补零点再格式化
        elif isinstance(value, bool):
            if value:
                value = 'true'
            else:
                value = 'false'
        elif isinstance(value, (list, tuple)):
            value = u','.join([force_str(v) for v in value])  # xyh：多值字段逗号拼接存储
        elif isinstance(value, (six.integer_types, float)):
            # Leave it alone.
            pass
        else:
            value = force_str(value)
        return value

    def _to_python(self, value):  # xyh：读出后尽力反序列化回原生类型（bool/日期/json）
        """
        Converts values from Whoosh to native Python values.

        A port of the same method in pysolr, as they deal with data the same way.
        """
        if value == 'true':
            return True
        elif value == 'false':
            return False

        if value and isinstance(value, six.string_types):
            possible_datetime = DATETIME_REGEX.search(value)  # xyh：先按 ISO8601 正则探测日期串

            if possible_datetime:
                date_values = possible_datetime.groupdict()

                for dk, dv in date_values.items():
                    date_values[dk] = int(dv)

                return datetime(
                    date_values['year'],
                    date_values['month'],
                    date_values['day'],
                    date_values['hour'],
                    date_values['minute'],
                    date_values['second'])

        try:
            # Attempt to use json to load the values.
            converted_value = json.loads(value)  # xyh：再尝试 json 解析数字/容器

            # Try to handle most built-in types.
            if isinstance(
                    converted_value,
                    (list,
                     tuple,
                     set,
                     dict,
                     six.integer_types,
                     float,
                     complex)):
                return converted_value
        except BaseException:
            # If it fails (SyntaxError or its ilk) or we don't trust it,
            # continue on.
            pass

        return value  # xyh：都失败则原样返回字符串


class WhooshSearchQuery(BaseSearchQuery):  # xyh：查询构造器：把 SQS 链式条件翻译成 Whoosh qparser 语法串
    def _convert_datetime(self, date):  # xyh：日期转 Whoosh 区间语法所需的 YYYYMMDDHHMMSS 紧凑格式
        if hasattr(date, 'hour'):
            return force_str(date.strftime('%Y%m%d%H%M%S'))
        else:
            return force_str(date.strftime('%Y%m%d000000'))

    def clean(self, query_fragment):  # xyh：清洗用户输入防注入：保留词降格、含特殊字符的整词加引号
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
                word = word.replace(word, word.lower())  # xyh：AND/OR 等大写保留词转小写失去语法含义

            for char in self.backend.RESERVED_CHARACTERS:
                if char in word:
                    word = "'%s'" % word  # xyh：含 * ? : 等特殊字符时整体单引号包裹
                    break

            cleaned_words.append(word)

        return ' '.join(cleaned_words)

    def build_query_fragment(self, field, filter_type, value):  # xyh：单个 filter 条件 → "(field:frag)" 查询片段
        from haystack import connections
        query_frag = ''
        is_datetime = False

        if not hasattr(value, 'input_type_name'):
            # Handle when we've got a ``ValuesListQuerySet``...
            if hasattr(value, 'values_list'):
                value = list(value)  # xyh：QuerySet 先物化

            if hasattr(value, 'strftime'):
                is_datetime = True

            if isinstance(value, six.string_types) and value != ' ':
                # It's not an ``InputType``. Assume ``Clean``.
                value = Clean(value)  # xyh：裸字符串默认走清洗包装
            else:
                value = PythonData(value)

        # Prepare the query using the InputType.
        prepared_value = value.prepare(self)  # xyh：Clean/Exact/Raw 各自决定转义策略

        if not isinstance(prepared_value, (set, list, tuple)):
            # Then convert whatever we get back to what pysolr wants if needed.
            prepared_value = self.backend._from_python(prepared_value)

        # 'content' is a special reserved word, much like 'pk' in
        # Django's ORM layer. It indicates 'no special field'.
        if field == 'content':
            index_fieldname = ''  # xyh：content 表示不限定字段（走默认解析字段）
        else:
            index_fieldname = u'%s:' % connections[self._using].get_unified_index(
            ).get_index_fieldname(field)  # xyh：逻辑字段名映射为索引实际字段名

        filter_types = {
            'content': '%s',
            'contains': '*%s*',  # xyh：通配符前后包裹实现"包含"
            'endswith': "*%s",
            'startswith': "%s*",
            'exact': '%s',
            'gt': "{%s to}",  # xyh：{} 开区间 / [] 闭区间是 Whoosh 区间查询语法
            'gte': "[%s to]",
            'lt': "{to %s}",
            'lte': "[to %s]",
            'fuzzy': u'%s~',  # xyh：波浪号触发模糊匹配（编辑距离）
        }  # xyh：Haystack filter 类型 → Whoosh 语法模板表

        if value.post_process is False:
            query_frag = prepared_value  # xyh：Raw 类输入跳过模板拼装，原样进查询
        else:
            if filter_type in [
                'content',
                'contains',
                'startswith',
                'endswith',
                'fuzzy']:
                if value.input_type_name == 'exact':
                    query_frag = prepared_value
                else:
                    # Iterate over terms & incorportate the converted form of
                    # each into the query.
                    terms = []

                    if isinstance(prepared_value, six.string_types):
                        possible_values = prepared_value.split(' ')  # xyh：空格切词后逐词套模板
                    else:
                        if is_datetime is True:
                            prepared_value = self._convert_datetime(
                                prepared_value)

                        possible_values = [prepared_value]

                    for possible_value in possible_values:
                        terms.append(
                            filter_types[filter_type] %
                            self.backend._from_python(possible_value))

                    if len(terms) == 1:
                        query_frag = terms[0]
                    else:
                        query_frag = u"(%s)" % " AND ".join(terms)  # xyh：★多词默认 AND——配合 jieba 分词，中文查询各词须同时命中
            elif filter_type == 'in':
                in_options = []

                for possible_value in prepared_value:
                    is_datetime = False

                    if hasattr(possible_value, 'strftime'):
                        is_datetime = True

                    pv = self.backend._from_python(possible_value)

                    if is_datetime is True:
                        pv = self._convert_datetime(pv)

                    if isinstance(pv, six.string_types) and not is_datetime:
                        in_options.append('"%s"' % pv)
                    else:
                        in_options.append('%s' % pv)

                query_frag = "(%s)" % " OR ".join(in_options)  # xyh：in → 引号选项 OR 析取
            elif filter_type == 'range':
                start = self.backend._from_python(prepared_value[0])
                end = self.backend._from_python(prepared_value[1])

                if hasattr(prepared_value[0], 'strftime'):
                    start = self._convert_datetime(start)

                if hasattr(prepared_value[1], 'strftime'):
                    end = self._convert_datetime(end)

                query_frag = u"[%s to %s]" % (start, end)  # xyh：range → [起 至 止] 闭区间
            elif filter_type == 'exact':
                if value.input_type_name == 'exact':
                    query_frag = prepared_value
                else:
                    prepared_value = Exact(prepared_value).prepare(self)  # xyh：Exact 包装确保整体精确匹配
                    query_frag = filter_types[filter_type] % prepared_value
            else:
                if is_datetime is True:
                    prepared_value = self._convert_datetime(prepared_value)

                query_frag = filter_types[filter_type] % prepared_value  # xyh：gt/gte/lt/lte 等直接套区间模板

        if len(query_frag) and not isinstance(value, Raw):
            if not query_frag.startswith('(') and not query_frag.endswith(')'):
                query_frag = "(%s)" % query_frag  # xyh：非 Raw 片段统一加括号保证布尔优先级

        return u"%s%s" % (index_fieldname, query_frag)  # xyh：字段前缀+片段拼成最终条件串

        # if not filter_type in ('in', 'range'):
        #     # 'in' is a bit of a special case, as we don't want to
        #     # convert a valid list/tuple to string. Defer handling it
        #     # until later...
        #     value = self.backend._from_python(value)


class WhooshEngine(BaseEngine):  # xyh：引擎注册入口：settings 中 ENGINE 指向本类即启用该后端
    backend = WhooshSearchBackend  # xyh：索引与查询执行端
    query = WhooshSearchQuery  # xyh：查询语法翻译端
