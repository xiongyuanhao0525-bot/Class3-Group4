# -*- coding: utf-8 -*-
"""#wxy servermanager/MemcacheStorage.py：把 WeRoBot 会话存到 Django cache（Redis）。

WeRoBot 自带 FileStorage 是单机文件、重启即失且多进程不安全；
这里实现 SessionStorage 接口，复用 djangoblog.utils.cache（即 Django settings.CACHES），
并通过 is_available 属性在启动时探测缓存是否真的可写。
"""
from werobot.session import SessionStorage
from werobot.utils import json_loads, json_dumps

from djangoblog.utils import cache


class MemcacheStorage(SessionStorage):
    """#wxy 基于 Django cache 的 WeRoBot 会话存储，所有 key 统一加 ws_ 前缀防止冲突。"""

    def __init__(self, prefix='ws_'):
        self.prefix = prefix
        self.cache = cache

    @property
    def is_available(self):
        """#wxy 可用性探测：写一个标记再读回，读写一致才认为缓存真的可用。
        robot.py 启动时据此决定是否回落 FileStorage。"""
        value = "1"
        self.set('checkavaliable', value=value)
        return value == self.get('checkavaliable')

    def key_name(self, s):
        """#wxy 拼最终缓存 key：前缀 + 原始 openid/会话 id。"""
        return '{prefix}{s}'.format(prefix=self.prefix, s=s)

    def get(self, id):
        """#wxy 读取会话；缓存未命中时返回空 dict（jsonpickle 可正常 decode）。"""
        id = self.key_name(id)
        session_json = self.cache.get(id) or '{}'
        return json_loads(session_json)

    def set(self, id, value):
        """#wxy 写会话：dict 对象 json 序列化后存入缓存。"""
        id = self.key_name(id)
        self.cache.set(id, json_dumps(value))

    def delete(self, id):
        """#wxy 删除会话（如粉丝主动退出管理员态时）。"""
        id = self.key_name(id)
        self.cache.delete(id)
