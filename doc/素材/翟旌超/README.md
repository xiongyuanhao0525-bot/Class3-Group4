# 界面流转思维导图 · 翟旌超

- **任务**：3班4组本周任务 —— 小组专属任务「界面流转思维导图」（分工表：翟旌超）
- **交付人**：翟旌超（软件工程 3 班，学号 2415304340）
- **分支**：`ZJC_branch`（**未改动 master、未改任何代码**，只新增 `doc/素材/翟旌超/` 下的素材）
- **依据**：本目录内容全部按仓库**真实**的 `urls.py`、模板和导航栏核对过，不是凭想象画的

## 一、文件清单

| 文件 | 说明 |
| --- | --- |
| `界面流转思维导图.puml` / `.png` / `.svg` | **主交付物**：以「首页」为中心，向外展开所有能跳转到的页面（含 URL、模板） |
| `界面流转图.puml` / `.png` / `.svg` | 辅助图：用箭头表达真实跳转方向，含「评论需登录」的登录闭环 |
| `README.md` | 本说明 + 页面清单/跳转关系表，供组长写《界面设计说明书》时直接引用 |

`.puml` 是 PlantUML 源码，用 VSCode 的 **PlantUML 插件**打开即可修改并重新导出 PNG/SVG；
也可以把源码粘贴到 <https://www.plantuml.com/plantuml> 在线渲染。

重新生成图片的命令（本机需要 Java）：

```bash
java -jar plantuml.jar -charset UTF-8 -tpng 界面流转思维导图.puml
java -jar plantuml.jar -charset UTF-8 -tsvg 界面流转思维导图.puml
```

## 二、页面清单（与纪秀茹的 9 张截图一一对应）

| 页面 | 真实 URL | 模板 | 从哪里进入 |
| --- | --- | --- | --- |
| 首页 | `/` | `blog/article_index.html` | 站点根地址、导航栏 Logo/首页 |
| 文章详情 | `/article/年/月/日/文章id.html` | `blog/article_detail.html` | 首页/列表页/搜索结果点文章标题 |
| 分类页 | `/category/分类名.html` | `blog/article_index.html` | 导航栏分类、文章里的分类名 |
| 标签页 | `/tag/标签名.html` | `blog/article_index.html` | 侧边栏标签云、文章里的标签 |
| 归档页 | `/archives.html` | `blog/article_archives.html` | 导航栏「归档」、页脚「归档」 |
| 友情链接页 | `/links.html` | `blog/links_list.html` | ⚠️ **模板里没有入口链接，只能直接输入网址访问** |
| 搜索页 | `/search?q=关键词` | `search/search.html` | 导航栏搜索框（桌面端/移动端） |
| 登录页 | `/login/` | `account/login.html` | 侧边栏「登录」、发评论未登录时自动跳转 |
| 管理后台 | `/admin/` | Django Admin | 侧边栏「管理后台」（需超级管理员账号） |

补充页面（不在这 9 张里，但存在）：作者页 `/author/用户名.html`、注册页 `/register/`、
忘记密码 `/forget_password/`、首页分页 `/page/页码/`、
分类/标签分页 `/category|tag/名称/页码.html`、错误页 `404/500`、
`/sitemap.xml`、`/feed/`、`/rss/`、`/health/`。

## 三、关键跳转关系（写说明书可直接用）

1. **首页是中心**：首页 → 文章详情、分类页、标签页、归档页、搜索页、登录页，以及首页自身的分页 `/page/页码/`。
2. **列表页 → 详情页**：分类页、标签页、归档页、搜索页里的文章标题都指向文章详情页。
3. **详情页内部跳转**：点作者名 → 作者页；点分类 → 分类页；点标签 → 标签页；
   上一篇/下一篇 → 另一篇文章详情；评论翻页（`?comment_page=N`）；评论点赞。
4. **登录闭环（流程最容易被忽略的一环）**：
   发评论需要登录（`CommentPostView` 继承 `AuthenticatedFormView`）。
   未登录时点「发表评论」→ 跳转 `/login/?next=当前页面` → 登录成功后**自动回到原文章**，不丢阅读位置；
   从侧边栏主动点「登录」时，登录成功后回首页（`success_url='/'`）。
5. **账号相关**：登录页 ↔ 注册页 `/register/`、忘记密码 `/forget_password/`；超管登录后可进 `/admin/`。
6. **公共入口**：`share_layout/base.html` 被所有页面继承，其中
   `nav.html`（导航栏：首页/分类/归档/搜索/独立页面）和 `footer.html`（首页/归档/RSS/工具站/GitHub）
   在每个页面都能用，所以「任意页面 → 这些页面」都是通的。

## 四、备注

- 导航栏里的「工具站」（`tools.lylinux.net`）和页脚的 GitHub 是**站外链接**，不属于站内页面流转。
- `nav.html` 中的「独立页面」（`nav_pages`）由后台配置，本项目默认未配置，所以导图里标注为可选入口。
- 该目录内容为素材，最终由杨杰翰统一命名为 `01-首页.png` 之类并汇总进 `doc/素材/汇总/`。
