# ============================================================
# blog/templatetags/vite_tags.py —— 让 Django 模板能加载 Vite 构建出来的前端资源
# 作用：前端用 Vite 打包（源码 src/main.js → 产物 dist/js/main-<hash>.js）。Vite 每次构建都会
#       把产物文件名换成带内容 hash 的新名字，模板里没法写死路径；本文件读取 Vite 构建时生成的
#       manifest.json（构建清单：入口名 → 真实文件名 的映射表），把 {% vite_js %} 自动翻译成
#       正确的 <script>/<link> 标签，并负责“开发模式 / 生产模式”两套加载方式的切换。
# 被谁用：templates/share_layout/base.html（第 154 行）、templates/share_layout/base_account.html
#         （第 47 行）—— 这两个模板开头先 {% load vite_tags %}，然后在 <head> 里
#         {% vite_js 'src/main.js' %}；开发服务器地址来自 djangoblog/settings.py 的 VITE_DEV_SERVER_URL。
# 本文件包含：
#   - load_manifest：读取并（仅生产模式）缓存 manifest.json，出错统一降级成空字典
#   - vite_asset：只返回资源 URL，不生成 HTML 标签
#   - vite_js：输出 <script type="module">，并把该入口附带的 CSS 一起输出
#   - vite_css：输出单独的 <link rel="stylesheet">
#   - vite_preload：输出 preload / modulepreload，让浏览器提前抓关键资源
#   - is_vite_dev_mode：模板里判断当前是不是 Vite 开发模式
#   - vite_dev_server_url：输出 Vite 开发服务器地址
# 注释人：翟旌超（软件工程 3 班 2415304340，#zjc）
# 说明：本次任务只添加中文注释，没有改动任何一行原有代码逻辑
# ============================================================
"""
Vite资源加载Django模板标签
用于在Django模板中加载Vite构建的前端资源

使用方法：
    {% load vite_tags %}
    {% vite_js 'src/main.js' %}
    {% vite_css 'src/styles/main.css' %}
"""

# —— Python 标准库 ——
# json：解析 manifest.json；os：拼 manifest 的文件路径（用 os.path.join，Windows / Linux 都对）
import json
import os

# —— Django 框架自带模块 ——
# template：模板标签库的入口，下面的 register 就是它提供的 Library 实例；
# settings：读 DEBUG 与 VITE_DEV_SERVER_URL 两项配置；
# mark_safe：把手工拼好的 HTML 标记成“安全字符串”，模板输出时不再做 HTML 转义；
# static：把“静态文件相对路径”补成 STATIC_URL 开头的可访问地址
from django import template

from django.conf import settings
from django.utils.safestring import mark_safe
from django.templatetags.static import static

# —— 补充导入：日志（Python 标准库，位置沿用原文件的写法）——
# logging：本文件是“前端资源加载失败”这类问题的第一现场，
# manifest 缺失 / 解析失败 / 入口找不到都从这里打日志，页面白屏时先看这条线
import logging

# 模板标签库的“注册表”：下面每个 @register.simple_tag 装饰的函数都会登记到它上面，
# 模板里 {% load vite_tags %} 之后就能按函数名调用（标签名默认就是函数名）
register = template.Library()
# 按模块名取日志器，日志里能直接看出是哪一块代码出的问题
logger = logging.getLogger(__name__)

# 缓存manifest内容
# 模块级全局变量（一个进程内只有一份）：生产模式下第一次读到的 manifest 存这里，
# 之后所有页面渲染都直接复用，不再重复“读磁盘 + 解析 JSON”。
# 开发模式下故意不缓存，原因见 load_manifest() 开头的判断
_manifest_cache = None


