# xyh：djangoblog 自身 app 的配置类 —— 借 Django 启动完成时机（ready）
# xyh：触发插件加载，使 plugins/ 目录下的挂件在请求开始前全部注册就绪。
from django.apps import AppConfig

class DjangoblogAppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'   # xyh：新建模型主键默认用 BigAutoField
    name = 'djangoblog'                                    # xyh：app 导入路径（INSTALLED_APPS 中的 'djangoblog'）

    def ready(self):   # xyh：app 注册表就绪回调，进程生命周期内仅执行一次
        super().ready()
        # Import and load plugins here
        from .plugin_manage.loader import load_plugins   # xyh：延迟导入避免循环依赖
        load_plugins()   # xyh：按 ACTIVE_PLUGINS 白名单实例化并注册全部插件 