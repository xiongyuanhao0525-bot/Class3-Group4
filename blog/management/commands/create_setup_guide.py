# ============================================================
# blog/management/commands/create_setup_guide.py —— 一键“种”出一篇建站教程文章的管理命令
# 作用：给刚部署好的空站点灌入一篇已发布的 Markdown 教程（DjangoBlog 从零搭建指南），
#       顺带把“技术教程”分类和 5 个技术标签建好，让首页/分类页立刻有内容可看；
#       属于“初始化演示数据”脚本，不参与 HTTP 请求，只由运维手动执行一次。
# 本文件包含：Command 类（management command 本体）、handle 方法（唯一入口，
#             流程：查作者 → 建分类 → 建标签 → 准备标题正文 → get_or_create 文章
#             → 新建立即挂标签 / 已存在则回写正文 → 清缓存）
# 注释人：翟旌超（软件工程 3 班 2415304340，#zjc）
# 说明：本次任务只添加中文注释，没有改动任何一行原有代码逻辑
# ============================================================
#
# 【先搞懂：什么是 management command（Django 管理命令）】
# 一句话：它就是一个放在 <应用>/management/commands/ 目录下的一次性脚本，
#        用 `python manage.py 文件名` 来跑；本文件的文件名是 create_setup_guide.py，
#        所以执行 `python manage.py create_setup_guide` 跑的就是这里。
# 1) 命令名从哪来：Django 启动时会把每个已安装 app 的 management/commands/ 目录扫一遍，
#    把里面的每个 .py 模块导入一次；模块名去掉 .py 就是命令名。因此该目录必须有 __init__.py，
#    文件名也不能和系统命令重名（否则会盖住 Django 自带的同名命令）。
# 2) 类名为什么必须是 Command：扫描到模块后 Django 只找名为 Command 的类，
#    实例化后执行 run_from_argv() → 最终调用 handle()。类名写错就等于没有这个命令。
# 3) handle() 是入口：真正的业务逻辑全写在 handle 里；想给命令加参数就实现
#    add_arguments(self, parser)，用 parser.add_argument('--force', action='store_true')
#    这类写法声明，参数解析结果会以 options['force'] 的形式传进 handle。
#    本文件没有实现 add_arguments，所以它不带任何命令行开关，直接裸跑即可；
#    多写的参数会被 Django 解析进 *args 后忽略掉。
# 4) 退出码约定：正常跑完返回 None 就是 0；要表达失败应抛 CommandError，
#    Django 会打红字并返回非 0，方便 CI/脚本判断。
# 5) self.stdout.write(...) 是官方推荐的输出方式：它比 print 更好，因为输出目标可被
#    调用方替换、能被测试捕获、还能套 self.style 上色；注意它默认不换行，
#    需要换行时要自己传 ending='\n'。本文件统一用 self.style.SUCCESS 打绿色成功提示。
#
# 【这个命令到底生成/写入什么】
# - 不写文件、不建目录、也没有文件路径要拼：所有数据都经 ORM 写进数据库。
#   所以本文件不需要 open(...)，也就没有 encoding='utf-8' 显式指定 —— 中文字符集
#   由数据库连接层决定（settings 里 MySQL 的 OPTIONS={'charset': 'utf8mb4'}）；
#   而 Python 3 源码文件默认就是 UTF-8，故也不需要 # -*- coding: utf-8 -*- 声明。
# - 读的数据：User（挑一个超级管理员当作者）、Category、Tag（用 get_or_create 拿到或建出）、
#   Article（按 title 查，已存在就不重复创建）。
# - 写的数据：1 个分类、最多 5 个标签、1 篇文章（Markdown 正文即下面的 body 字符串），
#   以及文章与标签的多对多关联；最后清一次缓存，避免旧的页面缓存继续生效。
#
# —— Django 框架 ——
# get_user_model()：按 settings.AUTH_USER_MODEL 取“当前生效的用户模型类”，
# 不直接 import User，换自定义用户模型或避免循环导入时才不会出问题
from django.contrib.auth import get_user_model
# BaseCommand：所有管理命令的基类，Django 靠它把命令挂到 manage.py 上，
# 它提供了 self.stdout / self.style 这些给命令用的工具
from django.core.management.base import BaseCommand

