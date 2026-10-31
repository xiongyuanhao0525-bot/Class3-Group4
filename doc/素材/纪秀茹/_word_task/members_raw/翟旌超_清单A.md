# 清单 A · 代码质量分析报告素材（blog 应用）· 翟旌超

> 交接对象：纪秀茹（负责《代码质量分析报告》）
> 依据：`blog/` 下 20 个非测试文件；所有行号均为**当前** `ZJC_branch` 上的真实行号（注释已加入后）。
> 统计口径：`代码行` = 非空、非注释的物理行（docstring 计入其中，单独统计为 268 行）。

---

## ① 负责文件的注释清单

完整清单见同目录 [`blog注释清单.md`](blog注释清单.md)。汇总如下：

- **20 个文件**，注释前 3373 行 → 注释后 **5338 行**，本次净新增 **1934 行中文注释**（另 `views.py` 的 188 行为早期提交，`#zjc` 名下合计 2122 行）。
- 覆盖：模型层（`models.py` 6 个业务模型 + `BaseModel`）、视图层（`views.py` 9 个类视图 + 2 个函数视图）、模板标签层（`blog_tags.py` 33 个、`vite_tags.py` 7 个）、后台（`admin.py` 6 个 ModelAdmin）、搜索（`documents.py` 9 个类、`search_indexes.py`）、中间件、上下文处理器、路由，以及 `management/commands` 下 8 个运维命令。
- 校验：每个文件都用 `zjc_check_ast.py` 比对注释前后的 AST（必须完全一致）+ `py_compile`，20/20 通过。

**写进报告的一句结论**：注释是“按代码事实”写的，不是模板套话——例如 `ping_baidu` 的推送失败只 `logger.error` 不抛异常、`build_index` 按 `ELASTICSEARCH_ENABLED` 分走 ES/Whoosh 两条链路，都是从代码里读出来的。

---

## ② 代码风格

### 2.1 总体印象

| 维度 | 现状 |
| --- | --- |
| 缩进 | 统一 4 空格，**0 行使用 Tab** |
| 命名 | 类 `PascalCase`、函数/变量 `snake_case`、常量 `UPPER_CASE`，基本一致 |
| 行长 | 按 flake8 口径（字符数 >120）共 3 行，**全是原有代码**：`blog_tags.py:872`（141）、`views.py:217`/`:220`（各 126）；我加的注释行没有一行超过 120 字符（最宽的是 `create_setup_guide.py:102` 的 102 字符，但内容是中文 Markdown，等宽显示宽度 180） |
| 行尾空白 | 42 行（`views.py` 12 行、`blog_tags.py` 30 行），属原代码遗留，与注释前逐字节相同 |
| 注释密度 | 大文件 0.8~0.9:1（注释:代码），小文件 2~4:1（含文件头与逐函数说明） |

### 2.2 正例（可写进报告“值得肯定”部分）

**正例 1：`blog/models.py:303-305`，三行把一件事说清**

```python
def viewed(self):
    self.views += 1
    self.save(update_fields=['views'])
```

职责单一、无多余分支；`update_fields` 这个参数把“只想改一列”的意图显式表达出来（配合 `models.py:92-111` 的特判才生效）。

**正例 2：`blog/documents.py:215` 起的 `ElaspedTimeDocumentManager`，把“建索引 / 删索引 / 写一条记录”三件强相关的事收在同一个类里**，调用方只认这一个入口（`blog/middleware.py:89` 只调 `.create()`），内聚性很好。

**正例 3：`blog/views.py:65-106` 的视图复用**——`ArticleListView` 把“分页 + 文章查询优化 + 模板 + 缓存”做成基类，`IndexView`（`views.py:106`）只覆写三个钩子：`link_type`（友链类型）、`get_queryset_data()`（过滤 `type='a', status='p'`）、`get_queryset_cache_key()`（`f'index_{self.page_number}'`），分类页/标签页/作者页/归档页同样按这个模式写，没有复制粘贴。

### 2.3 反例（可写进报告“需要改进”部分）

**反例 1：超长单行**，`blog/templatetags/blog_tags.py:872`（141 字符）

```python
non_default_users = [u for u in users_with_picture if u.picture != default_avatar_path and not u.picture.endswith('/avatar.png')]
```

**反例 2：URL 拼接重复**，`blog/views.py:217` 与 `:220`（各 126 字符），两行几乎一样，且 `#commentlist-container` 锚点硬编码了两遍：

