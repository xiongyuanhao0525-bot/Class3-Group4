# -*- coding: utf-8 -*-
"""#wxy servermanager/admin.py：两张表在 Django 后台的展示配置。"""
from django.contrib import admin
# Register your models here.


class CommandsAdmin(admin.ModelAdmin):
    """#wxy 运维命令表：列表页显示标题/命令/描述三项，方便管理员维护。"""
    list_display = ('title', 'command', 'describe')


class EmailSendLogAdmin(admin.ModelAdmin):
    """#wxy 邮件日志表：只读、禁止新增——只允许审计查看，不允许手工补录。"""
    list_display = ('title', 'emailto', 'send_result', 'creation_time')
    readonly_fields = (
        'title',
        'emailto',
        'send_result',
        'creation_time',
        'content')

    def has_add_permission(self, request):
        """#wxy 重写钩子：后台不允许新增邮件日志（只能由系统发信时写入）。"""
        return False
