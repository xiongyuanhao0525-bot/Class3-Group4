# ============================================================
# blog/management/commands/ping_baidu.py —— 向百度站长平台主动推送站点 URL 的 management command
# 作用：博客发文后想让它尽快被百度收录，可以用 python manage.py ping_baidu all|article|tag|category
#       把文章、标签、分类页面的完整 URL 一次性提交给百度，缩短百度蜘蛛发现新内容的周期。
#       推送只是“告知”搜索引擎，成功与否都不影响博客自身运行。
# 本文件包含：
#   Command.add_arguments() —— 声明 data_type 位置参数，限定只能取 all/article/tag/category
#   Command.get_full_url() —— 把站内相对路径拼成 https://域名/path 的绝对地址
#   Command.handle() —— 按类型收集 URL 列表，交给 SpiderNotify.baidu_notify 批量推送
# 注释人：翟旌超（软件工程 3 班 2415304340，#zjc）
# 说明：本次任务只添加中文注释，没有改动任何一行原有代码逻辑
# ============================================================

# —— Django 框架 ——
# BaseCommand：management command 的基类；python manage.py <命令名> 最终调用的就是 Command.handle()
from django.core.management.base import BaseCommand

# —— 项目内模块 ——
# SpiderNotify：对百度“普通收录-主动推送”HTTP 接口的封装，负责拼请求、发请求、判断返回码
# get_current_site()：取当前站点对象，用来拼 URL 的域名部分
# Article / Tag / Category：要推送的三类页面，分别对应文章详情、标签列表、分类列表
from djangoblog.spider_notify import SpiderNotify
from djangoblog.utils import get_current_site
from blog.models import Article, Tag, Category

# 当前站点域名（形如 xxx.com）：模块加载时取一次给 get_full_url() 复用，
# 避免每次拼 URL 都去查一遍站点配置（SITE 配置很少变，没必要反复读库）
site = get_current_site().domain


# 【Command】—— 主动把站点 URL 推送（ping）给百度
# 用法：python manage.py ping_baidu all
# 说明：management command 是 Django 的命令行脚本机制，放在 app/management/commands/ 下，
#       文件名就是命令名（这里是 ping_baidu）；类名必须叫 Command，Django 解析完参数后
#       调用 handle()，所以“推送”这件事的真正入口是 handle。
class Command(BaseCommand):
    # help 会显示在 python manage.py help 的命令说明里
    help = 'notify baidu url'

    # 【add_arguments】—— 声明命令行参数
    # 参数：parser（argparse.ArgumentParser）：Django 传进来的参数解析器
    # 返回：None
    # 说明：choices 把 data_type 限定在四个取值内，用户输错时 Django 直接报错并列出可选值，
    #       省掉 handle() 里再做一遍参数校验
    def add_arguments(self, parser):
        parser.add_argument(
            'data_type',
            type=str,
            choices=[
                'all',
                'article',
                'tag',
                'category'],
            help='article : all article,tag : all tag,category: all category,all: All of these')

    # 【get_full_url】—— 把相对路径补成带域名的绝对 URL
    # 参数：path（str）：站内相对路径，如 /tag/1
    # 返回：str：https://<当前域名><path>；百度主动推送只接受带协议的完整地址
    # 说明：文章模型自带的 get_full_url() 会直接给绝对地址，而标签/分类只有 get_absolute_url()
    #       给的相对路径，所以在命令里统一用这个方法兜底拼接
    def get_full_url(self, path):
        url = "https://{site}{path}".format(site=site, path=path)
        return url

    # 【handle】—— 命令执行入口：收集 URL 并批量推送
    # 参数：options['data_type']（str）：all / article / tag / category 之一
    # 返回：None；推送结果通过 self.stdout 打印
    # 说明：一次 handle 只发一次批量推送请求，百度接口按条数算配额，批量提交更省配额
    def handle(self, *args, **options):
        type = options['data_type']
        self.stdout.write('start get %s' % type)

        # 先把要推送的 URL 全部收进列表，最后统一提交，避免边查库边发请求
        urls = []
        # 文章只推已发布的（status='p' 即 published），草稿、私密文章不该被搜索引擎收录
        if type == 'article' or type == 'all':
            for article in Article.objects.filter(status='p'):
                urls.append(article.get_full_url())
        # 标签页：get_absolute_url() 给的是站内相对路径，需要再补域名
        if type == 'tag' or type == 'all':
            for tag in Tag.objects.all():
                url = tag.get_absolute_url()
                urls.append(self.get_full_url(url))
        # 分类页同理，分类模型也只提供相对路径
        if type == 'category' or type == 'all':
            for category in Category.objects.all():
                url = category.get_absolute_url()
                urls.append(self.get_full_url(url))

        self.stdout.write(
            self.style.SUCCESS(
                'start notify %d urls' %
                len(urls)))
        # 真正向百度站长平台发 HTTP 请求：SpiderNotify.baidu_notify 内部把 URL 用换行拼成一串 POST
        # 到 settings.BAIDU_NOTIFY_URL，并把接口返回的文本写进日志（成功与否看日志里的返回内容）。
        # 它用 try/except 包住整个请求：网络异常、token 失效、配额超限都只记日志、不抛出，
        # 所以推送失败既不会中断本命令，也不会影响博客对外服务
        SpiderNotify.baidu_notify(urls)
        self.stdout.write(self.style.SUCCESS('finish notify'))
