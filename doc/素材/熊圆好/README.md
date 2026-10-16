# 熊圆好（组长 xyh）本周任务成果

## 一、个人任务

### 1. TSPI 第 6–9 章阅读
- 第 6 章 软件需求：需求分类（功能/非功能/设计约束）、用例与场景建模
- 第 7 章 理解与表达需求：数据流图、数据字典、实体关系图、状态模型
- 第 8 章 需求验证：评审、原型、可追踪性
- 第 9 章 面向对象需求方法：用例图、参与者、include/extend、泛化
- 组会发言要点：用例编号必须贯穿用例图→用例规约→顺序图，否则交叉引用断裂

### 2. Django 架构熟悉（MVT）
请求链路：urls.py 路由分发 → 中间件链 → View（CBV 为主）→ Model（ORM）→ Template 渲染。
本项目特色：自定义 AdminSite 以 `is_superuser` 收紧后台准入；搜索走 Haystack 双后端（Whoosh/ES）；
Redis 缓存贯穿站点配置、分类树、侧边栏；插件体系通过钩子挂载文章底部/侧栏组件。

### 3. 代码中文标注（认领模块：djangoblog 核心 + blog 中间件）
| 文件 | 标注内容 |
|---|---|
| `blog/middleware.py` | 模块说明 + OnlineMiddleware 页面耗时统计逻辑（ES 落库、占位符替换）逐段注释 |
| `djangoblog/utils.py` | 模块说明 + get_sha256 签名、cache_decorator 缓存装饰器（含防穿透哨兵）、CommonMarkdown、send_email 信号解耦、get_blog_setting 配置单例、头像下载回退、侧栏缓存清理等全部公共函数 |
| `djangoblog/settings.py` | INSTALLED_APPS 逐 app 职责注释；MIDDLEWARE 中间件链执行顺序与各环节作用注释 |

标注原则：只加注释不改逻辑，全部文件通过 `python -m ast` 语法校验。

## 二、小组任务

### 系统架构图（本目录 `系统架构图.png`）
六层结构 + 外部系统侧栏：
1. **接入层**：浏览器读者 / 后台管理员 / 微信公众号粉丝 / 搜索引擎爬虫
2. **表现层**：前台模板、AdminSite 管理台、JSON 接口（表情/图床/搜索）
3. **URL 路由与中间件层**：五个 app 的路由分发、中间件链、CSRF/Session/Auth 防护
4. **业务逻辑层**：blog / accounts / comments / oauth / servermanager 五组视图
5. **领域模型与插件服务层**：六组模型 + 8 个插件钩子
6. **数据与基础设施层**：MySQL、Redis、Whoosh/ES、站点配置单例
右侧外部系统：微信公众平台、五家 OAuth、SMTP、ChatGPT、百度推送。
配套生成脚本：`系统架构图生成脚本.py`（matplotlib，可复现）。

### 数据流图（补交，本目录两张 PNG）
- `数据流图-顶层上下文图.png`：系统黑盒 + 4 外部实体（游客/注册用户、超级管理员、第三方平台、SMTP）+ 8 条边界数据流，Gane-Sarson 记号。
- `数据流图-0层分解图.png`：P0 分解为 P1 注册登录、P2 浏览搜索、P3 评论互动、P4 内容管理、P5 机器人服务五个加工；D1-D5 数据存储与杨杰翰《数据字典.md》模型分组一一对应（D1↔BlogUser、D2↔Article/Category/Tag、D3↔Comment/CommentReaction、D4↔BlogSettings、D5↔OAuthUser/commands），实线为写流、虚线为读流，父子图平衡。

### UML 包图（补交）
- `UML包图-应用包全景.png`：10 个包三行网格布局（表现层 templates/templatetags/plugins → 业务 app blog/comments/accounts/oauth → 支撑层 servermanager/djangoblog/外部框架），虚线箭头只画跨包依赖并标注性质（FK→Article、建号写 BlogUser、渲染插件钩子、settings 注册等）。与王鑫悦《模板UML包图.png》互补：后者细化模板继承，本图为应用包全景。

### 小组统稿
- 泛读报告统稿见 `doc/开源软件泛读报告-DjangoBlog.docx`（与"素材"目录同级，按课程模板六章节组织，嵌入全组素材）。

## 三、协调事项（组长）
- 组会安排：周三代码标注互查 → 周五模型图互查 → 周日统稿泛读报告
- 依赖管控：顺序图（zjc/yjh）已发放 28 用例编号底稿；数据字典（chj）与数据流图（jxr）命名表已对齐
- 本周待办：收齐 6 人 TSPI 笔记 → 汇总泛读报告 → 上传
