"""
oauth/templatetags/oauth_tags.py
================================
#yjh 本模块定义 oauth 应用的自定义模板标签：
    - load_oauth_applications 在登录页渲染"可用的第三方登录入口"列表
      （包含标签 inclusion_tag：渲染 oauth/oauth_applications.html 片段）
"""
from django import template
from django.urls import reverse

from oauth.oauthmanager import get_oauth_apps

register = template.Library()


@register.inclusion_tag('oauth/oauth_applications.html')
def load_oauth_applications(request):
    # yjh: 查询已启用的第三方登录方式，为每个平台拼好登录入口 URL：
    # /oauth/oauthlogin?type=<平台>&next_url=<当前页路径>
    # 这样登录完成后能回跳用户原来浏览的页面
    applications = get_oauth_apps()
    if applications:
        baseurl = reverse('oauth:oauthlogin')
        path = request.get_full_path()

        apps = list(map(lambda x: (x.ICON_NAME, '{baseurl}?type={type}&next_url={next}'.format(
            baseurl=baseurl, type=x.ICON_NAME, next=path)), applications))
    else:
        # yjh: 未配置任何第三方应用时返回空列表，登录页只显示账号密码登录
        apps = []
    return {
        'apps': apps
    }
