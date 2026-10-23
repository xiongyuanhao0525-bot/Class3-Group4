# xyh：插件加载器 —— Django app 注册表就绪后（apps.py ready()）被调用：
# xyh：遍历 settings.ACTIVE_PLUGINS 白名单 → 校验 plugins/<name>/plugin.py 存在 →
# xyh：动态 import 并取模块级 plugin 实例 → 追加进全局注册表 _loaded_plugins。
# xyh：其余 get_xxx 函数是对该注册表的只读查询入口（按名称/slug/位置检索）。
import os
import logging
from django.conf import settings

logger = logging.getLogger(__name__)

# 全局插件注册表
_loaded_plugins = []   # xyh：进程内单例列表，加载成功后全站共享，避免重复实例化

def load_plugins():
    """
    Dynamically loads and initializes plugins from the 'plugins' directory.
    This function is intended to be called when the Django app registry is ready.
    """
    global _loaded_plugins
    _loaded_plugins = []   # xyh：先清空再加载，支持热重载场景下的幂等调用

    for plugin_name in settings.ACTIVE_PLUGINS:   # xyh：只加载配置显式启用的插件（白名单机制）
        plugin_path = os.path.join(settings.PLUGINS_DIR, plugin_name)
        if os.path.isdir(plugin_path) and os.path.exists(os.path.join(plugin_path, 'plugin.py')):   # xyh：目录+入口文件双重校验
            try:
                # 导入插件模块
                plugin_module = __import__(f'plugins.{plugin_name}.plugin', fromlist=['plugin'])   # xyh：约定入口为 plugins.<slug>.plugin

                # 获取插件实例
                if hasattr(plugin_module, 'plugin'):
                    plugin_instance = plugin_module.plugin   # xyh：取模块级 plugin 变量（BasePlugin 子类实例）
                    _loaded_plugins.append(plugin_instance)
                    logger.info(f"Successfully loaded plugin: {plugin_name} - {plugin_instance.PLUGIN_NAME}")
                else:
                    logger.warning(f"Plugin {plugin_name} does not have 'plugin' instance")

            except ImportError as e:
                logger.error(f"Failed to import plugin: {plugin_name}", exc_info=e)
            except AttributeError as e:
                logger.error(f"Failed to get plugin instance: {plugin_name}", exc_info=e)
            except Exception as e:   # xyh：单个插件异常只记日志不中断，保证坏插件不影响整站启动
                logger.error(f"Unexpected error loading plugin: {plugin_name}", exc_info=e)

    return _loaded_plugins

def get_loaded_plugins():
    """获取所有已加载的插件"""
    return _loaded_plugins   # xyh：返回全局注册表引用（模板挂件标签遍历用）

def get_plugin_by_name(plugin_name):
    """根据名称获取插件"""
    for plugin in _loaded_plugins:
        if plugin.plugin_slug == plugin_name:   # xyh：注意实际比较的是 slug（目录名）而非 PLUGIN_NAME
            return plugin
    return None

def get_plugin_by_slug(plugin_slug):
    """根据slug获取插件"""
    for plugin in _loaded_plugins:
        if plugin.plugin_slug == plugin_slug:
            return plugin
    return None   # xyh：未找到返回 None，调用方需判空

def get_plugins_info():
    """获取所有插件的信息"""
    return [plugin.get_plugin_info() for plugin in _loaded_plugins]   # xyh：后台插件管理页的数据源

def get_plugins_by_position(position):
    """获取支持指定位置的插件"""
    return [plugin for plugin in _loaded_plugins if position in plugin.SUPPORTED_POSITIONS]   # xyh：模板挂件标签按位取插件再逐个渲染 