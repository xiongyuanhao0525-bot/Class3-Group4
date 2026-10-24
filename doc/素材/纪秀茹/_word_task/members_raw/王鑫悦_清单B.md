# 清单 B —— 王鑫悦（#wxy）servermanager 编码规范素材
> 用途：交陈汉佳，用于《Python 编码规范》正反例。

## ① 标注时发现"看不下去"的编码习惯（反例素材）

### 反例 1：变量/类名违反 PEP8 命名规范
```python
class commands(models.Model):   # 类名应该大驼峰 Commands
    ...
class WxUserInfo():            # 空括号应直接写 WxUserInfo(object)
```
Django Model 类名全小写 `commands`，与 PEP8（类名大驼峰）冲突；admin 里注册时容易混淆。

### 反例 2：魔法字符串 / 硬编码
```python
robot = WeRoBot(token=os.environ.get('DJANGO_WEROBOT_TOKEN') or 'lylinux', ...)
if settings.TESTING:
    passwd = '123'
```
开发 token `'lylinux'` 和测试密码 `'123'` 直接写在源码里，应抽到 settings 或 env。

### 反例 3：except 吞异常且未使用异常对象
```python
except Exception as e:        # F841: e 从未使用
    userinfo = WxUserInfo()
```
要么 `except Exception:`，要么 `logger.exception(e)`。

### 反例 4：魔法数字 / 状态机硬编码
```python
if self.userinfo.Count >= 3:  # 3 次锁定，没有常量名
```
应定义 `MAX_PASSWORD_RETRY = 3`。

### 反例 5：超长函数 + 嵌套 if（robot.handler 约 50 行）
`MessageHandler.handler()` 用一串 `if isAdmin / if isPasswordSet / if Command != ''` 串起整个状态机，新加状态要改主流程，建议拆成独立方法或用字典分发。

## ② 值得全组推广的写法（正例素材）

### 正例 1：`@property` 做可用性探测
```python
@property
def is_available(self):
    value = "1"
    self.set('checkavaliable', value=value)
    return value == self.get('checkavaliable')
```
把"缓存是否可用"这个易变判断封装成只读属性，调用方 `if memstorage.is_available:` 一行搞定，推荐在 Django settings/CACHE 判断场景复用。

### 正例 2：ModelAdmin 用 `readonly_fields + has_add_permission=False` 做只读审计表
```python
class EmailSendLogAdmin(admin.ModelAdmin):
    list_display = ('title', 'emailto', 'send_result', 'creation_time')
    readonly_fields = ('title', 'emailto', 'send_result', 'creation_time', 'content')
    def has_add_permission(self, request):
        return False
```
"只增不改、后台只读、禁止手工新增"——所有日志类表都可以照抄这套写法。

## ③ servermanager 特有约定（Django 约定类小节）

1. **WeRoBot 集成约定**：`urls.py` 用 `make_view(robot)` 把机器人挂成 Django view；`enable_session=True` 后微信粉丝会话由 `SESSION_STORAGE` 统一管理。
2. **会话存储双实现**：`MemcacheStorage`（Redis）与 `FileStorage`（本地文件）二选一，启动时按 `is_available` 自动回落——其他 app 若要做"缓存降级"可照抄。
3. **微信指令用正则 `@robot.filter(re.compile(...))` 分发**，兜底用 `@robot.handler`；新指令只要加一个 filter 装饰器即可，无需改路由。
4. **管理员运维命令走 `commands` 表注册 + `CommandHandler` 执行**：后台新增命令 = 新增一行表记录，无需重启服务。
