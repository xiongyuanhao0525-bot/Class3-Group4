# comments 评论模块功能说明（纪秀茹 · #jxr）

- **模块**：comments（文章评论、楼中楼回复、表情回应）
- **负责人**：纪秀茹（注释与测试标识 `#jxr`）；工作分支 `jxr_branch`
- **配套任务**：第 9 周任务 1.3，对应三个功能点——敏感词过滤、评论审核状态流转、表情回应缺陷修复
- **口径说明**：功能描述以 `comments/` 当前源码为准；测试用例编号与分组来自三个新增测试文件中的 `test_*` 方法；测试结果为上一阶段本地运行记录。

## 一、模块概述

comments 应用提供两类模型与两个接口：

| 模型 / 视图               | 职责                                                                     |
| --------------------- | ---------------------------------------------------------------------- |
| `Comment`             | 评论正文、作者、所属文章、父评论（自引用外键实现楼中楼）、展示开关 `is_enable`、审核状态 `review_status`     |
| `CommentReaction`     | 某用户对某条评论点的某一种表情；联合唯一约束 `comment + user + reaction_type` 保证同一表情只能存在一条记录 |
| `CommentPostView`     | 发表 / 回复评论（`POST /article/<article_id>/postcomment`，登录后可提交）             |
| `CommentReactionView` | 表情回应接口（`GET /comment/<comment_id>/react` 公开查统计；`POST` 登录后切换表情）         |

评论对外可见性以 `is_enable` 为准；`review_status` 为审核三态，与 `is_enable` 在模型保存时自动保持同步，文章列表、模板过滤等旧链路无需改动。

## 二、功能点 1：敏感词过滤

### 2.1 功能描述

用户提交评论时，表单对正文做敏感词检测，按站点配置采用两种处置策略：

- **block（默认，拦截）**：正文命中敏感词则不落库，表单返回校验错误，提示用户修改；错误提示只回显打码后的词，不把违禁词原样弹回页面。
- **mask（替换）**：正文命中但放行，落库前把命中词替换为等长的 `*`，其余正文原样保存。

**配置项**（在 `settings.py` 中可选覆盖）：

| 配置项                           | 说明                                              | 默认                                                 |
| ----------------------------- | ----------------------------------------------- | -------------------------------------------------- |
| `COMMENT_SENSITIVE_WORDS`     | 词库，支持列表 / 元组 / 集合，或逗号、顿号、空白分隔的字符串；配置为空时回退内置最小词库 | 内置 19 个通用垃圾信息词（广告、加微信、刷单、诈骗、色情、spam、casino、porn 等） |
| `COMMENT_SENSITIVE_WORD_MODE` | 处置模式：`block` 或 `mask`；非法配置值一律回退 `block`         | `block`                                            |

**抗绕过处理**：匹配前对正文与词库统一做 NFKC 归一化 + 大小写折叠 + 去除空白 / 标点 / 符号，因此"广 告""广*告""ＧＵＡＮＧＧＡＯ"等拆字、插符号、全角大小写变体同样能命中。词库只放通用垃圾信息关键词，不放入人身攻击词，避免误伤正常讨论。

### 2.2 实现位置

| 文件                            | 职责                                                                                               |
| ----------------------------- | ------------------------------------------------------------------------------------------------ |
| `comments/sensitive_words.py` | 纯函数模块，不依赖数据库：词库与模式读取、归一化、命中检测、区间合并、打码替换、命中提示文案、统一检查入口 `check_comment_body()`                     |
| `comments/forms.py`           | `CommentForm.clean_body()`：非空校验 + 调用 `check_comment_body()`；拦截模式抛 `ValidationError`，替换模式返回脱敏后的正文 |

调用链路：用户提交 → `clean_body()` → `check_comment_body(body)` 返回 `(是否放行, 处置后正文, 命中词, 生效模式)` → 表单翻译为校验错误或改写正文。

### 2.3 测试覆盖（`test_sensitive_words.py`，23 个用例）

