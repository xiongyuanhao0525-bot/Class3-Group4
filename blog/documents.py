# ============================================================
# blog/documents.py —— Elasticsearch 文档（Document）定义与索引管理
# 作用：本项目的全文检索有两条链路，本文件是“Elasticsearch 那条链路”的数据层：
#   1) Haystack 链路（默认 Whoosh 引擎）：索引入口在 blog/search_indexes.py；
#   2) Elasticsearch 链路：用 elasticsearch_dsl 直接把文章写成 ES 文档，
#      搜索时由 djangoblog/elasticsearch_backend.py 调本文件的 ArticleDocument 发查询。
#   本文件负责：读 settings.ELASTICSEARCH_DSL 建立 ES 连接、声明索引结构（字段类型 + 中文分词器）、
#   创建/删除索引、把 Django 的 Article 模型对象转换成 ES 文档、批量重建与增量更新索引。
# 本文件包含：
#   - ES 连接初始化：兼容 hosts 两种写法，支持用户名密码 / API Key / 证书 / 双向 TLS 认证
#   - GeoIp、UserAgentBrowser、UserAgentOS、UserAgentDevice、UserAgent：内嵌对象（InnerDoc）定义
#   - ElapsedTimeDocument：页面耗时（性能监控）索引的文档结构
#   - ElaspedTimeDocumentManager：建/删性能索引，并把一条访问记录写进 ES
#   - ArticleDocument：文章索引的文档结构（标题、正文、作者、分类、标签……）
#   - ArticleDocumentManager：建/删文章索引、ORM 对象转文档、全量重建、批量更新
# 注释人：翟旌超（软件工程 3 班 2415304340，#zjc）
# 说明：本次任务只添加中文注释，没有改动任何一行原有代码逻辑
# ============================================================

# —— Python 标准库 ——
# time：取毫秒级时间戳，用作性能日志文档的主键（不必再额外维护自增 id）
import time

# —— 第三方库：Elasticsearch ——
# elasticsearch.client：ES 官方客户端。这里只是让它被加载，
#   下面才能用 elasticsearch.exceptions.NotFoundError 判断“索引 / pipeline 不存在”这种正常情况
import elasticsearch.client
# settings：读项目配置，ELASTICSEARCH_DSL 里存着 ES 地址与认证信息
from django.conf import settings
# elasticsearch_dsl：ES 的“对象映射”封装，用 Python 类描述 ES 索引：
#   Document=一个文档/一条记录，InnerDoc=嵌在文档里的子对象，Text/Keyword/Date 等=字段类型
from elasticsearch_dsl import Document, InnerDoc, Date, Integer, Long, Text, Object, GeoPoint, Keyword, Boolean
# connections：elasticsearch_dsl 自己的连接池，注册之后 Document 才知道往哪台机器写
from elasticsearch_dsl.connections import connections

# —— 本项目自己的模块 ——
# Article：文章的 Django 模型，是文章索引的数据来源（ORM 对象 → ES 文档）
from blog.models import Article

# 是否启用 Elasticsearch：settings 里存在 ELASTICSEARCH_DSL 这一项才算启用
# （settings.py 中只有设置了环境变量 DJANGO_ELASTICSEARCH_HOST 才会生成它）。
# 没配就整段 ES 初始化跳过，本文件仍可安全 import；此时站内搜索走
# settings.HAYSTACK_CONNECTIONS 里配的 Whoosh 引擎。
ELASTICSEARCH_ENABLED = hasattr(settings, 'ELASTICSEARCH_DSL')

