# xyh：WordPress 风格钩子系统 —— 进程内全局注册表 _hooks{钩子名: [回调...]}；
# xyh：register() 供插件在 register_hooks() 阶段挂接；
# xyh：run_action() 无返回值广播执行（如文章创建/更新事件）；
# xyh：apply_filters() 管道式改写值（如正文 the_content 渲染后加工）。
# xyh：两类回调异常均被捕获记日志，单个坏回调不影响其余执行。
import logging

logger = logging.getLogger(__name__)

_hooks = {}   # xyh：钩子名 → 按注册顺序排列的回调列表


def register(hook_name: str, callback: callable):
    """
    注册一个钩子回调。
    """
    if hook_name not in _hooks:
        _hooks[hook_name] = []
    _hooks[hook_name].append(callback)   # xyh：同名钩子可叠加多个回调，注册顺序即执行顺序
    logger.debug(f"Registered hook '{hook_name}' with callback '{callback.__name__}'")


def run_action(hook_name: str, *args, **kwargs):
    """
    执行一个 Action Hook。
    它会按顺序执行所有注册到该钩子上的回调函数。
    """
    if hook_name in _hooks:
        logger.debug(f"Running action hook '{hook_name}'")
        for callback in _hooks[hook_name]:
            try:
                callback(*args, **kwargs)   # xyh：动作型：只做副作用（发通知/推爬虫等），丢弃返回值
            except Exception as e:
                logger.error(f"Error running action hook '{hook_name}' callback '{callback.__name__}': {e}", exc_info=True)


def apply_filters(hook_name: str, value, *args, **kwargs):
    """
    执行一个 Filter Hook。
    它会把 value 依次传递给所有注册的回调函数进行处理。
    """
    if hook_name in _hooks:
        logger.debug(f"Applying filter hook '{hook_name}'")
        for callback in _hooks[hook_name]:
            try:
                value = callback(value, *args, **kwargs)   # xyh：过滤型：上一回调的输出是下一回调的输入，链式加工
            except Exception as e:
                logger.error(f"Error applying filter hook '{hook_name}' callback '{callback.__name__}': {e}", exc_info=True)
    return value   # xyh：无注册回调时原样返回，保证主流程不受插件缺席影响
