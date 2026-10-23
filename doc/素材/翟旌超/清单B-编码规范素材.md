# 清单 B · 编码规范素材（blog 应用）· 翟旌超

> 交接对象：陈汉佳（负责《代码编码规范》、注释 / docstring 规范化、对照工具分析结果）
> 依据：`blog/` 下 20 个非测试文件 + `djangoblog/constants.py`、`djangoblog/utils.py`。行号均为当前 `ZJC_branch`。
> 下面每条都配了**真实代码位置**，可以直接抄进规范文档当“正例 / 反例”。

---

## ① 建议组内统一规范化的编码习惯

每组都按「问题 → 现状（真实代码）→ 建议规则」写，共 9 条，按落地成本从低到高排。

### 1. 缓存时长必须用常量，禁止裸算式

**问题**：同一个项目里，缓存过期时间有两种写法，其中裸算式很容易误读。

**现状**：
- `blog/templatetags/blog_tags.py:552` —— `cache.set("sidebar" + linktype, value, 60 * 60 * 60 * 3)`，实际 **648000 秒 ≈ 7.5 天**，读代码时几乎所有人都以为是“3 天”。
- 而 `blog/models.py:321` 用的是 `CacheTimeout.HOUR_10`（定义在 `djangoblog/constants.py:11`，`HOUR_10 = 60 * 60 * 10`）。

**建议规则**：
> 所有缓存超时一律引用 `djangoblog/constants.py` 里的 `CacheTimeout.*`；需要新时长先在 `CacheTimeout` 里加常量并写中文注释，代码里不得出现裸算式。

**附带**：`CacheTimeout` 现有 `MINUTE_1/5/10/30`、`HOUR_1/2/10/24`、`DAY_7/30`，覆盖了常见场景；侧边栏的 7.5 天可以新增 `DAY_7_5` 或直接把语义改成 `DAY_7`。

---

### 2. 禁止裸 `except:`

**问题**：`except:` 会连 `KeyboardInterrupt`、`SystemExit` 一起吞掉。

**现状**：`blog/management/commands/sync_user_avatar.py:49-54`

```python
def test_picture(self, url):
    try:
        if requests.get(url, timeout=2).status_code == 200:
            return True
    except:
        pass
```

**建议规则**：
> 只捕获预期的具体异常（这里是 `requests.RequestException`，必要时加 `django.core.exceptions.ValidationError`）；确实要兜底时写 `except Exception:` 并 `logger.warning(...)`，**不允许 `except:` 后直接 `pass`**。

---

### 3. 单行长度上限 120 字符，超长必须换行

**问题**：3 行超过 120 字符（其中 1 行 141 字符），diff 噪音大、评审时看不见。

**现状**：
- `blog/templatetags/blog_tags.py:872`（141 字符）
- `blog/views.py:217`、`blog/views.py:220`（各 126 字符）

**建议规则**：
> 行宽上限 120（与 flake8 默认 `max-line-length` 对齐后可调成 120）；超长时按“参数一行一个”或先定义中间变量再拼接的方式换行。中文注释按**两列宽**估算。
> 落地方式：`ruff check --line-length 120` 或 flake8，在 commit 前跑一遍。

---

### 4. 单个函数体建议 ≤ 60 行

**问题**：`handle()` 超过 290 行，里面是 200 行的长字符串常量，读起来像在读文件而不是读代码。

**现状**：
- `blog/management/commands/create_travel_data.py:58` `handle()` 共 **314 行**
- `blog/management/commands/create_setup_guide.py:71` `handle()` 共 **293 行**
- 其余最大两个：`blog/views.py:172` `get_context_data()` 101 行、`blog/templatetags/blog_tags.py:456` `load_sidebar()` 101 行

**建议规则**：
> 函数体超过 60 行先拆：数据准备 / 组装 / 输出分开；长文本（Markdown、正文模板）一律外置到 `blog/management/commands/data/*.md`，代码里只留 `open(...).read()`。一次性数据脚本可豁免，但要在文件头注明“一次性脚本，不做拆分”。

---

### 5. 未使用的导入必须删除（并让 CI 报 F401）

**问题**：8 处导入后从未使用，读者会误判模块的依赖关系。

**现状（已用脚本全量扫过）**：
- `blog/admin.py:25` —— `Category, Tag, Links, SideBar`（这四个是在 `djangoblog/admin_site.py:41-46` 注册的）
- `blog/templatetags/blog_tags.py:27` —— `hashlib`；`:31` —— `urllib`
- `blog/views.py:22` —— `get_object_or_404`；`:23` —— `render`；`:26` —— `_`；`:41` —— `ARTICLE_CONTENT_HOOK_NAME`；`:46` —— `ArticleListMixin`
- 例外：`blog/views.py:561` 的 `page_not_found_view / server_error_view / permission_denied_view` 是**故意**留的向后兼容再导出（文件里有注释说明），不要删。

