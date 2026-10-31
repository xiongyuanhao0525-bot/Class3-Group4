# 信息收集清单 A —— 交纪秀茹（用于《开源软件质量分析报告》）

> 填写人：熊圆好（#xyh）｜ 分析 app：`djangoblog`（公共模块）｜ 日期：2026-10-27
> 本文件为熊圆好个人填写版，已从组内共享模板 `doc/信息收集清单A-交纪秀茹.md` 拆分，直接交纪秀茹即可。

---

## 【熊圆好 · djangoblog】

**① 注释文件清单**（→ 报告"小组分工表"）

| 文件路径 | 注释行数 | 注释标识 |
|---|---|---|
| djangoblog/whoosh_cn_backend.py | 149 | #xyh |
| djangoblog/settings.py | 107 | #xyh |
| djangoblog/utils.py | 61 | #xyh |
| djangoblog/elasticsearch_backend.py | 60 | #xyh |
| djangoblog/blog_signals.py | 54 | #xyh |
| djangoblog/constants.py | 48 | #xyh |
| djangoblog/plugin_manage/base_plugin.py | 36 | #xyh |
| djangoblog/mixins.py | 35 | #xyh |
| djangoblog/logentryadmin.py | 30 | #xyh |
| djangoblog/urls.py | 27 | #xyh |
| djangoblog/sitemap.py | 22 | #xyh |
| djangoblog/plugin_manage/hook_constants.py | 18 | #xyh |
| djangoblog/admin_site.py | 16 | #xyh |
| djangoblog/plugin_manage/loader.py | 16 | #xyh |
| djangoblog/base_views.py | 14 | #xyh |
| djangoblog/feeds.py | 14 | #xyh |
| djangoblog/error_views.py | 11 | #xyh |
| djangoblog/plugin_manage/hooks.py | 10 | #xyh |
| djangoblog/spider_notify.py | 8 | #xyh |
| djangoblog/apps.py | 7 | #xyh |
| djangoblog/wsgi.py | 4 | #xyh |
| **合计（21 个文件）** | **747** | #xyh |

> 详细版另见 `doc/素材/熊圆好/注释文件清单-djangoblog.md`。统计口径：`#xyh` 标记行数；测试文件与 `__init__.py` 不计。

**② 代码风格**（→ "人工分析·代码风格"）

- 命名/行长/缩进：整体遵循 PEP8——类名 PascalCase（`ElasticSearchBackend`）、函数/变量 snake_case、常量全大写（`ALLOWED_TAGS`）；4 空格缩进统一；行长多数 ≤100 字符，少数配置行超 120；模块顺序为 docstring → import → 常量 → 类/函数，统一工整。
- 正例片段 1（`djangoblog/apps.py`，13 行内完成"启动即加载插件"，延迟导入规避循环依赖）：

```python
class DjangoblogAppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'djangoblog'

    def ready(self):                      # app 注册表就绪后仅执行一次
        super().ready()
        from .plugin_manage.loader import load_plugins   # 延迟导入避免循环依赖
        load_plugins()                    # 按 ACTIVE_PLUGINS 白名单加载插件
```

- 正例片段 2（`djangoblog/plugin_manage/hook_constants.py`，事件名/挂件位集中定义，杜绝魔法字符串）：

```python
ARTICLE_CONTENT_HOOK_NAME = "the_content"     # 正文过滤器钩子
POSITION_HOOKS = {                            # 7 个挂件位 → 模板标签注册键
    'article_top': 'article_top_widgets',
    'article_bottom': 'article_bottom_widgets',
    'sidebar': 'sidebar_widgets',
    ...
}
```

- 反例片段 1（`djangoblog/settings.py:189-211`，25 行被注释掉的 Elasticsearch 配置长期滞留源码，属"注释代码"坏味道，应删除或移入部署文档）：

```python
# ELASTICSEARCH_DSL = {
#     'default': {
#         'hosts': 'http://127.0.0.1:9200',
#         'verify_certs': False,
#         ...
#     },
# }
```

- 反例片段 2（`djangoblog/whoosh_cn_backend.py:58`，普通字符串中写正则 `\d`，应使用 raw string，否则触发 `SyntaxWarning: invalid escape sequence '\d'`）：

```python
DATETIME_REGEX = re.compile(
    '^(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})T...')
```

**③ 代码设计**（→ "人工分析·代码设计"）

