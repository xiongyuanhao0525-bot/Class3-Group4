# Python 编码规范

> 适用项目：Class3-Group4（旅行博客系统，Django 项目）
> 文档执笔：陈汉佳（#chj）
> 版本：v1.0 ｜ 状态：待交叉通读

---

## 一、小组信息（表头）

| 成员 | 学号 | GitHub 分支 | 本周任务 |
|---|---|---|---|
| 熊圆好（组长） | 2415304320 | xyh_branch | djangoblog 公共模块注释 |
| 纪秀茹 | 2415304310 | jxr_branch | 代码质量报告 |
| 翟旌超 | 2415304340 | ZJC_branch | blog 应用注释 |
| 王鑫悦 | 2415304306 | wxy_branch | servermanager 注释 |
| 陈汉佳 | 2415304339 | chj_branch | accounts 注释 + Python 编码规范 |
| 杨杰翰 | 2415304359 | yjh_branch | oauth 应用注释 |

> 学号已全员填写。

---

## 二、规范制定的主要目的

1. **统一代码风格**：本项目由 6 名组员协作开发，统一风格保证代码可读性，降低互相阅读成本。
2. **提升可维护性**：良好的命名、注释、结构便于后续扩展功能与修复缺陷。
3. **保障质量底线**：规范明确"只加注释不改逻辑"、禁止无关文件提交等红线，避免协作冲突。
4. **便于教学考核**：注释标识、提交信息规范便于老师与组长核查每位成员的工作量。

---

## 三、规范的适用范围

1. 本项目仓库 `Class3-Group4` 内**全部 Python 代码**（djangoblog、blog、comments、accounts、oauth、servermanager 等所有应用）。
2. 适用于所有组员的**日常开发、代码注释、文档编写与提交推送**。
3. 后续新增功能、修复缺陷同样遵循本规范。
4. 配置文件（requirements.txt、package.json 等）与前端代码（HTML/JS/CSS）不在本规范范围内。

---

## 四、编码规范

### 1. 命名规范

| 对象 | 规范写法 | 正例 | 反例 |
|---|---|---|---|
| 变量名 | 小写下划线（snake_case） | `article_id` | `articleId` |
| 函数名 | 小写下划线 | `form_valid` | `FormValid` |
| 方法名 | 小写下划线 | `get_reactions_summary` | `getReactions` |
| 类名 | 大驼峰（CapWords） | `CommentPostView` | `comment_post_view` |
| 常量 | 全大写下划线 | `_code_ttl` | `CodeTtl` |
| 模块/包 | 全小写 | `comments`, `views.py` | `Comments` |
| 外键字段 | 模型名小写 + `_id` | `author_id`、`article_id` | `authorid` |
| 布尔字段 | 用 is_/has_ 前缀 | `is_enable`、`is_active` | `enable_flag` |

> 实例说明：accounts/views.py 中 `comment_status`、`parent_comment_id` 均遵循小写下划线命名。

### 2. 代码布局与格式

1. **缩进**：统一使用 4 个空格，禁止 Tab 混用。
2. **行宽**：单行不超过 79 字符（Django 类定义、字符串可适当放宽）。
3. **空行**：
   - 模块内顶层函数/类之间空 **2 行**；
   - 类内方法之间空 **1 行**；
   - import 分组之间空 1 行（标准库 → Django → 项目内模块）。
4. **import 顺序**：标准库 > 第三方库 > Django 库 > 项目自定义模块，组内按字母序。

```python
# 正例
import logging
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import models

from djangoblog.utils import send_email
from .forms import CommentForm
```

5. **行尾**：文件末尾保留一个空行；不使用行尾空格。

### 3. 注释规范

1. **文件头注释**：每个 Python 文件开头用 `#` 注明模块职责与注释人标识（格式：`# 模块名 职责说明`）。

```python
# comments/views.py
# 评论模块视图层：发表评论 / 回复 / 表情回应
# 注释人：陈汉佳 #chj
```

