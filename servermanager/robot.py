# -*- coding: utf-8 -*-
"""#wxy 微信公众号机器人主模块（servermanager）

职责：基于 WeRoBot 框架，把微信公众号收到的每条消息路由到对应处理器，
实现两类能力：
  1）面向普通粉丝的文章查询与智能问答（?关键字搜索 / category 分类目录 /
     recent 最新文章 / help 帮助 / weather、idcard 占位 / 默认转 ChatGPT）；
  2）面向管理员的远程运维通道（ADMIN 进入 -> 双重 SHA256 密码校验 ->
     输入运维命令 -> 二次确认 Y -> 执行 commands 表中预定义命令 -> EXIT 退出）。

会话存储优先走 MemcacheStorage（Redis/缓存），不可用时回落到本地文件。
"""
import logging
import os
import re

import jsonpickle
from django.conf import settings
from werobot import WeRoBot
from werobot.replies import ArticlesReply, Article
from werobot.session.filestorage import FileStorage

from djangoblog.utils import get_sha256
from servermanager.api.blogapi import BlogApi
from servermanager.api.commonapi import ChatGPT, CommandHandler
from .MemcacheStorage import MemcacheStorage

# #wxy 实例化 WeRoBot：token 来自环境变量 DJANGO_WEROBOT_TOKEN，缺省用 lylinux（本地开发）
robot = WeRoBot(token=os.environ.get('DJANGO_WEROBOT_TOKEN')
                      or 'lylinux', enable_session=True)
# #wxy 会话存储：Redis 可用则走 Memcache，否则回落到本地文件 werobot_session
memstorage = MemcacheStorage()
if memstorage.is_available:
    robot.config['SESSION_STORAGE'] = memstorage
else:
    # #wxy 回退前先清理可能损坏的旧会话文件，避免反序列化异常
    if os.path.exists(os.path.join(settings.BASE_DIR, 'werobot_session')):
        os.remove(os.path.join(settings.BASE_DIR, 'werobot_session'))
    robot.config['SESSION_STORAGE'] = FileStorage(filename='werobot_session')

# #wxy 依赖注入：文章查询 API、运维命令处理器
blogapi = BlogApi()
cmd_handler = CommandHandler()
logger = logging.getLogger(__name__)


def convert_to_article_reply(articles, message):
    """#wxy 把文章查询结果包装成微信图文消息（ArticlesReply）：
    逐条取标题、正文截断摘要、正文里第一张 png/jpg 作为缩略图、原文链接。"""
    reply = ArticlesReply(message=message)
    from blog.templatetags.blog_tags import truncatechars_content
    for post in articles:
        # #wxy 正则抓正文里第一张 png/jpg 图片地址作为图文封面
        imgs = re.findall(r'(?:http\:|https\:)?\/\/.*\.(?:png|jpg)', post.body)
        imgurl = ''
        if imgs:
            imgurl = imgs[0]
        article = Article(
            title=post.title,
            description=truncatechars_content(post.body),
            img=imgurl,
            url=post.get_full_url()
        )
        reply.add_article(article)
    return reply


# #wxy 指令分发：消息以 ? 开头 -> 进入文章关键词搜索
@robot.filter(re.compile(r"^\?.*"))
def search(message, session):
    """#wxy ?关键字：去掉问号后调 BlogApi 全文检索，最多返回 8 条图文；无结果提示。"""
    s = message.content
    searchstr = str(s).replace('?', '')
    result = blogapi.search_articles(searchstr)
    if result:
        articles = list(map(lambda x: x.object, result))
        reply = convert_to_article_reply(articles, message)
        return reply
    else:
        return '没有找到相关文章。'


# #wxy 指令分发：严格等于 category（忽略大小写）-> 返回全部分类目录
@robot.filter(re.compile(r'^category\s*$', re.I))
def category(message, session):
    """#wxy category：列出全部文章分类名，逗号拼接返回。"""
    categorys = blogapi.get_category_lists()
    content = ','.join(map(lambda x: x.name, categorys))
    return '所有文章分类目录：' + content


# #wxy 指令分发：严格等于 recent（忽略大小写）-> 返回最新文章图文
@robot.filter(re.compile(r'^recent\s*$', re.I))
def recents(message, session):
    """#wxy recent：取最新 8 篇文章图文返回；无文章时提示。"""
    articles = blogapi.get_recent_articles()
    if articles:
        reply = convert_to_article_reply(articles, message)
        return reply
    else:
        return "暂时还没有文章"


# #wxy 指令分发：严格等于 help（忽略大小写）-> 返回帮助菜单
@robot.filter(re.compile('^help$', re.I))
def help(message, session):
    """#wxy help：打印全部支持的指令用法（提示粉丝不要用中文标点）。"""
    return '''欢迎关注!
            默认会与图灵机器人聊天~~
        你可以通过下面这些命令来获得信息
        ?关键字搜索文章.
        如?python.
        category获得文章分类目录及文章数.
        category-***获得该分类目录文章
        如category-python
        recent获得最新文章
        help获得帮助.
        weather:获得天气
        如weather:西安
        idcard:获得身份证信息
        如idcard:61048119xxxxxxxxxx
        music:音乐搜索
        如music:阴天快乐
        PS:以上标点符号都不支持中文标点~~
        '''