| 分组      | 覆盖场景                                                                             | 用例                                                                                                                                                                                                                                                |
| ------- | -------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 词库读取    | 从 settings 列表读取；从配置字符串切分；未配置 / 空配置回退内置词库                                         | `test_get_sensitive_words_from_settings`、`test_get_sensitive_words_from_string`、`test_get_sensitive_words_fallback`                                                                                                                               |
| 模式读取    | 默认模式为 block；非法模式回退 block                                                         | `test_get_filter_mode_default_block`                                                                                                                                                                                                              |
| 命中检测    | 直接命中；空格 / 插符号变体；全角与大小写不敏感；一句话多个命中                                                | `test_find_direct_word`、`test_find_obfuscated_with_space_and_symbol`、`test_find_fullwidth_and_case_insensitive`、`test_find_multiple_words`                                                                                                        |
| 不误伤     | 正常正文不命中                                                                          | `test_no_false_positive`                                                                                                                                                                                                                          |
| mask 替换 | 替换后长度保持不变；变体词整体区间打码；未命中原样返回；同词多次出现分别打码                                           | `test_mask_keeps_length`、`test_mask_obfuscated_span`、`test_mask_without_hit_returns_original`、`test_mask_multiple_occurrences`                                                                                                                    |
| 统一检查入口  | block 命中不放行；mask 命中返回脱敏正文                                                        | `test_check_block_mode`、`test_check_mask_mode`                                                                                                                                                                                                    |
| 提示文案    | 命中词保留首字、其余打码                                                                     | `test_describe_hits`                                                                                                                                                                                                                              |
| 表单层     | block 模式抛校验错误；正常正文通过；空白正文拒绝；mask 模式返回脱敏正文；block 命中不创建评论；mask 模式落库为脱敏正文；既有清洗逻辑仍可用 | `test_block_mode_raises_validation_error`、`test_clean_text_passes`、`test_blank_body_rejected`、`test_mask_mode_returns_masked_body`、`test_block_mode_does_not_create_comment`、`test_mask_mode_stores_masked_body`、`test_clean_comment_still_works` |

## 三、功能点 2：评论审核状态流转

### 3.1 功能描述

`Comment` 新增三态审核字段 `review_status`，与历史展示开关 `is_enable` 双向同步：

| 状态  | 取值         | 前台展示（`is_enable`） | 说明                |
| --- | ---------- | ----------------- | ----------------- |
| 待审  | `pending`  | 否                 | 新建评论默认状态；也可由管理员打回 |
| 通过  | `approved` | 是                 | 对外可见              |
| 拒绝  | `rejected` | 否                 | 明确拒绝展示            |

**初始状态**由站点"先审后发"配置决定：`comment_need_review=True` 时新评论为待审、不可见；否则直接通过、可见。

**模型方法**：`approve()`（通过并可见）、`reject()`（拒绝并隐藏）、`reset_to_pending()`（打回待审并隐藏）。重写 `save()` 保证任何入口写入后三态与展示开关一致：状态变化以 `review_status` 为准反推 `is_enable`；旧代码只改 `is_enable` 时自动反推对应状态；`update_fields` 路径下两个字段一起写入。

**缓存失效**：审核 / 展示状态一旦变化，立即失效该文章的评论页缓存、`comment_list()` 缓存、模板片段缓存与侧边栏"近期评论"缓存。早期 `blog_signals` 只在展示为真时清缓存，改为拒绝 / 待审时不会触发，因此在模型 `save()` 与后台操作中补充了主动清缓存逻辑。

**历史数据迁移**：`migrations/0006_comment_review_status.py` 新增 `review_status` 字段，并把历史 `is_enable=True` 回填为 `approved`、`False` 回填为 `pending`（隐藏的历史评论视为待审，而非拒绝）。

### 3.2 后台操作入口

`comments/admin.py` 为评论后台提供：

- 三个批量动作：审核通过、审核拒绝、打回待审；
- 状态徽标列：待审（琥珀）、通过（绿）、拒绝（红），支持按状态排序；
- 按 `review_status` 与 `is_enable` 双维度筛选；作者、文章两列链接到对应后台编辑页；
- `is_enable` 在后台只读，避免两个开关互相冲突；
- 批量动作逐条 `save()`（不使用 `queryset.update()`），确保缓存失效逻辑被触发；
- 单条删除与批量删除同样清理对应文章的评论缓存。