```python
'comment_next_page_url'] = self.object.get_absolute_url() + f'?comment_page={next_page}#commentlist-container'
'comment_prev_page_url'] = self.object.get_absolute_url() + f'?comment_page={prev_page}#commentlist-container'
```

**反例 3：字符串格式化风格混用**——同一文件里既有 f-string（`blog/models.py:316` `logger.info(f'Cache HIT: article comments (id={self.id})')`），又有 `.format()`（`blog/templatetags/blog_tags.py:553` `'set sidebar cache.key:{key}'.format(...)`）、还有 `%` 风格（`blog/management/commands/ping_baidu.py:71` `'start get %s' % type`、`:92` `'start notify %d urls' % ...`）。

**反例 4：标识符拼写不一致**（历史遗留，不建议改，因为改了就影响模板键名/外部 import）：
- `blog/templatetags/blog_tags.py:512` `commment_list`（多一个 m）
- `blog/templatetags/blog_tags.py:542` `'sidabar_links'`（应为 sidebar）
- `blog/documents.py:215` `ElaspedTimeDocumentManager`（应为 Elapsed，注释里已注明是历史拼写）

---

## ③ 代码设计说明

### 3.1 分层结构（清晰，是这个项目最大的设计优点）

```
urls.py（路由，13 条）
   └─ views.py（9 个类视图 + 2 个函数视图）
        ├─ models.py（数据 + 领域方法：comment_list / viewed / get_full_url）
        ├─ templatetags/blog_tags.py（展示逻辑：侧边栏、分页、Markdown、SEO）
        ├─ mixins（djangoblog/mixins.py：整页缓存、查询优化、分页）
        └─ forms.py（表单）
横切：middleware.py（耗时埋点）、context_processors.py（全站变量）、
      documents.py + search_indexes.py（搜索）、admin.py + djangoblog/admin_site.py（后台）、
      management/commands/（8 个运维命令）
```

### 3.2 内聚性好的地方

1. **`BlogSettings` 单例**：模型层 `clean()` 校验唯一（`blog/models.py:677-679`），后台层用 `has_add_permission` / `has_delete_permission` / `changelist_view` 三个钩子把“不许加、不许删、进列表直奔编辑页”做全（`blog/admin.py:275-309`）。约束落在数据层而不只靠 UI。
2. **`ElaspedTimeDocumentManager`**：性能索引的三个操作集中一个类（见 ②）。
3. **`vite_tags`**：manifest 读取、开发/生产判断、兜底日志都收敛在 `load_manifest()` 一个函数（`blog/templatetags/vite_tags.py:87-131`），7 个标签共用。

### 3.3 耦合问题（报告里可以点名的三处）

1. **ES 文档字段与模型字段手工同步**：`blog/documents.py:320-330` 的 `pub_time` / `status` / `comment_status` / `type` / `views` / `article_order` 与 `models.Article` 是两套定义，代码注释只能写“与模型保持一致”。**模型加一个可搜索字段，就必须记得改 `ArticleDocument`**，否则搜索页读不到，而且不会报错——这是隐性契约。
2. **模板标签直接扛数据查询**：`blog/templatetags/blog_tags.py:456-556` 的 `load_sidebar` 一个标签里查了文章、分类、标签、友链、侧边栏、评论、独立页面等 8 类数据，还自己管缓存。好处是模板一行 `{% load_sidebar %}` 搞定；代价是展示层与数据层耦合，换个页面布局就要动标签代码。
3. **后台“定义与注册分离”**：ModelAdmin 写在 `blog/admin.py`，注册却在 `djangoblog/admin_site.py:41-46`。新增一个模型要改两个文件、两个 app；漏了注册后台就看不到，且没有任何报错。

---

## ④ 亮点（至少 1-2 处，附点评）

### 亮点 1：把“浏览量 +1”从整行重写降级为单列 UPDATE

位置：`blog/models.py:92-111`（`BaseModel.save` 特判） + `blog/models.py:303-305`（`Article.viewed`）

```python
def save(self, *args, **kwargs):
    is_update_views = isinstance(
        self, Article) and 'update_fields' in kwargs and kwargs['update_fields'] == ['views']
    if is_update_views:
        Article.objects.filter(pk=self.pk).update(views=self.views)
    else:
        if 'slug' in self.__dict__:
            slug = getattr(self, 'title') if 'title' in self.__dict__ else getattr(self, 'name')
            setattr(self, 'slug', slugify(slug))
        super().save(*args, **kwargs)
```

**点评**：浏览量是最高频的写操作，而文章正文可能有几百 KB。默认 `save()` 会把整行重新写一遍、顺手刷新 `last_modify_time`、重算 slug；这里用一个显式契约换成了 `UPDATE blog_article SET views=? WHERE id=?` 一条语句，写入量和锁范围都小一个数量级。

