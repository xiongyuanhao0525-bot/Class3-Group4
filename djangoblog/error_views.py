#!/usr/bin/env python
# encoding: utf-8

"""
Django Blog 统一错误处理视图
提供统一的错误页面渲染，减少重复代码
"""

# xyh：统一错误处理模块——djangoblog/urls.py 的 handler404/403/400/500 全部指向本模块。
# xyh：设计意图：四种错误共用一个渲染出口（render_error_page），模板、日志格式保持一致，
# xyh：后续要换错误页样式只需改一处（低耦合）。

import logging
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


# xyh：全项目错误页唯一渲染出口：记日志 + 渲染 blog/error_page.html
def render_error_page(request, status_code, message, exception=None):
    """
    通用错误页面渲染函数

    统一处理各种 HTTP 错误，提供一致的错误页面展示

    Args:
        request: HTTP 请求对象
        status_code: HTTP 状态码（404, 403, 500等）
        message: 错误消息（支持国际化）
        exception: 异常对象（可选），会被记录到日志

    Returns:
        HttpResponse: 渲染后的错误页面

    Usage:
        def my_error_handler(request, exception):
            return render_error_page(request, 404, "Page not found", exception)
    """
    if exception:  # xyh：仅在携带异常对象时落 ERROR 日志（500 无异常则不重复记）
        logger.error(
            f'HTTP {status_code} Error: {exception}',
            exc_info=True,  # xyh：附完整堆栈便于排障
            extra={
                'request': request,
                'status_code': status_code
            }
        )

    return render(
        request,
        'blog/error_page.html',
        {
            'message': message,
            'statuscode': str(status_code)
        },
        status=status_code  # xyh：响应状态码与错误类型一致，SEO/监控可辨
    )


# xyh：404 处理器——Django 自动传入 exception；template_name 参数仅为兼容签名未使用
def page_not_found_view(request, exception, template_name='blog/error_page.html'):
    """
    404 错误页面处理器

    当用户访问不存在的页面时显示

    Args:
        request: HTTP 请求对象
        exception: 异常对象
        template_name: 模板名称（保留参数以兼容 Django 标准）

    Returns:
        HttpResponse: 404 错误页面
    """
    return render_error_page(
        request,
        404,
        _('Sorry, the page you requested is not found, please click the home page to see other?'),
        exception
    )


# xyh：500 处理器——不接收 exception（Django 约定），文案引导回首页而非暴露堆栈
def server_error_view(request, template_name='blog/error_page.html'):
    """
    500 错误页面处理器

    当服务器内部错误时显示

    Args:
        request: HTTP 请求对象
        template_name: 模板名称（保留参数以兼容 Django 标准）

    Returns:
        HttpResponse: 500 错误页面
    """
    return render_error_page(
        request,
        500,
        _('Sorry, the server is busy, please click the home page to see other?')
    )


# xyh：403 处理器——权限不足（如非 superuser 访问后台）时由 Django 分发至此
def permission_denied_view(request, exception, template_name='blog/error_page.html'):
    """
    403 错误页面处理器

    当用户无权限访问时显示

    Args:
        request: HTTP 请求对象
        exception: 异常对象
        template_name: 模板名称（保留参数以兼容 Django 标准）

    Returns:
        HttpResponse: 403 错误页面
    """
    return render_error_page(
        request,
        403,
        _('Sorry, you do not have permission to access this page?'),
        exception
    )


# xyh：400 处理器——请求本身非法（格式错误/伪造 CSRF token 等）时触发
def bad_request_view(request, exception, template_name='blog/error_page.html'):
    """
    400 错误页面处理器

    当请求格式错误时显示

    Args:
        request: HTTP 请求对象
        exception: 异常对象
        template_name: 模板名称（保留参数以兼容 Django 标准）

    Returns:
        HttpResponse: 400 错误页面
    """
    return render_error_page(
        request,
        400,
        _('Sorry, the request was invalid?'),
        exception
    )