### 3.3 测试覆盖（`test_review_status.py`，20 个用例）

| 分组               | 覆盖场景                                     | 用例                                                                                                                                                        |
| ---------------- | ---------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 初始状态             | 新建评论默认为待审                                | `test_default_is_pending`                                                                                                                                 |
| 三态方法同步           | 通过同步可见；拒绝同步隐藏；打回待审                       | `test_approve_syncs_enable`、`test_reject_syncs_enable`、`test_reset_to_pending`                                                                            |
| 旧写法兼容            | 直接把 `is_enable=True` 派生为通过；`False` 派生为待审 | `test_legacy_enable_true_derives_approved`、`test_legacy_enable_false_derives_pending`                                                                     |
| 双字段变更            | 状态与开关同时变化时以审核状态为准                        | `test_status_wins_when_both_changed`                                                                                                                      |
| update_fields 路径 | 部分字段保存时两字段仍保持同步                          | `test_update_fields_path_keeps_fields_in_sync`                                                                                                            |
| 视图初始状态           | 需审核 → 待审；不需审核 → 通过                       | `test_need_review_creates_pending`、`test_no_review_creates_approved`                                                                                      |
| 前台可见性            | 待审评论不进入文章评论列表；通过评论进入列表                   | `test_pending_comment_not_in_article_list`、`test_approved_comment_in_article_list`                                                                        |
| 后台批量动作           | 通过动作；拒绝动作清除评论列表缓存；打回待审动作                 | `test_approve_action`、`test_reject_action_clears_cached_list`、`test_reset_action`                                                                         |
| 后台单条修改           | 拒绝后清缓存；打回待审清缓存；通过后评论可见                   | `test_change_form_reject_clears_comment_list_cache`、`test_change_form_pending_clears_comment_list_cache`、`test_change_form_approve_makes_comment_visible` |
| 后台删除             | 删除已通过评论后清除缓存                             | `test_delete_approved_comment_clears_cache`                                                                                                               |
| 后台展示             | 状态列在列表页渲染                                | `test_status_column_rendered`                                                                                                                             |

## 四、功能点 3：表情回应缺陷修复

### 4.1 修复前的已知问题

1. **查询次数偏高**：原实现先按表情分组，再对每种表情各查一次用户列表、各查一次是否已点；一条评论最多 8 种表情时最多发出 17 条 SQL。
2. **返回键不稳定**：没有回应的表情不出现在返回结果中，前端最后一个回应取消后该键突然消失。
3. **并发切换报错**：切换表情用 `get_or_create` 判断，两个请求同时到达可能都尝试插入，触发唯一约束报错并返回 500。
4. **异常分支非 JSON**：评论不存在、类型非法、未登录等分支可能返回 HTML 错误页，前端 `res.json()` 解析失败。

### 4.2 修复后行为

- **查询优化**：`get_reactions_summary()` 用 1 条 SQL 取回全部回应并在内存中分组计数、整理前 10 位用户名；登录用户再补 1 条 SQL 查询自己点过哪些表情（匿名用户共 1 条，登录用户共 2 条）。
- **固定返回全部表情**：按 `REACTION_CHOICES` 顺序输出 8 种表情（👍 👎 ❤️ 😄 🎉 😕 🚀 👀），无回应的表情返回 `count=0`，前端可直接按键取值。
- **切换语义与并发兜底**：`POST` 先查后写，已存在则删除（取消）、不存在则新增；整体放入事务，捕获 `IntegrityError`，极端并发下唯一约束挡下重复插入时按"已添加"返回，不再把 500 抛给前端。
- **JSON 契约**：`GET` 公开访问；`POST` 需登录（未登录返回 401 JSON）；表情类型必须是预设表情之一（非法返回 400 JSON）；只允许对已通过审核（`is_enable=True`）的评论回应，待审 / 拒绝评论与不存在评论统一返回 404 JSON。
- 响应体中 `GET` 与 `POST` 共用同一组装方法，保证两处字段一致；`POST` 额外返回 `action`（`added` / `removed`）。