# —— 项目内模块 ——
# 命令本质就是“用 ORM 批量造数据”，所以直接复用 blog 应用的数据模型：
# Article（文章，正文用 Markdown 字段）、Tag（标签，多对多）、Category（分类，外键）
from blog.models import Article, Tag, Category


# 【Command】—— 管理命令的壳子，只负责“挂名字 + 提供输出工具”，业务全在 handle 里
# 说明：Django 扫到本模块后只认这个名字的类，改名命令就消失；继承 BaseCommand
# 才能拿到 self.stdout（输出）、self.style（上色）、self.handle 的调用链
class Command(BaseCommand):
    # help：命令的一句话说明，`python manage.py help create_setup_guide` 会原样打印，
    # 也是 `python manage.py` 列表里该命令后面的描述；因此要写清用途而不是写实现细节
    help = 'add a technical tutorial article about installing DjangoBlog'

    # 【handle】—— 命令的唯一入口，`python manage.py create_setup_guide` 时被 Django 调用
    # 参数：*args / **options 由命令行解析结果交进来；本命令没实现 add_arguments，
    #       所以 options 里只有 Django 固定的 verbosity/settings 等，业务上用不到，直接忽略
    # 返回：None —— 管理命令不向调用方返回数据，结果只通过 self.stdout 打印给人看；
    #       真要表示失败应抛 CommandError（Django 会转成非 0 退出码）
    # 说明：整体是“幂等”设计 —— 反复执行不会造出重复的分类/标签/文章，重启脚本很安全
    def handle(self, *args, **options):
        # 作者必须是“人”而不是空值：Article.author 是外键且不允许空，
        # 所以优先挑一个超级管理员当这篇文章的作者（后台里最容易认出来的那个账号）
        user = get_user_model().objects.filter(is_superuser=True).first()
        # 兜底：站点还没建 superuser 时退化为“任意第一个用户”，
        # 只为让命令不至于因为没作者而崩；一个用户都没有时这里仍会拿到 None，随后入库会报错
        if not user:
            user = get_user_model().objects.first()

        # get_or_create 返回 (对象, 是否新建) 的二元组：分类按 name 查，
        # 没有就建一个 —— 所以重复执行不会出现第二个“技术教程”分类；
        # 这里用 _ 接住“是否新建”，因为脚本不关心它是新建还是复用
        category, _ = Category.objects.get_or_create(name='技术教程')

        # 固定一份标签清单，既用于下面建标签，也用于后面给文章挂多对多关系
        tag_names = ['Django', 'Python', 'VSCode', 'Git', 'GitHub']
        # 用 dict 做“标签名 → Tag 对象”的缓存，后面 article.tags.add() 时就不用再查库
        tags = {}
        # 逐个 get_or_create：标签是弱实体，先保证它存在，再谈关联；
        # 顺序遍历保证键值对齐全，重复执行同一份清单同样得到同样的 5 个标签
        for name in tag_names:
            tags[name], _ = Tag.objects.get_or_create(name=name)

        # 标题：Article.title 在模型上是 unique 的，因此它天然成为“这篇文章”的业务主键，
        # 下面 get_or_create 靠它判断是首次创建还是已存在
        title = '从零搭建 DjangoBlog：VSCode + Git + GitHub 完整指南'
        # 正文是一整段三引号多行字符串（Markdown 原文，原样存库，渲染时才转 HTML）：
        # 三引号让换行、引号、反引号代码块都不用转义，写长文最省事；
        # 注意内容是“数据”不是代码，所以里面出现的中文、# 标题、表格都只是文本
        body = '''# 从零搭建 DjangoBlog：VSCode + Git + GitHub 完整指南

本文记录从零开始搭建 DjangoBlog 博客系统的完整流程，涵盖开发环境准备、Git 配置、从 GitHub 克隆仓库、依赖安装、数据库配置以及项目启动。照着一步步做，就能在自己的电脑上跑起这套博客。

## 一、环境要求

开始之前，请确保电脑上已经安装好以下软件：

| 软件 | 版本要求 | 作用 |
|---|---|---|
| Python | 3.10 及以上 | 运行 Django 后端 |
| MySQL / MariaDB | 5.7 及以上 | 数据库 |
| Node.js | 18 及以上 | 构建前端资源 |
| Git | 任意较新版本 | 版本控制、克隆仓库 |

在终端里可以用下面的命令确认版本：

```bash
python --version
node --version
npm --version
git --version
```

## 二、安装并配置 VSCode

1. 到官网下载安装 [Visual Studio Code](https://code.visualstudio.com/)。
2. 装好后，安装几个对 Python 开发很有用的扩展：
   - **Python**（微软官方）
   - **Pylance**（代码智能提示）
   - **GitLens**（Git 可视化）
   - **Django**（模板语法高亮）

安装扩展的方法：点击左侧活动栏的「扩展」图标（或按 `Ctrl + Shift + X`），搜索扩展名后点「安装」。

## 三、配置 Git

首次使用 Git 需要设置用户名和邮箱，这些信息会记录在每次提交里：

```bash
git config --global user.name "你的名字"
git config --global user.email "你的邮箱"
```

如果要从 GitHub 用 SSH 方式克隆（推荐），先生成 SSH 密钥：

```bash
ssh-keygen -t ed25519 -C "你的邮箱"
```

一路回车即可。然后查看公钥内容：

```bash
cat ~/.ssh/id_ed25519.pub
```

把输出的内容复制到 GitHub 的 **Settings → SSH and GPG keys → New SSH key** 里保存。

## 四、从 GitHub 克隆仓库

在终端里进入你存放项目的目录，执行：

```bash
git clone https://github.com/liangliangyy/DjangoBlog.git
cd DjangoBlog
```

如果是 SSH 方式：

```bash
git clone git@github.com:liangliangyy/DjangoBlog.git
```

克隆完成后，当前目录下就会多出一个 `DjangoBlog` 文件夹，这就是项目源码。

## 五、用 VSCode 打开项目

在终端里直接执行：

```bash
code DjangoBlog
```

或者先打开 VSCode，通过「文件 → 打开文件夹」选择 `DjangoBlog` 目录。

打开后，VSCode 右下角可能会提示「是否安装推荐的扩展」，直接同意即可。

## 六、创建虚拟环境（推荐）

在项目根目录创建并激活虚拟环境，避免依赖污染全局环境：

```bash
# Windows
python -m venv venv
venv\\Scripts\\activate

# macOS / Linux
python3 -m venv venv
source venv/bin/activate
```

激活成功后，终端提示符前面会出现 `(venv)`。

## 七、安装依赖（requirements.txt）

项目根目录的 `requirements.txt` 列出了所有 Python 依赖，直接安装：

```bash
pip install -r requirements.txt
```

主要依赖包括：

- `Django` —— Web 框架
- `mysqlclient` —— MySQL 数据库驱动
- `django-compressor` —— 静态资源压缩
- `django-haystack` + `Whoosh` —— 全文搜索
- `elasticsearch` —— 可选的 ES 搜索引擎
- `django-mdeditor` —— Markdown 编辑器

## 八、创建数据库并配置连接

先在 MySQL 里创建数据库：

```sql
CREATE DATABASE `djangoblog` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

然后打开 `djangoblog/settings.py`，找到 `DATABASES` 配置，改成你自己的连接信息：

```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'djangoblog',        # 数据库名
        'USER': 'root',              # 账号
        'PASSWORD': '你的密码',        # 密码
        'HOST': '127.0.0.1',
        'PORT': 3306,
        'OPTIONS': {'charset': 'utf8mb4'},
    }
}
```

## 九、初始化数据库

依次执行迁移命令，Django 会自动在数据库里建好所有表：

```bash
python manage.py makemigrations
python manage.py migrate
```

接着创建超级管理员账号（用于登录后台）：

```bash
python manage.py createsuperuser
```

按提示输入用户名、邮箱和密码即可。

## 十、构建前端资源

前端使用 Vite 构建，需要先安装 npm 依赖再打包：

```bash
cd frontend
npm install
npm run build
cd ..
```

构建产物会输出到 `blog/static/blog/dist/`。最后收集一下静态文件：

```bash
python manage.py collectstatic --noinput
```

## 十一、启动项目

```bash
python manage.py runserver
```

浏览器打开 `http://127.0.0.1:8000/` 就能看到首页，后台管理在 `http://127.0.0.1:8000/admin/`。

## 十二、Git 日常操作

修改代码后，把改动提交并推送到远程仓库：

```bash
git status                 # 查看改动
git add .                  # 暂存所有改动
git commit -m "修改说明"     # 提交
git push origin main       # 推送
```

拉取远程最新代码：

```bash
git pull origin main
```

## 十三、GitHub 协作

- **Fork**：点击仓库右上角 Fork，把项目复制到自己的账号下。
- **Issue**：遇到问题或提建议，在 Issues 页面新建。
- **Pull Request**：在分支上改完代码后，提交 PR 给原作者合并。

## 结语

至此，一套完整的 DjangoBlog 就从零跑起来了。后续可以继续探索后台的站点配置、主题配色、插件系统、全文搜索等功能。

> 小提示：改了 `settings.py` 或站点配置后，记得执行 `python manage.py clear_cache` 清缓存，否则改动可能不会立即生效。
'''

        # 以 unique 的 title 作为“是否已种过这篇文章”的判定条件：
        # 命中就返回老文章（created=False，defaults 整个被忽略），没命中才按 defaults 建新文章。
        # 这样命令天然幂等 —— 重复执行不会产生第二篇同名文章，而模型层的 unique 约束
        # 又保证不可能出现“两篇都被创建”的竞态后果
        article, created = Article.objects.get_or_create(
            title=title,
            defaults={
                'body': body,
                'category': category,
                # 作者外键：必须是一个真实存在的用户，否则数据库外键约束直接报错
                'author': user,
                # 'p' = Published（已发布），走 Article.STATUS_CHOICES；
                # 用已发布状态是为了命令跑完首页立刻能看到，而不是留一篇草稿
                'status': 'p',
                # 'a' = Article（普通文章），走 Article.TYPE；
                # 另一个可选值 'p' 是独立页面，那种不进列表/归档，不适合教程文章
                'type': 'a',
            },
        )
        # 分支一：这次真的新建了文章 → 补上多对多标签关系
        if created:
            # 多对多关系必须等主对象有主键（save 之后）才能 add，get_or_create 已经存过，
            # 所以这里直接按缓存的 tags 字典逐个挂；文章与标签是 M2M，add 会写中间表
            for tag_name in tag_names:
                article.tags.add(tags[tag_name])
            # self.stdout.write 默认不换行，靠每次 write 把提示拼在自己的行上没意义，
            # 这里只求“有一条可见的成功回执”，颜色用 SUCCESS（绿）
            self.stdout.write(self.style.SUCCESS(f'创建文章成功: {title}'))
        # 分支二：文章早已存在 → 只把正文和分类刷新成最新版本
        else:
            # 手动改这两个字段再 save：相当于“以本命令里的 body 为准”覆盖正文，
            # 方便改了脚本里的教程内容后重跑一次就同步到线上文章
            article.body = body
            article.category = category
            # save() 会把整行写回，但本次只改过 body/category 两个属性，
            # views/pub_time/author/status 仍是库里读出来的原值，已有标签也不动，
            # 这样就不会把线上积累的阅读数和发布时间冲掉
            article.save()
            self.stdout.write(self.style.SUCCESS(f'文章已存在，已更新: {title}'))

        # 局部 import：只有命令跑到最后才需要缓存模块，放函数里可以避免模块级导入时
        # 就依赖缓存配置；djangoblog.utils 里的 cache 正是 django.core.cache.cache（默认缓存实例）
        from djangoblog.utils import cache
        # 全量 clear 而不是精确删某个 key：文章一变，首页列表、分类页、详情页、
        # 侧边栏都可能被缓存过，逐个算 key 容易漏；这是低频运维命令，清空整库最省事也最可靠
        cache.clear()
        # 最后一条提示：告诉执行者“内容已生效，不需要怀疑是缓存没刷新”
        self.stdout.write(self.style.SUCCESS('缓存已清理'))
