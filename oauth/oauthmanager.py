"""
oauth/oauthmanager.py
=====================
#yjh 本模块是第三方登录（OAuth2.0）的核心策略层，采用"策略模式 + 模板方法"设计：
    - BaseOauthManager 定义 OAuth 授权的标准三步流程（抽象接口）：
      ① get_authorization_url  生成跳转第三方授权页的 URL
      ② get_access_token_by_code 用授权码 code 换取 access_token
      ③ get_oauth_userinfo     用 access_token 拉取第三方用户资料
    - 每个第三方平台（微博/Google/GitHub/Facebook/QQ）一个子类，
      只实现自己平台的差异部分（URL、参数、响应解析）。
    - 模块底部的 get_oauth_apps()/get_manager_by_type() 是工厂函数，
      根据数据库 OAuthConfig 中启用的配置动态实例化对应管理器。
#yjh 注意：各平台的 appkey/appsecret/callback_url 均存于数据库
    OAuthConfig 表（后台可配），而不是写死在代码里，便于多环境切换。
"""
import json
import logging
import os
import urllib.parse
from abc import ABCMeta, abstractmethod

import requests

from djangoblog.utils import cache_decorator
from oauth.models import OAuthUser, OAuthConfig

logger = logging.getLogger(__name__)


class OAuthAccessTokenException(Exception):
    '''
    oauth授权失败异常
    #yjh 当用 code 换 access_token 失败（如 code 过期、appsecret 错误、
    用户拒绝授权）时抛出，views.authorize 捕获后重定向回首页
    '''


class BaseOauthManager(metaclass=ABCMeta):
    # yjh: OAuth 管理器抽象基类（模板方法模式）。
    # 子类必须实现 4 个抽象方法，通用能力（HTTP 请求、配置读取）在此复用。
    """获取用户授权"""
    # yjh: 第三方平台的"授权页"地址，子类以类属性覆盖
    AUTH_URL = None
    """获取token"""
    # yjh: 第三方平台的"code 换 token"接口地址
    TOKEN_URL = None
    """获取用户信息"""
    # yjh: 第三方平台的"用户信息"接口地址
    API_URL = None
    '''icon图标名'''
    # yjh: 平台标识，同时作为数据库 OAuthConfig.type 的取值（如 'github'）
    ICON_NAME = None

    def __init__(self, access_token=None, openid=None):
        # yjh: 两个核心会话状态：access_token（访问令牌）、openid（平台内用户唯一标识）
        self.access_token = access_token
        self.openid = openid

    @property
    def is_access_token_set(self):
        # yjh: 是否已拿到 access_token（授权流程第②步完成的标志）
        return self.access_token is not None

    @property
    def is_authorized(self):
        # yjh: 是否完成完整授权（token 和 openid 都具备才能拉取用户信息）
        return self.is_access_token_set and self.access_token is not None and self.openid is not None

    @abstractmethod
    def get_authorization_url(self, nexturl='/'):
        # yjh: 抽象方法①：拼接授权页 URL，nexturl 为登录成功后的回跳地址
        pass

    @abstractmethod
    def get_access_token_by_code(self, code):
        # yjh: 抽象方法②：用回调携带的 code 换 access_token
        pass

    @abstractmethod
    def get_oauth_userinfo(self):
        # yjh: 抽象方法③：拉取第三方用户资料并组装成 OAuthUser（未保存入库）
        pass

    @abstractmethod
    def get_picture(self, metadata):
        # yjh: 抽象方法④：从原始 metadata（JSON 字符串）中解析头像地址
        pass

    def do_get(self, url, params, headers=None):
        # yjh: 封装的 GET 请求，统一打日志便于排查第三方接口问题
        rsp = requests.get(url=url, params=params, headers=headers)
        logger.info(rsp.text)
        return rsp.text

    def do_post(self, url, params, headers=None):
        # yjh: 封装的 POST 请求，注意参数走的是 params（查询串）而非表单 body
        rsp = requests.post(url, params, headers=headers)
        logger.info(rsp.text)
        return rsp.text

    def get_config(self):
        # yjh: 按 ICON_NAME 从数据库读取本平台配置（appkey/appsecret/回调地址）
        # yjh: 注意：数据库允许同类型多条时只取第一条，但 OAuthConfig.clean 已限制唯一
        value = OAuthConfig.objects.filter(type=self.ICON_NAME)
        return value[0] if value else None


