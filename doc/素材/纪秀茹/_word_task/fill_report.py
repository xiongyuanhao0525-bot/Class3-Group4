# -*- coding: utf-8 -*-
"""填充 TARGET_DOCX v2：替换占位文本、插图、填分工表（数据来自各成员分支清单A，不新增表格）。"""
import copy
from pathlib import Path
from docx import Document
from docx.text.paragraph import Paragraph
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH

TARGET = Path(r'C:\Users\16570\Class3-Group4\doc\开源软件质量分析报告-DjangoBlog.docx')
IMG = Path(r'C:\Users\16570\Class3-Group4\doc\素材\纪秀茹\数据模型类图.png')

doc = Document(str(TARGET))
paras = doc.paragraphs


def black_run(r_el):
    rPr = r_el.find(qn('w:rPr'))
    if rPr is None:
        rPr = OxmlElement('w:rPr')
        r_el.insert(0, rPr)
    color = rPr.find(qn('w:color'))
    if color is None:
        color = OxmlElement('w:color')
        rPr.append(color)
    color.set(qn('w:val'), '000000')


def set_text(p, text):
    runs = p.runs
    if runs:
        runs[0].text = text
        black_run(runs[0]._r)
        for r in runs[1:]:
            r._r.getparent().remove(r._r)
    else:
        black_run(p.add_run(text)._r)


def insert_after(anchor_p, text):
    new_p_el = OxmlElement('w:p')
    pPr = anchor_p._p.pPr
    if pPr is not None:
        new_p_el.append(copy.deepcopy(pPr))
    anchor_p._p.addnext(new_p_el)
    new_par = Paragraph(new_p_el, anchor_p._parent)
    black_run(new_par.add_run(text)._r)
    return new_par


def set_cell(cell_el, text):
    ps = cell_el.findall(qn('w:p'))
    for p_el in ps[1:]:
        cell_el.remove(p_el)
    p0 = ps[0]
    for r in p0.findall(qn('w:r')):
        p0.remove(r)
    r = OxmlElement('w:r')
    t = OxmlElement('w:t')
    t.text = text
    t.set(qn('xml:space'), 'preserve')
    r.append(t)
    black_run(r)
    p0.append(r)


def ensure_cant_split(tr_el, header=False):
    trPr = tr_el.find(qn('w:trPr'))
    if trPr is None:
        trPr = OxmlElement('w:trPr')
        tr_el.insert(0, trPr)
    if trPr.find(qn('w:cantSplit')) is None:
        trPr.append(OxmlElement('w:cantSplit'))
    if header:
        if trPr.find(qn('w:tblHeader')) is None:
            trPr.append(OxmlElement('w:tblHeader'))
    else:
        th = trPr.find(qn('w:tblHeader'))
        if th is not None:
            trPr.remove(th)


def find_para(prefix):
    for p in paras:
        if p.text.startswith(prefix):
            return p
    raise RuntimeError('not found: ' + prefix)


# ---------- 封面 ----------
set_text(find_para('“***”'), '开源软件质量分析报告')
set_text(find_para('组号：xx'), '组号：3班4组')
set_text(find_para('小组成员：xx'), '小组成员：熊圆好、纪秀茹、陈汉佳、翟旌超、王鑫悦、杨杰翰')

