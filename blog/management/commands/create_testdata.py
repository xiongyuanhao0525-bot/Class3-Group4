# ============================================================
# blog/management/commands/create_testdata.py —— 一键灌入博客测试数据的 management command
# 作用：开发、联调、演示时用 python manage.py create_testdata 批量造出「1 个测试用户 +
#       父子两级分类 + 1 个公共标签 + 19 篇文章」的最小数据集，让首页、分类页、标签页、
#       文章详情页都有内容。所有记录都用 get_or_create 写入，重复执行不会产生重复数据。
# 本文件包含：
#   Command —— 命令类；handle() 依次创建用户、分类、标签、文章，最后清一次缓存
# 注释人：翟旌超（软件工程 3 班 2415304340，#zjc）
# 说明：本次任务只添加中文注释，没有改动任何一行原有代码逻辑
# ============================================================

# —— Django 框架 ——
# get_user_model()：取项目实际使用的用户模型（本项目在默认 User 基础上做过扩展），不能写死 User
# make_password()：按 Django 的密码哈希规则处理明文密码，直接存明文会被认证后端拒绝
# BaseCommand：所有 management command 的基类，负责解析命令行参数、提供 self.stdout 输出
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand

# —— 项目内模块 ——
# Article / Tag / Category：博客的三张核心业务表，测试数据就是往这三张表里写
from blog.models import Article, Tag, Category


# 【Command】—— 生成博客测试数据
# 用法：python manage.py create_testdata
# 说明：management command 是 Django 的命令行脚本机制，放在 app/management/commands/ 下，
#       文件名即命令名（这里是 create_testdata）；Django 启动时自动发现，类名必须叫 Command，
#       解析完命令行参数后就调用 handle()，业务逻辑全写在这个方法里。
class Command(BaseCommand):
    # help 会显示在 python manage.py help 的命令列表里
    help = 'create test datas'

    # 【handle】—— 命令执行入口：按「用户 → 父分类 → 子分类 → 标签 → 文章」的顺序造数据
    # 参数：*args / **options：命令行参数（本命令不需要，保留签名方便以后扩展）
    # 返回：None；结果通过 self.stdout 打印
    # 说明：外键有先后依赖，所以顺序不能乱；全部用 get_or_create 写入，重复执行不会撞唯一约束
    def handle(self, *args, **options):
        # 测试用户：邮箱、用户名固定，方便直接登录；get_or_create 返回 (对象, 是否新建)，
        # 取 [0] 只用对象本身，已存在时直接复用
        user = get_user_model().objects.get_or_create(
            email='test@test.com', username='测试用户', password=make_password('test!q@w#eTYU'))[0]

        # 先建父分类：parent_category=None 表示它是顶级类目（后台“父类目”下拉里为空）
        pcategory = Category.objects.get_or_create(
            name='我是父类目', parent_category=None)[0]

        # 再建子分类，parent_category 指向刚建的父分类，凑成两级类目树，
        # 用来验证分类页的层级展示和面包屑导航
        category = Category.objects.get_or_create(
            name='子类目', parent_category=pcategory)[0]

        # 兜底保存一次：确保分类（含 parent_category 外键）真正落库后再往下引用
        category.save()
        # 公共标签：下面 19 篇文章都会挂上它，用来演示「一个标签对应多篇文章」的标签列表页
        basetag = Tag()
        basetag.name = "标签"
        basetag.save()
        # 循环造 19 篇（1~19）：标题、正文用序号区分，作者统一指向测试用户
        for i in range(1, 20):
            # 每篇文章都挂在子分类下；get_or_create 以这几列作为“这条记录是否已存在”的判断条件
            article = Article.objects.get_or_create(
                category=category,
                title='nice title ' + str(i),
                body='nice content ' + str(i),
                author=user)[0]
            # 每篇再单独建一个专属标签，和上面的公共标签一起挂到文章上
            tag = Tag()
            tag.name = "标签" + str(i)
            tag.save()
            # 多对多：add() 只是往中间表插一行，重复 add 不会产生重复关联，重跑安全
            article.tags.add(tag)
            article.tags.add(basetag)
            article.save()

        # 放到函数内导入：只有真正执行命令时才需要缓存工具，同时也避开模块导入期的循环依赖
        from djangoblog.utils import cache
        # 数据变了，之前缓存的文章列表、分类树、标签云都该失效，否则页面还显示旧内容
        cache.clear()
        # 打印成功提示；style.SUCCESS 给这行输出上绿色，便于在终端里确认执行结果
        self.stdout.write(self.style.SUCCESS('created test datas \n'))