class WBOauthManager(BaseOauthManager):
    # yjh: 新浪微博 OAuth2.0 实现（无需代理，国内可直接访问）
    AUTH_URL = 'https://api.weibo.com/oauth2/authorize'
    TOKEN_URL = 'https://api.weibo.com/oauth2/access_token'
    API_URL = 'https://api.weibo.com/2/users/show.json'
    ICON_NAME = 'weibo'

    def __init__(self, access_token=None, openid=None):
        # yjh: 各子类构造时统一从数据库读配置，未配置时降级为空字符串（不会抛异常）
        config = self.get_config()
        self.client_id = config.appkey if config else ''
        self.client_secret = config.appsecret if config else ''
        self.callback_url = config.callback_url if config else ''
        super(
            WBOauthManager,
            self).__init__(
            access_token=access_token,
            openid=openid)

    def get_authorization_url(self, nexturl='/'):
        params = {
            'client_id': self.client_id,
            'response_type': 'code',
            'redirect_uri': self.callback_url + '&next_url=' + nexturl
        }
        # yjh: 微博不支持在 state 参数里带 next_url，项目采用的做法是
        # 把 next_url 拼在回调地址后面，回调时再从 query string 中取出
        url = self.AUTH_URL + "?" + urllib.parse.urlencode(params)
        return url

    def get_access_token_by_code(self, code):

        params = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': self.callback_url
        }
        # yjh: 微博规范要求 POST 请求换 token
        rsp = self.do_post(self.TOKEN_URL, params)

        obj = json.loads(rsp)
        if 'access_token' in obj:
            self.access_token = str(obj['access_token'])
            # yjh: 微博在换 token 的响应里直接返回 uid，即用户的 openid
            self.openid = str(obj['uid'])
            # yjh: 微博实现里拿到 token 后"顺手"直接拉取用户信息并返回（与其他平台不同）
            return self.get_oauth_userinfo()
        else:
            # yjh: 响应中没有 token 说明授权失败，抛出异常由上层捕获
            raise OAuthAccessTokenException(rsp)

    def get_oauth_userinfo(self):
        if not self.is_authorized:
            # yjh: 未完成授权直接返回 None，防御式编程
            return None
        params = {
            'uid': self.openid,
            'access_token': self.access_token
        }
        rsp = self.do_get(self.API_URL, params)
        try:
            datas = json.loads(rsp)
            # yjh: 把第三方返回的字段映射到本站 OAuthUser 模型
            user = OAuthUser()
            user.metadata = rsp  # yjh: 原始报文整体留档，后续可解析更多字段
            user.picture = datas['avatar_large']  # yjh: 大图头像
            user.nickname = datas['screen_name']
            user.openid = datas['id']
            user.type = 'weibo'
            user.token = self.access_token
            if 'email' in datas and datas['email']:
                # yjh: 微博默认不返回 email，需应用单独申请权限，故做判空
                user.email = datas['email']
            return user
        except Exception as e:
            # yjh: 解析失败只记日志返回 None，由视图层决定跳转，避免 500
            logger.error(e)
            logger.error('weibo oauth error.rsp:' + rsp)
            return None

    def get_picture(self, metadata):
        # yjh: 从头像字段需要二次解析的场景（如缓存的 metadata）取大图
        datas = json.loads(metadata)
        return datas['avatar_large']


class ProxyManagerMixin:
    # yjh: 代理支持混入类：Google/GitHub/Facebook 在国内网络不可直连，
    # 通过环境变量 HTTP_PROXY 配置代理后，重写 do_get/do_post 带上 proxies。
    # 利用 Python MRO（方法解析顺序），Mixin 写在基类左边即可覆盖请求方法。
    def __init__(self, *args, **kwargs):
        if os.environ.get("HTTP_PROXY"):
            self.proxies = {
                "http": os.environ.get("HTTP_PROXY"),
                "https": os.environ.get("HTTP_PROXY")
            }
        else:
            self.proxies = None

    def do_get(self, url, params, headers=None):
        rsp = requests.get(url=url, params=params, headers=headers, proxies=self.proxies)
        logger.info(rsp.text)
        return rsp.text

    def do_post(self, url, params, headers=None):
        rsp = requests.post(url, params, headers=headers, proxies=self.proxies)
        logger.info(rsp.text)
        return rsp.text


