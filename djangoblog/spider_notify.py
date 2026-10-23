# xyh：搜索引擎主动推送 —— 新文章发布后把链接直接 POST 给百度收录接口，
# xyh：比被动等 sitemap.xml 抓取更快；由 blog_signals 的文章创建/更新钩子触发。
import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class SpiderNotify():   # xyh：静态方法集合形式的轻量工具类（无实例状态）
    @staticmethod
    def baidu_notify(urls):
        try:
            data = '\n'.join(urls)   # xyh：多条 URL 以换行拼接，符合批量推送协议
            result = requests.post(settings.BAIDU_NOTIFY_URL, data=data)   # xyh：推送到配置中的百度主动推送地址
            logger.info(result.text)   # xyh：记录百度返回（含成功条数/配额信息）
        except Exception as e:
            logger.error(e)   # xyh：推送失败仅记日志，不影响文章发布主流程

    @staticmethod
    def notify(url):
        SpiderNotify.baidu_notify(url)   # xyh：对外统一入口，当前仅转发百度通道（预留多渠道扩展点）
