# blog 应用中文注释清单 · 翟旌超

- **任务**：分工表「6.1 / 6.2 对负责部分代码添加注释」「6.3 对负责部分的代码进行质量分析」
- **交付人**：翟旌超（软件工程 3 班，学号 2415304340，代码内标识 `#zjc`）
- **分支**：`ZJC_branch`（只改 `blog/` 下的注释，**未改动任何代码行、docstring、行尾空白**）
- **提交记录**：`eae6ebe`（views.py 首批）+ 本次提交（其余 19 个文件）
- **校验工具**：`zjc_check_ast.py`（比对注释前后两棵 AST）+ `python -m py_compile`，仓库根目录执行

## 一、文件清单

一共 **20 个文件、本次净新增 1934 行中文注释**，全部带作者标识 `#zjc`。

| # | 文件 | 总行数 | 注释行 | 代码行 | 本次净增注释 | 注释重点 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `blog/models.py` | 688 | 279 | 339 | 263 | 6 个业务模型 + `BaseModel` + `LinkShowType` 枚举：审计字段与 slug 自动生成、浏览量单列 UPDATE、缓存键与超时 |
| 2 | `blog/views.py` | 572 | 189 | 302 | 0（早期提交 `eae6ebe`） | 9 个类视图 + `fileupload`/`clean_cache_view` 两个函数视图 + 错误页的请求链路、详情页 prev/next、评论翻页 |
| 3 | `blog/templatetags/blog_tags.py` | 1167 | 461 | 549 | 425 | 33 个标签/过滤器：侧边栏 8 张表的查询与缓存、头像回源、Markdown 渲染、SEO meta |
| 4 | `blog/admin.py` | 325 | 184 | 104 | 122 | 6 个 ModelAdmin + 1 个 ModelForm：列表/筛选/内联配置、`BlogSettings` 单例三钩子 |
| 5 | `blog/documents.py` | 416 | 170 | 198 | 159 | 9 个类：ES 文档映射、IK 分词器分工、UA 解析、`ElaspedTimeDocumentManager` 建索引 |
| 6 | `blog/management/commands/create_setup_guide.py` | 363 | 118 | 169 | 102 | 命令入口 + 293 行 Markdown 模板 |
| 7 | `blog/management/commands/create_travel_data.py` | 371 | 164 | 131 | 134 | 批量造 15 篇旅行文章（正文常量 200 行） |
| 8 | `blog/templatetags/vite_tags.py` | 392 | 169 | 165 | 156 | 7 个标签：manifest 三级兜底、开发/生产自动切换、CSS 内联与 preload |
| 9 | `blog/urls.py` | 168 | 91 | 60 | 70 | 13 条路由的 URL 规则与反查名真实引用处、`cache_page` 生效范围与 4 个坑 |
| 10 | `blog/apps.py` | 122 | 71 | 41 | 65 | `AppConfig`、`ready()` 时机与幂等要求、搜索索引存在性检查 |
| 11 | `blog/middleware.py` | 105 | 63 | 35 | 63 | 两阶段计时、`response.streaming` 跳过、占位符字节替换、异常兜底 |
| 12 | `blog/context_processors.py` | 109 | 58 | 44 | 56 | 20 个全站模板变量、10 小时整块缓存、新分类 10 小时不进导航的副作用 |
| 13 | `blog/management/commands/sync_user_avatar.py` | 100 | 52 | 42 | 52 | 头像回源与幂等性、`test_picture` 探测、裸 `except` 的风险 |
| 14 | `blog/management/commands/ping_baidu.py` | 99 | 48 | 41 | 48 | `add_arguments` 的 `choices` 校验、失败只记日志不中断 |
| 15 | `blog/forms.py` | 62 | 42 | 13 | 42 | 搜索表单 `BlogSearchForm` 的字段与 URL 拼装 |
| 16 | `blog/management/commands/create_testdata.py` | 81 | 40 | 32 | 40 | 造的 4 类样例数据与顺序依赖 |
| 17 | `blog/management/commands/build_index.py` | 54 | 36 | 13 | 35 | ES / Whoosh 两条索引链路的开关分支 |
| 18 | `blog/management/commands/clear_cache.py` | 39 | 27 | 7 | 27 | 清的是默认缓存区全部键，不是 `cache1`/`cache2` 分频缓存 |
| 19 | `blog/management/commands/build_search_words.py` | 39 | 26 | 8 | 25 | 标签+分类词表去重、`print` 输出便于重定向 |
| 20 | `blog/search_indexes.py` | 66 | 50 | 10 | 50 | Whoosh 引擎的索引字段与 `Indexable` 配置 |
| | **合计** | **5338** | **2338** | **2303** | **1934** | 注释前合计 3373 行 |

