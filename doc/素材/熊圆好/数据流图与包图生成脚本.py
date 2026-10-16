# -*- coding: utf-8 -*-
"""数据流图（顶层+0层）与 UML 包图 生成脚本（代做，供审查）"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, FancyArrowPatch, Circle

plt.rcParams["font.family"] = ["Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False
INK = "#1a1a1a"
OUT = r"D:\Documents\qwen-agent\fLMu1oWlVC\default\uml"


def flow(ax, x1, y1, x2, y2, label, fs=9.5, rad=0.0, lx=0, ly=0, dashed=False, color=INK):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=13,
                                 lw=1.2, color=color, linestyle="--" if dashed else "-",
                                 connectionstyle=f"arc3,rad={rad}", zorder=5))
    mx = x1 + (x2 - x1) * 0.5 + (-(y2 - y1)) * rad * 0.5 + lx
    my = y1 + (y2 - y1) * 0.5 + ((x2 - x1)) * rad * 0.5 + ly
    ax.text(mx, my, label, fontsize=fs, ha="center", va="center", zorder=6, color=color,
            bbox=dict(boxstyle="round,pad=0.14", fc="white", ec="none", alpha=0.95))


def ent(ax, x, y, w, h, text, fs=11):
    ax.add_patch(Rectangle((x - w / 2, y - h / 2), w, h, fc="#e8f0fb", ec=INK, lw=1.6, zorder=3))
    ax.text(x, y, text, fontsize=fs, ha="center", va="center", zorder=4, fontweight="bold")


def proc(ax, x, y, r, num, name, fs=10.5):
    ax.add_patch(Circle((x, y), r, fc="#fdf3e3", ec=INK, lw=1.7, zorder=3))
    ax.text(x, y + r * 0.32, name, fontsize=fs, ha="center", va="center", zorder=4, fontweight="bold")
    ax.text(x, y - r * 0.38, num, fontsize=8.5, ha="center", va="center", zorder=4, color="#7a5c00")


def store(ax, x, y, w, h, name, fs=10):
    a, b = name.split("|")
    ax.add_patch(Rectangle((x - w / 2, y - h / 2), w, h, fc="#e9f4f8", ec=INK, lw=1.3, zorder=3))
    ax.plot([x - w / 2, x - w / 2 + 26], [y, y], color=INK, lw=1.3, zorder=4)
    ax.text(x - w / 2 + 13, y + h / 4, a, fontsize=fs - 1.5, ha="center", va="center", zorder=4)
    ax.text(x + 14, y, b, fontsize=fs, ha="center", va="center", zorder=4)


# ============ 图1 顶层上下文图 ============
fig = plt.figure(figsize=(16, 9))
ax = fig.add_axes([0, 0, 1, 1])
ax.set_xlim(0, 1600); ax.set_ylim(0, 900); ax.set_aspect("equal"); ax.axis("off")
ax.text(800, 860, "DjangoBlog 系统 顶层数据流图（上下文图）｜软件工程3班4组", fontsize=15, fontweight="bold", ha="center")
ax.add_patch(Circle((800, 450), 145, fc="#f3ecf7", ec=INK, lw=2.2, zorder=3))
ax.text(800, 468, "DjangoBlog", fontsize=15, ha="center", va="center", fontweight="bold", zorder=4)
ax.text(800, 428, "博客系统", fontsize=13, ha="center", va="center", fontweight="bold", zorder=4)
ent(ax, 250, 745, 260, 64, "游客 / 注册用户")
ent(ax, 1350, 745, 220, 60, "超级管理员")
ent(ax, 210, 170, 300, 64, "第三方平台\n(微博/QQ/GitHub/微信)")
ent(ax, 1390, 170, 240, 60, "SMTP 邮件服务器")
flow(ax, 330, 705, 655, 545, "浏览请求·注册信息·登录凭据\n评论内容·搜索关键词", ly=42)
flow(ax, 655, 555, 330, 740, "文章页·搜索结果\n发布结果·登录状态", ly=-44)
flow(ax, 1270, 725, 945, 555, "文章增删改·分类标签维护\n评论审核·站点配置", ly=40)
flow(ax, 945, 545, 1270, 705, "管理列表·操作反馈", ly=-38)
flow(ax, 330, 205, 670, 355, "OAuth 授权回调\n微信消息", ly=-38)
flow(ax, 670, 345, 330, 195, "授权跳转·机器人应答", ly=36)
flow(ax, 1340, 205, 935, 350, "发送回执", ly=-20)
flow(ax, 935, 340, 1340, 195, "激活/找回密码/审核通知邮件", ly=32)
ax.text(800, 60, "符号：圆＝系统（黑盒）；矩形＝外部实体；箭头＝跨系统边界的数据流（标注流名）。",
        fontsize=10, ha="center", color="#4a5568")
fig.savefig(OUT + r"\数据流图-顶层上下文图.png", dpi=170)

# ============ 图2 0层分解图 ============
fig = plt.figure(figsize=(20, 12))
ax = fig.add_axes([0, 0, 1, 1])
ax.set_xlim(0, 2000); ax.set_ylim(0, 1200); ax.set_aspect("equal"); ax.axis("off")
ax.text(1000, 1165, "DjangoBlog 系统 0 层数据流图（P0 分解）｜软件工程3班4组", fontsize=15, fontweight="bold", ha="center")
ent(ax, 260, 1035, 260, 62, "游客 / 注册用户")
ent(ax, 1060, 1035, 220, 58, "超级管理员")
ent(ax, 1710, 1035, 300, 62, "第三方平台\n(微信/OAuth 五家)")
proc(ax, 260, 820, 68, "P1", "注册与登录")
proc(ax, 640, 820, 68, "P2", "浏览与搜索")
proc(ax, 1010, 820, 68, "P3", "评论互动")
proc(ax, 1390, 820, 68, "P4", "内容管理")
proc(ax, 1710, 820, 68, "P5", "机器人服务")
store(ax, 260, 540, 280, 52, "D1|用户表")
store(ax, 660, 540, 330, 52, "D2|文章/分类/标签表")
store(ax, 1060, 540, 300, 52, "D3|评论/回应表")
store(ax, 1430, 540, 280, 52, "D4|站点配置表")
store(ax, 1740, 540, 260, 52, "D5|授权/运维表")
flow(ax, 235, 1000, 235, 890, "注册信息·登录凭据\n找回密码", lx=-58)
flow(ax, 310, 888, 310, 1000, "会话状态", rad=-0.55, ly=6)
flow(ax, 260, 750, 260, 568, "写入新用户")
flow(ax, 292, 568, 292, 750, None, dashed=True)
flow(ax, 355, 1010, 585, 868, "浏览/搜索请求")
flow(ax, 585, 878, 355, 1018, "文章列表·详情·搜索结果", rad=-0.12, ly=-8)
flow(ax, 640, 750, 660, 568, None)
flow(ax, 700, 568, 665, 750, "文章数据", dashed=True, lx=34)
flow(ax, 710, 820, 940, 820, "详情页含评论区")
flow(ax, 355, 998, 985, 866, "评论内容·表情回应", rad=0.18, ly=8)
flow(ax, 985, 876, 355, 1006, "发布结果(锚点定位)", rad=0.18, ly=8)
flow(ax, 1010, 750, 1060, 568, "新评论(启用/待审)")
flow(ax, 1100, 568, 1015, 750, "已启用评论", dashed=True, lx=30)
flow(ax, 1060, 1000, 1390, 890, "文章增删改·分类标签·审核·配置")
flow(ax, 1340, 888, 1010, 1000, "管理反馈", rad=-0.15, ly=6)
flow(ax, 1350, 752, 730, 548, "写文章+分类标签", rad=0.1, ly=-8)
flow(ax, 1420, 752, 1085, 552, "审核→改启用态", rad=0.1, ly=-6)
flow(ax, 1390, 888, 1430, 568, "写配置(清缓存)", rad=-0.4, lx=26)
flow(ax, 1460, 568, 1460, 750, None, dashed=True)
flow(ax, 1622, 1000, 1690, 890, "微信消息/指令", ly=-14)
flow(ax, 1690, 888, 1622, 1000, "搜文结果·问答回复", rad=-0.4, lx=-20, ly=10)
flow(ax, 1710, 750, 1740, 568, "命令白名单校验")
flow(ax, 1775, 568, 1745, 750, "授权用户记录", dashed=True, lx=28)
ax.text(260, 420, "P1：校验→写D1→邮件激活(SMTP)\n含找回密码/防暴力破解", fontsize=9, ha="center", color="#4a5568")
ax.text(660, 420, "P2：首页/分类/标签/归档/详情\n读D2；搜索经ES/Whoosh索引", fontsize=9, ha="center", color="#4a5568")
ax.text(1060, 420, "P3：登录校验→按D4开关定\n启用态→写D3", fontsize=9, ha="center", color="#4a5568")
ax.text(1430, 420, "P4：仅 is_superuser；写D2·\n审核D3·配置D4", fontsize=9, ha="center", color="#4a5568")
ax.text(1740, 420, "P5：微信webhook→\n搜文/ChatGPT/口令运维", fontsize=9, ha="center", color="#4a5568")
ax.text(1000, 260, "符号：矩形＝外部实体；圆＝加工；双横线框＝数据存储；实线＝写流/主流向，虚线＝读流。\n"
        "存储对照：D1-BlogUser　D2-Article/Category/Tag　D3-Comment/CommentReaction　D4-BlogSettings　D5-OAuthUser/commands",
        fontsize=10, ha="center", color="#4a5568")
fig.savefig(OUT + r"\数据流图-0层分解图.png", dpi=170)

# ============ 图3 UML 包图（网格布局，依赖走邻接/行间通道） ============
fig = plt.figure(figsize=(19, 12.5))
ax = fig.add_axes([0, 0, 1, 1])
ax.set_xlim(0, 1900); ax.set_ylim(0, 1250); ax.set_aspect("equal"); ax.axis("off")
ax.text(950, 1218, "DjangoBlog 系统 UML 包图（应用包全景与依赖）｜软件工程3班4组", fontsize=15, fontweight="bold", ha="center")

PKG = {}


def pkg(key, x, y, w, h, name, items, fc="#fbfcfe"):
    PKG[key] = (x, y, w, h)
    ax.add_patch(Rectangle((x, y), w, h, fc=fc, ec=INK, lw=1.5, zorder=2))
    ax.add_patch(Rectangle((x + 6, y + h - 26), 30, 20, fc="#d9e6f7", ec=INK, lw=1.0, zorder=3))
    ax.text(x + 21, y + h - 16, "«pkg»", fontsize=7, ha="center", va="center", zorder=4)
    ax.text(x + w / 2, y + h - 44, name, fontsize=11.5, fontweight="bold", ha="center", va="center", zorder=4)
    ax.text(x + w / 2, y + (h - 62) / 2 + 2, items, fontsize=8.8, ha="center", va="center", zorder=4, color="#333")


# A 行（表现/扩展）
pkg("templates", 90, 990, 480, 170, "templates（表现层模板）",
    "share_layout/base.html 母版\nblog/ 首页·详情·归档·友链\naccount/ 登录·注册·找回\noauth/ 绑定确认　约30个模板")
pkg("templatetags", 710, 990, 480, 170, "blog/templatetags（模板标签）",
    "blog_tags.py：侧栏组件渲染\nrender_plugin_widgets 插件入口\nvite_tags.py：前端资源打包\ncomments_tags.py：评论树")
pkg("plugins", 1330, 990, 480, 170, "plugins（可插拔扩展）",
    "8 个插件包：copyright·reading_time\nview_count·seo_optimizer\nlazy_loading·recommendation\ncloudflare·external_links", fc="#f6ecec")
# B 行（业务 app）
pkg("blog", 90, 700, 400, 190, "blog（内容核心 app）",
    "models: Article·Category·Tag\nLinks·SideBar·BlogSettings\nviews: Index/Detail/Category\n/Tag/Author/Archives/LinkList\nadmin: 批量发布·评论开关", fc="#fdf3e3")
pkg("comments", 560, 700, 400, 190, "comments（评论 app）",
    "models: Comment·CommentReaction\nviews: CommentPostView\nCommentReactionView\nforms: CommentForm\nparent_comment 自关联回复", fc="#fdf3e3")
pkg("accounts", 1030, 700, 400, 190, "accounts（用户认证 app）",
    "models: BlogUser(AbstractUser)\nviews: Register·Login·Logout\n·ForgetPassword\nSecureFormView 防暴力破解\n邮箱激活/验证码", fc="#fdf3e3")
pkg("oauth", 1500, 700, 310, 190, "oauth（第三方登录）",
    "models: OAuthUser\n·OAuthConfig\noauthmanager:\n5 平台授权策略\n回调自动建号", fc="#fdf3e3")
# C 行（机器人/核心/外部）
pkg("servermanager", 90, 400, 400, 190, "servermanager（微信机器人）",
    "models: commands·EmailSendLog\nrobot.py: werobot 指令\n?搜文·recent·ChatGPT 兜底\n/robot webhook·口令白名单", fc="#fdf3e3")
pkg("djangoblog", 560, 400, 870, 190, "djangoblog（工程核心包）",
    "settings.py: INSTALLED_APPS·中间件链·DB/Redis/ES 配置\nurls.py: 根路由 include 各 app\nutils.py: cache_decorator·get_sha256·send_email·get_blog_setting\nadmin_site.py: 后台 is_superuser 唯一准入　blog_signals.py: 邮件信号", fc="#eef7ec")
pkg("external", 1500, 400, 310, 190, "外部框架与服务",
    "Django 组件\nhaystack·mdeditor\nwerobot·bleach\nMySQL·Redis\nES/Whoosh·SMTP\n微信/五家OAuth", fc="#fafafa")


def dep(a, b, label=None, rad=0.0, sx=None, sy=None, tx=None, ty=None, lx=0, ly=0):
    A, B = PKG[a], PKG[b]
    x1 = sx if sx is not None else A[0] + A[2] / 2
    y1 = sy if sy is not None else A[1]
    x2 = tx if tx is not None else B[0] + B[2] / 2
    y2 = ty if ty is not None else B[1] + B[3]
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=13,
                                 lw=1.2, color=INK, linestyle="--",
                                 connectionstyle=f"arc3,rad={rad}", zorder=5))
    if label:
        mx = x1 + (x2 - x1) / 2 + (-(y2 - y1)) * rad * 0.5 + lx
        my = y1 + (y2 - y1) / 2 + ((x2 - x1)) * rad * 0.5 + ly
        ax.text(mx, my, label, fontsize=8.8, ha="center", va="center", zorder=6, color="#333",
                bbox=dict(boxstyle="round,pad=0.13", fc="white", ec="#c8c8c8", lw=0.6, alpha=0.97))


# A 行横向
dep("templates", "templatetags", "调用自定义标签", sy=1075, ty=1075, ly=16)
dep("templatetags", "plugins", "渲染插件钩子", sy=1075, ty=1075, ly=16)
# B 行横向
dep("comments", "blog", "FK→Article", sy=795, ty=795, ly=16)
dep("comments", "accounts", "FK→BlogUser", sy=760, ty=760, ly=-16)
dep("oauth", "accounts", "建号写用户", sy=800, ty=800, ly=16)
# 纵向：视图渲染模板
dep("blog", "templates", "视图渲染模板", sy=890, ty=990, lx=60)
# B→djangoblog 汇聚（向下）
dep("blog", "djangoblog", "注册于 settings\n路由 include", sy=700, ty=590, lx=-60)
dep("comments", "djangoblog", None, sy=700, ty=590)
dep("accounts", "djangoblog", None, sy=700, ty=590)
dep("oauth", "djangoblog", None, sy=700, ty=590, rad=0.12)
# servermanager 纵向/横向
dep("servermanager", "blog", "机器人查文章", sx=290, sy=590, tx=290, ty=700, lx=68)
dep("servermanager", "djangoblog", None, sx=490, sy=495, tx=560, ty=495)
dep("djangoblog", "external", "依赖框架服务", sx=1430, sy=495, tx=1500, ty=495, ly=16)

ax.text(950, 250, "约定：虚线箭头＝包依赖（依赖者→被依赖者）；«pkg» 标签为 UML 包符号；同包内 Model/View/Admin 相互引用省略；\n"
        "djangoblog 与各业务 app 之间为双向关系（settings 注册 app、app 反向引用 utils 工具），图中统一画为 app→djangoblog 一条。\n"
        "素材对照：模板继承细分包图见 doc/素材/王鑫悦/模板UML包图.png；分层架构见 doc/素材/熊圆好/系统架构图.png。",
        fontsize=9.8, ha="center", color="#4a5568")
fig.savefig(OUT + r"\UML包图-应用包全景.png", dpi=170)
print("DONE3")