# ---------- 一、待分析开源软件概述 ----------
p7 = find_para('//<介绍待分析程序代码')
set_text(p7, '本次分析的软件是开源博客系统 DjangoBlog。DjangoBlog 是基于 Python 3 与 Django 框架开发的开源博客系统，主要功能包括：文章的分类管理与发布、读者评论与表情互动、分类标签与友链维护、第三方账号（微博/Google/GitHub/Facebook/QQ）OAuth 登录、全文搜索（Whoosh/Elasticsearch）以及微信机器人管理等。')
p7b = insert_after(p7, '项目按 6 个业务应用（app）组织代码，各应用职责单一，代码规模（非测试代码物理行，组长按任务分工方案统计的基准口径）为：blog 应用负责文章、分类、标签与友链，约 3459 行，是最大的模块；djangoblog 应用提供公共基础设施（设置、事件、插件框架、搜索后端等），约 3561 行；oauth 应用实现第三方 OAuth 登录，约 989 行；servermanager 应用实现微信机器人管理，约 378 行，是最小的模块；comments 应用负责评论与表情反应，约 437 行；accounts 应用负责用户注册登录，约 546 行。')
p7c = insert_after(p7b, '代码整体情况：项目采用模型-视图-模板（MVT）分层，模型层基于 Django ORM，视图层以类视图为主。经各组成员统计，全项目约 120 余个类（blog 55 个、djangoblog 36 个、oauth 14 个、servermanager 10 个等）、10 余张数据表。代码整体结构清晰、层次分明，其数据模型类图如图 1 所示。')
p_img = insert_after(p7c, '')
p_img.alignment = WD_ALIGN_PARAGRAPH.CENTER
p_img.add_run().add_picture(str(IMG), width=Cm(14))
p_cap = insert_after(p_img, '图 1　DjangoBlog 数据模型类图（数据来源：依据项目 models 层整理，纪秀茹绘制，2026年10月）')
p_cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
for r in p_cap.runs:
    r.font.size = Pt(10.5)
    r.font.name = 'Times New Roman'
    rPr = r._r.get_or_add_rPr()
    rf = rPr.find(qn('w:rFonts'))
    if rf is None:
        rf = OxmlElement('w:rFonts')
        rPr.append(rf)
    rf.set(qn('w:eastAsia'), '宋体')

# ---------- 二、软件质量分析方法及工具 ----------
set_text(find_para('//<说明分析代码的哪些质量要素'),
         '本项目主要从内部质量与外部质量两个层面分析代码：内部质量重点关注编码风格（是否遵循 PEP8 规范）与设计质量（模块化程度、信息隐藏、内聚度与耦合度）；外部质量重点关注代码中可能存在的缺陷与错误，如异常处理不当、配置安全隐患、潜在越权与资源效率问题。')

set_text(find_para('//<说明采用什么方法来分析代码'),
         '针对内部质量，采用“人工阅读代码+代码静态分析工具”相结合的方法：小组 6 名成员按分工对各自应用逐行精读并添加中文注释（注释统一以“#成员姓名首字母”标识，如 #jxr），在此基础上人工评价编码风格与设计质量；同时运行 Pylint、Flake8 静态分析工具扫描全部代码，得到量化检查结果。针对外部质量，通过人工阅读代码排查潜在缺陷（如异常未捕获、配置硬编码等），并结合 Django 自带测试进行验证。')

set_text(find_para('//<介绍代码质量分析工具'),
         '本项目使用的代码质量分析工具为 Pylint 与 Flake8（由王鑫悦负责对全仓库统一运行并导出结果）：Pylint 4.1.3 是 Python 静态代码分析工具，检查错误类（未定义名字、非法导入等）、风格类（PEP8 违规）、设计类（方法过于复杂等）问题并给出重构建议，输出 0～10 分质量评分；Flake8 7.4.1 集成 PyFlakes 4.0.3（未使用导入、未定义名字等逻辑错误）、pycodestyle 2.15.0（PEP8 风格：行长、缩进、空白）与 McCabe 0.7.0（圈复杂度），在 Python 3.13.16 环境下以行长上限 120 运行，输出“代码/行号/检查码/说明”清单。')

# ---------- 三、人工分析代码的质量情况 ----------
set_text(find_para('//<介绍通过人工阅读代码，所发现的代码质量情况。'),
         '小组全体成员对 6 个应用完成了逐行精读与注释，人工分析结论如下（各应用注释情况见表 1）。')

