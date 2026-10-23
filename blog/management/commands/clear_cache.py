# ============================================================
# blog/management/commands/clear_cache.py —— 手动清空全站缓存的 management command
# 作用：项目把站点配置、文章列表、侧边栏等热点数据放在 Django 缓存里，本命令调用
#       djangoblog.utils.cache.clear() 把整块缓存直接清掉，改完模板/配置或线上出现
#       脏数据后跑一次，读者就能立刻看到最新内容，而不用等缓存自然过期。
# 本文件包含：
#   Command —— 继承 BaseCommand 的命令类，handle() 是命令真正的执行入口
# 注释人：翟旌超（软件工程 3 班 2415304340，#zjc）
# 说明：本次任务只添加中文注释，没有改动任何一行原有代码逻辑
# ============================================================

# —— Django 框架 / 项目内模块 ——
# BaseCommand：所有 management command 的基类，负责解析命令行参数、提供 self.stdout
# cache：djangoblog.utils 里封装的缓存对象，底层就是 Django cache framework，支持 clear()
from django.core.management.base import BaseCommand

from djangoblog.utils import cache


# 【Command】—— 清空整个缓存后端
# 用法：python manage.py clear_cache
# 说明：management command 就是放在 app/management/commands/ 目录下、用
#       python manage.py <命令名> 调用的自定义命令；Django 约定类名必须叫 Command，
#       它只负责解析参数，真正的业务逻辑写在 handle() 里。
class Command(BaseCommand):
    # help 文案会出现在 python manage.py help 的命令清单里
    help = 'clear the whole cache'

    # 【handle】—— 命令执行入口
    # 参数：*args / **options：命令行参数（本命令不需要任何参数，保留签名便于扩展）
    # 返回：None；执行结果通过 self.stdout 打印到控制台
    def handle(self, *args, **options):
        # cache.clear() 清的是 Django 默认缓存区里的全部键：站点配置（get_blog_setting）、
        # 文章/标签/分类列表等被缓存的查询结果会一起失效，下次访问会重新查库并回填缓存。
        # 之所以要手动清：缓存没有统一的失效钩子，改完模板、站点配置或直接动了数据库后，
        # 页面仍会继续读旧缓存，线上表现就是“改了没生效”。
        cache.clear()
        # 提示清理成功；style.SUCCESS 给这行输出套上绿色，方便在终端里一眼看到
        self.stdout.write(self.style.SUCCESS('Cleared cache\n'))