# 未启用 ES 时，这个 if 体内一行都不执行，文件里其余类定义照常加载
if ELASTICSEARCH_ENABLED:
    # 延迟到“确实启用”才导入顶层 Elasticsearch 类，避免没装 ES 依赖的环境 import 就报错
    from elasticsearch import Elasticsearch

    # 取 'default' 这一组连接配置（ELASTICSEARCH_DSL 是 {别名: 配置} 形式的字典）
    es_config = settings.ELASTICSEARCH_DSL['default']

    # ------------------------------------------------------------
    # —— 第一步：把 hosts 统一成 ["http://host:port", ...] 这种列表 ——
    # ES 客户端允许字符串或列表，但字符串必须是“带协议”的完整 URL；
    # 而 settings 里为了简洁常写成 127.0.0.1:9200，这里做一次兼容补全
    # ------------------------------------------------------------
    # 处理 hosts 配置，确保有 scheme
    hosts = es_config['hosts']
    if isinstance(hosts, str):
        # 如果没有 scheme，自动添加 http://
        if not hosts.startswith(('http://', 'https://')):
            hosts = f'http://{hosts}'
        # 包成列表，让下面两种分支返回的类型保持一致
        hosts = [hosts]
    elif isinstance(hosts, list):
        # 处理列表中的每个 host
        processed_hosts = []
        for host in hosts:
            if not host.startswith(('http://', 'https://')):
                host = f'http://{host}'
            processed_hosts.append(host)
        # 用新列表覆盖，不动 settings 里的原始配置
        hosts = processed_hosts

    # ES 连接配置（动态适配认证方式）
    # verify_certs 默认 False：开发环境多用自签证书，关掉校验才连得上
    es_params = {
        'hosts': hosts,
        'verify_certs': es_config.get('verify_certs', False),
    }

    # 支持用户名密码认证（ES 8.x 默认启用安全特性）
    # 方式二：basic 认证，用户名和密码两项都配了才启用
    if 'username' in es_config and 'password' in es_config:
        es_params['basic_auth'] = (es_config['username'], es_config['password'])

    # 支持 API Key 认证
    # 方式三：API Key，适合只给某个服务授予受限权限的场景
    if 'api_key' in es_config:
        es_params['api_key'] = es_config['api_key']

    # 支持证书认证
    # 方式四：CA 证书，用来校验 ES 服务端证书（生产环境通常配合 verify_certs=True 使用）
    if 'ca_certs' in es_config:
        es_params['ca_certs'] = es_config['ca_certs']

    # 支持客户端证书
    # 方式五：双向 TLS，客户端也要出示证书，证书与私钥必须成对出现
    if 'client_cert' in es_config and 'client_key' in es_config:
        es_params['client_cert'] = es_config['client_cert']
        es_params['client_key'] = es_config['client_key']

    # 创建连接
    # 两个连接各管一摊：es 用于直接调 REST 风格接口（ingest / indices），
    # connections.create_connection 把同一套参数注册给 elasticsearch_dsl，
    # 之后 Document.save() / Document.init() 才能自动找到这台 ES
    es = Elasticsearch(**es_params)
    connections.create_connection(**es_params)

    # 设置 GeoIP pipeline
    # ingest pipeline（写入预处理管道）：ES 存文档前按处理器列表加工数据，
    # 这里的 geoip 处理器会把文档里的 ip 字段解析成国家 / 城市 / 经纬度
    try:
        es.ingest.get_pipeline(id='geoip')
    except elasticsearch.exceptions.NotFoundError:
        # 查不到说明集群里还没有这个管道，就创建一份；已存在则什么都不做（保证可重复执行）
        es.ingest.put_pipeline(id='geoip', body={
            "description": "Add geoip info",
            "processors": [
                {
                    "geoip": {
                        "field": "ip"
                    }
                }
            ]
        })


# ------------------------------------------------------------
# —— 内嵌对象（InnerDoc）：性能索引里用到的子结构 ——
# InnerDoc 与 Document 的区别：Document 对应一个独立索引，能单独 save / search；
# InnerDoc 只是挂在别的文档里面的一段 JSON 结构，不能单独建索引。
# ES 里字段类型定好之后不建议再改，所以把“地理位置”“浏览器信息”拆成小类，
# 字段含义一眼可见，也方便别处复用。
# ------------------------------------------------------------

# 【GeoIp】—— 一条访问记录解析出的地理位置（由写入时的 geoip pipeline 按 ip 补上）
class GeoIp(InnerDoc):
    # 大洲名，如 Asia；Keyword 不分词，整串精确匹配
    continent_name = Keyword()
    # 国家二字码，如 CN
    country_iso_code = Keyword()
    # 国家名，如 China
    country_name = Keyword()
    # 经纬度；GeoPoint 类型可用于地图范围 / 距离查询
    location = GeoPoint()