p24 = find_para('//<介绍相关程序设计语言的编码风格')
set_text(p24, '项目整体遵循 PEP8 编码风格，命名、缩进、行长度规范统一，代码风格良好，仅有少量历史遗留问题。统一采用 4 空格缩进（blog 应用 0 行 Tab）、类名大驼峰、函数与变量小写蛇形、常量全大写，import 分组清晰（标准库→第三方→项目内）。正例方面：blog/models.py 的 viewed() 方法三行说清“浏览量+1”且用 update_fields 显式表达只想改一列；oauth 的 BaseOauthManager 将 AUTH_URL/TOKEN_URL/API_URL/ICON_NAME 四个类属性集中声明，各平台子类只覆盖差异点；servermanager/models.py 每个字段均带中文 verbose_name，urls.py 用 app_name 命名空间隔离路由；djangoblog/apps.py 的 ready() 方法内延迟导入规避循环依赖，hook_constants.py 集中定义钩子常量杜绝魔法字符串。')
p24b = insert_after(p24, '反例方面：blog_tags.py 第 872 行单行 141 字符、views.py 第 217/220 行 126 字符且“#commentlist-container”锚点硬编码两遍，同一模块内 f-string、.format()、% 三种格式化混用，并存在历史拼写错误 commment_list、sidabar_links、ElaspedTimeDocumentManager（不建议改，涉及模板键名与外部引用）；oauth 存在中英混杂的魔法注释（如“facebook 的 token 过长”）与 90+ 字符的 URL 常量行，且项目无统一行宽配置文件；servermanager/robot.py 续行多缩进 14 空格（flake8 E127）并硬编码开发 token；djangoblog/settings.py 有 25 行被注释掉的旧配置、whoosh_cn_backend.py 以非 raw 字符串书写正则 \\d。结论：代码风格总体遵循 PEP8，个别历史遗留问题已登记入改进计划。')

p28 = find_para('//<介绍程序设计的基本原则')
set_text(p28, '项目总体上遵循模块化、信息隐藏、高内聚、低耦合四项设计原则，可维护性较好，存在几处可点名的耦合点。模块化：blog 应用按“路由→视图→模型/模板标签/表单+横切（中间件、搜索、后台、运维命令）”分层清晰；oauth 应用将第三方平台 HTTP 交互细节独立到 oauthmanager.py 策略层，视图层只编排流程；servermanager 的 robot.py 只做消息路由与状态机，api/ 目录按单一职责拆分；djangoblog 分 5 层职责（框架配置/横切基础设施/事件/后台/插件框架）。信息隐藏：djangoblog/base_views.py 把 CSRF、登录校验、禁缓存等横切保护收敛到 dispatch 层；blog 的 BlogSettings 单例把“仅一份配置”约束落在数据层 clean() 与后台三个权限钩子上；vite_tags 的 load_manifest() 收敛 manifest 读取与兜底逻辑。')
p28b = insert_after(p28, '高内聚：blog 的 ElaspedTimeDocumentManager 把建索引/删索引/写记录收在同一个类；oauth 的 BaseOauthManager 采用策略模式+模板方法，5 个平台子类各约 60~90 行只实现差异部分，对修改关闭、对扩展开放；comments 的 Comment 模型以自引用外键实现楼中楼，CommentReaction 用 unique_together 保证同一用户对同一评论的同一表情唯一。低耦合：comments 视图继承 AuthenticatedFormView 复用登录与表单流程；oauth 的 ProxyManagerMixin 利用 Python MRO 组合注入代理能力，零 if-else。不足与耦合点：blog 的 ES 文档字段与 Article 模型字段需手工同步（隐性契约）、load_sidebar 一个标签直接查询文章/分类/标签等 8 类数据、ModelAdmin 定义与注册分离（blog/admin.py 与 djangoblog/admin_site.py 两处）；oauth 5 个子类构造函数前 4 行完全重复（复制粘贴 5 次）、authorize 视图约 100 行承担 8 件事；servermanager 的 BlogApi 直接 import blog ORM，双向耦合；djangoblog 的 blog_signals 事件中心单函数约 110 行集中分发多 app 模型。')

