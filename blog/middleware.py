# ============================================================
# blog/middleware.py —— 自定义中间件：统计每个请求的处理耗时
# 作用：Django 每处理完一个请求，这里量一下这个页面「从进来到出去」花了多久；
#       把耗时写进 Elasticsearch（ES，一种搜索引擎式的数据库）做访问统计，
#       同时把 HTML 里的 <!!LOAD_TIMES!!> 占位符替换成真实耗时数字。
# 本文件包含：OnlineMiddleware 类（__init__ 装配、__call__ 请求/响应两阶段）
# 注释人：翟旌超（软件工程 3 班 2415304340，#zjc）
# 说明：本次任务只添加中文注释，没有改动任何一行原有代码逻辑
# ============================================================
# —— 中间件的概念（第一次读请先看这段）——
# 中间件（middleware）：Django 在请求进入视图之前、响应离开视图之后依次穿过的
# 一串可插拔组件，每层都能拿到 request 和 response，像流水线工位一样各管一段；
# 本文件在 djangoblog/settings.py 的 MIDDLEWARE 里以
# 'blog.middleware.OnlineMiddleware' 注册，并且排在列表最后一项。
# 请求阶段按 MIDDLEWARE 列表从上往下穿，响应阶段则从下往上返回，
# 所以它是"离视图最近"的一层：视图刚产生响应，它马上就能拿到。
# —— Python 标准库 ——
# logging：按模块名打日志，出错时能看出是哪个文件报的；
# time：取时间戳，用两次 time.time() 的差值算请求耗时
import logging
import time

# —— 第三方库 ——
# ipware：从请求头里稳妥地取客户端真实 IP（会参考 X-Forwarded-For 等代理头）；
# user_agents：把浏览器 UA 字符串解析成 浏览器 / 系统 / 设备 三个结构化对象
from ipware import get_client_ip
from user_agents import parse

# —— 本项目自己的模块 ——
# ELASTICSEARCH_ENABLED：布尔开关，只有 settings 里配了 ES 才是 True；
# ElaspedTimeDocumentManager：把一条访问记录写进 ES 的管理类（实现见 blog/documents.py）
from blog.documents import ELASTICSEARCH_ENABLED, ElaspedTimeDocumentManager

# 本模块的日志记录器：中间件里出的问题都记到这里，不抛给用户
logger = logging.getLogger(__name__)


# ------------------------------------------------------------
# 【OnlineMiddleware】—— 量出每个页面的渲染耗时，写 ES 并回填到页面里
# 说明：新版 Django 的中间件就是一个"可调用对象"——服务启动时实例化一次并常驻，
#       之后每个请求调用一次 __call__；这里没用老的 process_request/process_response
#       接口，而是在 __call__ 里手写"请求阶段 + 响应阶段"，读起来更直观。
# 注意：实例被所有请求共用，所以"每个请求各自的数据"只能放在 __call__ 的局部变量里。
# ------------------------------------------------------------
class OnlineMiddleware(object):
    # 【__init__】—— 装配阶段，只在服务启动时执行一次
    # 参数：get_response（callable）：Django 注入的"下一层"处理函数，最终会调到视图
    # 返回：无
    # 说明：把下一层存到 self 上，__call__ 里才能继续往下调；这就是"中间件链"的串法。
    #       get_response 给默认值 None，是为了方便脱离 Django 手工 new 出来做测试。
    def __init__(self, get_response=None):
        self.get_response = get_response
        super().__init__()

    # 【__call__】—— 每个请求都会调用一次，一次调用覆盖请求 + 响应两个阶段
    # 参数：request（WSGIRequest）：本次请求对象
    # 返回：response（HttpResponse）：最终交给浏览器的响应
    # 说明：self.get_response(request) 这一句之前是请求阶段（还没有响应），
    #       之后是响应阶段（响应已生成，可以读改 response.content）。
    def __call__(self, request):
        ''' page render time '''
        # 请求阶段：先记下进入本中间件的时刻，最后用两次时间的差值算总耗时
        start_time = time.time()
        # 把请求交给下一层（一路走到视图），拿回已经渲染好的响应；
        # 这一行本身就是"页面渲染"的主体，所以它必须夹在两次计时之间
        response = self.get_response(request)
        # 响应阶段开始：从请求头里取 UA 字符串（浏览器、操作系统等信息），
        # request.META 的键名规则是 "HTTP_" + 头部名大写、横线换下划线
        http_user_agent = request.META.get('HTTP_USER_AGENT', '')
        # 取客户端真实 IP（经过代理时也能取到）；第二个返回值表示 IP 是否可直接路由，这里不用
        ip, _ = get_client_ip(request)
        # 解析 UA：得到 browser / os / device 三个对象，写 ES 时会被拆成字段
        user_agent = parse(http_user_agent)
        # 流式响应（StreamingHttpResponse：内容边算边发）没有完整的 content，
        # 既没法做字节替换，也不适合按"整页"计时，所以直接跳过
        if not response.streaming:
            try:
                # 结束时刻减开始时刻 = 本次请求总耗时（单位：秒）
                cast_time = time.time() - start_time
                # 只有配置了 Elasticsearch 才写访问记录；没配就只做下面的耗时回填
                if ELASTICSEARCH_ENABLED:
                    # 统计口径统一成毫秒并保留 2 位小数，方便在 ES 里聚合、排序
                    time_taken = round((cast_time) * 1000, 2)
                    # 只记 path 不记查询串，避免同一页面因参数不同被拆成一堆记录
                    url = request.path
                    # 局部导入 timezone：只在真要写 ES 时才导入，少一点启动开销
                    from django.utils import timezone
                    # 写一条访问记录：内部先把 UA 拍平成字段，再走 geoip 管道解析 IP 归属地
                    ElaspedTimeDocumentManager.create(
                        url=url,
                        time_taken=time_taken,
                        log_datetime=timezone.now(),
                        useragent=user_agent,
                        ip=ip)
                # 把页面里预留的 <!!LOAD_TIMES!!> 占位符换成刚算出的耗时（页面没写这个占位符时，
                # replace 找不到目标会原样返回，不会报错）；响应内容是字节串，所以匹配串用 b'...' 前缀，替换值也要 encode 成字节，
                # str(cast_time)[:5] 是"截取前 5 个字符"（如 0.012），是截断而非四舍五入
                response.content = response.content.replace(
                    b'<!!LOAD_TIMES!!>', str.encode(str(cast_time)[:5]))
            # 兜底：统计或替换出错绝不能影响正常访问，只记日志，页面照常返回
            except Exception as e:
                logger.error("Error OnlineMiddleware: %s" % e)

        # 必须返回响应，否则浏览器拿不到页面（这是 __call__ 的唯一出口）
        return response