# 【UserAgentBrowser】—— 浏览器信息：Family 是浏览器家族名（如 Chrome），Version 是版本号
# 字段名沿用 user_agents 库的命名习惯（首字母大写），方便把解析结果直接赋过来
class UserAgentBrowser(InnerDoc):
    Family = Keyword()
    Version = Keyword()


# 【UserAgentOS】—— 操作系统信息；字段结构与浏览器完全一样，直接继承复用，不必重写
class UserAgentOS(UserAgentBrowser):
    pass


# 【UserAgentDevice】—— 设备信息：手机 / 平板 / PC 的家族、品牌、型号
class UserAgentDevice(InnerDoc):
    Family = Keyword()
    Brand = Keyword()
    Model = Keyword()


# 【UserAgent】—— 把浏览器、系统、设备、原始 UA 字符串、是否爬虫打包成一个整体
# 三个子对象都 required=False：UA 解析失败或缺字段时，不至于让整条文档写入失败
class UserAgent(InnerDoc):
    # Object 表示“此处是嵌套对象”，值填上面的类
    browser = Object(UserAgentBrowser, required=False)
    os = Object(UserAgentOS, required=False)
    device = Object(UserAgentDevice, required=False)
    # 原始 UA 字符串，用 Text 分词，便于按其中关键字检索
    string = Text()
    # 是否为爬虫 / 机器人访问；统计真实用户量时要排除这些
    is_bot = Boolean()


# 【ElapsedTimeDocument】—— 页面耗时（性能监控）索引的文档结构，一条记录 = 一次请求
# Document 来自 elasticsearch_dsl，作用类似 Django 的 Model：
#   用类属性声明字段，save() 时自动序列化成 JSON 写进 ES；meta.id 就是这条文档的主键
class ElapsedTimeDocument(Document):
    # 被访问的路径，精确匹配用；不分词，避免 /blog/1 被切碎
    url = Keyword()
    # 这次请求的耗时（毫秒）
    time_taken = Long()
    # 记录时间；Date 类型支持时间范围查询与按时间聚合统计
    log_datetime = Date()
    # 访问者 IP，写入时交给 geoip pipeline 解析
    ip = Keyword()
    # 解析出的地理位置，可能为空
    geoip = Object(GeoIp, required=False)
    # 解析出的 UA 信息，可能为空
    useragent = Object(UserAgent, required=False)

    # Meta 里的 Index 类：告诉 elasticsearch_dsl 这个类对应集群里哪个索引、用什么设置
    class Index:
        # 索引名；性能数据单独一个索引，便于按需清理而不影响文章索引
        name = 'performance'
        settings = {
            # 分片数：单机开发环境 1 个足够，分片过多反而浪费资源
            "number_of_shards": 1,
            # 副本数：单节点集群设 0，否则索引会一直处于 yellow 状态
            "number_of_replicas": 0
        }