p31 = find_para('//<总结该代码所体现的高水平的编程方法')
set_text(p31, '项目代码体现了多处高水平的编程方法与技能：')
skills = [
    '（1）浏览量单列更新（blog）：BaseModel.save 对 update_fields==[\'views\'] 特判，把最高频的写操作从整行重写降级为单条 UPDATE，写入量与锁范围小一个数量级（其并发隐患见 3.4 第 1 条）。',
    '（2）Vite manifest 三级兜底（blog）：manifest 缺失、JSON 解析失败、入口名不存在三级分别降级，前端构建产物缺失时页面“没样式”而不是“服务器错误”，且开发模式不缓存 manifest、改前端后刷新即生效。',
    '（3）邮箱两级兜底策略（oauth）：GitHub 未公开邮箱时调 /user/emails 接口，一次循环同时实现“主邮箱优先”与“已验证邮箱兜底”，break+elif 配合无多余状态变量，接口异常外层 try 降级为 warning 不阻断登录。',
    '（4）MRO 注入代理能力（oauth）：ProxyManagerMixin 写在基类左边即覆盖 do_get/do_post 为带代理版本，需要代理的平台就混入、不需要就不混入，零基类改动实现能力差异化。',
    '（5）缓存可用性探测（servermanager）：MemcacheStorage 启动时写一个 key 再读回，确认缓存真可用才使用，否则回落到本地文件，比假设“Redis 一定可用”鲁棒。',
    '（6）钩子系统与缓存穿透防护（djangoblog）：plugin_manage/hooks.py 提供 register/run_action/apply_filters 三件套且每个回调 try/except 隔离，单个坏插件不会拖垮全站；utils.cache_decorator 用哨兵值缓存 None 结果防止缓存穿透。',
    '（7）表情反应切换与楼中楼（comments）：CommentReactionView 利用 get_or_create+unique_together 实现“再点一次即取消”；parse_commenttree 递归展开嵌套评论；get_reactions_summary 用 select_related 避免 N+1 查询。',
]
anchor = p31
for s in skills:
    anchor = insert_after(anchor, s)

# ---------- 3.4 代码质量问题（文字列举，不新增表格） ----------
p34 = find_para('//<逐一列举')
set_text(p34, '人工阅读共发现 14 处质量问题或瑕疵（汇总各成员清单 A 与本组精读发现，均只加注释未改逻辑），逐一列举如下（状态说明：“建议修”为低风险高收益；“建议不改”为修复收益小于回归风险）：')
issues = [
    '（1）blog/views.py：浏览量 self.views += 1 后整列回写，读-改-写非原子，并发访问同一文章会少计阅读量。状态：未修复（建议改为 F(\'views\')+1）。',
    '（2）blog/urls.py /clean 路由：直接绑定 cache.clear()，无登录/权限校验，任何人访问即可清空全站缓存。状态：未修复（建议加 is_staff 校验或删除路由）。',
    '（3）blog/templatetags/blog_tags.py:872：单行 141 字符超长。状态：未修复（建议修，仅换行）。',
    '（4）blog/models.py comment_list()：把 QuerySet 直接 cache.set，pickle 反序列化惰性查询集，模型字段变更后旧缓存可能反序列化失败。状态：未修复（建议不改，改动面大）。',
    '（5）blog/admin.py:25 与 blog_tags.py:27/31、views.py:22 等：多处 import 未使用（F401）。状态：未修复（建议修）。',
    '（6）oauthmanager.py get_oauth_apps()：用 __subclasses__() 反射发现策略类，对 import 顺序敏感、不支持多级继承，将来可能静默漏掉平台。状态：未修复（建议显式注册表）。',
    '（7）oauthmanager.py QQ 平台：链式 replace 剥 JSONP 外壳，昵称/字段含 ) 或 ; 会被误删。状态：未修复（建议正则提取）。',
    '（8）oauth/views.py：局部变量名 type 遮蔽 Python 内置函数。状态：未修复（建议改名 oauth_type）。',
    '（9）servermanager/api/commonapi.py：os.popen(cmd) 直接执行命令，未做白名单外转义。状态：建议不改（运维命令为管理员后台受控注册）。',
    '（10）servermanager/robot.py:29：硬编码开发 token 作为环境变量兜底。状态：未修复（生产环境有 env 覆盖）。',
    '（11）djangoblog/settings.py:44-45：SECRET_KEY 带公开默认值，未配置环境变量时签名/会话可被伪造；DEBUG 默认 True、ALLOWED_HOSTS=[\'*\']。状态：未修复（建议部署校验）。',
    '（12）djangoblog/urls.py:45：handle403 拼写错误（Django 约定 handler403），错误页绑定不生效。状态：未修复（建议改）。',
    '（13）comments/views.py:53-54：文章关闭评论时 form_valid 直接 raise ValidationError，可能触发 500。状态：未修复（建议改为表单错误提示）。',
    '（14）comments/utils.py send_comment_email：邮件发送失败仅记日志不阻断主流程。状态：已评估可接受（不改）。',
]
anchor = p34
for s in issues:
    anchor = insert_after(anchor, s)