### 4.3 测试覆盖（`test_reactions.py`，13 个用例）

| 分组         | 覆盖场景                                             | 用例                                                                                                                                  |
| ---------- | ------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------- |
| 查询次数       | 匿名用户汇总 1 条 SQL；登录用户汇总 2 条 SQL                    | `test_anonymous_summary_uses_single_query`、`test_authenticated_summary_uses_two_queries`                                            |
| 用户预览       | 预览顺序稳定；每种表情预览用户上限 10 人                           | `test_user_preview_order_is_stable`、`test_user_preview_limited_to_ten`                                                              |
| 空汇总        | 无回应时返回全 0 的固定结构                                  | `test_empty_summary`                                                                                                                |
| GET 接口     | 返回含可用表情列表的 JSON；不存在评论返回 JSON 404；待审评论返回 404      | `test_get_returns_json_with_available_reactions`、`test_get_missing_comment_returns_json_404`、`test_get_pending_comment_returns_404` |
| POST 鉴权与校验 | 未登录返回鉴权错误；非法表情类型返回 `success` 字段；不存在评论返回 JSON 404 | `test_post_requires_login`、`test_post_invalid_type_has_success_field`、`test_post_missing_comment_returns_404`                       |
| 切换行为       | 同一表情先加后取消；不同表情互不影响                               | `test_add_then_remove`、`test_different_emojis_are_independent`                                                                      |

## 五、涉及文件清单

| 文件                                                  | 职责                                              |
| --------------------------------------------------- | ----------------------------------------------- |
| `comments/sensitive_words.py`                       | 敏感词词库、归一化、命中检测、打码替换与统一检查入口                      |
| `comments/forms.py`                                 | 评论提交表单；正文非空校验 + 敏感词处置                           |
| `comments/models.py`                                | `Comment` / `CommentReaction` 模型；三态同步、缓存失效、表情汇总 |
| `comments/admin.py`                                 | 评论与表情回应后台；三态批量动作、状态徽标、缓存清理                      |
| `comments/views.py`                                 | 评论提交视图；表情回应 JSON 接口（查询、切换、鉴权与异常契约）              |
| `comments/utils.py`                                 | 文章评论相关缓存失效；评论 / 回复通知邮件（失败仅记日志）                  |
| `comments/urls.py`                                  | `postcomment`、`comment_react` 两条路由              |
| `comments/migrations/0006_comment_review_status.py` | 三态字段迁移与历史数据回填                                   |
| `comments/test_sensitive_words.py`                  | 敏感词过滤测试（23 例）                                   |
| `comments/test_review_status.py`                    | 审核状态流转测试（20 例）                                  |
| `comments/test_reactions.py`                        | 表情回应测试（13 例）                                    |

## 六、测试与验证情况

- 本轮新增 3 个测试文件，共 **56 个**用例（敏感词 23、审核状态 20、表情回应 13）；测试基于 Django `TestCase`，随对应功能提交到 `jxr_branch`。
- 加上 comments 既有测试文件（`test_comment_business_logic.py`、`test_views.py`、`tests.py`），上一阶段本地运行 comments 全量测试结果为 **Ran 92 tests, OK**。
- 既有测试文件不属于本轮新增；本轮改动未修改任何业务逻辑之外的既有行为，审核状态以 `is_enable` 作为对外可见性判断，旧查询链路保持不变。

## 七、遗留边界

1. `views.py:53-54`：文章关闭评论时 `form_valid` 直接抛出 `ValidationError`，可能触发 500；报告建议改为表单错误提示。
2. `utils.py` `send_comment_email`：邮件发送失败仅记录日志、不阻断主流程；经评估该行为可接受，保留现状。
3. `models.py` `comment_list()` 直接缓存 QuerySet，存在 pickle 反序列化隐患；报告评估改动面大，列为建议不改的历史项。