**建议规则**：
> 提交前跑 `flake8 --select=F401`（或 ruff 的 `F401`），未使用导入一律删除；为兼容而保留的再导出，必须在同一行上方写 `# noqa: F401` + 一行原因。

---

### 6. 字符串格式化统一用 f-string

**问题**：三种风格并存，读代码要在三种语法间切换。

**现状**：
- f-string：`blog/models.py:316` `logger.info(f'Cache HIT: article comments (id={self.id})')`
- `.format()`：`blog/templatetags/blog_tags.py:553` `logger.info('set sidebar cache.key:{key}'.format(key="sidebar" + linktype))`
- `%`：`blog/management/commands/ping_baidu.py:71` `self.stdout.write('start get %s' % type)`、`:92` `'start notify %d urls' % ...`

**建议规则**：
> 新增代码统一 f-string（Python 3.6+ 已满足）；`.format()` 与 `%` 只在“字符串本身是模板、需要多次复用”时使用，且要在就近注释里说明原因（例如日志里需要保留模板给监控系统做聚合）。

---

### 7. 文件卫生：别留行尾空白，文件末尾留一个换行

**问题**：`blog/views.py` 12 处、`blog/templatetags/blog_tags.py` 30 处行尾带空格，共 42 行。

**建议规则**：
> 加 `.editorconfig`（`trim_trailing_whitespace = true`、`insert_final_newline = true`），或 pre-commit 里挂 `trailing-whitespace` / `end-of-file-fixer` 钩子。
> **注意**：存量这 42 行不要为了“整洁”整文件重排——会把 diff 放大到几百行，反而没法评审。建议“只在自己改动的行上顺手清”。

---

### 8. 会改变全局状态的接口必须有权限校验

**问题**：`/clean` 直接绑一个 `cache.clear()` 视图，没有任何登录/权限判断。

**现状**：`blog/urls.py:164-167` → `views.clean_cache_view`，后者只有一句 `cache.clear()`。

**建议规则**：
> 任何会清缓存、改配置、跑批量任务的视图，必须满足至少一条：①`@login_required` + `user.is_staff`；②仅允许 `127.0.0.1`（内网/运维）；③干脆不做成 URL，只留 `manage.py` 命令。项目其实已经有 `blog/management/commands/clear_cache.py`，URL 版本属于重复实现。

---

### 9. 历史拼写不要“顺手修正”

**问题**：项目里有 3 处拼写错误，但它们同时是**模板变量名 / 外部 import 名**，改了会静默失效（不报错、只是不显示）。

**现状**：
| 位置 | 拼写 | 牵连 | 处理 |
| --- | --- | --- | --- |
| `blog/templatetags/blog_tags.py:542` | `'sidabar_links'`（应为 sidebar） | `blog/tags/*.html` 模板里的 `{{ sidabar_links }}` | **不改**，在注释里注明 |
| `blog/templatetags/blog_tags.py:512` | `commment_list`（多一个 m） | 仅本文件内部变量 | 可改，但价值低 |
| `blog/documents.py:215` | `ElaspedTimeDocumentManager`（应为 elapsed） | `blog/middleware.py:89`、`blog/test_middleware.py` 的 `@patch('blog.middleware.ElaspedTimeDocumentManager.create')` | **不改**（改名会打断已有测试和外部引用），注释里注明“历史拼写” |

**建议规则**：
> 新增代码命名前先 `git grep` 一下目标名字，避免出现第二种拼写；发现存量拼写错误时**只加注释不改名**，并在规范文档里登记成“已知历史欠债表”，防止新人重复“修正”。

---

## ② 值得推广的写法（可直接抄成“团队推荐用法”）

### 推广 1：中间件的“两阶段计时 + 流式响应跳过 + 兜底不抛异常”

位置：`blog/middleware.py:60-105`

```python
def __call__(self, request):
    start_time = time.time()                                  # middleware.py:63
    response = self.get_response(request)                     # middleware.py:66  两次计时之间夹着整条渲染链路
    ...
    if not response.streaming:                                # middleware.py:76  流式响应没有完整 content，跳过
        try:
            cast_time = time.time() - start_time              # middleware.py:79
            if ELASTICSEARCH_ENABLED:
                time_taken = round((cast_time) * 1000, 2)     # middleware.py:83  统一成毫秒、保留两位
                ElaspedTimeDocumentManager.create(url=request.path, time_taken=time_taken, ...)
            response.content = response.content.replace(
                b'<!!LOAD_TIMES!!>', str.encode(str(cast_time)[:5]))   # middleware.py:98-99
        except Exception as e:                                # middleware.py:101 只记日志，页面照常返回
            logger.error("Error OnlineMiddleware: %s" % e)
```