# #wxy 占位指令：weather 尚未接入真实天气 API
@robot.filter(re.compile(r'^weather\:.*$', re.I))
def weather(message, session):
    """#wxy weather:城市：预留指令，尚未实现。"""
    return "建设中..."


# #wxy 占位指令：idcard 尚未接入身份证查询
@robot.filter(re.compile(r'^idcard\:.*$', re.I))
def idcard(message, session):
    """#wxy idcard:号码：预留指令，尚未实现。"""
    return "建设中..."


# #wxy 兜底处理器：上面 filter 都没命中的消息走这里，交给 MessageHandler
@robot.handler
def echo(message, session):
    """#wxy 默认消息入口：进入管理员状态机判断，否则转 ChatGPT。"""
    handler = MessageHandler(message, session)
    return handler.handler()


class MessageHandler:
    """#wxy 管理员运维通道状态机。

    会话内状态保存在微信粉丝 openid 下（WxUserInfo，jsonpickle 序列化）：
      isAdmin       是否已发起 ADMIN 流程
      isPasswordSet 是否已通过密码校验
      Count         连续密码错误次数（>=3 次锁定）
      Command       待二次确认的运维命令
    """

    def __init__(self, message, session):
        userid = message.source
        self.message = message
        self.session = session
        self.userid = userid
        try:
            # #wxy 从会话恢复该粉丝的管理员状态
            info = session[userid]
            self.userinfo = jsonpickle.decode(info)
        except Exception as e:
            # #wxy 新粉丝/无历史状态 -> 用默认空状态
            userinfo = WxUserInfo()
            self.userinfo = userinfo

    @property
    def is_admin(self):
        return self.userinfo.isAdmin

    @property
    def is_password_set(self):
        return self.userinfo.isPasswordSet

    def save_session(self):
        """#wxy 状态变更后写回会话缓存。"""
        info = jsonpickle.encode(self.userinfo)
        self.session[self.userid] = info

    def handler(self):
        """#wxy 状态机主流程（按顺序判断，仅考虑主路径）。"""
        info = self.message.content

        # #wxy 已通过验证的管理员输入 EXIT -> 清空状态退出运维模式
        if self.userinfo.isAdmin and info.upper() == 'EXIT':
            self.userinfo = WxUserInfo()
            self.save_session()
            return "退出成功"

        # #wxy 任何人输入 ADMIN -> 进入管理员验证流程
        if info.upper() == 'ADMIN':
            self.userinfo.isAdmin = True
            self.save_session()
            return "输入管理员密码"

        # #wxy 已进入 ADMIN 但还没过密码：当前消息视为密码进行校验
        if self.userinfo.isAdmin and not self.userinfo.isPasswordSet:
            # #wxy 密码取 settings.WXADMIN；测试环境固定 123；比对时对用户输入做两次 SHA256
            passwd = settings.WXADMIN
            if settings.TESTING:
                passwd = '123'
            if passwd.upper() == get_sha256(get_sha256(info)).upper():
                self.userinfo.isPasswordSet = True
                self.save_session()
                return "验证通过,请输入命令或者要执行的命令代码:输入helpme获得帮助"
            else:
                # #wxy 连续错 3 次直接锁定（重置状态）
                if self.userinfo.Count >= 3:
                    self.userinfo = WxUserInfo()
                    self.save_session()
                    return "超过验证次数"
                self.userinfo.Count += 1
                self.save_session()
                return "验证失败，请重新输入管理员密码:"

        # #wxy 已通过验证：处于运维命令会话中
        if self.userinfo.isAdmin and self.userinfo.isPasswordSet:
            # #wxy 上一条已输入待执行命令，本条回 Y 则真正执行
            if self.userinfo.Command != '' and info.upper() == 'Y':
                return cmd_handler.run(self.userinfo.Command)
            else:
                if info.upper() == 'HELPME':
                    return cmd_handler.get_help()
                # #wxy 否则把本条消息记为待执行命令，要求用户二次确认
                self.userinfo.Command = info
                self.save_session()
                return "确认执行: " + info + " 命令?"

        # #wxy 非管理员、未命中任何指令 -> 默认转 ChatGPT 对话
        return ChatGPT.chat(info)


class WxUserInfo():
    """#wxy 单个微信粉丝在运维通道中的会话状态（jsonpickle 序列化存储）。"""

    def __init__(self):
        self.isAdmin = False        # #wxy 是否已发起 ADMIN
        self.isPasswordSet = False   # #wxy 是否已通过密码校验
        self.Count = 0               # #wxy 连续密码错误计数
        self.Command = ''           # #wxy 待二次确认的运维命令文本
