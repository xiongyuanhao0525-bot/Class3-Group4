# xyh：钩子名称常量表 —— 全站统一的"事件名/挂件位"字典，
# xyh：业务代码（blog/views.py 等）触发与插件 register() 挂接都引用本模块，
# xyh：避免魔法字符串散落两处导致拼写不一致。
ARTICLE_DETAIL_LOAD = 'article_detail_load'   # xyh：文章详情页加载完成（动作钩子，可推爬虫/统计）
ARTICLE_CREATE = 'article_create'             # xyh：新建文章（动作钩子）
ARTICLE_UPDATE = 'article_update'             # xyh：更新文章（动作钩子）
ARTICLE_DELETE = 'article_delete'             # xyh：删除文章（动作钩子）

ARTICLE_CONTENT_HOOK_NAME = "the_content"     # xyh：正文过滤器钩子：渲染后的 HTML 依次经插件加工

# 位置钩子常量
POSITION_HOOKS = {   # xyh：七个页面挂件位 → 模板标签取用的注册键名，与 BasePlugin.render_{position}_widget 一一对应
    'article_top': 'article_top_widgets',         # xyh：文章顶部
    'article_bottom': 'article_bottom_widgets',   # xyh：文章底部
    'sidebar': 'sidebar_widgets',                 # xyh：侧边栏
    'header': 'header_widgets',                   # xyh：页头
    'footer': 'footer_widgets',                   # xyh：页脚
    'comment_before': 'comment_before_widgets',   # xyh：评论列表前
    'comment_after': 'comment_after_widgets',     # xyh：评论列表后
}

# 资源注入钩子
HEAD_RESOURCES_HOOK = 'head_resources'   # xyh：聚合插件 CSS/JS/head HTML 注入 <head>
BODY_RESOURCES_HOOK = 'body_resources'   # xyh：聚合插件 body 底部资源