**为什么值得推广**：性能统计属于“锦上添花”，一旦它抛异常，整个站点的每个请求都会 500。这个实现做对了两件事——①`get_response()` 前后分别取值，天然覆盖视图前后的耗时；②`response.streaming` 判断避免对 `StreamingHttpResponse` 取 `.content`（那会直接抛 `AttributeError`）；③整段 `try/except` 里只 `logger.error`。

**可优化一点（写进规范时提一句）**：写 ES 的毫秒值用了 `round(..., 2)`（`middleware.py:83`），但回填到页面的秒数是 `str(cast_time)[:5]`（`middleware.py:99`）——这是**截断**不是四舍五入，`0.99999` 会显示成 `0.999`，建议统一改成 `'{:.2f}'.format(cast_time)`。

### 推广 2：静态资源标签的“三级兜底 + 环境自动切换”

位置：`blog/templatetags/vite_tags.py:87-131`（`load_manifest`）、`:216` 起（`vite_js` 里 `if not manifest:` 走开发分支）

**为什么值得推广**：
- manifest 不存在 → `warning` + `{}`；解析失败 → `error` + `{}`；入口找不到 → `error` + 空输出。**页面永远能渲染**，最坏结果是“没样式”，而不是“500”。
- 开发模式不缓存 manifest（改完前端刷新即见），生产模式进程内缓存一次（省 IO），这个判断只有一行：`if not settings.DEBUG and _manifest_cache is not None: return _manifest_cache`。
- 这套写法可以平移到任何“构建产物依赖”的场景（图片 hash、CSS 指纹、i18n 包）。

### 推广 3：缓存装饰器统一入口

位置：`djangoblog/utils.py:36` `def cache_decorator(expiration=3 * 60)`，用法见 `blog/models.py:286`、`:337`、`:345`、`:412`、`:434`、`:482`

**为什么值得推广**：把“取缓存 → 未命中 → 计算 → 回填”四步收敛成一个装饰器，模型方法只关心业务值。**规范建议**：统一写成 `@cache_decorator(expiration=CacheTimeout.HOUR_10)`（关键字形式），不要一半位置参数一半关键字——现状 `blog/models.py:286` 是 `@cache_decorator(CacheTimeout.HOUR_10)`，`:337` 是 `@cache_decorator(expiration=CacheTimeout.HOUR_10)`。

### 推广 4：启动期只做幂等检查，失败只 warning

位置：`blog/apps.py:48-59` `ready()` → `check_search_index()`

**为什么值得推广**：`ready()` 在每个进程都会跑（runserver 重载子进程、每个 gunicorn worker），所以它必须“可重复、代价小、不依赖别人先启动”；这里只做一次索引存在性检查，且整段包 `try/except` 只 `logger.warning`——**搜索引擎不可用不能让网站起不来**。

---

## ③ blog 应用特有的编码约定（写规范时可直接作为“本项目约定”章节）

### 3.1 management command（运维脚本）约定

- **位置**：`blog/management/commands/<命令名>.py`，必须存在 `__init__.py`（已有）。
- **类名固定** `Command(BaseCommand)`；**文件名就是命令名**，`python manage.py <文件名>` 调用。
- `help` 属性写一句用途，会出现在 `python manage.py help` 里。
- 参数校验优先用 `add_arguments` 的 `choices=`（例：`blog/management/commands/ping_baidu.py:45-56`），而不是在 `handle()` 里自己 `if` 判断。
- 输出统一用 `self.stdout.write(...)` / `self.stderr.write(...)`，**不要 `print`**（唯一例外：`build_search_words.py:39` 是有意用 `print` 输出纯词表便于 `> words.txt` 重定向，已加注释说明）。
- 现有 8 个命令：`build_index`、`build_search_words`、`clear_cache`、`create_setup_guide`、`create_testdata`、`create_travel_data`、`ping_baidu`、`sync_user_avatar`。

### 3.2 模板标签（templatetags）约定