- 模块拆分合理，共 5 层职责：框架配置层（`settings.py`/`urls.py`/`wsgi.py`）、横切基础设施层（`mixins.py`/`utils.py`/`constants.py`）、事件层（`blog_signals.py`）、后台层（`admin_site.py`/`logentryadmin.py`）、插件框架层（`plugin_manage/` 4 文件）。
- 内聚度高的典型：`plugin_manage` 把"钩子注册表（hooks.py）/ 插件加载（loader.py）/ 插件基类（base_plugin.py）/ 钩子常量（hook_constants.py）"拆得边界清晰，各自单一职责；`base_views.py` 把 CSRF/登录/敏感参数/禁缓存等横切保护收敛到 `dispatch` 层，业务视图继承即得。
- 耦合度：`blog_signals.model_post_save_callback` 以 `isinstance` 分发并直接引用 `comments`/`oauth`/`blog` 多 app 模型，属"事件中心"式集中耦合——换来了各业务模块不必互相调用（调用方解耦），代价是新增模型要改信号函数；`admin_site.py` 星号导入全部 app 的 admin 并集中注册，是全局唯一汇聚点（有意的中心化）。

**④ 编程技能亮点**（→ "人工分析·编程技能"）

1. **WordPress 式钩子系统**（`plugin_manage/hooks.py`）：`register` / `run_action` / `apply_filters` 三件套，动作钩子只做副作用、过滤钩子链式加工，且每个回调 try/except 隔离——**单个坏插件不会拖垮全站**，扩展性设计到位。
   ```python
   for callback in _hooks[hook_name]:
       try:
           value = callback(value, *args, **kwargs)   # 链式加工
       except Exception as e:
           logger.error(...)                          # 坏回调只记日志
   ```
2. **缓存穿透防护**（`utils.cache_decorator`）：用哨兵值 `__default_cache_value__` 缓存 `None` 结果，下次命中直接返回 `None` 而不再查库；键生成优先取对象 `get_cache_key()`，否则用 `(函数, 参数)` 的 SHA256 摘要——**通用且零侵入**。
3. **约定优于配置**（`base_plugin.render_position_widget`）：按位置名反射拼出 `render_{position}_widget` 方法名调用，新增挂件位无需改基类；同一位置多插件按 `POSITION_PRIORITIES` 排序。
4. **Mixin 组合**（`mixins.ArticleListMixin`）：一键组合"优化查询 + 缓存 + 页码"三项能力，业务视图零重复代码。

**⑤ 质量问题清单**（→ "人工分析·代码质量问题"）

| 问题描述 | 位置 | 状态 |
|---|---|---|
| `SECRET_KEY` 带公开默认值，未配置环境变量时签名/会话可被伪造 | settings.py:44-45 | 未修复（建议不改：上游设计，部署须配环境变量；注释已标 ⚠） |
| `DEBUG` 默认 True、`ALLOWED_HOSTS = ['*']` | settings.py:47、52 | 未修复（同上，属部署配置项） |
| 百度主动推送 URL 硬编码 token | settings.py:319-320 | 未修复（建议不改，环境变量已预留 `DJANGO_BAIDU_NOTIFY_URL`） |
| `handle403` 拼写错误（Django 约定为 `handler403`），绑定实际不生效 | urls.py:45 | 未修复（建议改） |
| 非 raw 字符串写 `\d` 正则，触发 SyntaxWarning | whoosh_cn_backend.py:58 | 未修复（建议加 `r` 前缀） |
| 裸 `except:` 吞掉所有异常（含 KeyboardInterrupt） | utils.py:75 | 未修复（建议改 `except Exception`） |
| `model_post_save_callback` 单函数约 110 行、多分支 `isinstance` 分发 | blog_signals.py:81-183 | 未修复（建议拆分重构） |
| `WXADMIN` 默认口令硬编码 | settings.py:335-336 | 未修复（建议不改，环境变量已预留） |

**⑥ 改进建议 ≥2 条**（→ "下一步的改进计划"）

1. **配置外置化与启动校验**：提供 `.env.example`，把 `SECRET_KEY`/`DEBUG`/`ALLOWED_HOSTS`/百度 token/邮件凭据列为必填，`settings.py` 启动时对缺失项直接报错（fail-fast），杜绝"默认值上生产"。
2. **修正隐性缺陷**：`handle403 → handler403`；`whoosh_cn_backend.py` 正则加 `r` 前缀；`utils.cache_decorator` 裸 `except` 收窄为 `except Exception`。
3. **拆分事件中心**：`blog_signals.py` 的 `post_save` 统一回调改为按 `sender` 分别注册多个 `@receiver`，每个模型一个处理函数，降低单函数复杂度、便于单测。

**⑦ 体量数据**（→ "一、待分析开源软件概述"，复核确认）

- `djangoblog` app：非测试 `.py` 文件 **22 个**（不含 `__init__.py` 计 21 个），非测试代码 **3854 行**，主要类 **36 个**；测试 5 个文件约 1795 行。
- 复核意见：与组长统计（27 文件 / 5436 行）的差异源于组长口径含测试文件；**确认无误**。
