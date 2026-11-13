import json
from unittest.mock import patch
from urllib.parse import parse_qs, unquote, urlparse

from django.conf import settings
from django.contrib import auth
from django.contrib.auth import get_user_model
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse

from djangoblog.utils import get_sha256
from oauth.models import OAuthConfig, OAuthUser
from oauth.oauthmanager import BaseOauthManager


def _oauth_state(url):
    # 从 oauthlogin 的跳转地址中取出本次授权流程的 state（回调时须原样带回）
    return parse_qs(urlparse(url).query).get('state', [''])[0]



# Create your tests here.
class OAuthConfigTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.factory = RequestFactory()
        # 清除 OAuth apps 缓存，避免测试隔离问题
        from django.core.cache import cache
        cache.clear()

    def test_oauth_login_test(self):
        c = OAuthConfig()
        c.type = 'weibo'
        c.appkey = 'appkey'
        c.appsecret = 'appsecret'
        c.save()

        response = self.client.get('/oauth/oauthlogin?type=weibo')
        self.assertEqual(response.status_code, 302)
        self.assertTrue("api.weibo.com" in response.url)
        state = _oauth_state(response.url)

        response = self.client.get(
            f'/oauth/authorize?type=weibo&code=code&state={state}')
        # 授权失败时展示友好提示页（功能点3），而不是静默跳首页
        self.assertEqual(response.status_code, 200)
        self.assertIn('授权失败', response.content.decode())