# ------------------------------------------------------------
# —— manifest 读取层：下面所有标签的数据来源 ——
# manifest.json 是 Vite 构建产物里的“清单”，仓库里现在是这个结构（key 是入口名，值是该项的构建信息）：
# {
#   "src/main.js": {
#     "file": "js/main-D8ugGE-1.js",      ← 真正产出的文件，名字带内容 hash（内容一变名字就变）
#     "name": "main",                     ← chunk 名
#     "src": "src/main.js",               ← 源码入口，和 key 一致
#     "isEntry": true,                    ← 是不是入口 chunk
#     "css": ["css/main-O2BVLqTd.css"]    ← 这个入口“顺带”产出的 CSS（JS 里 import 的样式被抽出来的）
#   }
# }
# 所以模板里传的 'src/main.js' 必须和这里的 key 一模一样，写错就会“查不到入口”。
# 为什么要这么绕：文件名带 hash 是为了让浏览器敢长期缓存（内容一变 URL 就变），
# 代价是模板不可能预知文件名 —— manifest 就是“源码路径 → 带 hash 产物路径”的对照表。
# ------------------------------------------------------------

# 【load_manifest】—— 读取 manifest.json，返回“入口名 → 构建信息”的字典
# 参数：无（路径由 settings.BASE_DIR 拼出来）
# 返回：dict：解析成功返回清单内容；文件不存在、或 JSON 坏掉，都返回 {}（空字典）
# 说明：返回 {} 在本文件里是一句“暗号”——所有标签看到空字典就当作处于开发模式，
#       转而去连 Vite 开发服务器。先把异常收干净再返回空，模板渲染才不会 500。
def load_manifest():
    """
    加载Vite生成的manifest.json文件
    包含所有构建资源的映射关系
    """
    global _manifest_cache

    # 开发模式下不使用缓存，每次都重新读取
    # 生产模式下使用缓存提高性能
    # DEBUG=True（开发）时这段永远不生效：每次调用都重新读文件，
    # 这样 Vite 重新构建了一次 manifest，页面刷新就能立刻用上新文件名，不用重启 Django
    if not settings.DEBUG and _manifest_cache is not None:
        return _manifest_cache

    # manifest文件路径
    # 放在 .vite/ 子目录是 Vite 5+ 的默认约定（vite.config 里打开 build.manifest 才会生成该文件）；
    # 用 settings.BASE_DIR 拼绝对路径，所以从哪个目录启动 manage.py 都能找对
    manifest_path = os.path.join(
        settings.BASE_DIR,
        'blog/static/blog/dist/.vite/manifest.json'
    )

    # 把“读文件 + 解析 JSON”一起包进 try：开发环境很可能还没构建过（文件不存在），
    # 或者构建到一半文件残缺（JSON 不合法）。这两种都只说明“暂时没有清单”，
    # 属于预期情况，靠下面的 except 降级处理，绝不能让页面报错
    try:
        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest = json.load(f)
            # 仅在生产模式下缓存
            if not settings.DEBUG:
                # 直接写全局变量；下次调用命中开头那句缓存判断就返回
                _manifest_cache = manifest
            logger.info(f'✅ Vite manifest loaded from: {manifest_path}')
            return manifest
    # 兜底 1：文件不存在 —— 开发模式最常见（还没跑 npm run build），
    # 提示去看 Vite dev server，而不是把它当成错误
    except FileNotFoundError:
        # 开发模式下manifest可能不存在
        logger.warning(f'⚠️  Vite manifest not found: {manifest_path}')
        logger.warning('🔧 Running in development mode. Make sure Vite dev server is running.')
        return {}
    # 兜底 2：文件在、但内容不是合法 JSON（构建被中断、手工改坏）——
    # 记一条 error 便于排查，返回值同样降级成 {}，页面照常渲染
    except json.JSONDecodeError as e:
        logger.error(f'❌ Failed to parse manifest.json: {e}')
        return {}