# 【ElaspedTimeDocumentManager】—— 性能索引的管理器：建索引 / 删索引 / 写一条记录，三件事收在一处
# 说明：类名里的 Elasped 是历史拼写（比正确英文 elapsed 少一个 e），
#       外部已有代码按这个名字 import，为保持兼容这里不改名
class ElaspedTimeDocumentManager:
    # 【build_index】—— 确保 performance 索引存在（幂等：已存在就什么都不做）
    @staticmethod
    def build_index():
        # 局部导入：只有真用到 ES 时才需要这个包
        from elasticsearch import Elasticsearch
        # 使用已配置好的连接参数
        client = Elasticsearch(**es_params)
        # 先问集群：这个索引在不在
        res = client.indices.exists(index="performance")
        if not res:
            # init() 按类里声明的字段和 settings 创建索引
            ElapsedTimeDocument.init()

    # 【delete_index】—— 删除 performance 索引；索引本来就不存在时静默跳过
    @staticmethod
    def delete_index():
        from elasticsearch import Elasticsearch
        es = Elasticsearch(**es_params)
        try:
            es.indices.delete(index='performance')
        except elasticsearch.exceptions.NotFoundError:
            # 索引不存在说明“删除”的目标已经达成，吞掉异常，
            # 让调用方（如重建脚本）可以无脑调用，不用先判断再删
            pass

    # 【create】—— 把一条请求记录写进 performance 索引
    # 参数：url（str）：请求路径；time_taken（int）：耗时毫秒；
    #       log_datetime（datetime）：记录时间；useragent：user_agents 库解析好的 UA 结果对象；
    #       ip（str）：访问者 IP
    # 返回：无（数据直接写进 ES）
    @staticmethod
    def create(url, time_taken, log_datetime, useragent, ip):
        # 先保证索引存在，否则首次写入会报索引不存在
        ElaspedTimeDocumentManager.build_index()
        # 下面把 user_agents 的解析结果逐项搬到 ES 文档结构上：两边字段含义一致，所以逐个赋值
        ua = UserAgent()
        ua.browser = UserAgentBrowser()
        ua.browser.Family = useragent.browser.family
        ua.browser.Version = useragent.browser.version_string

        ua.os = UserAgentOS()
        ua.os.Family = useragent.os.family
        ua.os.Version = useragent.os.version_string

        ua.device = UserAgentDevice()
        ua.device.Family = useragent.device.family
        ua.device.Brand = useragent.device.brand
        ua.device.Model = useragent.device.model
        ua.string = useragent.ua_string
        ua.is_bot = useragent.is_bot

        # meta.id 用“当前毫秒时间戳”做主键：访问量再大也基本不会撞，且天然按时间有序
        doc = ElapsedTimeDocument(
            meta={
                'id': int(
                    round(
                        time.time() *
                        1000))
            },
            url=url,
            time_taken=time_taken,
            log_datetime=log_datetime,
            useragent=ua, ip=ip)
        # pipeline="geoip"：写入时先过一遍管道，把 ip 解析成 geoip 子对象再入库，
        # 应用层只需传 IP，地理位置由 ES 补全
        doc.save(pipeline="geoip")


# ------------------------------------------------------------
# —— 文章索引：站内搜索真正的数据来源 ——
# ------------------------------------------------------------

# 【ArticleDocument】—— 一篇文章在 ES 里的样子，字段就是搜索页能取到、能用来筛选的东西
# 为什么要单独建索引而不用直接查 MySQL：ES 会对 Text 字段建倒排索引，
# 中文切词后能按“词”命中；MySQL 的 LIKE '%关键词%' 既慢又只能整串匹配
class ArticleDocument(Document):
    # 标题 / 正文的两个分析器分工不同：
    #   analyzer（写入索引时用）ik_max_word：切到最细（“中国社会科学院”→“中国/社会/科学院”…），
    #     索引里词条多，召回率高；
    #   search_analyzer（查询时用）ik_smart：查询串只粗粒度切一次，减少切太碎造成的误匹配。
    # 这是 IK 中文分词器的经典搭配
    # 正文全文
    body = Text(analyzer='ik_max_word', search_analyzer='ik_smart')
    # 标题全文，权重高、最常被搜
    title = Text(analyzer='ik_max_word', search_analyzer='ik_smart')
    # 作者只取“昵称 + id”：列表页要显示昵称，点击时要按 id 跳作者归档页；
    # 用 Object(properties=...) 嵌套而非拆成 author_nickname / author_id 两个平铺字段，
    # 语义上更清楚，也跟 Django 里 author 是一个对象对得上
    author = Object(properties={
        'nickname': Text(analyzer='ik_max_word', search_analyzer='ik_smart'),
        'id': Integer()
    })
    # 分类同理：name 用于显示与搜索，id 用于拼 /category/<id> 这类链接
    category = Object(properties={
        'name': Text(analyzer='ik_max_word', search_analyzer='ik_smart'),
        'id': Integer()
    })
    # 标签是一对多关系，存成“对象数组”：一条文档里带一个 tags 列表，每个元素是 {name, id}
    tags = Object(properties={
        'name': Text(analyzer='ik_max_word', search_analyzer='ik_smart'),
        'id': Integer()
    })

    # 发布时间；搜索页按时间排序 / 过滤用
    pub_time = Date()
    # 文章状态：p=已发布、d=草稿（与 models.Article 里 status 的取值一致）
    status = Text()
    # 评论开关状态（o=开放、c=关闭），搜索结果据此决定是否显示“去评论”
    comment_status = Text()
    # 文章类型（a=文章、p=页面 等，与模型保持一致）
    type = Text()
    # 阅读量，可用于“按热度排序”
    views = Integer()
    # 置顶 / 排序权重，数字越小越靠前，与模型的 article_order 对应
    article_order = Integer()

    class Index:
        # 文章索引名；djangoblog/elasticsearch_backend.py 里搜的就是这个索引
        name = 'blog'
        settings = {
            # 单机开发：1 个分片够用
            "number_of_shards": 1,
            # 单节点无法分配副本，设 0 避免索引一直是 yellow
            "number_of_replicas": 0
        }