**但要写进报告的隐患**（我已在注释里标注）：
- 靠魔法字符串 `['views']` 触发，任何人手写 `save(update_fields=['views', 'title'])` 就静默失效，退化成整行写；
- `self.views += 1` 是读-改-写，两个请求同时进来会少计一次（并发丢更新），正确写法是 `F('views') + 1`；
- 不走 `save()` 就不会触发 `post_save` 信号，未来若有信号监听（缓存失效、ES 同步）会漏掉。

### 亮点 2：Vite manifest 的三级兜底，让前端构建产物缺失也不会 500

位置：`blog/templatetags/vite_tags.py:87-131`

- 第一级：manifest 文件不存在（开发模式没构建）→ `logger.warning` + 返回 `{}`；
- 第二级：JSON 解析失败 → `logger.error` + 返回 `{}`；
- 第三级：入口名不在 manifest 里 → `logger.error` + 返回空字符串（标签输出空，页面正常渲染）。

再配合“开发模式不缓存 manifest、生产模式进程内缓存一次”（`vite_tags.py:98`），做到：改前端重新构建后**刷新页面即可生效，不用重启 Django**；构建产物缺失时页面是“没样式”，而不是“服务器错误”。

**备选亮点（如果报告需要第三个）**：`blog_tags.py:456-556` 侧边栏 8 张表的查询被一次查完并整块缓存 7.5 天，命中时整个侧边栏 0 次 SQL。

---

## ⑤ 质量问题清单

> 状态列说明：**未修复（建议不改）** 指修复收益小于回归风险；**未修复（建议修）** 指低风险高收益。

| # | 位置 | 问题 | 影响 | 状态 |
| --- | --- | --- | --- | --- |
| 1 | `blog/models.py:303-305` | 浏览量 `self.views += 1` 后整列回写，读-改-写不是原子操作 | 并发访问同一篇文章时少计阅读量 | 未修复（建议修） |
| 2 | `blog/templatetags/blog_tags.py:552` | 缓存时长写死 `60 * 60 * 60 * 3`，实际是 **648000 秒 ≈ 7.5 天**，和语义上的“3 天”不符 | 代码里另有 `CacheTimeout` 常量类，两套写法并存，易误读 | 未修复（建议不改） |
| 3 | `blog/models.py:311-323` | `comment_list()` 把 **QuerySet** 直接 `cache.set`，返回时是 pickle 反序列化的惰性查询集 | 模型字段变更后旧缓存可能反序列化失败；评论审核通过后最长 10 小时才出现 | 未修复（建议不改，改动面大） |
| 4 | `blog/models.py:685-688`、`blog/admin.py:311-324` | 保存站点设置后 `cache.clear()` 全量清空（局部 import 绕过循环依赖） | 一次改配置导致全站缓存冷启动，缓存穿透到数据库 | 未修复（建议不改） |
| 5 | `blog/urls.py:164-167` | `/clean` 路由直接绑 `clean_cache_view`（一句 `cache.clear()`），**无登录/权限校验** | 任何人访问该 URL 即可清空全站缓存，生产环境可被用来打库 | 未修复（建议修：加 `is_staff` 校验或改用 `manage.py clear_cache`） |
| 6 | `blog/management/commands/sync_user_avatar.py:53` | 裸 `except:` 吞掉所有异常（含 `KeyboardInterrupt`、`SystemExit`） | 命令无法用 Ctrl+C 中断；真实错误被完全掩盖 | 未修复（建议修：改 `except Exception`） |
| 7 | `blog/admin.py:25` | `Category, Tag, Links, SideBar` 四个导入未被使用 | 静态检查报 F401；读者误以为在本文件注册 | 未修复（建议修） |
| 8 | `blog/templatetags/blog_tags.py:27`、`:31` | `hashlib`、`urllib` 导入未使用 | 同上 | 未修复 |
| 9 | `blog/views.py:22`、`:23`、`:26`、`:41`、`:46` | `get_object_or_404`、`render`、`_`、`ARTICLE_CONTENT_HOOK_NAME`、`ArticleListMixin` 导入未使用 | 同上 | 未修复 |
| 10 | `blog/management/commands/build_index.py:30`、`build_search_words.py:25` | 遗留 `# TODO 参数化` | 索引名、词表输出路径写死在代码里 | 未修复 |
| 11 | `blog/management/commands/create_travel_data.py:58`（314 行）、`create_setup_guide.py:71`（293 行） | 单个 `handle()` 方法超过 290 行，正文是 200 行三引号常量 | 难读、难改一个字（要改代码，不能改数据） | 未修复（建议不改：一次性脚本） |
| 12 | `blog/templatetags/blog_tags.py:872` | 单行 141 字符 | 阅读需横向滚动，diff 噪音大 | 未修复（建议修，仅换行） |
| 13 | `blog/views.py:217`、`:220` | 单行 126 字符，且 `#commentlist-container` 锚点硬编码两处 | 改锚点要改两处，漏一处就跳转错位 | 未修复 |
| 14 | `blog/views.py` 12 处、`blog/templatetags/blog_tags.py` 30 处 | 行尾有多余空格 | 部分编辑器保存即产生无意义 diff | 未修复（属原代码遗留） |
| 15 | `blog/management/commands/build_search_words.py:39` | 用 `print` 而不是 `self.stdout.write` | 违反 Django 命令惯例 | 未修复（建议不改：这里就是要纯文本输出便于重定向） |

