# ============================================================
# blog/management/commands/build_search_words.py —— 导出站内专有词（标签名/分类名）的 management command
# 作用：站内搜索用 Whoosh + jieba 的 ChineseAnalyzer 做中文分词，而 jieba 默认词典里没有博客
#       自己的标签名、分类名，搜索时这些词很容易被切碎导致搜不到。本命令把所有标签名、
#       分类名去重后按行打印，重定向保存即可当作中文分词的用户词表：
#       python manage.py build_search_words > words.txt
# 本文件包含：
#   Command —— 命令类；handle() 收集 Tag / Category 的名称，一行一个写到标准输出
# 注释人：翟旌超（软件工程 3 班 2415304340，#zjc）
# 说明：本次任务只添加中文注释，没有改动任何一行原有代码逻辑
# ============================================================

# —— Django 框架 ——
# BaseCommand：management command 的基类，python manage.py build_search_words 执行它的 handle()
from django.core.management.base import BaseCommand

# —— 项目内模块 ——
# Tag / Category：博客的标签表与分类表，它们的 name 就是站内特有的词汇，正是要导出的词表来源
from blog.models import Tag, Category


# 【Command】—— 生成搜索用的中文词表
# 说明：management command 是 Django 的命令行脚本机制，文件放在 app/management/commands/ 下，
#       文件名即命令名；Django 启动时自动注册，执行时调用 Command.handle() 作为入口。
# TODO 参数化
class Command(BaseCommand):
    # help 会显示在 python manage.py help 里
    help = 'build search words'

    # 【handle】—— 命令执行入口：输出「标签名 + 分类名」词表
    # 参数：*args / **options：命令行参数（本命令不需要）
    # 返回：None；词表用 print 直接写标准输出，方便 shell 重定向保存成 txt
    def handle(self, *args, **options):
        # 用 set 去重：同一个词可能既是标签又是分类，或被多篇文章共用，
        # 重复词交给分词器只会变成噪声
        datas = set([t.name for t in Tag.objects.all()] +
                    [t.name for t in Category.objects.all()])
        # 一行一个词输出；重定向成文件后可直接给 jieba.load_userdict() 或搜索建议词库使用
        print('\n'.join(datas))