class OauthLoginTest(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        self.factory = RequestFactory()
        # 清除 OAuth apps 缓存，避免测试隔离问题
        from django.core.cache import cache
        cache.clear()
        self.apps = self.init_apps()

    def init_apps(self):
        applications = [p() for p in BaseOauthManager.__subclasses__()]
        for application in applications:
            c = OAuthConfig()
            c.type = application.ICON_NAME.lower()
            c.appkey = 'appkey'
            c.appsecret = 'appsecret'
            c.save()
        return applications

    def get_app_by_type(self, type):
        for app in self.apps:
            if app.ICON_NAME.lower() == type:
                return app

    @patch("oauth.oauthmanager.WBOauthManager.do_post")
    @patch("oauth.oauthmanager.WBOauthManager.do_get")
    def test_weibo_login(self, mock_do_get, mock_do_post):
        weibo_app = self.get_app_by_type('weibo')
        assert weibo_app
        url = weibo_app.get_authorization_url()
        mock_do_post.return_value = json.dumps({"access_token": "access_token",
                                                "uid": "uid"
                                                })
        mock_do_get.return_value = json.dumps({
            "avatar_large": "avatar_large",
            "screen_name": "screen_name",
            "id": "id",
            "email": "email",
        })
        userinfo = weibo_app.get_access_token_by_code('code')
        self.assertEqual(userinfo.token, 'access_token')
        self.assertEqual(userinfo.openid, 'id')

    @patch("oauth.oauthmanager.GoogleOauthManager.do_post")
    @patch("oauth.oauthmanager.GoogleOauthManager.do_get")
    def test_google_login(self, mock_do_get, mock_do_post):
        google_app = self.get_app_by_type('google')
        assert google_app
        url = google_app.get_authorization_url()
        mock_do_post.return_value = json.dumps({
            "access_token": "access_token",
            "id_token": "id_token",
        })
        mock_do_get.return_value = json.dumps({
            "picture": "picture",
            "name": "name",
            "sub": "sub",
            "email": "email",
        })
        token = google_app.get_access_token_by_code('code')
        userinfo = google_app.get_oauth_userinfo()
        self.assertEqual(userinfo.token, 'access_token')
        self.assertEqual(userinfo.openid, 'sub')

    @patch("oauth.oauthmanager.GitHubOauthManager.do_post")
    @patch("oauth.oauthmanager.GitHubOauthManager.do_get")
    def test_github_login(self, mock_do_get, mock_do_post):
        github_app = self.get_app_by_type('github')
        assert github_app
        url = github_app.get_authorization_url()
        self.assertTrue("github.com" in url)
        self.assertTrue("client_id" in url)
        mock_do_post.return_value = "access_token=gho_16C7e42F292c6912E7710c838347Ae178B4a&scope=repo%2Cgist&token_type=bearer"
        mock_do_get.return_value = json.dumps({
            "avatar_url": "avatar_url",
            "name": "name",
            "id": "id",
            "email": "email",
        })
        token = github_app.get_access_token_by_code('code')
        userinfo = github_app.get_oauth_userinfo()
        self.assertEqual(userinfo.token, 'gho_16C7e42F292c6912E7710c838347Ae178B4a')
        self.assertEqual(userinfo.openid, 'id')


    @patch("oauth.oauthmanager.GitHubOauthManager.do_post")
    @patch("oauth.oauthmanager.GitHubOauthManager.do_get")
    def test_github_login_private_email(self, mock_do_get, mock_do_post):
        """Test GitHub OAuth login when user's email is private"""
        github_app = self.get_app_by_type('github')
        assert github_app
        url = github_app.get_authorization_url()
        # Verify the URL starts with GitHub's OAuth endpoint
        self.assertTrue(url.startswith("https://github.com/login/oauth/authorize"))
        self.assertTrue("client_id" in url)
        # Check that the scope parameter includes user:email (URL-encoded form)
        self.assertIn("user:email", unquote(url))
        
        mock_do_post.return_value = "access_token=gho_test_token&scope=user:email&token_type=bearer"
        
        # First call returns user info without email (private email)
        # Second call returns emails from /user/emails endpoint
        mock_do_get.side_effect = [
            json.dumps({
                "avatar_url": "avatar_url",
                "name": "name",
                "id": "id",
                "email": None,  # Email is private
            }),
            json.dumps([
                {
                    "email": "user@example.com",
                    "primary": True,
                    "verified": True,
                    "visibility": "private"
                }
            ])
        ]
        
        token = github_app.get_access_token_by_code('code')
        userinfo = github_app.get_oauth_userinfo()
        self.assertEqual(userinfo.token, 'gho_test_token')
        self.assertEqual(userinfo.openid, 'id')
        self.assertEqual(userinfo.email, 'user@example.com')
        # Verify both API calls were made
        self.assertEqual(mock_do_get.call_count, 2)

    @patch("oauth.oauthmanager.FaceBookOauthManager.do_post")
    @patch("oauth.oauthmanager.FaceBookOauthManager.do_get")
    def test_facebook_login(self, mock_do_get, mock_do_post):
        facebook_app = self.get_app_by_type('facebook')
        assert facebook_app
        url = facebook_app.get_authorization_url()
        self.assertTrue("facebook.com" in url)
        mock_do_post.return_value = json.dumps({
            "access_token": "access_token",
        })
        mock_do_get.return_value = json.dumps({
            "name": "name",
            "id": "id",
            "email": "email",
            "picture": {
                "data": {
                    "url": "url"
                }
            }
        })
        token = facebook_app.get_access_token_by_code('code')
        userinfo = facebook_app.get_oauth_userinfo()
        self.assertEqual(userinfo.token, 'access_token')

    @patch("oauth.oauthmanager.QQOauthManager.do_get", side_effect=[
        'access_token=access_token&expires_in=3600',
        'callback({"client_id":"appid","openid":"openid"} );',
        json.dumps({
            "nickname": "nickname",
            "email": "email",
            "figureurl": "figureurl",
            "openid": "openid",
        })
    ])
    def test_qq_login(self, mock_do_get):
        qq_app = self.get_app_by_type('qq')
        assert qq_app
        url = qq_app.get_authorization_url()
        self.assertTrue("qq.com" in url)
        token = qq_app.get_access_token_by_code('code')
        userinfo = qq_app.get_oauth_userinfo()
        self.assertEqual(userinfo.token, 'access_token')

    @patch("oauth.oauthmanager.WBOauthManager.do_post")
    @patch("oauth.oauthmanager.WBOauthManager.do_get")
    def test_weibo_authoriz_login_with_email(self, mock_do_get, mock_do_post):

        mock_do_post.return_value = json.dumps({"access_token": "access_token",
                                                "uid": "uid"
                                                })
        mock_user_info = {
            "avatar_large": "avatar_large",
            "screen_name": "screen_name1",
            "id": "id",
            "email": "email",
        }
        mock_do_get.return_value = json.dumps(mock_user_info)

        response = self.client.get('/oauth/oauthlogin?type=weibo')
        self.assertEqual(response.status_code, 302)
        self.assertTrue("api.weibo.com" in response.url)
        state = _oauth_state(response.url)

        response = self.client.get(
            f'/oauth/authorize?type=weibo&code=code&state={state}')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/')

        user = auth.get_user(self.client)
        assert user.is_authenticated
        self.assertTrue(user.is_authenticated)
        self.assertEqual(user.username, mock_user_info['screen_name'])
        self.assertEqual(user.email, mock_user_info['email'])
        self.client.logout()

        # 重新发起一次授权，拿到新的 state 才能通过回调校验
        response = self.client.get('/oauth/oauthlogin?type=weibo')
        state = _oauth_state(response.url)
        response = self.client.get(
            f'/oauth/authorize?type=weibo&code=code&state={state}')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/')

        user = auth.get_user(self.client)
        assert user.is_authenticated
        self.assertTrue(user.is_authenticated)
        self.assertEqual(user.username, mock_user_info['screen_name'])
        self.assertEqual(user.email, mock_user_info['email'])

    @patch("oauth.oauthmanager.WBOauthManager.do_post")
    @patch("oauth.oauthmanager.WBOauthManager.do_get")
    def test_weibo_authoriz_login_without_email(self, mock_do_get, mock_do_post):

        mock_do_post.return_value = json.dumps({"access_token": "access_token",
                                                "uid": "uid"
                                                })
        mock_user_info = {
            "avatar_large": "avatar_large",
            "screen_name": "screen_name1",
            "id": "id",
        }
        mock_do_get.return_value = json.dumps(mock_user_info)

        response = self.client.get('/oauth/oauthlogin?type=weibo')
        self.assertEqual(response.status_code, 302)
        self.assertTrue("api.weibo.com" in response.url)
        state = _oauth_state(response.url)

        response = self.client.get(
            f'/oauth/authorize?type=weibo&code=code&state={state}')

        self.assertEqual(response.status_code, 302)

        oauth_user_id = int(response.url.split('/')[-1].split('.')[0])
        self.assertEqual(response.url, f'/oauth/requireemail/{oauth_user_id}.html')

        response = self.client.post(response.url, {'email': 'test@gmail.com', 'oauthid': oauth_user_id})

        self.assertEqual(response.status_code, 302)
        sign = get_sha256(settings.SECRET_KEY +
                          str(oauth_user_id) + settings.SECRET_KEY)

        url = reverse('oauth:bindsuccess', kwargs={
            'oauthid': oauth_user_id,
        })
        self.assertEqual(response.url, f'{url}?type=email')

        path = reverse('oauth:email_confirm', kwargs={
            'id': oauth_user_id,
            'sign': sign
        })
        response = self.client.get(path)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, f'/oauth/bindsuccess/{oauth_user_id}.html?type=success')
        user = auth.get_user(self.client)
        from oauth.models import OAuthUser
        oauth_user = OAuthUser.objects.get(author=user)
        self.assertTrue(user.is_authenticated)
        self.assertEqual(user.username, mock_user_info['screen_name'])
        self.assertEqual(user.email, 'test@gmail.com')
        self.assertEqual(oauth_user.pk, oauth_user_id)


