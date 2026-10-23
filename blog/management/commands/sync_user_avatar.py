# ============================================================
# blog/management/commands/sync_user_avatar.py —— 批量修复第三方登录用户头像的 management command
# 作用：OAuth（GitHub / Google / 微博等）用户注册时，头像地址是直接照抄对方平台的，时间一长
#       常常 404，或者指向本地 static 目录里已经不存在的老文件。本命令遍历全部 OAuthUser，
#       逐个校验 picture 字段：远程地址一律下载到本地保存，本地文件失效的尝试重新拉取，
#       实在救不回来的统一换成默认头像。
# 用法：python manage.py sync_user_avatar
# 本文件包含：
#   Command.test_picture() —— 探测一个图片 URL 是否还能正常访问（HTTP 200）
#   Command.handle() —— 遍历所有 OAuthUser，按「本地可用 / 本地失效 / 远程地址 / 空值」四种情况修正 picture
# 注释人：翟旌超（软件工程 3 班 2415304340，#zjc）
# 说明：本次任务只添加中文注释，没有改动任何一行原有代码逻辑
# ============================================================

# —— 第三方库 ——
# requests：发 HTTP 请求下载头像、探测图片地址是否还活着
import requests
# —— Django 框架 ——
# BaseCommand：management command 的基类，命令的入口方法叫 handle()
# static()：把 static 目录下的相对路径转成带 STATIC_URL 前缀的可访问地址
from django.core.management.base import BaseCommand
from django.templatetags.static import static

# —— 项目内模块 ——
# save_user_avatar()：下载远程图片存到 STATICFILES/avatar/ 下并返回新的 static 路径；
#                     下载失败时它内部会返回默认头像，所以调用方总能拿到一个可用地址
# OAuthUser：第三方登录用户表；picture（头像地址）、metadata（平台返回的用户信息）、
#            type（哪个平台）、nickname（昵称）是同步头像要用的字段
# get_manager_by_type()：按 OAuth 平台类型取对应管理器，用它的 get_picture() 重新拉一次头像
from djangoblog.utils import save_user_avatar
from oauth.models import OAuthUser
from oauth.oauthmanager import get_manager_by_type


# 【Command】—— 同步（修复）OAuth 用户头像
# 用法：python manage.py sync_user_avatar
# 说明：management command 是 Django 的命令行脚本机制，放在 app/management/commands/ 下，
#       文件名即命令名（这里是 sync_user_avatar）；Django 启动时自动发现，类名必须叫 Command，
#       执行时调用 handle()，业务逻辑都写在里面。
class Command(BaseCommand):
    # help 文案会出现在 python manage.py help 的列表里
    help = 'sync user avatar'

    # 【test_picture】—— 探测一个图片地址是否还能访问
    # 参数：url（str）：本站 static 路径或远程图片地址
    # 返回：True 表示 HTTP 200 可访问；异常或非 200 时隐式返回 None（即“不可用”）
    # 说明：只用来判断本地已有头像文件还在不在，超时压到 2 秒，避免网络慢时整条命令卡住；
    #       任何异常都吞掉，因为这里的结论只有“能用/不能用”两种，不必区分原因
    def test_picture(self, url):
        try:
            if requests.get(url, timeout=2).status_code == 200:
                return True
        except:
            pass

    # 【handle】—— 命令执行入口：逐个用户修正头像地址
    # 参数：*args / **options：命令行参数（本命令不需要）
    # 返回：None；进度通过 self.stdout 打印
    # 说明：幂等性（重复执行结果一致）靠两件事：①picture 已经是可访问的本地地址就直接 continue，
    #       不做任何修改；②每处理完一条都把最终地址写回 u.picture 并 save()，远程图统一落成本地地址、
    #       拿不到的用默认头像兜底。所以反复跑不会越跑越乱，也不会重复下载。
    def handle(self, *args, **options):
        # static("../") 会把 STATIC_URL 与 '..' 做 urljoin 并规范化，实际得到站点根路径 '/'，
        # 于是 startswith 就能判断 picture 是不是以 / 开头的站内路径（远程头像则是 http(s):// 开头）
        static_url = static("../")
        # 头像来源：OAuthUser.picture（登录时由 oauthmanager 的 get_picture() 从平台 metadata 里取出并存下）；
        # metadata 里留着平台用户信息/令牌，必要时可以据此重新拉一次头像
        users = OAuthUser.objects.all()
        self.stdout.write(f'开始同步{len(users)}个用户头像')
        for u in users:
            self.stdout.write(f'开始同步:{u.nickname}')
            url = u.picture
            if url:
                # 情况一：已经是本站 static 路径，只需确认文件还在
                if url.startswith(static_url):
                    if self.test_picture(url):
                        continue
                    else:
                        # 情况二：本地文件没了 —— 有 metadata 就走第三方接口重新取头像，
                        # 并立刻下载到本地；没 metadata（老数据、授权过期）只能退回默认头像
                        if u.metadata:
                            manage = get_manager_by_type(u.type)
                            url = manage.get_picture(u.metadata)
                            url = save_user_avatar(url)
                        else:
                            url = static('blog/img/avatar.png')
                else:
                    # 情况三：还是远程地址（注册时没落地过），直接下载保存到本地
                    url = save_user_avatar(url)
            else:
                # 情况四：picture 为空的历史用户，直接给默认头像
                url = static('blog/img/avatar.png')
            if url:
                self.stdout.write(
                    f'结束同步:{u.nickname}.url:{url}')
                # 回写并保存：下次重跑时 picture 已是可访问的本地地址，会走 continue 分支，
                # 这正是本命令可以反复执行而不会产生重复文件的原因
                u.picture = url
                u.save()
        self.stdout.write('结束同步')
