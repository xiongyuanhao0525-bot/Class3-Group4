# -*- coding: utf-8 -*-
"""#wxy servermanager/models.py：servermanager 应用的数据模型。

两张表都不在前台展示，而是支撑微信机器人与运维通道：
  commands      - 管理员可通过微信执行的 shell 命令注册表
  EmailSendLog  - 系统对外发邮件的流水日志（只增不改，供后台审计）
"""
from django.db import models


class commands(models.Model):
    """#wxy 运维命令注册表：管理员后台可维护标题/命令/描述，
    微信端输入 title 即触发 command 对应的 shell 命令执行。"""
    title = models.CharField(max_length=100, default='', verbose_name='命令标题')
    command = models.CharField(max_length=100, default='', verbose_name='命令内容')
    describe = models.CharField(max_length=100, default='', verbose_name='命令描述')
    creation_time = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    last_modify_time = models.DateTimeField(auto_now=True, verbose_name='修改时间')

    class Meta:
        # #wxy 表名保持小写复数风格（原作者命名习惯，与 blog app 一致）
        verbose_name = '命令'
        verbose_name_plural = verbose_name
        db_table = 'commands'


class EmailSendLog(models.Model):
    """#wxy 邮件发送日志：每次外发邮件（找回密码/通知等）写一条，记录收件人、主题、正文、成功与否。"""
    emailto = models.CharField(max_length=200, verbose_name='收件人')
    title = models.CharField(max_length=200, verbose_name='邮件主题')
    content = models.TextField(verbose_name='邮件内容')
    send_result = models.BooleanField(default=False, verbose_name='发送结果')
    creation_time = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')

    class Meta:
        # #wxy 后台按时间倒序，最新邮件在最前
        verbose_name = '邮件发送记录'
        verbose_name_plural = verbose_name
        db_table = 'email_send_log'
        ordering = ('-creation_time',)