2. **注释标识**：协作注释统一使用 `#姓名缩写` 标注，便于追溯贡献者（如 `#chj`、`#xyh`、`#jxr`、`#zjc`、`#wxy`、`#yjh`）。
3. **docstring**：类、函数、方法使用三引号 docstring 说明用途；视图类需注明"自动提供的基类能力"（如 CSRF 保护、登录验证）。

```python
class LoginView(LoginFormView):
    """
    用户登录视图
    使用 LoginFormView 基类，自动提供：
    - 敏感参数保护（password）
    - CSRF 保护
    - 禁用缓存
    """
```

4. **行内注释**：解释"为什么这么做"而非"做了什么"；注释与代码之间空一格（`# 注释`）。

```python
# 正例
user.is_active = False          # 注册后先冻结，待邮箱验证通过再激活

# 反例
user.is_active = False          # 设置 user.is_active 为 False
```

5. **注释不改逻辑**：注释任务只允许增加注释，禁止修改任何业务逻辑；确需改动代码的，单独 commit 并在提交信息中写明原因。

### 4. Django 框架约定

1. **视图**：优先使用**类视图**（`django.views.View` 及项目基类 `SecureFormView`、`LoginFormView`、`AuthenticatedFormView`），统一暴露 `form_class`、`template_name` 属性；函数视图仅在简单页面（如 `account_result`）使用。
2. **URL 命名**：每个路由 `name` 使用小写下划线；模块内统一 `app_name`，跨应用跳转用 `应用名:路由名`（如 `accounts:login`）。

```python
app_name = "accounts"
urlpatterns = [
    re_path(r'^login/$', views.LoginView.as_view(success_url='/'), name='login'),
]
```

3. **表单**：模型表单继承 `ModelForm`（如 `CommentForm`），非模型表单继承 `forms.Form`；字段校验统一用 `clean_字段名()` 方法；带样式的输入框在 `__init__` 中统一设置 `widget`。
4. **模型**：
   - 自定义用户模型继承 `AbstractUser`；
   - 常用字段类型：`CharField`、`TextField`、`IntegerField`、`DateTimeField`、`BooleanField`；
   - 时间字段统一 `default=now`（`django.utils.timezone.now`）；
   - 外键命名 `xxx_id`，`on_delete` 必须显式指定（本项目用 `CASCADE`）；
   - `Meta` 内声明 `ordering`、`verbose_name` 等。
5. **模板标签**：自建模板标签放 `templatetags/` 目录；函数名与注册名一致。
6. **后台管理**：`admin.py` 中注册模型并继承 `UserAdmin` 等基类，配置 `list_display`、`search_fields`、`ordering`。
7. **数据库访问**：优先用 ORM（`objects.get/filter`）与 `get_object_or_404`，禁止直接拼接 SQL。
8. **登录验证**：视图内使用 `request.user.is_authenticated` 判断登录态；敏感操作校验 CSRF（默认开启）。

### 5. 国际化与多语言

1. 面向用户展示的文案统一使用 `gettext_lazy` / `_()` 包裹，便于翻译：

```python
nickname = models.CharField(_('nick name'), max_length=100, blank=True)
```

2. 日志、调试输出可用中文，无需国际化。

### 6. 异常与日志

1. 使用 `logging.getLogger(__name__)` 记录关键流程（登录、验证等），禁止 `print` 调试输出留在代码中。
2. 主动校验失败时抛出 `ValidationError`（表单）或返回错误 JSON；禁止捕获异常后静默吞掉。
3. 视图返回 JSON 时统一结构：`{'success': True/False, ...}`，错误场景携带 `error` 字段并设置对应 HTTP 状态码（401/400/403）。

### 7. 版本控制与提交规范