# ---------- 四、工具分析代码的质量情况 ----------
p37 = find_para('//<概述通过工具分析')
set_text(p37, '按分工，王鑫悦对全仓库 6 个应用统一运行 Pylint 4.1.3 与 Flake8 7.4.1（行长上限 120），结果按 app 导出至 doc/素材/王鑫悦/工具结果/。整体结论：全仓库代码静态质量良好，Pylint 各应用评分均不低于 7.5 分，Flake8 共报告 311 条问题，以风格级问题为主，无严重逻辑错误。')
p37b = insert_after(p37, 'Flake8 结果：6 个应用共 311 条问题，分布为 djangoblog 148 条、blog 109 条、accounts 21 条、oauth 16 条、comments 13 条、servermanager 4 条。问题类型集中于 E501 行超长（主要在 Django 自动生成的迁移文件与既有代码）、F401 未使用导入、F841 未使用变量、F403/F405 星号导入（主要在测试文件）、W291 行尾空格等。其中 servermanager 仅 4 条且均为历史遗留（W391/E127/F841/F401），本次加注释未引入新问题；comments 13 条集中在测试代码与 utils.py 既有行尾空格。')
p37c = insert_after(p37b, 'Pylint 结果：各应用最终评分依次为 accounts 8.04、oauth 7.87、servermanager 7.77、djangoblog 7.63、blog 7.58、comments 7.50。主要扣分项为：部分模块/类/函数缺少 docstring、少量代码行超长、个别未使用变量；Django ORM 的 E1101 no-member 误报在个别应用少量存在。')
p37d = insert_after(p37c, '修复情况：comments 应用文件末尾缺换行（W292）3 处已在本组注释过程中修复（views.py、forms.py、models.py）；其余问题均为历史遗留或风格级建议，已登记入改进计划，未在“只加注释不改逻辑”任务范围内改动。')

# ---------- 五、小组分工 ----------
p40 = find_para('//<列表说明每个成员分析和修复的模块')
set_text(p40, '按分工方案，6 名成员各精读一个应用，分工与注释情况如表 1 所示（数据来自各成员分支提交的清单 A）。')

table1 = doc.tables[0]
rows1 = [
    ('熊圆好', 'djangoblog（公共模块）', 'whoosh_cn_backend.py 1093 行、settings.py 464 行、utils.py/mixins.py 631 行、elasticsearch_backend.py/blog_signals.py/base_views.py/error_views.py/constants.py/logentryadmin.py/admin_site.py/sitemap.py/feeds.py/urls.py/plugin_manage（4 文件）等约 1370 行', '#xyh'),
    ('纪秀茹', 'comments（评论互动）', 'views.py、models.py 共 256 行（陈汉佳已标注发表/回复/表情回应，核对补全）；admin.py/utils.py/templatetags/comments_tags.py/forms.py/urls.py 约 181 行；另编写本质量分析报告', '#jxr'),
    ('翟旌超', 'blog（文章模块）', 'templatetags/blog_tags.py 733 行、models.py 491 行（纪秀茹已标 170 行，补全并保留原标识）、documents.py 254 行、admin.py 202 行、management/commands 约 820 行、vite_tags.py 231 行、urls.py/middleware.py/context_processors.py/forms.py/apps.py/search_indexes.py 约 270 行（views.py 572 行已标注）', '#zjc'),
    ('陈汉佳', 'accounts（用户模块）', 'views.py 226 行、forms.py 117 行、admin.py/utils.py/models.py/user_login_backend.py/urls.py/apps.py 约 203 行；另编写《Python 编码规范》', '#chj'),
    ('王鑫悦', 'servermanager（微信机器人）', 'robot.py 187 行、api/commonapi.py+api/blogapi.py 91 行、models.py/MemcacheStorage.py/admin.py/urls.py/views.py 约 100 行；另对全仓库运行 Pylint+Flake8 并导出结果', '#wxy'),
    ('杨杰翰', 'oauth（第三方登录）', 'oauthmanager.py 524 行、views.py 280 行、models.py/admin.py/urls.py/forms.py/templatetags/oauth_tags.py 约 185 行', '#yjh'),
]
hdr1 = table1.rows[0]
# 表头第4列改短，避免竖排；整个表格不设置跨页重复表头
tcs0 = hdr1._tr.findall(qn('w:tc'))
set_cell(tcs0[3], '代码注释标识')
# 调整列宽：成员/分析模块/主要工作/注释标识（单位 twips，总宽 8862=模板版心）
grid = table1._tbl.find(qn('w:tblGrid'))
cols = grid.findall(qn('w:gridCol'))
widths = ['1200', '1300', '3762', '2600']
for c, w in zip(cols, widths):
    c.set(qn('w:w'), w)
