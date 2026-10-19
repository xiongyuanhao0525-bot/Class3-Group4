# xyh：插件体系基类模块 —— 所有插件继承 BasePlugin 获得统一的
# xyh：生命周期（元数据校验 → 定位插件目录 → init_plugin → register_hooks）、
# xyh：位置渲染协议（render_{position}_widget 约定命名反射调用）、
# xyh：模板/静态资源隔离（plugins/<slug>/templates、plugins/<slug>/static）
# xyh：以及 head/body 资源注入点。是理解"主题挂件如何挂进页面"的入口文件。
import logging
from pathlib import Path

from django.template import TemplateDoesNotExist
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


# xyh：插件抽象基类：定义元数据、显示位置、优先级与各类可重写钩子方法
class BasePlugin:
    # 插件元数据
    PLUGIN_NAME = None          # xyh：插件显示名（必填，缺失在 __init__ 抛错）
    PLUGIN_DESCRIPTION = None   # xyh：插件功能描述（必填）
    PLUGIN_VERSION = None       # xyh：版本号（必填）
    PLUGIN_AUTHOR = None        # xyh：作者（可选）

    # 插件配置
    SUPPORTED_POSITIONS = []  # 支持的显示位置
    DEFAULT_PRIORITY = 100  # 默认优先级（数字越小优先级越高）
    POSITION_PRIORITIES = {}  # 各位置的优先级 {'sidebar': 50, 'article_bottom': 80}

    def __init__(self):  # xyh：实例化即完成插件初始化全流程：校验元数据→解析目录/slug→子类初始化→注册钩子
        if not all([self.PLUGIN_NAME, self.PLUGIN_DESCRIPTION, self.PLUGIN_VERSION]):
            raise ValueError("Plugin metadata (PLUGIN_NAME, PLUGIN_DESCRIPTION, PLUGIN_VERSION) must be defined.")

        # 设置插件路径
        self.plugin_dir = self._get_plugin_directory()   # xyh：由子类所在文件反推插件根目录
        self.plugin_slug = self._get_plugin_slug()      # xyh：目录名作为唯一标识，模板/静态路径均以此隔离

        self.init_plugin()      # xyh：子类自定义初始化钩子
        self.register_hooks()   # xyh：子类向 hooks 机制注册动作/过滤器回调

    def _get_plugin_directory(self):
        """获取插件目录路径"""
        import inspect
        plugin_file = inspect.getfile(self.__class__)   # xyh：反射取子类定义所在 .py 文件
        return Path(plugin_file).parent                 # xyh：该文件上级目录即插件根目录

    def _get_plugin_slug(self):
        """获取插件标识符（目录名）"""
        return self.plugin_dir.name   # xyh：用目录名做 slug，保证模板/静态资源命名空间唯一

    def init_plugin(self):
        """
        插件初始化逻辑
        子类可以重写此方法来实现特定的初始化操作
        """
        logger.info(f'{self.PLUGIN_NAME} initialized.')   # xyh：默认仅打点；子类可在此加载配置/预计算

    def register_hooks(self):
        """
        注册插件钩子
        子类可以重写此方法来注册特定的钩子
        """
        pass   # xyh：默认空实现；子类在此调用 hooks.register() 挂接动作/过滤器

    # === 位置渲染系统 ===
    def render_position_widget(self, position, context, **kwargs):
        """
        根据位置渲染插件组件
        
        Args:
            position: 位置标识
            context: 模板上下文
            **kwargs: 额外参数
            
        Returns:
            dict: {'html': 'HTML内容', 'priority': 优先级} 或 None
        """
        if position not in self.SUPPORTED_POSITIONS:   # xyh：位置不在白名单直接跳过，实现按位挂载
            return None

        # 检查条件显示
        if not self.should_display(position, context, **kwargs):   # xyh：运行时二次判断（如仅文章页显示）
            return None

        # 调用具体的位置渲染方法
        method_name = f'render_{position}_widget'      # xyh：约定优于配置：按位置名拼出方法名反射调用
        if hasattr(self, method_name):
            html = getattr(self, method_name)(context, **kwargs)
            if html:
                priority = self.POSITION_PRIORITIES.get(position, self.DEFAULT_PRIORITY)   # xyh：同位置多插件按优先级排序
                return {
                    'html': html,
                    'priority': priority,
                    'plugin_name': self.PLUGIN_NAME
                }

        return None

    def should_display(self, position, context, **kwargs):
        """
        判断插件是否应该在指定位置显示
        子类可重写此方法实现条件显示逻辑
        
        Args:
            position: 位置标识
            context: 模板上下文
            **kwargs: 额外参数
            
        Returns:
            bool: 是否显示
        """
        return True   # xyh：默认总是显示，子类可按页面类型/登录态收窄

    # === 各位置渲染方法 - 子类重写 ===
    # xyh：以下七个 render_xxx_widget 对应 hook_constants.POSITION_HOOKS 的七个挂件位，
    # xyh：基类统一返回 None，子类按需重写其一或多个即可挂进模板对应区块。
    def render_sidebar_widget(self, context, **kwargs):
        """渲染侧边栏组件"""
        return None

    def render_article_bottom_widget(self, context, **kwargs):
        """渲染文章底部组件"""
        return None

    def render_article_top_widget(self, context, **kwargs):
        """渲染文章顶部组件"""
        return None

    def render_header_widget(self, context, **kwargs):
        """渲染页头组件"""
        return None

    def render_footer_widget(self, context, **kwargs):
        """渲染页脚组件"""
        return None

    def render_comment_before_widget(self, context, **kwargs):
        """渲染评论前组件"""
        return None

    def render_comment_after_widget(self, context, **kwargs):
        """渲染评论后组件"""
        return None

    # === 模板系统 ===
    def render_template(self, template_name, context=None):
        """
        渲染插件模板
        
        Args:
            template_name: 模板文件名
            context: 模板上下文
            
        Returns:
            HTML字符串
        """
        if context is None:
            context = {}

        template_path = f"plugins/{self.plugin_slug}/{template_name}"   # xyh：模板命名空间 plugins/<slug>/，避免与主题模板冲突

        try:
            return render_to_string(template_path, context)
        except TemplateDoesNotExist:
            logger.warning(f"Plugin template not found: {template_path}")
            return ""   # xyh：缺模板时降级为空串而非抛错，保证页面不被插件拖垮

    # === 静态资源系统 ===
    def get_static_url(self, static_file):
        """获取插件静态文件URL"""
        from django.templatetags.static import static
        return static(f"{self.plugin_slug}/static/{self.plugin_slug}/{static_file}")   # xyh：静态文件同样按 slug 隔离命名空间

    def get_css_files(self):
        """获取插件CSS文件列表"""
        return []   # xyh：子类重写返回 css 相对路径列表，由前端聚合注入 <head>

    def get_js_files(self):
        """获取插件JavaScript文件列表"""
        return []   # xyh：子类重写返回 js 相对路径列表

    def get_critical_head_html(self, context=None):
        """
        获取需要在<head>最早执行的关键HTML内容（阻塞式加载）

        用于防闪烁脚本等必须在页面渲染前执行的关键代码。
        此方法返回的内容会在所有CSS和其他资源之前加载。

        注意：此方法应该只用于真正需要阻塞加载的关键资源，
        普通资源请使用 get_head_html()
        """
        return ""   # xyh：阻塞级注入点（如主题防闪烁脚本），优先级高于 CSS

    def get_head_html(self, context=None):
        """获取需要插入到<head>中的HTML内容（在CSS之后）"""
        return ""   # xyh：非阻塞 head 注入点（统计脚本、meta 等）

    def get_body_html(self, context=None):
        """获取需要插入到<body>底部的HTML内容"""
        return ""   # xyh：body 末尾注入点（挂件容器、延迟脚本等）

    def get_plugin_info(self):
        """
        获取插件信息
        :return: 包含插件元数据的字典
        """
        return {   # xyh：供后台插件管理页展示的元数据快照
            'name': self.PLUGIN_NAME,
            'description': self.PLUGIN_DESCRIPTION,
            'version': self.PLUGIN_VERSION,
            'author': self.PLUGIN_AUTHOR,
            'slug': self.plugin_slug,
            'directory': str(self.plugin_dir),
            'supported_positions': self.SUPPORTED_POSITIONS,
            'priorities': self.POSITION_PRIORITIES
        }