# ------------------------------------------------------------
# —— 模板标签层：下面每个函数都用 @register.simple_tag 注册成模板标签 ——
# simple_tag 干了什么：把一个普通 Python 函数变成模板里可直接调用的标签。
#   模板里写 {% vite_js 'src/main.js' %}，Django 就替你调用 vite_js('src/main.js')，
#   并把返回值直接输出到页面；也可以 {% vite_js 'src/main.js' as s %} 只取返回值不输出。
# 用它可以不用写自定义标签的解析器（tag 类那种复杂写法），参数照样能传。
# 两条必须牢记的规矩：
#   1) 标签返回值默认会被 HTML 转义（< > & 变成 &lt; 这类实体），所以凡是返回“HTML 片段”的，
#      都要套一层 mark_safe(...)，告诉 Django“这段是我自己拼的可信 HTML，别转义”；
#   2) 模板顶部必须先 {% load vite_tags %}（把本文件注册的标签加载进当前模板）才能用，
#      这一步写在 base.html / base_account.html 的开头。
# ------------------------------------------------------------

# 【vite_asset】—— 只算出一个资源 URL，不生成 HTML 标签
# 参数：entry_name（str）：manifest 里的入口名，如 'src/main.js'
# 返回：str：生产模式返回带 hash 的静态地址，如 /static/blog/dist/js/main-D8ugGE-1.js；
#       清单里没有这个入口时，退化成“开发服务器地址 + 入口名”
# 说明：返回值是纯 URL（没有 mark_safe），适合放进 <img src>、CSS、或 as 变量后再使用
@register.simple_tag
def vite_asset(entry_name):
    """
    获取Vite构建资源的URL

    Args:
        entry_name: 入口文件名，如 'src/main.js'

    Returns:
        资源URL

    用法：
        {% vite_asset 'src/main.js' %}
    """
    manifest = load_manifest()

    # 生产模式：清单里有这个入口，就取它本次构建产出的真实文件名
    if entry_name in manifest:
        # 形如 'js/main-D8ugGE-1.js'，hash 保证长缓存不会读到旧文件
        file_path = manifest[entry_name]['file']
        # 交给 static() 补成 STATIC_URL 开头的地址：/static/blog/dist/js/main-D8ugGE-1.js
        # （文件实际在 blog/static/blog/dist/ 下，Django 的静态文件机制负责对上）
        return static(f'blog/dist/{file_path}')

    # 开发模式回退到Vite开发服务器
    vite_dev_server = getattr(settings, 'VITE_DEV_SERVER_URL', 'http://localhost:5173')
    return f'{vite_dev_server}/{entry_name}'