- 文件放在 `blog/templatetags/`，模板里要先 `{% load blog_tags %}` / `{% load vite_tags %}`。
- 三种注册方式，按用途选：
  - `@register.simple_tag` —— 返回字符串（例：`blog_tags.py:180` `render_article_content`）
  - `@register.inclusion_tag('blog/tags/xxx.html')` —— 返回 dict 由子模板渲染（例：`load_sidebar` 用的是 `blog/tags/sidebar.html`），**片段模板统一放 `blog/tags/` 目录**
  - `@register.filter` —— 用于管道语法（例：`truncate`、`timeformat`）
- 标签里**不做权限判断、不写业务写操作**；写操作一律走视图。
- 标签内部允许直接查模型（现状如此），但**必须自己管缓存**且缓存键带前缀，方便 `/clean` 或按前缀清理。

### 3.3 模型（models）约定

- 所有业务模型继承 `BaseModel`（`blog/models.py:78`），自动获得：`id`、`creation_time`、`last_modify_time`、`slug` 自动生成、`get_full_url()`。
- 覆写 `save()` 时**必须调用 `super().save()`**，唯一例外是 `views` 单列更新（`blog/models.py:92-111`，见清单 A 亮点 1）。
- 字段的 `verbose_name` 用 `gettext_lazy`，如 `models.CharField(_('title'), max_length=200)`（`blog/models.py:158`）。
- 枚举字段用 `CharField(max_length=1, choices=...)` + 模块级 choices 元组（`models.py:142-190` 的 `STATUS_CHOICES` / `COMMENT_STATUS` / `TYPE`，以及 `models.py:64` 的 `LinkShowType`），**数据库里只存单字符**，取值含义写进 choices 的 label。
- 需要被缓存的方法用 `@cache_decorator(...)`，需要被搜索结果用到的字段要在 `blog/documents.py` 的 `ArticleDocument` 里同步定义（**这是隐性契约，加字段必须两处改**）。

### 3.4 URL 约定

- 站内页面统一 `.html` 后缀：详情页 `/article/<年>/<月>/<日>/<id>.html`、分类 `/category/<slug>.html`、标签 `/tag/<slug>.html`、归档 `/archives.html`、友链 `/links.html`。
- 首页分页 `/page/<页码>/`，分类/标签分页 `/category|tag/<名称>/<页码>.html`。
- 需要缓存的整页才加 `cache_page(...)`（目前只有 `/archives.html`），加之前想清楚“数据多久变一次”。
- 每条路由都给 `name=`，模板/代码里用 `{% url %}`、`reverse()` 反查，不要手写 URL。

### 3.5 后台（admin）约定

- `ModelAdmin` 定义在 `blog/admin.py`，**注册在 `djangoblog/admin_site.py:41-46`**（项目用的是自定义 `DjangoBlogAdminSite`，不是 `admin.site`）。新增模型要同时改两个文件。
- 列表页默认列够用时不要写 `list_display`；需要裁掉自动字段时用 `exclude = ('last_mod_time', 'creation_time')`（例：`blog/admin.py:254`）。
- 全局配置类模型用“单例三钩子”：`has_add_permission` 返回 `not Model.objects.exists()`、`has_delete_permission` 返回 `False`、`changelist_view` 直接重定向到编辑页（`blog/admin.py:275-309`，`BlogSettings` 是范本）。

### 3.6 缓存约定

- 统一通过 `djangoblog.utils.cache` 访问缓存（不要直接 import `django.core.cache.cache`）。
- 缓存键用 `djangoblog/constants.py:37` 的 `CacheKey` 模板拼，键名带业务前缀（`article_comments_`、`article_prev_`、`category_list_`…）。
- 缓存时长用 `djangoblog/constants.py:11` 的 `CacheTimeout`。
- 注意 `LocMemCache` 是**每进程一份**：`/clean` 只清当前进程的缓存，多 worker 部署下其他 worker 仍持旧值——这条要写进规范的“已知限制”。

---

## 附：统计口径备忘（对照工具分析结果时用）

| 口径 | 数值 | 说明 |
| --- | --- | --- |
| 负责文件 | 20 个 | 不含 `tests.py`、6 个 `test_*.py`、`migrations/` |
| 物理行（注释前 → 后） | 3373 → 5338 | 本次净增注释 1934 行 |
| 纯代码行（非空、非注释） | 2303 | 其中 docstring 268 行 |
| docstring | 268 行（含 31 空行） | |
| 类 / 函数 | 55 / 131 | 含方法 |
| 整个 `blog/` 目录 | 40 个 py 文件、8004 物理行、4374 行非注释非空行 | 含测试与迁移 |

> 组长的基准「3459 行」与本表口径不同（应是“含注释物理行”或 cloc 默认列）。规范文档里建议只写一条口径并加脚注，别让两处数字打架。
