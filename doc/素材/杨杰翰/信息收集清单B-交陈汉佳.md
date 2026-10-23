# 信息收集清单 B —— 交陈汉佳（用于《Python 语言编码规范》）

> 填写人：杨杰翰（#yjh）｜ 分析 app：`oauth`（第三方登录模块）｜ 日期：2026-10-20
> 代码片段均来自 `oauth/`，可直接作为规范各小标题的正例/反例。

---

## 【杨杰翰 · oauth】

## ① "看不下去"的编码习惯（反例，均摘自项目真实代码）

### 反例 1：变量名遮蔽 Python 内置函数

**位置**：oauth/views.py `oauthlogin`、`authorize`

```python
def oauthlogin(request):
    type = request.GET.get('type', None)   # type 是内置函数！
    if not type:
        return HttpResponseRedirect('/')
    manager = get_manager_by_type(type)
```

`type` 是 Python 内置函数，被局部变量遮蔽后，函数内再想用 `type(x)` 做类型判断就会报 `TypeError: 'str' object is not callable`。**规范建议**：一律改名 `oauth_type` / `login_type`， flake8 的内置遮蔽检查（A002）应纳入 CI。

### 反例 2：魔法数字 + 无注释的"为什么"

**位置**：oauth/models.py

```python
token = models.CharField(max_length=150, null=True, blank=True)
```

150 是怎么来的？直到在 views.py 看到 `if type == 'facebook': user.token = ''  # facebook的token过长` 才知道"150 装不下 Facebook token"。**规范建议**：涉及外部系统限制的魔法数字，必须在字段旁写明出处（如 `# 微博token约107字符，Facebook可超200，故超长时置空`），否则下一个改字段的人只能猜。

### 反例 3：注释写了等于没写

**位置**：oauth/views.py authorize

```python
        # facebook的token过长
        if type == 'facebook':
            user.token = ''
```

只说"过长"，不说多长、为什么置空而不是扩字段。读者还得自己去翻模型定义才能理解。**规范建议**：注释回答"为什么这么做"，而不是复述"做了什么"；一句话注释里至少包含一个具体数字或约束。

### 反例 4：脆弱的字符串外科手术

**位置**：oauth/oauthmanager.py QQOauthManager.get_open_id

```python
rsp = rsp.replace(
    'callback(', '').replace(
    ')', '').replace(
    ';', '')
obj = json.loads(rsp)
```

QQ 返回 JSONP（`callback( {...} );`），作者用三次 `replace` 剥外壳。一旦 JSON 内容里出现 `)` 或 `;`（比如昵称），解析直接崩。**规范建议**：解析结构化文本一律用正则提取（`re.search(r'callback\((.*)\);', rsp, re.S)`）或专用库，禁止对未受信输入做链式 replace。

### 反例 5：过宽的 except 吞掉一切

**位置**：oauth/oauthmanager.py 各平台 get_oauth_userinfo

```python
        except Exception as e:
            logger.error(e)
            logger.error('github oauth error.rsp:' + rsp)
            return None
```

网络超时、JSON 解析失败、字段缺失，三种完全不同的故障被压成同一个 `None`，调用方（views.authorize）只能笼统地"回跳原页面"。**规范建议**：至少区分 `requests.RequestException`（网络层）与 `(json.JSONDecodeError, KeyError)`（报文层），前者可提示重试，后者应上报告警——第三方接口改版时全靠日志才能发现。

### 反例 6：复制粘贴 5 次的构造函数

**位置**：oauth/oauthmanager.py 五个平台子类的 `__init__`

```python
    def __init__(self, access_token=None, openid=None):
        config = self.get_config()
        self.client_id = config.appkey if config else ''
        self.client_secret = config.appsecret if config else ''
        self.callback_url = config.callback_url if config else ''
        super(WBOauthManager, self).__init__(...)
```

这段在 WB/Google/GitHub/Facebook/QQ 五个子类里**一字不差重复 5 遍**。**规范建议**：重复 3 次即应上提基类；5 次已经是"看得见的维护成本"——哪天要加 `self.timeout = 10` 就得改 5 个地方，漏一个就是线上事故。

### 反例 7：死代码

**位置**：oauth/views.py RequireEmailView.get

```python
        if oauthuser.email:
            pass
            # return HttpResponseRedirect('/')
```

判断已有邮箱后什么都不做（真正的重定向被注释掉了），已有邮箱的用户照样看到补填页。**规范建议**：被注释的代码要么恢复要么删除，禁止"注释掉先留着"——git 历史就是最好的"留着"。

---

## ② 值得全组推广的写法（正例）

### 正例 1：策略模式 + 类属性差异表，新增平台零样板