ensure_cant_split(hdr1._tr, header=False)
for row in rows1:
    new_tr = copy.deepcopy(hdr1._tr)
    ensure_cant_split(new_tr, header=False)
    table1._tbl.append(new_tr)
    tcs = new_tr.findall(qn('w:tc'))
    for i, val in enumerate(row):
        set_cell(tcs[i], val)

next_el = table1._tbl.getnext()
while next_el is not None and next_el.tag != qn('w:p'):
    next_el = next_el.getnext()
if next_el is not None:
    note_p = Paragraph(next_el, doc)
    set_text(note_p, '注：注释文件与行数按《第7-8周大作业任务分工方案》分配填写；行数为各 app 非测试代码物理行（组长统计基准），分析素材以各成员提交的清单 A 与王鑫悦工具结果为准。')

# ---------- 六、下一步的改进计划 ----------
p48 = find_para('//<概述下一步将针对系统的哪些功能或不足进行改进')
set_text(p48, '下一步将针对系统的以下 10 个功能或不足进行改进：')
improves = [
    '（1）配置外置化与启动校验（djangoblog）：提供 .env.example，将 SECRET_KEY、DEBUG、ALLOWED_HOSTS、百度 token、邮件凭据列为必填项，settings.py 启动时对缺失项直接报错（fail-fast），杜绝“默认值上生产”。',
    '（2）修正隐性缺陷（djangoblog）：handle403 改为 Django 约定的 handler403；whoosh_cn_backend.py 正则加 r 前缀；utils.cache_decorator 裸 except 收窄为 except Exception。',
    '（3）浏览量改为数据库侧自增（blog）：Article.viewed() 改为 filter(pk=...).update(views=F(\'views\')+1)，消除读-改-写与魔法字符串，并可删除 BaseModel.save 中的特判。',
    '（4）/clean 路由加最小鉴权（blog）：增加 @login_required+is_staff 校验，或删除该路由统一使用已有的 manage.py clear_cache 命令。',
    '（5）ES 文档一致性校验（blog）：在 documents.py 旁增加断言测试，用 _meta.fields 对比 ArticleDocument 与 Article 的可搜索字段集合，模型加字段忘同步时 CI 直接报错。',
    '（6）oauth 平台管理重构：把 5 个子类重复的构造逻辑上提到 BaseOauthManager.__init__；平台注册从 __subclasses__() 反射改为显式注册表（类装饰器维护字典），消除对 import 顺序的依赖。',
    '（7）评论交互与防垃圾（comments）：文章关闭评论时不再抛 ValidationError，改为表单错误提示；结合 is_enable 审核字段增加敏感词自动拦截、评论频率限制与后台批量审核界面。',
    '（8）拆分事件中心（djangoblog）：blog_signals 的 post_save 统一回调改为按 sender 分别注册多个 @receiver，每个模型一个处理函数，降低单函数复杂度、便于单元测试。',
    '（9）工具噪声清理（全仓库）：整理数据库迁移文件超长行；清理测试代码中的未使用导入与变量；为业务类与函数补齐 docstring。',
    '（10）servermanager 命令执行改造：将 os.popen(cmd) 替换为 subprocess.run(shell=False, timeout=30)，加超时与输出截断，防止卡死机器人会话；BlogApi 抽接口以便单测替换。',
]
anchor = p48
for s in improves:
    anchor = insert_after(anchor, s)

doc.save(str(TARGET))
print('saved:', TARGET)
print('paragraphs:', len(doc.paragraphs), 'tables:', len(doc.tables))