# 【ArticleDocumentManager】—— 文章索引的生命周期管理：建、删、转换、全量重建、批量更新
# 被谁用：管理命令 build_index（删掉后全量重建）、blog/apps.py 启动时检查并补建空索引、
#         djangoblog/elasticsearch_backend.py 在搜索 / 重建索引时也持有一个本类实例
class ArticleDocumentManager():

    # 【__init__】—— 实例化即确保 blog 索引存在，调用方不必再单独记得建索引
    def __init__(self):
        self.create_index()

    # 【create_index】—— 按 ArticleDocument 声明的字段与 settings 创建 blog 索引
    # 说明：init() 是 elasticsearch_dsl 的“不存在才创建”，重复调用不会报错
    def create_index(self):
        ArticleDocument.init()

    # 【delete_index】—— 删除 blog 索引（重建前先清空，避免旧的字段映射残留影响新结构）
    # 说明：索引本来就不存在时忽略异常，让“先删后建”的流程可以反复执行
    def delete_index(self):
        from elasticsearch import Elasticsearch
        es = Elasticsearch(**es_params)
        try:
            es.indices.delete(index='blog')
        except elasticsearch.exceptions.NotFoundError:
            pass

    # 【convert_to_doc】—— 把 Django 的 Article 模型对象（们）转换成 ArticleDocument（们）
    # 参数：articles（QuerySet | 可迭代对象）：要转换的文章集合；
    #       QuerySet 是 Django 的惰性查询结果集，只有真正遍历时才发 SQL
    # 返回：list[ArticleDocument]：还没写进 ES 的文档对象，之后统一 save()
    # 说明：这里是“关系型数据 → 文档型数据”的翻译层，字典的键必须和上面 ArticleDocument 的字段一一对应
    def convert_to_doc(self, articles):
        return [
            ArticleDocument(
                meta={
                    # 用文章主键当 ES 主键：重建/更新会覆盖同一文档，不会写出重复数据
                    'id': article.id},
                body=article.body,
                title=article.title,
                author={
                    'nickname': article.author.username,
                    'id': article.author.id},
                category={
                    'name': article.category.name,
                    'id': article.category.id},
                # 多对多关系要 .all() 才能拿到全部标签；用列表推导把每个 Tag 行转成 {name, id}
                tags=[
                    {
                        'name': t.name,
                        'id': t.id} for t in article.tags.all()],
                pub_time=article.pub_time,
                status=article.status,
                comment_status=article.comment_status,
                type=article.type,
                views=article.views,
                article_order=article.article_order) for article in articles]

    # 【rebuild】—— 全量重建文章索引（首次建库、索引损坏或字段结构调整后调用）
    # 参数：articles（QuerySet | None）：只重建指定的一批文章；不传就取全部文章
    # 返回：无
    def rebuild(self, articles=None):
        # 再确认一次索引存在，防止索引被手工删掉后 rebuild 直接失败
        ArticleDocument.init()
        # 惰性 QuerySet，遍历时才真正查库
        articles = articles if articles else Article.objects.all()
        docs = self.convert_to_doc(articles)
        for doc in docs:
            # 逐条 save()：数据量很大时可以换成 bulk 批量写入，这里为了逻辑清晰一条条写
            doc.save()

    # 【update_docs】—— 批量保存若干文档对象（增量更新：主键相同即覆盖旧文档）
    # 参数：docs（list[ArticleDocument]）：一般来自 convert_to_doc
    # 返回：无
    def update_docs(self, docs):
        for doc in docs:
            doc.save()
