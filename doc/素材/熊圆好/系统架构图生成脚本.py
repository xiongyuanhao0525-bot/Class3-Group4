# -*- coding: utf-8 -*-
"""DjangoBlog 系统架构图（matplotlib 渲染）"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, FancyArrowPatch

plt.rcParams["font.family"] = ["Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False

W, H = 2000, 1150
fig = plt.figure(figsize=(W / 100, H / 100))
ax = fig.add_axes([0, 0, 1, 1])
ax.set_xlim(0, W); ax.set_ylim(0, H); ax.set_aspect("equal"); ax.axis("off")
INK = "#1a1a1a"

LX, LW = 60, 1330


def band(y, h, title, color):
    ax.add_patch(Rectangle((LX, y), LW, h, fc=color, ec=INK, lw=1.4, zorder=1))
    ax.text(LX + 14, y + h - 16, title, fontsize=12.5, fontweight="bold",
            va="top", ha="left", zorder=4)


def cols(items, y, h, gap=14):
    n = len(items)
    w = (LW - 40 - gap * (n - 1)) / n
    out = []
    for i, (t, fs) in enumerate(items):
        x = LX + 20 + i * (w + gap)
        ax.add_patch(Rectangle((x, y), w, h, fc="white", ec=INK, lw=1.1, zorder=2))
        ax.text(x + w / 2, y + h / 2, t, fontsize=fs, ha="center", va="center", zorder=3)
        out.append((x, w))
    return out


def arrow(x1, y1, x2, y2, label=None, color=INK, ls="-", lw=1.4):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=16,
                                 lw=lw, color=color, linestyle=ls, zorder=5))
    if label:
        ax.text((x1 + x2) / 2, (y1 + y2) / 2 + 11, label, fontsize=9, color=color,
                ha="center", va="center", zorder=6,
                bbox=dict(boxstyle="round,pad=0.1", fc="white", ec="none", alpha=0.92))


def poly_arrow(pts, color=INK, lw=1.4):
    for (x1, y1), (x2, y2) in zip(pts, pts[1:-1]):
        ax.plot([x1, x2], [y1, y2], color=color, lw=lw, zorder=5)
    ax.add_patch(FancyArrowPatch(pts[-2], pts[-1], arrowstyle="-|>", mutation_scale=15,
                                 lw=lw, color=color, zorder=5))


ax.text(W / 2, H - 30, "DjangoBlog 系统架构图（软件工程 3 班 4 组 · 熊圆好）",
        fontsize=16, fontweight="bold", ha="center", va="center")

# ===== 六层 =====
band(1000, 92, "接入层（客户端）", "#e8f0fb")
cols([("浏览器读者\n（前台页面）", 10), ("后台管理员\n（/admin 管理台）", 10),
      ("微信公众号\n（服务号粉丝）", 10), ("搜索引擎爬虫\n（sitemap / RSS）", 10)], 1006, 48)

band(880, 104, "表现层（Presentation）", "#eef7ec")
cols([("Django Templates\n博客前台模板", 9.8), ("AdminSite 管理台\n自定义站点（is_superuser 准入）", 9.8),
      ("JSON 接口\n评论表情 / 图片上传 / 搜索", 9.8)], 886, 60)

band(770, 92, "URL 路由与中间件层", "#fdf3e3")
cols([("urls.py 分发\nblog·accounts·comments\noauth·servermanager", 9.4),
      ("中间件链\nSecurity·Common·Online\n（请求耗时统计）", 9.6),
      ("CSRF·Session·Auth\n请求级防护", 9.8)], 776, 48)

band(610, 142, "业务逻辑层（View / Class-Based Views）", "#f3ecf7")
biz = cols([("blog.views\nIndexView·ArticleDetailView\nCategory/Tag/Author/Archives\nEsSearchView·fileupload", 9.3),
            ("accounts.views\nRegister·Login·Logout\nForgetPassword\n邮箱激活验证", 9.3),
            ("comments.views\nCommentPostView\nCommentReactionView\n（登录校验+审核开关）", 9.3),
            ("oauth.views\noauthlogin·authorize\n五种平台授权回调\n邮箱补绑", 9.3),
            ("servermanager\nwerobot 机器人\n?搜索/帮助/ChatGPT\n口令白名单运维", 9.3)], 616, 98)

band(440, 152, "领域模型与插件服务层（Model + Plugins）", "#e9f4f8")
mdl = cols([("blog.models\nArticle·Category·Tag\nLinks·SideBar·BlogSettings", 9.4),
            ("accounts.models\nBlogUser\n（AbstractUser 扩展）", 9.4),
            ("comments.models\nComment·CommentReaction\n（自关联回复/唯一约束）", 9.4),
            ("oauth.models\nOAuthUser·OAuthConfig", 9.4),
            ("plugins 插件钩子\ncopyright·reading_time\nseo·recommendation 等 8 个", 9.4)], 446, 108)

band(310, 112, "数据与基础设施层", "#f6ecec")
data = cols([("MySQL 主数据库\n（Django ORM）", 9.8), ("Redis 缓存\n（配置/评论列表/页面）", 9.8),
             ("Whoosh / Elasticsearch\n全文搜索索引", 9.8), ("站点配置单例\nBlogSettings（禁增删/清缓存）", 9.4)], 316, 68)

# ===== 右侧外部系统 =====
ax.add_patch(Rectangle((1450, 310), 490, 782, fc="#fafafa", ec=INK, lw=1.4, zorder=1))
ax.text(1464, 1092 - 16, "外部系统 / 第三方服务", fontsize=12.5, fontweight="bold", va="top", zorder=4)
ext_boxes = [("微信公众平台 API\n（消息收发 webhook）", 990), ("微博 / Google / GitHub\nQQ / Facebook OAuth", 860),
             ("SMTP 邮件服务\n（激活/找回密码/审核通知）", 730), ("ChatGPT 接口\n（机器人兜底问答）", 600),
             ("百度站长推送\n（ping_baidu）", 470)]
for t, y in ext_boxes:
    ax.add_patch(Rectangle((1470, y), 450, 64, fc="white", ec=INK, lw=1.1, zorder=2))
    ax.text(1695, y + 32, t, fontsize=9.8, ha="center", va="center", zorder=3)
for y, lab in [(1022, "webhook"), (892, "OAuth"), (762, "SMTP"), (632, "AI 对话")]:
    arrow(1390, y, 1468, y, None, color="#2b6cb0")
    ax.text(1429, y + 15, lab, fontsize=8.5, color="#2b6cb0", ha="center", va="center", zorder=6,
            bbox=dict(boxstyle="round,pad=0.08", fc="white", ec="none", alpha=0.92))

# ===== 层间主数据流 =====
arrow(400, 1000, 400, 984, "HTTP 请求 / 响应")
arrow(400, 880, 400, 862, "URL 解析 → 中间件 → 视图")
arrow(620, 770, 620, 752)
arrow(620, 610, 620, 592, "ORM 读写")
arrow(203, 440, 203, 422, None)
arrow(1246, 440, 1246, 422, None)
ax.text(730, 428, "持久化", fontsize=9, va="center", zorder=6,
        bbox=dict(boxstyle="round,pad=0.1", fc="white", ec="none", alpha=0.92))

# ===== 缓存 / 搜索旁路（走列间隙与层间走廊） =====
cx_comments = biz[2][0] + biz[2][1] / 2
cx_oauth = biz[3][0] + biz[3][1] / 2
gap_c3 = (mdl[2][0] + mdl[2][1] + mdl[3][0]) / 2      # 模型层 列3/列4 间隙
gap_c4 = (mdl[3][0] + mdl[3][1] + mdl[4][0]) / 2      # 模型层 列4/列5 间隙
redis_cx = data[1][0] + data[1][1] / 2
es_cx = data[2][0] + data[2][1] / 2
poly_arrow([(cx_comments, 616), (cx_comments, 575), (gap_c3, 575),
            (gap_c3, 430), (redis_cx, 430), (redis_cx, 384)], color="#805ad5")
ax.text((gap_c3 + redis_cx) / 2, 410, "缓存读写", fontsize=9, color="#805ad5",
        ha="center", va="center", zorder=6,
        bbox=dict(boxstyle="round,pad=0.08", fc="white", ec="none", alpha=0.92))
poly_arrow([(cx_oauth, 616), (cx_oauth, 575), (gap_c4, 575),
            (gap_c4, 424), (es_cx, 424), (es_cx, 384)], color="#805ad5")
ax.text((gap_c4 + es_cx) / 2 + 60, 410, "索引查询", fontsize=9, color="#805ad5",
        ha="center", va="center", zorder=6,
        bbox=dict(boxstyle="round,pad=0.08", fc="white", ec="none", alpha=0.92))

# ===== 底部说明 =====
ax.add_patch(Rectangle((60, 190), 1880, 96, fc="white", ec="#8894a6", lw=1))
ax.text(80, 262, "读图要点：", fontsize=11, fontweight="bold", va="center")
ax.text(80, 226, "① 请求自上而下穿过六层：接入 → 表现 → 路由/中间件 → 业务视图 → 模型/插件 → 数据设施；② 后台与前台共用同一套模型，管理台以 is_superuser 作为唯一准入；"
        "③ 搜索、缓存为视图层旁路依赖；④ 外部系统均经业务视图接入，不直接进入模型层。",
        fontsize=10, va="center")
ax.text(60, 150, "图例：淡彩横带＝分层；白框＝组件（框内注明对应代码模块）；蓝色横向箭头＝与外部系统的交互；紫色箭头＝缓存/搜索旁路。",
        fontsize=9.5, va="center", color="#4a5568")

fig.savefig(r"D:\Documents\qwen-agent\fLMu1oWlVC\default\uml\系统架构图.png", dpi=170)
print("OK")