---

## ⑥ 改进建议（至少 2 条，按优先级排序）

1. **浏览量改成数据库侧自增（最高性价比）**
   把 `Article.viewed()` 改为 `Article.objects.filter(pk=self.pk).update(views=F('views') + 1)`，彻底消掉读-改-写；`BaseModel.save` 里那段 `update_fields == ['views']` 的特判就可以一并删掉，同时消除魔法字符串与“绕过信号”两个隐患。

2. **给 ES 文档加一致性校验**
   在 `blog/documents.py` 旁边加一个测试：断言 `ArticleDocument` 的字段集合 ⊇ `Article` 里需要被搜索的字段集合（用 `_meta.fields` 对比），模型加字段忘了同步时 CI 直接红。比“靠注释提醒”可靠。

3. **`/clean` 加最小鉴权**
   在 `blog/views.py` 的 `clean_cache_view` 上加 `@login_required` + `request.user.is_staff` 判断，或直接把这条路由删掉、统一用已有的 `python manage.py clear_cache`（`blog/management/commands/clear_cache.py` 已经实现了同样功能）。

4. **把两处 `cache.clear()` 收敛成“按前缀失效”**
   `CacheKey` 已经有 `article_comments_`、`sidebar` 这类前缀，理论上可以只清受影响的键；退一步也可以在 `djangoblog/utils.py` 里封装一个 `invalidate_blog_settings()`，避免两处（模型 + Admin）各写一份 `cache.clear()`。

5. **超长脚本拆函数（低优先级）**
   `create_travel_data.py` / `create_setup_guide.py` 的 `handle()` 拆成 `ensure_categories()` / `build_body()` / `write_file()`，长正文常量移到 `blog/management/commands/data/*.md`，让“改文案”不再等于“改代码”。

---

## ⑦ 代码体量说明（给报告“代码规模”一节）

| 指标 | 数值 |
| --- | --- |
| 负责文件数 | 20 个（不含 `tests.py`、`test_*.py`、`migrations/`） |
| 注释前物理行 | 3373 行 |
| 当前物理行 | **5338 行**（其中中文注释 2338 行、空行 697 行） |
| **纯代码行（不含注释/空行）** | **2303 行**（其中 docstring 268 行，真正语句约 2035 行） |
| docstring | 268 行（含 31 个空行） |
| 类 / 函数 | 55 个类、131 个函数（含方法） |
| 最大文件 | `blog/templatetags/blog_tags.py`（1167 行，33 个标签，549 行实际代码） |
| 其次 | `blog/models.py`（688 行）、`blog/views.py`（572 行） |
| 最大单个函数 | `create_travel_data.py:58 handle()` 314 行；`create_setup_guide.py:71 handle()` 293 行（其余函数均 < 101 行） |

**与组长基准 3459 行的核对**：那个数大概率是“含注释的物理行”或工具口径（cloc 默认把注释算在注释列、代码列只算语句）。按统一口径复核：
- 这 20 个文件**注释前**物理行 3373 行；
- 剔除注释与空行后 2303 行（含 docstring 268 行）；
- 若把 `blog/tests.py`（305 行）与 6 个 `test_*.py` 一起算，整个 `blog/` 目录是 **40 个 py 文件、8004 物理行、4374 行非注释非空行**。

> 建议报告里统一写成：“`blog` 应用非测试代码 20 个文件、5338 物理行、其中有效代码 2303 行，注释覆盖 2338 行”，并在脚注里说明 3459 行是另一种统计口径，避免两处数字打架。
