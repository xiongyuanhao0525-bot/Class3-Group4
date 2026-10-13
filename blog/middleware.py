# -*- coding: utf-8 -*-
"""
博客自定义中间件模块（标注人：熊圆好）
作用：在 Django 内置中间件链的最后追加 OnlineMiddleware，
     统计每个页面的渲染耗时，供性能分析与前端展示使用。
"""
import logging
import time

from ipware import get_client_ip
from user_agents import parse

from blog.documents import ELASTICSEARCH_ENABLED, ElaspedTimeDocumentManager

logger = logging.getLogger(__name__)


class OnlineMiddleware(object):
    """页面耗时统计中间件。

    处理流程：记录开始时间 -> 交给下游视图生成响应 -> 计算耗时；
    若开启了 Elasticsearch，则把本次请求的 URL、耗时、UA、IP 写入
    耗时索引（ElaspedTimeDocumentManager），用于后续统计报表；
    同时把响应体中的占位符 <!!LOAD_TIMES!!> 替换为真实耗时（秒），
    供模板直接显示"本页加载用时"。流式响应（文件下载等）跳过统计。
    """

    def __init__(self, get_response=None):
        # get_response 为下游处理链（下一个中间件或视图）
        self.get_response = get_response
        super().__init__()

    def __call__(self, request):
        ''' page render time '''
        start_time = time.time()
        response = self.get_response(request)
        # 解析客户端真实 IP（兼容反向代理）与 User-Agent
        http_user_agent = request.META.get('HTTP_USER_AGENT', '')
        ip, _ = get_client_ip(request)
        user_agent = parse(http_user_agent)
        if not response.streaming:
            try:
                cast_time = time.time() - start_time
                if ELASTICSEARCH_ENABLED:
                    # 耗时（毫秒）连同访问信息写入 ES 索引
                    time_taken = round((cast_time) * 1000, 2)
                    url = request.path
                    from django.utils import timezone
                    ElaspedTimeDocumentManager.create(
                        url=url,
                        time_taken=time_taken,
                        log_datetime=timezone.now(),
                        useragent=user_agent,
                        ip=ip)
                # 用真实秒数（保留 5 个字符）替换模板中的占位符
                response.content = response.content.replace(
                    b'<!!LOAD_TIMES!!>', str.encode(str(cast_time)[:5]))
            except Exception as e:
                # 统计失败不影响正常响应返回
                logger.error("Error OnlineMiddleware: %s" % e)

        return response