# 【vite_js】—— 输出加载前端入口 JS 的 <script> 标签（开发/生产两条路径）
# 参数：entry_name（str）：入口名，默认 'src/main.js'（和 manifest 里的 key 对应）
# 返回：str：一段 HTML 片段，已用 mark_safe 标记为安全
# 说明：模板里的典型写法（本项目的 templates/share_layout/base.html 第 154 行就是这么用的，
#       位置在 <head> 里、紧跟样式表之后）：
#       {% load vite_tags %}
#       <head>
#         <link rel="stylesheet" ...>
#         {% vite_js 'src/main.js' %}
#       </head>
#   为什么敢放在 <head>：这个标签同时输出 CSS，放前面样式能更早生效、少一次样式闪烁；
#   而 <script type="module"> 天生延迟执行（defer 语义），放 head 也不会阻塞 HTML 解析。
#   同一个标签还顺便负责输出这个入口的 CSS —— 见下面“收集所有CSS文件”那一段的说明。
@register.simple_tag
def vite_js(entry_name='src/main.js'):
    """
    加载Vite构建的JavaScript资源

    在开发模式下，会加载Vite开发服务器的资源（带HMR）
    在生产模式下，会加载构建后的资源

    Args:
        entry_name: 入口文件名，默认 'src/main.js'

    Returns:
        HTML script标签

    用法：
        {% vite_js 'src/main.js' %}
    """
    manifest = load_manifest()

    # 开发模式：使用Vite开发服务器
    # 判断依据是“清单为空”。开发时根本不构建、也就没有 manifest，于是自动走这条分支
    if not manifest:
        # 优先读 settings.VITE_DEV_SERVER_URL（djangoblog/settings.py 里配的是 http://localhost:5173）；
        # 没配就用 Vite 的默认端口 5173 兜底，保证老环境也不会因为缺这项配置而抛 AttributeError
        vite_dev_server = getattr(settings, 'VITE_DEV_SERVER_URL', 'http://localhost:5173')
        # /@vite/client 是 Vite 注入的客户端脚本：负责热更新（HMR，改代码后浏览器自动刷新/替换模块），
        # 必须排在业务入口之前加载，后面的 src/main.js 才能连上它建立的 WebSocket；
        # type="module"：Vite 产出的是 ES Module，浏览器要按模块方式加载；
        # mark_safe：这整段是手拼的 HTML，不标记就会被转义成 &lt;script&gt; 文本直接显示在页面上
        return mark_safe(f'''
            <!-- Vite开发模式 -->
            <script type="module" src="{vite_dev_server}/@vite/client"></script>
            <script type="module" src="{vite_dev_server}/{entry_name}"></script>
        ''')

    # 生产模式：使用构建后的文件
    # 兜底：清单读到了、但没有这个入口（入口名写错 / 该 chunk 被删掉）——
    # 记一条 error 再说，返回空串：页面顶多少了 JS，而不是让整个模板渲染失败
    if entry_name not in manifest:
        logger.error(f'❌ Entry "{entry_name}" not found in manifest')
        return ''

    # 这一项的完整构建信息（file / css / isEntry ...）
    entry_data = manifest[entry_name]
    file_path = entry_data['file']
    js_url = static(f'blog/dist/{file_path}')

    # 收集所有CSS文件
    # 为什么 JS 标签里要管 CSS：Vite 会把 src/main.js 里 import 的样式抽成独立的 .css 文件，
    # 清单的 css 字段记着它们。生产环境直接用 <link> 引进来，样式能和 HTML 一起到达，
    # 不会出现“先裸屏、JS 跑起来才套上样式”的闪一下（FOUC），也少一次由 JS 动态插标签的请求
    css_html = ''
    if 'css' in entry_data:
        for css_file in entry_data['css']:
            css_url = static(f'blog/dist/{css_file}')
            # 逐条拼成 <link>；末尾的 \n 让最终 HTML 一个标签占一行，方便在浏览器里查看源码
            css_html += f'    <link rel="stylesheet" href="{css_url}">\n'

    # 生产模式输出：先把 CSS 摆好（样式先就位），再引带 hash 的 JS；
    # crossorigin：模块脚本按 CORS 规则加载，带这个属性浏览器才会给出准确的报错信息
    return mark_safe(f'''
    <!-- Vite生产模式 -->
{css_html}    <script type="module" crossorigin src="{js_url}"></script>
''')


# 【vite_css】—— 单独输出某个 CSS 入口的 <link> 标签
# 参数：entry_name（str）：CSS 入口名，默认 'src/styles/main.css'
# 返回：str：生产模式返回 <link rel="stylesheet" ...>；开发模式返回空串
# 说明：只在“需要单独控制某个 CSS 文件”时才用（比如只给某页加一张表）；
#       常规情况用 vite_js 就够了 —— 它会把入口依赖的 CSS 一并输出，不会重复加载。
#       用法：{% vite_css 'src/styles/main.css' %}
@register.simple_tag
def vite_css(entry_name='src/styles/main.css'):
    """
    加载Vite构建的CSS资源

    注意：在开发模式下，CSS通过JS注入，不需要单独加载

    Args:
        entry_name: 入口文件名，默认 'src/styles/main.css'

    Returns:
        HTML link标签

    用法：
        {% vite_css 'src/styles/main.css' %}
    """
    manifest = load_manifest()

    # 开发模式：CSS通过Vite的HMR自动注入
    # 所以这里返回空串（不是漏写）：开发时样式由 vite_js 引入的 @vite/client 动态插进去，
    # 再额外输出一个 <link> 反而会和热更新插入的样式重复
    if not manifest:
        return ''

    # 生产模式：加载构建后的CSS
    # 兜底同 vite_js：入口不存在就只打日志、返回空串，不让模板抛异常
    if entry_name not in manifest:
        logger.error(f'❌ Entry "{entry_name}" not found in manifest')
        return ''

    file_path = manifest[entry_name]['file']
    css_url = static(f'blog/dist/{file_path}')
    return mark_safe(f'<link rel="stylesheet" href="{css_url}">')