1. **分支**：每位成员使用自己的分支（`姓名缩写_branch`），禁止直接提交 master。
2. **提交信息**：格式 `姓名: 操作说明`（如 `陈汉佳: 标注accounts注册/登录/找回密码代码 #chj`）。
3. **提交范围**：只提交本次任务相关文件；**禁止提交** `frontend/package-lock.json`、虚拟环境、本地缓存等无关文件。
4. **注释任务红线**：只加注释不改逻辑；确需改代码必须单独 commit 并说明。
5. **推送前**：先 `git pull origin master` 同步最新代码，解决冲突后再提交。

### 8. 代码正反例对照

| 场景 | 正例 | 反例 |
|---|---|---|
| 获取对象 | `get_object_or_404(Article, pk=article_id)` | `Article.objects.get(pk=article_id)`（不存在会抛异常） |
| 判断登录 | `if request.user.is_authenticated:` | `if request.user:` |
| 密码保存 | `user.set_password(raw)` / `make_password(raw)` | 明文赋值 `user.password = raw` |
| 布尔判断 | `if not created:` | `if created == False:` |
| 拼接 URL | `reverse('accounts:login')` | 硬编码 `'/login/'` 字符串 |

---

## 五、组员清单 B 素材汇编（编码正反例实例）

> 素材来源：各成员信息收集清单 B（交陈汉佳汇总，用于本规范）。已合入：王鑫悦（servermanager）；其余组员素材交齐后补充。

### 5.1 servermanager 反例（王鑫悦 #wxy 提供）

1. **类名违反 PEP8**：`class commands(models.Model)` 类名应大驼峰 `Commands`。
2. **魔法字符串/硬编码**：开发 token `'lylinux'`、测试密码 `'123'` 直接写在源码里，应抽到 settings 或环境变量。
3. **吞异常且未使用异常对象**：`except Exception as e:` 中 `e` 从未使用（flake8 F841），应改为 `except Exception:` 或 `logger.exception(e)`。
4. **魔法数字**：`if self.userinfo.Count >= 3` 中 `3` 含义不明，应定义常量 `MAX_PASSWORD_RETRY = 3`。
5. **超长函数 + 嵌套 if**：`handler()` 约 50 行用一串 if 串起状态机，新加状态要改主流程，建议拆成独立方法或用字典分发。

### 5.2 servermanager 正例（王鑫悦 #wxy 提供）

1. **`@property` 做可用性探测**：把"缓存是否可用"封装成只读属性，调用方一行判断。

```python
@property
def is_available(self):
    value = "1"
    self.set('checkavaliable', value=value)
    return value == self.get('checkavaliable')
```

2. **只读审计表写法**：`readonly_fields` + `has_add_permission=False`，日志类表通用。

```python
class EmailSendLogAdmin(admin.ModelAdmin):
    list_display = ('title', 'emailto', 'send_result', 'creation_time')
    readonly_fields = ('title', 'emailto', 'send_result', 'creation_time', 'content')

    def has_add_permission(self, request):
        return False
```

### 5.3 servermanager 特有约定（Django 约定类小节）

1. WeRoBot 集成：`urls.py` 用 `make_view(robot)` 挂载机器人；`enable_session=True` 后微信会话由 `SESSION_STORAGE` 统一管理。
2. 会话存储双实现：`MemcacheStorage`（Redis）与 `FileStorage`（本地文件）二选一，启动时按 `is_available` 自动回落，可作缓存降级范例。
3. 微信指令用 `@robot.filter(re.compile(...))` 正则分发，兜底用 `@robot.handler`；新指令只需加 filter 装饰器，无需改路由。
4. 管理员运维命令走 `commands` 表注册 + `CommandHandler` 执行：新增命令 = 新增一行表记录，无需重启服务。

---

## 六、附注

1. 本规范依据 **PEP 8**（Python 代码风格指南）与本项目实际代码整理而成。
2. 正反例素材来源：accounts / comments 应用精读实例；其他组员收集的清单 B 素材合入后补充至本文件"附注"。
3. 本规范由陈汉佳执笔，与《代码质量报告》（纪秀茹）交叉通读后提交 master。