class OAuthStateSecurityTest(TestCase):
    """功能点1：OAuth state 参数校验（防登录 CSRF）"""

    def setUp(self):
        self.client = Client()
        from django.core.cache import cache
        cache.clear()
        OAuthConfig.objects.create(
            type='weibo', appkey='appkey', appsecret='appsecret',
            callback_url='http://testserver/oauth/authorize',
            is_enable=True)

    @patch("oauth.oauthmanager.WBOauthManager.do_post")
    def test_callback_without_state_is_rejected(self, mock_do_post):
        """回调缺少 state（伪造回调）必须拒绝，且不触发换取 token"""
        mock_do_post.return_value = json.dumps(
            {"access_token": "access_token", "uid": "uid"})

        response = self.client.get('/oauth/authorize?type=weibo&code=code')

        self.assertEqual(response.status_code, 400)
        self.assertIn('授权请求已失效', response.content.decode())
        mock_do_post.assert_not_called()
        self.assertFalse(auth.get_user(self.client).is_authenticated)

    @patch("oauth.oauthmanager.WBOauthManager.do_post")
    def test_callback_with_wrong_state_is_rejected(self, mock_do_post):
        """state 被篡改（与 session 不一致）必须拒绝"""
        mock_do_post.return_value = json.dumps(
            {"access_token": "access_token", "uid": "uid"})

        response = self.client.get('/oauth/oauthlogin?type=weibo')
        response = self.client.get(
            '/oauth/authorize?type=weibo&code=code&state=forged')

        self.assertEqual(response.status_code, 400)
        self.assertIn('授权请求已失效', response.content.decode())
        mock_do_post.assert_not_called()

    @patch("oauth.oauthmanager.WBOauthManager.do_post")
    @patch("oauth.oauthmanager.WBOauthManager.do_get")
    def test_state_cannot_be_replayed(self, mock_do_get, mock_do_post):
        """同一个 state 只能用一次，重放必须拒绝"""
        mock_do_post.return_value = json.dumps(
            {"access_token": "access_token", "uid": "uid"})
        mock_do_get.return_value = json.dumps({
            "avatar_large": "avatar_large",
            "screen_name": "screen_name1",
            "id": "id",
            "email": "email",
        })

        response = self.client.get('/oauth/oauthlogin?type=weibo')
        state = _oauth_state(response.url)
        self.client.get(f'/oauth/authorize?type=weibo&code=code&state={state}')

        # 原样重放同一 state：session 中已消费，必须拒绝
        response = self.client.get(
            f'/oauth/authorize?type=weibo&code=code&state={state}')
        self.assertEqual(response.status_code, 400)
        self.assertIn('授权请求已失效', response.content.decode())


