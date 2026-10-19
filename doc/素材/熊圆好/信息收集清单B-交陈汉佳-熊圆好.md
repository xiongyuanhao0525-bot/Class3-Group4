# 信息收集清单 B —— 交陈汉佳（用于《Python 语言编码规范》）

> 填写人：熊圆好（#xyh）｜ 分析 app：`djangoblog`（公共模块）｜ 日期：2026-10-27
> 本文件为熊圆好个人填写版，已从组内共享模板 `doc/信息收集清单B-交陈汉佳.md` 拆分，直接交陈汉佳即可。
> 代码片段均来自 `djangoblog/`，可直接作为规范各小标题的正例/反例。

---

## 【熊圆好 · djangoblog】

**① 看不下去的编码习惯**（→ 规范各小标题反例）

| 问题类别 | 代码片段（文件:行号） | 一句话说明 |
|---|---|---|
| 注释代码长期滞留 | settings.py:189-211（25 行 `# ELASTICSEARCH_DSL = {...}` 整块注释） | 被注释掉的配置块应删除或移入部署文档，不应留在源码里 |
| 魔法数字/硬编码凭据 | settings.py:319-320：`'http://data.zz.baidu.com/urls?site=...&token=1uAOGrMsUm5syDGn'` | URL 与 token 写死，敏感值必须走环境变量（该文件 WXADMIN 同理） |
| 非 raw 字符串写正则 | whoosh_cn_backend.py:58：`'^(?P<year>\d{4})...'` | 正则中的 `\d` 应写 `r'\d'`，否则触发 SyntaxWarning 且语义易错 |
| 裸 except 吞异常 | utils.py:75：`except:` | 捕获了所有异常（含 KeyboardInterrupt/SystemExit），应写 `except Exception` |
| 超长函数 + 多重分支 | blog_signals.py:81-183 `model_post_save_callback` 约 110 行，`isinstance` 分发 5 类模型 | 建议按 `sender` 拆成多个 `@receiver` 单函数 |
| 拼写错误 | urls.py:45：`handle403 = 'blog.views.permission_denied_view'` | Django 约定名为 `handler403`，拼错导致 403 自定义页不生效 |

**② 值得推广的写法**（→ 规范各小标题正例）

1. **布尔环境变量统一解析**（settings.py:32-34）——避免各配置项各写一套 `== 'True'`：

```python
def env_to_bool(env, default):
    str_val = os.environ.get(env)
    return default if str_val is None else str_val == 'True'
```

2. **WordPress 式钩子三件套**（plugin_manage/hooks.py）——插件可插拔、坏插件不影响主流程：

```python
def register(hook_name: str, callback: callable): ...
def run_action(hook_name: str, *args, **kwargs): ...      # 动作：只做副作用
def apply_filters(hook_name: str, value, *args, **kwargs): ...  # 过滤：链式加工
```

3. **横切保护收敛到 dispatch**（base_views.py）——视图基类统一叠加 CSRF/登录/脱敏/禁缓存装饰器，业务视图继承即得：

```python
@method_decorator(sensitive_post_parameters('password'))
@method_decorator(csrf_protect)
@method_decorator(never_cache)
def dispatch(self, request, *args, **kwargs): ...
```

4. **缓存键集中为格式化模板**（constants.py `CacheKey`）——`'article_comments_{article_id}'` 等集中定义，读写两端引用同一模板，杜绝手拼 key 不一致。

**③ app 特有约定**（→ Django 约定类小节）

- **信号集中注册**：全站自定义信号（`send_email_signal`、`oauth_user_login_signal`）与全部 `@receiver` 集中在 `blog_signals.py`，由 `djangoblog/apps.py` 的 `ready()` 导入完成注册——新增信号/接收器只改这一处。
- **后台集中注册**：`INSTALLED_APPS` 使用 `SimpleAdminConfig` 关闭自动发现，所有 app 的 Admin 类统一 star-import 后在 `admin_site.py` 注册到全局唯一 `admin_site` 单例；准入在 `DjangoBlogAdminSite.has_permission` 收紧为 `is_superuser`。
- **插件目录与加载约定**：`plugins/<slug>/plugin.py` 必须暴露模块级 `plugin` 实例；`settings.ACTIVE_PLUGINS` 白名单控制启用；`loader.py` 按白名单动态导入并校验入口文件存在，单个插件加载失败只记日志不中断启动。
- **钩子常量集中**：事件名/挂件位统一放 `plugin_manage/hook_constants.py`，触发方与注册方都引用常量，避免字符串拼写不一致。
- **无 management command**：`djangoblog` 不含自定义管理命令（运维指令在 `servermanager`），新增命令应放对应业务 app 的 `management/commands/` 下并采用 `create_*`/`build_*` 动词命名（参考 `blog/management/commands/` 现状）。