# 【vite_preload】—— 输出“预加载”标签，让浏览器在解析到正式标签之前就开始下载关键资源
# 参数：entry_name（str）：入口名（没给默认值，必须显式传）
# 返回：str：<link rel="modulepreload"> / <link rel="preload" as="style"> 等；取不到就返回空串
# 说明：preload 只是“提前抓”，不会执行；它和上面加载标签的关系是“并行下载、稍后复用”，
#       属于性能优化手段，可加可不加，去掉页面照样能用。
#       用法：{% vite_preload 'src/main.js' %}（一般放在 <head> 里）
@register.simple_tag
def vite_preload(entry_name):
    """
    预加载Vite资源

    用于优化关键资源的加载速度

    Args:
        entry_name: 入口文件名

    Returns:
        HTML link preload标签

    用法：
        {% vite_preload 'src/main.js' %}
    """
    manifest = load_manifest()

    # 开发模式（清单为空）或入口不存在，都返回空串：
    # 开发时资源由 dev server 即时编译，预加载没有意义，多输出只会报 404
    if not manifest or entry_name not in manifest:
        return ''

    file_path = manifest[entry_name]['file']
    url = static(f'blog/dist/{file_path}')

    # 根据文件类型决定预加载方式
    # .js 用 modulepreload：它懂 ES Module 的依赖图，能把 import 出去的兄弟模块也一起预取，
    #   普通 preload 抓回来的模块脚本浏览器不一定复用，白下一遍；
    # .css 用 as="style"：告诉浏览器这是样式表，按样式优先级抓取，别当成普通二进制下载；
    # 其他类型（图片、字体等）只做最普通的提前下载
    if file_path.endswith('.js'):
        return mark_safe(f'<link rel="modulepreload" crossorigin href="{url}">')
    elif file_path.endswith('.css'):
        return mark_safe(f'<link rel="preload" href="{url}" as="style">')
    else:
        return mark_safe(f'<link rel="preload" href="{url}">')


# 【is_vite_dev_mode】—— 模板里判断“当前是不是 Vite 开发模式”，给 {% if %} 用
# 参数：无
# 返回：bool：是开发模式返回 True
# 说明：判断标准跟其他标签保持一致 —— 有 manifest 就是生产构建，没有就是开发模式。
#       模板里先用 as 把结果存进变量再判断，写法如下：
#       {% is_vite_dev_mode as dev_mode %}
#       {% if dev_mode %}<div class="dev-banner">开发模式</div>{% endif %}
@register.simple_tag
def is_vite_dev_mode():
    """
    判断是否处于Vite开发模式

    Returns:
        True/False

    用法：
        {% is_vite_dev_mode as dev_mode %}
        {% if dev_mode %}
            <div class="dev-banner">开发模式</div>
        {% endif %}
    """
    manifest = load_manifest()
    # bool(manifest)：{} 是假值 → 没清单 → 开发模式；有内容 → 生产构建。
    # 取反再返回，让模板里读起来是“是不是开发模式”，语义正着写，不用在模板里写 not
    return not bool(manifest)


# 【vite_dev_server_url】—— 输出 Vite 开发服务器地址
# 参数：无
# 返回：str：如 'http://localhost:5173'
# 说明：给模板里需要自己拼地址的场景用（比如调试面板、开发提示），
#       和 vite_js 内部读的是同一项配置，所以两处永远一致。
#       用法：{% vite_dev_server_url %}
@register.simple_tag
def vite_dev_server_url():
    """
    获取Vite开发服务器URL

    Returns:
        开发服务器URL

    用法：
        {% vite_dev_server_url %}
    """
    # getattr 的第三个参数是默认值：settings 里没配 VITE_DEV_SERVER_URL 时退回 Vite 默认端口
    return getattr(settings, 'VITE_DEV_SERVER_URL', 'http://localhost:5173')