class OAuthBindingViewTest(TestCase):
    """功能点2：第三方账号绑定/解绑"""

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        OAuthConfig.objects.create(
            type='weibo', appkey='appkey', appsecret='appsecret',
            callback_url='http://testserver/oauth/authorize',
            is_enable=True)
        self.user = get_user_model().objects.create_user(
            username='binduser', email='bind@example.com', password='password')
        self.client.force_login(self.user)

    def test_bindings_page_renders(self):
        """账号管理页可正常打开，并列出可绑定平台"""
        response = self.client.get(reverse('oauth:bindings'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('微博', response.content.decode())

    @patch("oauth.oauthmanager.WBOauthManager.do_get")
    @patch("oauth.oauthmanager.WBOauthManager.do_post")
    def test_bind_third_party_account(self, mock_do_post, mock_do_get):
        """已登录用户发起绑定后，第三方身份挂到当前账号（而不是登录成新账号）"""
        mock_do_post.return_value = json.dumps(
            {"access_token": "token", "uid": "uid-bind"})
        mock_do_get.return_value = json.dumps({
            "avatar_large": "avatar", "screen_name": "nick",
            "id": "id", "email": "bind@example.com"})

        response = self.client.get('/oauth/oauthlogin?type=weibo&bind=1')
        state = _oauth_state(response.url)
        response = self.client.get(
            f'/oauth/authorize?type=weibo&code=code&state={state}')

        self.assertEqual(response.status_code, 302)
        self.assertIn('result=bound', response.url)
        oauth_user = OAuthUser.objects.get(type='weibo', openid='id')
        self.assertEqual(oauth_user.author_id, self.user.id)

    def test_unbind_own_account(self):
        """解绑自己的第三方账号"""
        oauth_user = OAuthUser.objects.create(
            author=self.user, openid='openid-unbind', nickname='nick',
            type='weibo', token='token')

        response = self.client.post(
            reverse('oauth:unbind', kwargs={'oauthid': oauth_user.id}))

        self.assertEqual(response.status_code, 302)
        self.assertIn('result=unbound', response.url)
        self.assertFalse(OAuthUser.objects.filter(id=oauth_user.id).exists())

    def test_cannot_unbind_last_login_method(self):
        """无可用密码且只剩一个绑定时，禁止解绑（防把自己锁在门外）"""
        # 改密码会使已有 session 失效，因此先设为不可用密码再登录
        self.user.set_unusable_password()
        self.user.save()
        self.client.force_login(self.user)
        oauth_user = OAuthUser.objects.create(
            author=self.user, openid='openid-last', nickname='nick',
            type='weibo', token='token')

        response = self.client.post(
            reverse('oauth:unbind', kwargs={'oauthid': oauth_user.id}))

        self.assertEqual(response.status_code, 302)
        self.assertIn('result=last', response.url)
        self.assertTrue(OAuthUser.objects.filter(id=oauth_user.id).exists())

    def test_cannot_unbind_other_users_account(self):
        """不能解绑别人名下的第三方账号"""
        other = get_user_model().objects.create_user(
            username='other', email='other@example.com', password='password')
        oauth_user = OAuthUser.objects.create(
            author=other, openid='openid-other', nickname='nick',
            type='weibo', token='token')

        response = self.client.post(
            reverse('oauth:unbind', kwargs={'oauthid': oauth_user.id}))

        self.assertEqual(response.status_code, 404)
        self.assertTrue(OAuthUser.objects.filter(id=oauth_user.id).exists())

    def test_unbind_requires_post(self):
        """解绑必须用 POST，GET 请求被拒绝（防 CSRF 式解绑）"""
        oauth_user = OAuthUser.objects.create(
            author=self.user, openid='openid-get', nickname='nick',
            type='weibo', token='token')

        response = self.client.get(
            reverse('oauth:unbind', kwargs={'oauthid': oauth_user.id}))

        self.assertEqual(response.status_code, 405)
        self.assertTrue(OAuthUser.objects.filter(id=oauth_user.id).exists())


class OAuthFailureHintTest(TestCase):
    """功能点3：授权失败友好提示与分阶段日志"""

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.client = Client()
        OAuthConfig.objects.create(
            type='weibo', appkey='appkey', appsecret='appsecret',
            callback_url='http://testserver/oauth/authorize',
            is_enable=True)
        OAuthConfig.objects.create(
            type='github', appkey='appkey', appsecret='appsecret',
            callback_url='http://testserver/oauth/authorize',
            is_enable=True)

    def test_unsupported_type_shows_friendly_page(self):
        """未知平台不再静默跳首页，而是给出提示页"""
        response = self.client.get('/oauth/authorize?type=unknown')

        self.assertEqual(response.status_code, 200)
        self.assertIn('不支持的第三方登录方式', response.content.decode())

    def test_token_failure_shows_friendly_page_and_logs(self):
        """换取 token 失败：提示页 + 带阶段的 warning 日志"""
        with self.assertLogs('oauth.views', level='WARNING') as logs:
            response = self.client.get('/oauth/oauthlogin?type=github')
            state = _oauth_state(response.url)
            with patch("oauth.oauthmanager.GitHubOauthManager.do_post") as mock_do_post:
                mock_do_post.return_value = 'error=bad_verification_code'
                response = self.client.get(
                    f'/oauth/authorize?type=github&code=code&state={state}')

        self.assertEqual(response.status_code, 200)
        page = response.content.decode()
        self.assertIn('获取授权凭证失败', page)
        self.assertIn('重新授权', page)
        self.assertTrue(any('stage=token_failed' in line for line in logs.output))

    @patch("oauth.oauthmanager.GitHubOauthManager.do_get")
    @patch("oauth.oauthmanager.GitHubOauthManager.do_post")
    def test_userinfo_failure_shows_friendly_page(
            self, mock_do_post, mock_do_get):
        """拉取用户信息失败：提示页而非静默回跳"""
        mock_do_post.return_value = 'access_token=token&token_type=bearer'
        mock_do_get.return_value = 'invalid json'

        response = self.client.get('/oauth/oauthlogin?type=github')
        state = _oauth_state(response.url)
        response = self.client.get(
            f'/oauth/authorize?type=github&code=code&state={state}')

        self.assertEqual(response.status_code, 200)
        self.assertIn('获取第三方用户信息失败', response.content.decode())