class GoogleOauthManager(ProxyManagerMixin, BaseOauthManager):
    # yjh: Google OAuth2.0 / OpenID Connect 实现（继承代理 Mixin）
    AUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
    TOKEN_URL = 'https://www.googleapis.com/oauth2/v4/token'
    API_URL = 'https://www.googleapis.com/oauth2/v3/userinfo'
    ICON_NAME = 'google'

    def __init__(self, access_token=None, openid=None):
        config = self.get_config()
        self.client_id = config.appkey if config else ''
        self.client_secret = config.appsecret if config else ''
        self.callback_url = config.callback_url if config else ''
        super(
            GoogleOauthManager,
            self).__init__(
            access_token=access_token,
            openid=openid)

    def get_authorization_url(self, nexturl='/'):
        params = {
            'client_id': self.client_id,
            'response_type': 'code',
            'redirect_uri': self.callback_url,
            'scope': 'openid email',
        }
        # yjh: scope='openid email' 是 OIDC 标准写法，可申请到 email 声明
        url = self.AUTH_URL + "?" + urllib.parse.urlencode(params)
        return url

    def get_access_token_by_code(self, code):
        params = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'grant_type': 'authorization_code',
            'code': code,

            'redirect_uri': self.callback_url
        }
        rsp = self.do_post(self.TOKEN_URL, params)

        obj = json.loads(rsp)

        if 'access_token' in obj:
            self.access_token = str(obj['access_token'])
            # yjh: 注意这里把 id_token（JWT）暂存进 openid 字段，
            # 仅为通过 is_authorized 校验；真正的 openid 是后面 userinfo 接口返回的 sub
            self.openid = str(obj['id_token'])
            logger.info(self.ICON_NAME + ' oauth ' + rsp)
            return self.access_token
        else:
            raise OAuthAccessTokenException(rsp)

    def get_oauth_userinfo(self):
        if not self.is_authorized:
            return None
        params = {
            'access_token': self.access_token
        }
        rsp = self.do_get(self.API_URL, params)
        try:

            datas = json.loads(rsp)
            user = OAuthUser()
            user.metadata = rsp
            user.picture = datas['picture']
            user.nickname = datas['name']
            # yjh: OIDC 标准中 sub 字段才是用户唯一标识，覆盖掉之前的 id_token
            user.openid = datas['sub']
            user.token = self.access_token
            user.type = 'google'
            if datas['email']:
                user.email = datas['email']
            return user
        except Exception as e:
            logger.error(e)
            logger.error('google oauth error.rsp:' + rsp)
            return None

    def get_picture(self, metadata):
        datas = json.loads(metadata)
        return datas['picture']


class GitHubOauthManager(ProxyManagerMixin, BaseOauthManager):
    # yjh: GitHub OAuth2.0 实现（继承代理 Mixin）
    AUTH_URL = 'https://github.com/login/oauth/authorize'
    TOKEN_URL = 'https://github.com/login/oauth/access_token'
    API_URL = 'https://api.github.com/user'
    # yjh: 单独的邮箱接口——用户未公开邮箱时 /user 不返回 email 字段
    EMAILS_API_URL = 'https://api.github.com/user/emails'
    ICON_NAME = 'github'

    def __init__(self, access_token=None, openid=None):
        config = self.get_config()
        self.client_id = config.appkey if config else ''
        self.client_secret = config.appsecret if config else ''
        self.callback_url = config.callback_url if config else ''
        super(
            GitHubOauthManager,
            self).__init__(
            access_token=access_token,
            openid=openid)

    def get_authorization_url(self, next_url='/'):
        params = {
            'client_id': self.client_id,
            'response_type': 'code',
            'redirect_uri': f'{self.callback_url}&next_url={next_url}',
            'scope': 'user:email'
        }
        # yjh: scope='user:email' 才能访问 /user/emails 读取用户私有邮箱
        url = self.AUTH_URL + "?" + urllib.parse.urlencode(params)
        return url

    def get_access_token_by_code(self, code):
        params = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'grant_type': 'authorization_code',
            'code': code,

            'redirect_uri': self.callback_url
        }
        rsp = self.do_post(self.TOKEN_URL, params)

        # yjh: GitHub 默认返回 form-urlencoded 格式（access_token=xxx&scope=...），
        # 而非 JSON，所以这里用 parse_qs 解析而不是 json.loads
        from urllib import parse
        r = parse.parse_qs(rsp)
        if 'access_token' in r:
            self.access_token = (r['access_token'][0])
            return self.access_token
        else:
            raise OAuthAccessTokenException(rsp)

    def get_oauth_userinfo(self):

        # yjh: GitHub 要求 token 放在 Authorization 请求头（Bearer 方案），
        # 而不是像微博/QQ 那样放在查询参数里
        rsp = self.do_get(self.API_URL, params={}, headers={
            "Authorization": "Bearer " + self.access_token
        })
        try:
            datas = json.loads(rsp)
            user = OAuthUser()
            user.picture = datas['avatar_url']
            user.nickname = datas['name']
            user.openid = datas['id']
            user.type = 'github'
            user.token = self.access_token
            user.metadata = rsp
            if 'email' in datas and datas['email']:
                # yjh: 用户在 GitHub 设置了公开邮箱，直接用
                user.email = datas['email']
            else:
                # If email is not public, fetch from /user/emails endpoint
                # yjh: 邮箱未公开时，调用 /user/emails 兜底获取（亮点设计）：
                # 优先取"已验证 + 主邮箱"，其次任一已验证邮箱，保证拿到可用邮箱
                try:
                    emails_rsp = self.do_get(self.EMAILS_API_URL, params={}, headers={
                        "Authorization": "Bearer " + self.access_token
                    })
                    emails = json.loads(emails_rsp)
                    # Find verified email, prioritizing primary verified email
                    for email_data in emails:
                        if email_data.get('verified'):
                            if email_data.get('primary'):
                                # Primary verified email takes priority
                                # yjh: 主邮箱且已验证——最优选择，立即结束循环
                                user.email = email_data.get('email')
                                break
                            elif not user.email:
                                # Use first verified email as fallback
                                # yjh: 先记录第一个已验证邮箱作为兜底，继续找主邮箱
                                user.email = email_data.get('email')
                except Exception as e:
                    logger.warning(f'Failed to fetch private email from GitHub API. User login will fail if email is required: {e}')
            return user
        except Exception as e:
            logger.error(e)
            logger.error('github oauth error.rsp:' + rsp)
            return None

    def get_picture(self, metadata):
        datas = json.loads(metadata)
        return datas['avatar_url']