**位置**：oauth/oauthmanager.py

```python
class BaseOauthManager(metaclass=ABCMeta):
    AUTH_URL = None
    TOKEN_URL = None
    API_URL = None
    ICON_NAME = None

class GitHubOauthManager(ProxyManagerMixin, BaseOauthManager):
    AUTH_URL = 'https://github.com/login/oauth/authorize'
    TOKEN_URL = 'https://github.com/login/oauth/access_token'
    API_URL = 'https://api.github.com/user'
    ICON_NAME = 'github'
```

**推广理由**：每个子类开头 4 行类属性就是一张"差异表"，新成员接手时不用读任何方法就能知道这个平台接的是哪三个端点。我们组其他 app（如支付、短信渠道）遇到"多平台多供应商"场景时，强烈建议套用这个结构：**抽象基类定流程骨架，类属性声明端点，子类只填差异**。

### 正例 2：开放重定向防护用 Django 官方工具函数，不自己造轮子

**位置**：oauth/views.py get_redirecturl

```python
    if url_has_allowed_host_and_scheme(
        url=nexturl,
        allowed_hosts={site_domain},
        require_https=request.is_secure()
    ):
        return nexturl
    logger.info('非法url:' + str(nexturl))
    return '/'
```

**推广理由**：登录回跳是最经典的开放重定向攻击面，自己写 `startswith('/')` 之类的判断极易漏掉 `//evil.com` 这种协议相对 URL。Django 官方 `url_has_allowed_host_and_scheme` 已处理全部边界情况，且校验失败时有日志留痕、有安全兜底（回首页）。**凡是"跳转到用户可控 URL"的地方，必须过这个函数**——建议写进全组编码规范安全条款。

---

## ③ oauth 模块特有约定（建议上升为项目约定）

### 约定 1：Django 信号做横切扩展点

oauth 登录成功后不直接写登录日志，而是发信号（views.py authorize / emailconfirm）：

```python
from djangoblog.blog_signals import oauth_user_login_signal
...
oauth_user_login_signal.send(sender=authorize.__class__, id=user.id)
```

**约定内容**：视图只负责主流程，"登录日志、发通知、积分奖励"这类横切关注点一律挂信号接收器，接收器统一放 `djangoblog/blog_signals.py` 注册。好处是 oauth app 不依赖日志模块，将来加"登录送积分"不用改 oauth 一行代码。

### 约定 2：inclusion_tag 封装可复用模板片段

登录页的"第三方登录入口列表"不是写在视图里，而是模板标签（oauth/templatetags/oauth_tags.py）：

```python
@register.inclusion_tag('oauth/oauth_applications.html')
def load_oauth_applications(request):
    applications = get_oauth_apps()
    ...
    return {'apps': apps}
```

模板里一句 `{% load_oauth_applications request %}` 即可渲染。**约定内容**：凡是"多个页面都要出现的、需要查数据的 UI 片段"（如侧边栏、标签云、登录入口），一律做成 inclusion_tag，禁止在多个视图里重复拼同样的 context。

### 约定 3：第三方凭据一律存数据库配置表，禁止硬编码

所有平台的 appkey/appsecret/callback_url 都存 `OAuthConfig` 表，代码里通过 `get_config()` 读取，后台 Admin 可动态启停（`is_enable` 字段）。**约定内容**：本组项目接入任何外部服务（对象存储、短信、邮件 SMTP），凭据和开关都照此办理——代码库里出现明文密钥视为红线。

### 约定 4：防伪造链接用"SECRET_KEY 包裹 id"的简易签名

邮箱确认链接的签名算法（views.py emailconfirm）：

```python
sign = get_sha256(settings.SECRET_KEY + str(id) + settings.SECRET_KEY)
```

**约定内容**：项目内所有"发到用户邮箱/短信里的可点击链接"，签名统一用这个双向包裹模式 + 大写 hex 比较（`.upper() == sign.upper()`，忽略大小写差异）。虽然严格性不如 HMAC，但对本项目威胁模型足够，且全项目只用这一种，便于审计。

### 约定 5：模型层用 clean() 做业务唯一性校验

`OAuthConfig.clean()` 保证同类型平台只有一条配置，且用 `exclude(id=self.id)` 处理编辑场景：

```python
def clean(self):
    if OAuthConfig.objects.filter(
            type=self.type).exclude(id=self.id).count():
        raise ValidationError(_(self.type + _('already exists')))
```

**约定内容**：涉及"唯一性但又不适合加数据库 unique 约束"的业务规则（如还要区分启用状态），统一在模型 `clean()` 里做，并必须写 `exclude(id=self.id)`——这是最容易被忘、忘掉就出 bug 的细节。