> 口径说明：`注释行` = 整行以 `#` 开头的行；`代码行` = 非空、非注释、非 docstring 的物理行；另有 docstring 268 行未计入。
> 本次净增注释 = 当前注释行 − `git show HEAD:` 中的注释行（`views.py` 为 0 是因为那 188 行在更早的 `eae6ebe` 里已提交，本次只把文件头的作者标识行补成 `#zjc`）。
> 合计净增 1934 行，加上 `views.py` 此前已提交的 188 行，`#zjc` 名下注释共 **2122 行**。

## 二、注释写法（统一规范）

1. **只做整行插入 `#`**，从不写行尾注释——保证代码行、docstring、原有注释逐字不变。实测 `git diff` 的删除行数为 **0**（唯一例外是 `views.py` 文件头那行加 `#zjc` 标识）。
2. **每个文件固定文件头**（6 行）：`注释人：翟旌超（软件工程 3 班 2415304340，#zjc）` + 该模块在项目里干什么 + “只添加中文注释、不改代码”的声明。
3. **每个类 / 函数前一段说明**：`# 【函数名】—— 一句话功能`，再跟 `# 参数：` / `# 返回：` / `# 说明：`，说明里写“为什么这么写”“真实引用处”“坑在哪”。
4. **术语保留英文原词**：Cache-Aside、QuerySet、slug、CSRF、ES、manifest、migration 等不硬译，只在首次出现时用括号解释。
5. **标点全角**，中文与英文/数字之间留空格；引号统一用 `“”`。
6. **不承诺代码没做的事**：例如 `ping_baidu` 实测是 `try/except + logger.error`，注释就写“失败不中断”，不编造返回码判断。

## 三、自检方法与结果

```bash
# 1) AST 等价校验：注释前后语法树必须完全一致
python zjc_check_ast.py blog/models.py
# 输出：AST-EQUAL ok  blog/models.py  lines 425 -> 688  (comment lines now 279)

# 2) 语法编译校验
python -m py_compile blog/models.py
```

**全量结果**：20 个文件逐个 `AST-EQUAL ok`，40 个 `.py`（含 `tests.py`、`test_*.py`、`migrations/`）`py_compile` 全部通过（0 输出、0 报错）。

```
AST-EQUAL ok  blog/admin.py                       lines 202 -> 325   (comment lines now 184)
AST-EQUAL ok  blog/documents.py                   lines 254 -> 416   (comment lines now 170)
AST-EQUAL ok  blog/templatetags/blog_tags.py      lines 733 -> 1167  (comment lines now 461)
AST-EQUAL ok  blog/templatetags/vite_tags.py      lines 231 -> 392   (comment lines now 169)
...（20 个文件全部 ok）
```

三项硬校验：

| 校验项 | 方法 | 结果 |
| --- | --- | --- |
| 语法树等价 | `ast.dump(ast.parse(文件))` 与 `git show HEAD:文件` 对比 | 20/20 一致 |
| 删除行 | `git diff --numstat HEAD -- blog` 的删除列 | 19 个文件全 0，`views.py` 1 行（文件头补 `#zjc`） |
| 行尾空白 | 统计 `line != line.rstrip()` 的行数 | `views.py` 12 行、`blog_tags.py` 30 行，与 HEAD **完全相同**（都是原代码遗留） |

## 四、需要知道的几点

1. **`blog/views.py` 的 188 行注释不是本次新加的**：这是作者本人在 `eae6ebe` 里做的，本次只把文件头的作者标识行换成了 `#zjc`。统计“谁写了多少注释”时请按此口径。
2. **注释密度偏高**：小文件（`forms.py` 42 注释 / 13 代码、`clear_cache.py` 27 / 7）注释比高于代码，因为文件头 + 每个类和方法的说明是硬性要求；大文件（`blog_tags.py` 461 / 549 ≈ 0.84:1、`models.py` 279 / 339 ≈ 0.82:1）。
3. **行尾空白是原代码遗留，不是我加的**：`views.py` 12 行、`blog_tags.py` 30 行，共 42 行，与注释前逐字节相同。我在质量分析里把它列为待统一项，但不擅自清理。
4. **`management/commands` 下实际有 8 个命令**（分工表写“7 个”是估算）：`build_index`、`build_search_words`、`clear_cache`、`create_setup_guide`、`create_testdata`、`create_travel_data`、`ping_baidu`、`sync_user_avatar`。文件名就是命令名，跑 `python manage.py help` 能对上。
5. **换行符**：仓库开了 `core.autocrlf=true`，工作区里 CRLF/LF 混排是 Windows 检出的差异，提交后仓库内统一为 LF，`git diff` 不会出现整文件改动。