class FaceBookOauthManager(ProxyManagerMixin, BaseOauthManager):
    # yjh: Facebook OAuth2.0 实现，使用 Graph API v16.0（继承代理 Mixin）
    AUTH_URL = 'https://www.facebook.com/v16.0/dialog/oauth'
    TOKEN_URL = 'https://graph.facebook.com/v16.0/oauth/access_token'
    API_URL = 'https://graph.facebook.com/me'
    ICON_NAME = 'facebook'

    def __init__(self, access_token=None, openid=None):
        config = self.get_config()
        self.client_id = config.appkey if config else ''
        self.client_secret = config.appsecret if config else ''
        self.callback_url = config.callback_url if config else ''
        super(
            FaceBookOauthManager,
            self).__init__(
            access_token=access_token,
            openid=openid)

    def get_authorization_url(self, next_url='/'):
        params = {
            'client_id': self.client_id,
            'response_type': 'code',
            'redirect_uri': self.callback_url,
            'scope': 'email,public_profile'
        }
        # yjh: public_profile 提供 id/name，email 需单独声明 scope
        url = self.AUTH_URL + "?" + urllib.parse.urlencode(params)
        return url

    def get_access_token_by_code(self, code):
        params = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            # 'grant_type': 'authorization_code',
            'code': code,

            'redirect_uri': self.callback_url
        }
        rsp = self.do_post(self.TOKEN_URL, params)

        obj = json.loads(rsp)
        if 'access_token' in obj:
            token = str(obj['access_token'])
            self.access_token = token
            return self.access_token
        else:
            raise OAuthAccessTokenException(rsp)

    def get_oauth_userinfo(self):
        params = {
            'access_token': self.access_token,
            # yjh: Graph API 特点：必须用 fields 显式声明要返回哪些字段
            'fields': 'id,name,picture,email'
        }
        try:
            rsp = self.do_get(self.API_URL, params)
            datas = json.loads(rsp)
            user = OAuthUser()
            user.nickname = datas['name']
            user.openid = datas['id']
            user.type = 'facebook'
            user.token = self.access_token
            user.metadata = rsp
            if 'email' in datas and datas['email']:
                user.email = datas['email']
            # yjh: Facebook 头像是多层嵌套结构 picture.data.url，需逐级判空防 KeyError
            if 'picture' in datas and datas['picture'] and datas['picture']['data'] and datas['picture']['data']['url']:
                user.picture = str(datas['picture']['data']['url'])
            return user
        except Exception as e:
            logger.error(e)
            return None

    def get_picture(self, metadata):
        datas = json.loads(metadata)
        return str(datas['picture']['data']['url'])


