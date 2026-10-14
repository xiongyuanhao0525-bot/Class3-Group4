# 顺序图 · 翟旌超（软工3班4组 · 2415304340）

> **本周小组任务（分工表 zjc 一行）**：负责 `accounts`（注册 / 登录 / 找回密码流程）模块，交付物 = **顺序图 ×3：注册、登录、第三方登录**。
> 本目录即为该交付物的**可直接提交版本**：分工表要求的 3 张之外，**额外补齐模块内第 4 条流程"找回密码"**，
> 共 4 张顺序图（PNG 图片 + SVG 矢量图 + PlantUML 源码）+ 本说明，覆盖 `accounts` 模块全部关键流程。

---

## 一、文件清单

| 文件 | 内容 | 用途 |
| --- | --- | --- |
| `顺序图1_用户注册与邮箱验证.puml` / `.png` / `.svg` | 注册（含邮箱验证激活） | **主交付物 ①** |
| `顺序图2_用户登录.puml` / `.png` / `.svg` | 登录（用户名/邮箱 + 密码，含"记住我"） | **主交付物 ②** |
| `顺序图3_第三方登录.puml` / `.png` / `.svg` | 第三方授权登录（微博/Google/GitHub/QQ/Facebook） | **主交付物 ③** |
| `顺序图4_找回密码.puml` / `.png` / `.svg` | 找回密码 / 重置密码（邮箱验证码 + 新密码） | **额外补齐**：对应分工表里的"找回密码流程" |
| `顺序图_README.md` | 本文件：步骤表 + 代码对照表 + 异常分支 + 导出方法 | 交作业说明、组长汇总时直接引用 |

- `.puml` 是 PlantUML 源码，用 VSCode 的 **PlantUML 插件**打开即可改字、改流程并重新导出图片；
  也可以把源码整段粘到 <https://www.plantuml.com/plantuml> 在线渲染。
