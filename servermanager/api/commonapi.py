# -*- coding: utf-8 -*-
"""#wxy servermanager/api/commonapi.py：通用能力类。

ChatGPT  - 微信默认消息的智能问答后端（OpenAI gpt-3.5-turbo）。
CommandHandler - 管理员运维命令的注册表与执行器（commands 表驱动）。
"""
import logging
import os

import openai

from servermanager.models import commands

logger = logging.getLogger(__name__)

# #wxy OpenAI key 与代理从环境变量读取，避免硬编码
openai.api_key = os.environ.get('OPENAI_API_KEY')
if os.environ.get('HTTP_PROXY'):
    openai.proxy = os.environ.get('HTTP_PROXY')


class ChatGPT:
    """#wxy 微信默认消息的 ChatGPT 问答封装（静态方法调用）。"""

    @staticmethod
    def chat(prompt):
        """#wxy 把用户消息作为 user 提问发给 gpt-3.5-turbo，返回回答文本；
        任何异常（网络/key 失效等）都兜底为“服务器出错了”，不把堆栈抛给微信粉丝。"""
        try:
            completion = openai.ChatCompletion.create(model="gpt-3.5-turbo",
                                                      messages=[{"role": "user", "content": prompt}])
            return completion.choices[0].message.content
        except Exception as e:
            logger.error(e)
            return "服务器出错了"


class CommandHandler:
    """#wxy 运维命令处理器：启动时把 commands 表全部命令载入内存，
    run(title) 按命令标题（不区分大小写）匹配，匹配到则通过 os.popen 执行 shell 命令并回显结果。"""

    def __init__(self):
        self.commands = commands.objects.all()

    def run(self, title):
        """
        #wxy 运行命令
        :param title: 命令
        :return: 返回命令执行结果
        """
        cmd = list(
            filter(
                lambda x: x.title.upper() == title.upper(),
                self.commands))
        if cmd:
            return self.__run_command__(cmd[0].command)
        else:
            return "未找到相关命令，请输入hepme获得帮助。"

    def __run_command__(self, cmd):
        """#wxy 真正执行 shell 命令（os.popen 同步读输出）；任何异常都返回错误提示。
        注意：此方法以服务器当前用户权限执行，命令内容由 admin 后台预先注册。"""
        try:
            res = os.popen(cmd).read()
            return res
        except BaseException:
            return '命令执行出错!'

    def get_help(self):
        """#wxy HELPME：拼接所有已注册命令的标题+描述返回给管理员。"""
        rsp = ''
        for cmd in self.commands:
            rsp += '{c}:{d}\n'.format(c=cmd.title, d=cmd.describe)
        return rsp


# #wxy 本地直接运行时的自测入口（非 Django 启动路径）
if __name__ == '__main__':
    chatbot = ChatGPT()
    prompt = "写一篇1000字关于AI的论文"
    print(chatbot.chat(prompt))