class QQOauthManager(BaseOauthManager):
    # yjh: QQ 互联 OAuth2.0 实现（国内平台，无需代理）
    AUTH_URL = 'https://graph.qq.com/oauth2.0/authorize'
    TOKEN_URL = 'https://graph.qq.com/oauth2.0/token'
    API_URL = 'https://graph.qq.com/user/get_user_info'
    # yjh: QQ 特有：openid 不在换 token 的响应里，需要单独接口获取
    OPEN_ID_URL = 'https://graph.qq.com/oauth2.0/me'
    ICON_NAME = 'qq'

    def __init__(self, access_token=None, openid=None):
        config = self.get_config()
        self.client_id = config.appkey if config else ''
        self.client_secret = config.appsecret if config else ''
        self.callback_url = config.callback_url if config else ''
        super(
            QQOauthManager,
            self).__init__(
            access_token=access_token,
            openid=openid)

    def get_authorization_url(self, next_url='/'):
        params = {
            'response_type': 'code',
            'client_id': self.client_id,
            'redirect_uri': self.callback_url + '&next_url=' + next_url,
        }
        url = self.AUTH_URL + "?" + urllib.parse.urlencode(params)
        return url

    def get_access_token_by_code(self, code):
        params = {
            'grant_type': 'authorization_code',
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'code': code,
            'redirect_uri': self.callback_url
        }
        # yjh: 注意 QQ 换 token 用的是 GET 请求（微博是 POST），各平台规范不统一
        rsp = self.do_get(self.TOKEN_URL, params)
        if rsp:
            # yjh: QQ 返回的也是 form-urlencoded 格式，用 parse_qs 解析
            d = urllib.parse.parse_qs(rsp)
            if 'access_token' in d:
                token = d['access_token']
                self.access_token = token[0]
                return token
        else:
            raise OAuthAccessTokenException(rsp)

    def get_open_id(self):
        # yjh: QQ 流程第③步前置：先拿 openid（腾讯系应用间用户唯一标识）
        if self.is_access_token_set:
            params = {
                'access_token': self.access_token
            }
            rsp = self.do_get(self.OPEN_ID_URL, params)
            if rsp:
                # yjh: QQ 返回 JSONP 格式：callback( {"openid":"..."} );
                # 需先剥掉 callback( 和 ); 外壳才能按 JSON 解析
                rsp = rsp.replace(
                    'callback(', '').replace(
                    ')', '').replace(
                    ';', '')
                obj = json.loads(rsp)
                openid = str(obj['openid'])
                self.openid = openid
                return openid

    def get_oauth_userinfo(self):
        openid = self.get_open_id()
        if openid:
            params = {
                'access_token': self.access_token,
                # yjh: QQ 接口要求额外传 oauth_consumer_key（即 appid）
                'oauth_consumer_key': self.client_id,
                'openid': self.openid
            }
            rsp = self.do_get(self.API_URL, params)
            logger.info(rsp)
            obj = json.loads(rsp)
            user = OAuthUser()
            user.nickname = obj['nickname']
            user.openid = openid
            user.type = 'qq'
            user.token = self.access_token
            user.metadata = rsp
            if 'email' in obj:
                user.email = obj['email']
            if 'figureurl' in obj:
                # yjh: QQ 头像字段名为 figureurl（默认 40×40 尺寸）
                user.picture = str(obj['figureurl'])
            return user

    def get_picture(self, metadata):
        datas = json.loads(metadata)
        return str(datas['figureurl'])


@cache_decorator(expiration=100 * 60)
def get_oauth_apps():
    # yjh: 工厂函数：读取数据库中"已启用"的 OAuth 配置，
    # 利用 __subclasses__() 反射拿到所有管理器子类，匹配后实例化返回。
    # 结果缓存 100 分钟，避免每次登录页渲染都查库。
    configs = OAuthConfig.objects.filter(is_enable=True).all()
    if not configs:
        return []
    configtypes = [x.type for x in configs]
    applications = BaseOauthManager.__subclasses__()
    apps = [x() for x in applications if x().ICON_NAME.lower() in configtypes]
    return apps


def get_manager_by_type(type):
    # yjh: 按平台标识（如 'github'）从已启用的管理器中查找对应实例，
    # 供 views 层 oauthlogin/authorize 调用；找不到返回 None
    applications = get_oauth_apps()
    if applications:
        finds = list(
            filter(
                lambda x: x.ICON_NAME.lower() == type.lower(),
                applications))
        if finds:
            return finds[0]
    return None