- 本机重新生成图片的命令（需要 Java，本机已装 JDK；`plantuml.jar` 在 `桌面\plantuml\`）：

```powershell
java -Dfile.encoding=UTF-8 -jar C:\Users\91585\Desktop\plantuml\plantuml.jar -charset UTF-8 -tpng 顺序图1_用户注册与邮箱验证.puml
java -Dfile.encoding=UTF-8 -jar C:\Users\91585\Desktop\plantuml\plantuml.jar -charset UTF-8 -tsvg 顺序图1_用户注册与邮箱验证.puml
```

- **写进 Word / PPT**：优先插 `.png`（与 Word 兼容最好）；需要放大不失真时插 `.svg`（Word 2016+ / PPT 支持 svg）。

---

## 二、四张图分别画了什么

| 图 | 一句话说明 | 主要参与者（生命线） |
| --- | --- | --- |
| 顺序图1 注册与邮箱验证 | 访客提交注册表单 → 校验 → 新建**未激活**账号 → 发验证邮件 → 点邮件链接把 `is_active` 置真 | 访客、浏览器/注册页、URL 路由、`RegisterView`、`RegisterForm`、`BlogUser`、邮件信号、`EmailSendLog`、用户邮箱 |
| 顺序图2 用户登录 | 提交用户名或邮箱 + 密码 → 认证后端比对 → 写会话并定有效期（记住我 30 天 / 默认 14 天）→ 跳转，另含退出登录 | 用户、浏览器/登录页、URL 路由、`LoginView`、`LoginForm`、认证后端、`BlogUser`、会话、缓存 |
| 顺序图3 第三方登录 | 点第三方图标 → 跳平台授权 → 回调换 token 取用户信息 → 匹配/新建本地 `OAuthUser` 与 `BlogUser` → 免密登录；无邮箱时走"补充邮箱 + 邮件确认绑定" | 用户、浏览器/登录页、URL 路由、`oauthlogin()`、`authorize()`、授权管理器、第三方平台、`OAuthUser`、`BlogUser`、登录信号、会话与 Cookie |
| 顺序图4 找回密码 | 邮箱申请 6 位验证码（存缓存 5 分钟）→ 提交验证码 + 新密码 → 校验通过后用 `make_password` 覆盖旧密码 → 跳登录页 | 用户、浏览器/忘记密码页、URL 路由、`ForgetPasswordEmailCode`、`ForgetPasswordView`、表单、验证码工具、缓存、邮件信号、`BlogUser`、用户邮箱 |

---

## 三、顺序图1：注册与邮箱验证（步骤表）

| 阶段 | 步骤 | 说明 |
| --- | --- | --- |
| 一、提交注册表单 | [1]–[8] | 打开 `/register/`（GET）→ `RegisterView`（`SecureFormView`，带 `csrf_protect`）渲染表单 → 用户提交（POST）→ CSRF 校验 → 构造 `RegisterForm` |
| 二、表单校验 | [9]–[13] | `clean_username()`、`clean_email()`（邮箱查重）、`clean_password2()`（两次一致 + 强度校验）；失败即回表单页报错 |
| 三、建号 + 发信 | [14]–[24] | `form.save(False)` → `is_active=False`、`source='Register'` → `save(True)` 落库（INSERT `accounts_bloguser`）→ 生成 `sign` 与验证链接 → `send_email()` 派发信号 → SMTP 投递 + 写 `EmailSendLog` → 302 到注册结果页 |
| 四、邮箱验证 | [25]–[36] | 点邮件链接 → `account_result()` → `get_object_or_404(BlogUser)` → 重算 `c_sign` 与 URL 中 `sign` 比对 → 通过则 `user.is_active = True` 并 `UPDATE`，页面提示"验证成功"，之后可登录（衔接顺序图2） |

## 四、顺序图2：登录（步骤表）

| 阶段 | 步骤 | 说明 |
| --- | --- | --- |
| 一、打开登录页 | [1]–[5] | `LoginView` 继承 `LoginFormView`，`dispatch()` 叠加 `sensitive_post_parameters('password')` + `csrf_protect` + `never_cache`；`get_context_data()` 读取 `next`（缺省 `/`） |
| 二、提交并认证 | [6]–[15] | POST → `AuthenticationForm(data=POST, request=request)` → `authenticate()` → `EmailOrUsernameModelBackend`：含 `@` 按邮箱查、否则按用户名查 → `check_password()` + `is_active` 校验 |
| 三、失败处理 | 分支 | 用户不存在 / 密码错误 / 账号未激活 → 返回表单页显示错误，留在登录页 |
| 四、成功处理 | [16]–[24] | `delete_sidebar_cache()` → `auth.login()` 写会话 → 勾选「记住我」则 `set_expiry(2626560s≈30天)`，否则 `1209600s=14天` → `get_success_url()` 校验 `next`（防开放重定向）→ 302 跳转 + 下发 `logged_user` Cookie |
| 五、退出登录 | [25]–[30] | `/logout/` → `LogoutView`（`LogoutRedirectView`，`never_cache`）→ `logout()` 清会话 → 302 回 `/login/` 并删除 `logged_user` Cookie |

## 五、顺序图3：第三方登录（步骤表）

| 阶段 | 步骤 | 说明 |
| --- | --- | --- |
| 一、跳转授权 | [1]–[10] | 登录页图标（`oauth_tags.load_oauth_applications`）→ `/oauth/oauthlogin?type=..&next_url=..` → `get_manager_by_type()` 取平台管理器 → `get_redirecturl()` 安全校验 → `get_authorization_url()` → 302 跳出到第三方授权页 |
| 二、回调取 token | [11]–[23] | 用户授权 → `/oauth/authorize?code=..` → `get_access_token_by_code(code)` 换 token → `get_oauth_userinfo()` 取 openid/昵称/头像/邮箱 |
| 三、本地账号匹配 | [24]–[27] | 昵称为空则生成 `djangoblog+yyMMddhhmmss`；按 `(type, openid)` 查 `OAuthUser`（老用户刷新头像/昵称）；facebook 的 token 置空 |
| 四、有邮箱分支 | [28]–[42] | 事务内按 `author_id` 找已绑定账号，否则 `get_or_create(email=..)` 新建/复用 `BlogUser`（`source='authorize'`，昵称重名时用时间戳兜底）→ 回写 `OAuthUser.author` → 发 `oauth_user_login_signal`（头像本地化 `save_user_avatar()` + 清缓存）→ `login()` + `set_expiry(14 天)` → 302 + `logged_user` Cookie |
| 五、无邮箱分支 | [43]–[50] | 先落库 → 跳 `/oauth/requireemail/{oauthid}.html` 补邮箱 → `RequireEmailView.form_valid()` 存邮箱并发送绑定邮件 → 点 `/oauth/emailconfirm/{id}/{sign}.html` → `emailconfirm()` 校验 `sign`、建/取 `BlogUser`、`login()` → `bindsuccess` 页提示绑定成功 |

## 六、顺序图4：找回密码（步骤表）

| 阶段 | 步骤 | 说明 |
| --- | --- | --- |
| 一、申请验证码 | [1]–[15] | 打开 `/forget_password/` → 点"获取验证码"（`account.js` 用 AJAX POST `/forget_password_code/`）→ `ForgetPasswordEmailCode.post()` → 邮箱格式校验（失败返回"错误的邮箱"）→ `generate_code()` 生成 6 位数字 → `send_verify_email()` 发信 → `set_code()` 按邮箱写入缓存（**TTL 300 秒**）→ 返回 `ok`，前端开始 60 秒倒计时 |
| 二、提交新密码 | [16]–[32] | POST `/forget_password/` → `ForgetPasswordView`（`SecureFormView`，CSRF 保护）→ 表单按字段顺序校验：`clean_new_password2()`（两次一致 + 强度）→ `clean_email()`（邮箱必须已注册）→ `clean_code()` → `utils.verify(email, code)` 比对缓存验证码 → 全部通过后 `BlogUser.objects.get(email=..)` → `make_password()` 覆盖密码 → `save()` → 302 跳 `/login/`，用新密码登录（衔接顺序图2） |

---

## 七、步骤 ↔ 代码对照表（写报告时的"设计依据"）

### 顺序图1（`accounts` 注册）

| 步骤 | 代码位置 |
| --- | --- |
| [1]–[4] 表单页 | `accounts/urls.py`: `^register/$` → `views.RegisterView`；`templates/account/registration_form.html` |
| [7] CSRF | `djangoblog/base_views.py`: `SecureFormView.dispatch()` → `@method_decorator(csrf_protect)` |
| [8]–[13] 校验 | `accounts/forms.py`: `RegisterForm`（`clean_email()` 邮箱查重、`clean_password2()` 强度校验、`Meta.fields = ("username","email")`） |
| [14]–[17] 建号 | `accounts/views.py`: `RegisterView.form_valid()` → `form.save(False)`、`user.is_active=False`、`user.source='Register'`、`user.save(True)` |
| [18]–[19] 签名与链接 | `djangoblog/utils.py`: `get_sha256()`（HMAC-SHA256）；`reverse('account:result')`；`settings.DEBUG` 时域名改为 `127.0.0.1:8000` |
| [20]–[22] 发邮件 | `djangoblog/utils.py`: `send_email()` → 派发 `send_email_signal`；`djangoblog/blog_signals.py`: `send_email_signal_handler()` → `EmailMultiAlternatives.send()` + 写 `servermanager.models.EmailSendLog` |
| [25]–[36] 验证 | `accounts/views.py`: `account_result(request)`；`accounts/urls.py`: `path('account/result.html', views.account_result, name='result')` |

### 顺序图2（`accounts` 登录 / 退出）

| 步骤 | 代码位置 |
| --- | --- |
| [1]–[5] 登录页 | `accounts/urls.py`: `^login/$`；`templates/account/login.html`（`name="remember"`、`<input type="hidden" name="next" value="{{ redirect_to }}">`） |
| [2]–[4] 视图基类 | `djangoblog/base_views.py`: `LoginFormView.dispatch()`（`sensitive_post_parameters` / `csrf_protect` / `never_cache`） |
| [9]–[15] 认证 | `accounts/views.py`: `LoginView.form_valid()` → `AuthenticationForm(data=..., request=...)`；`accounts/forms.py`: `LoginForm`；`accounts/user_login_backend.py`: `EmailOrUsernameModelBackend.authenticate()` |
| [16]–[18] 会话 | `accounts/views.py`: `delete_sidebar_cache()`、`auth.login()`；`djangoblog/settings.py`: `AUTHENTICATION_BACKENDS` |
| [19]–[20] 有效期 | `djangoblog/settings.py`: `REMEMBER_ME_LOGIN_TTL = 2626560`、`SESSION_COOKIE_AGE = 1209600`；`accounts/views.py`: `session.set_expiry()` |
| [21]–[24] 跳转与 Cookie | `accounts/views.py`: `get_success_url()` → `url_has_allowed_host_and_scheme(...)`、`response.set_cookie('logged_user', ...)` |
| [25]–[30] 退出 | `accounts/views.py`: `LogoutView`（`url = '/login/'`）→ `logout()`、`delete_sidebar_cache()`、`response.delete_cookie('logged_user')` |

### 顺序图3（第三方登录）

| 步骤 | 代码位置 |
| --- | --- |
| [1]–[2] 登录入口 | `oauth/templatetags/oauth_tags.py`: `load_oauth_applications()` → `/oauth/oauthlogin?type=..&next_url=..`；`templates/oauth/oauth_applications.html` |
| [3]–[10] 授权跳转 | `oauth/views.py`: `oauthlogin()`、`get_redirecturl()`；`oauth/oauthmanager.py`: `get_manager_by_type()`、`get_authorization_url()` |
| [13]–[23] 回调换 token | `oauth/views.py`: `authorize()`；`oauth/oauthmanager.py`: `get_access_token_by_code()`（`OAuthAccessTokenException`）、`get_oauth_userinfo()` |
| [24]–[27] 本地匹配 | `oauth/models.py`: `OAuthUser`（`type` / `openid` / `nickname` / `picture` / `author` 外键 / `metadata`） |
| [28]–[42] 自动建号登录 | `oauth/views.py`: `transaction.atomic()` + `get_user_model().objects.get_or_create(email=...)`、`author.source='authorize'`、`login()`、`session.set_expiry()`、`set_cookie('logged_user')`；`djangoblog/blog_signals.py`: `oauth_user_login_signal_handler()` → `save_user_avatar()` |
| [43]–[50] 补邮箱绑定 | `oauth/views.py`: `RequireEmailView.form_valid()`、`emailconfirm()`、`bindsuccess()`；`accounts/models.py`: `BlogUser`（`AUTH_USER_MODEL`） |

### 顺序图4（`accounts` 找回密码）

| 步骤 | 代码位置 |
| --- | --- |
| [1]–[3] 忘记密码页 | `accounts/urls.py`: `^forget_password/$`；`templates/account/forget_password.html` |
| [4]–[5] 申请验证码 | `blog/static/account/js/account.js`: `$("#btn").onclick` → `$.ajax({url: "/forget_password_code/", type: "POST", data: {email, csrfmiddlewaretoken}})` |
| [6]–[8] 验证码接口 | `accounts/urls.py`: `^forget_password_code/$`；`accounts/views.py`: `ForgetPasswordEmailCode.post()`；`accounts/forms.py`: `ForgetPasswordCodeForm` |
| [9] 生成验证码 | `djangoblog/utils.py`: `generate_code()` → `random.sample(string.digits, 6)` |
| [10]–[11] 发验证码邮件 | `accounts/utils.py`: `send_verify_email(to_mail, code, subject=_("Verify Email"))` → `djangoblog/utils.py`: `send_email()` → `blog_signals.py`: `send_email_signal_handler()`（SMTP + 写 `EmailSendLog`） |
| [12]–[13] 存缓存 | `accounts/utils.py`: `set_code()` → `cache.set(email, code, _code_ttl.seconds)`，`_code_ttl = timedelta(minutes=5)` |
| [16]–[19] 提交重置 | `accounts/urls.py`: `^forget_password/$` → `views.ForgetPasswordView`（`SecureFormView` → `csrf_protect`）；`accounts/forms.py`: `ForgetPasswordForm` |
| [20] 新密码校验 | `accounts/forms.py`: `clean_new_password2()` → 两次一致 + `password_validation.validate_password()` |
| [21] 邮箱校验 | `accounts/forms.py`: `clean_email()` → `BlogUser.objects.filter(email=..).exists()`（不存在则 "email does not exist"） |
| [22]–[25] 验证码校验 | `accounts/forms.py`: `clean_code()` → `accounts/utils.py`: `verify(email, code)`（内部 `get_code()` 读缓存，不一致返回 "Verification code error"） |
| [26]–[32] 重置密码 | `accounts/views.py`: `ForgetPasswordView.form_valid()` → `BlogUser.objects.filter(email=..).get()`、`make_password(new_password2)`、`blog_user.save()`、`HttpResponseRedirect('/login/')` |

---

## 八、异常 / 分支一览（答辩、写报告可直接用）

| 场景 | 处理 |
| --- | --- |
| 注册：邮箱已存在 | `clean_email()` → "email already exists"，回注册页 |
| 注册：两次密码不一致 | `clean_password2()` → "passwords do not match"，回注册页 |
| 注册：CSRF 非法 | `csrf_protect` → 403，不进业务逻辑 |
| 注册：验证链接被篡改 | `sign` 与服务端重算 `c_sign` 不一致 → 403 Forbidden |
| 注册：重复点验证链接 | `is_active` 已为 `True` → 302 直接回首页 |
| 注册：邮件发送失败 | 仅写 `EmailSendLog(send_result=False)`，注册流程照常完成（可后台补发） |
| 登录：用户名/邮箱不存在、密码错误 | 认证后端返回 `None` → 表单报错，留在登录页 |
| 登录：账号未激活 | `user_can_authenticate()` 判定 `is_active=False` → 拒绝登录 |
| 登录：`next` 为站外地址 | `url_has_allowed_host_and_scheme()` 不通过 → 回退 `success_url='/'`（防开放重定向） |
| 登录：密码泄露风险 | `sensitive_post_parameters('password')` 对日志/报错堆栈脱敏 |
| 第三方：授权类型非法 | `get_manager_by_type()` 返回 `None` → 302 回首页 |
| 第三方：换 token 失败 | `OAuthAccessTokenException` → 记 warning 后回首页/重发授权 |
| 第三方：用户信息接口异常 | `except Exception` 捕获，`rsp=None` → 重新发起授权 |
| 第三方：平台无邮箱（QQ/Facebook） | 走"补充邮箱 → 邮件确认绑定"子流程；绑定链接 `sign` 不符 → 403 |
| 第三方：昵称为空 / 重名 | 生成 `djangoblog+时间戳` 作为用户名兜底 |
| 找回密码：邮箱格式非法 | `ForgetPasswordCodeForm` 校验失败 → 返回"错误的邮箱"，不发验证码 |
| 找回密码：邮箱未注册 | `clean_email()` → "email does not exist"，回表单页 |
| 找回密码：两次密码不一致 / 强度不足 | `clean_new_password2()` → "passwords do not match" / `password_validation` 报错 |
| 找回密码：验证码错误或超过 5 分钟 | `verify()` 比对缓存失败 → "Verification code error"（`set_code` 的 TTL 300 秒） |
| 找回密码：CSRF 非法 | `ForgetPasswordView`（`SecureFormView`）→ `csrf_protect` → 403 |

---

## 九、安全与技术要点（报告里的"设计说明"小节可摘）

1. **密码安全**：注册密码经 Django `UserCreationForm` 校验强度后以 PBKDF2 哈希入库；登录用 `check_password()` 比对，日志中密码被 `sensitive_post_parameters` 脱敏。
2. **邮箱验证令牌**：`sign = sha256(sha256(SECRET_KEY + id))`，服务端可重算校验，链接被篡改即 403。
3. **CSRF**：`SecureFormView` / `LoginFormView` 统一通过装饰器加 `csrf_protect`，模板表单带 `{% csrf_token %}`。
4. **Cookie 策略**：`logged_user=true`（`httponly=False`、`samesite='Lax'`）仅用于前端判断登录态；真正的身份靠 Django session。
5. **会话有效期**：默认 2 周，勾选"记住我"延长到 30 天（`REMEMBER_ME_LOGIN_TTL`）。
6. **登录后缓存一致性**：登录/退出、第三方资料更新、评论写入都会 `delete_sidebar_cache()`，避免缓存里残留旧登录态或旧侧边栏。
7. **第三方登录免密**：`OAuthUser` 与 `BlogUser` 通过 `author` 外键绑定；同一邮箱自动复用已有账号，避免重复注册。
8. **找回密码的验证码时效**：6 位随机数字按邮箱为 key 存缓存，TTL 300 秒（5 分钟）过期自动失效；重置成功后密码以 PBKDF2 哈希覆盖旧值。
   注：默认 `CACHES` 是 `LocMemCache`（单进程内存），若多进程/多机部署应改用 Redis（`settings.py` 已支持 `DJANGO_REDIS_URL`），否则验证码在进程间不共享。

---

## 十、交付人信息

- 姓名：翟旌超　班级：软件工程 3 班　学号：2415304340
- 小组：3 班 4 组（组长：熊圆好；组员：纪秀茹、翟旌超、王鑫悦、陈汉佳、杨杰翰）
- 负责模块：`accounts`（注册 / 登录 / 找回密码流程）
- 本次交付：顺序图 ×3（注册、登录、第三方登录）+ **额外补齐**顺序图 ×1（找回密码）+ 本说明
