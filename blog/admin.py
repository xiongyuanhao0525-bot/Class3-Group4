# -*- coding: utf-8 -*-
# 博客后台管理模块（blog/admin.py）
# 作用：注册 Django 自带的 Admin 后台，管理博客的文章、标签、分类、
#       友链、侧边栏和博客全局设置。
# 说明：以下只添加中文注释，不修改任何代码逻辑。
# 补充注释：翟旌超（#zjc）

# —— 第三方框架：Django 提供的表单、后台与工具函数 ——
# forms：ModelForm 基类，让"表单字段"从模型定义自动推导出来
from django import forms
# admin：Django 内置的后台管理站点；ModelAdmin 是"某张表在后台怎么展示"的配置类
from django.contrib import admin
# get_user_model：按项目配置取当前用户模型（本项目是 djangoblog 的 Ouser），避免写死表名
from django.contrib.auth import get_user_model
# reverse：用"URL 名字 + 参数"反查真实网址，后台链接靠它生成，不必写死 /admin/...
from django.urls import reverse
# format_html：拼接含 HTML 的字符串，会把结果标记为安全，防止 XSS 与页面被转义坏
from django.utils.html import format_html
# gettext_lazy：惰性翻译，字符串先占位、真正渲染时才翻译，多语言站点常用
from django.utils.translation import gettext_lazy as _

# Register your models here.
# —— 项目内模块：blog 应用自己的模型 ——
# 导入本应用的数据模型：文章、分类、标签、友链、侧边栏、博客设置
from .models import Article, Category, Tag, Links, SideBar, BlogSettings


# ------------------------------------------------------------
# —— 文章编辑表单 ——
# ------------------------------------------------------------
# 【ArticleForm】—— 文章后台编辑页使用的自定义 ModelForm
# 说明：ModelForm 是 Django"由模型自动生成表单"的基类：只要在 Meta 里声明
#       model 和 fields，框架就会按字段类型生成控件（CharField→输入框、
#       外键→下拉框），并复用模型的校验规则与 save() 逻辑。
# 说明：这里特意留一个自己的 Form 类，是为了将来能整体替换某个字段的控件
#       （例如把正文换成富文本编辑器），而不必去动 Admin 的配置。
# 注意：本类没有覆写 __init__。若以后要在 __init__ 里动态收窄外键候选集
#       （例如只允许选超级管理员当作者），第一行必须先写
#       super().__init__(*args, **kwargs)：self.fields 是父类构造过程才填好的，
#       跳过父类会拿到空 fields，后面访问 self.fields['author'] 直接 KeyError。
class ArticleForm(forms.ModelForm):
    # body = forms.CharField(widget=AdminPagedownWidget())
    # 上面这行是被注释掉的富文本编辑器控件，暂时不使用
    class Meta:
        # 表单关联的文章模型
        model = Article
        # 表单包含模型的所有字段
        fields = '__all__'


# 以下 4 个函数是 Admin 后台的"批量操作"动作，
# 用于在文章列表页勾选多篇文章后统一修改状态。
# 说明：这是 Django 的固定约定——批量动作函数一律接收
#       (modeladmin, request, queryset) 三个参数：modeladmin 是当前 ArticlelAdmin
#       实例，request 是本次请求，queryset 是"用户在列表页打了勾的那些行"拼成的
#       查询集（QuerySet：Django 的惰性查询结果集，真正遍历时才发 SQL）；
#       函数执行完，框架会回到列表页并提示"成功修改 N 项"。
# 说明：动作函数只有挂到 ModelAdmin.actions 列表里，后台才会在下拉框中显示出来。


# 【makr_article_publish】—— 批量发布：把勾选文章的状态改成 p（publish 已发布）
# 说明：queryset.update() 只发一条 UPDATE SQL，不逐条调用 obj.save()，
#       所以快；也正因为不走 save()，不会触发 post_save 信号。
def makr_article_publish(modeladmin, request, queryset):
    # 批量发布：把选中的文章状态改为 'p'（publish 已发布）
    queryset.update(status='p')


# 【draft_article】—— 批量转为草稿：把勾选文章的状态改成 d（draft 草稿）
def draft_article(modeladmin, request, queryset):
    # 批量转为草稿：把选中的文章状态改为 'd'（draft 草稿）
    queryset.update(status='d')


# 【close_article_commentstatus】—— 批量关闭评论：评论状态改成 c（close 关闭）
def close_article_commentstatus(modeladmin, request, queryset):
    # 批量关闭评论：把选中文章的评论状态改为 'c'（close 关闭）
    queryset.update(comment_status='c')


# 【open_article_commentstatus】—— 批量开启评论：评论状态改成 o（open 开启）
def open_article_commentstatus(modeladmin, request, queryset):
    # 批量开启评论：把选中文章的评论状态改为 'o'（open 开启）
    queryset.update(comment_status='o')


# 为上面 4 个批量操作设置后台列表中显示的英文说明（本地化翻译用）
# 说明：short_description 是 Django 约定的属性，后台"动作"下拉框直接读它当显示名；
#       外面套 _() 是为了随语言包翻译（所以源码里写英文、界面上可能是中文）。
makr_article_publish.short_description = _('Publish selected articles')
draft_article.short_description = _('Draft selected articles')
close_article_commentstatus.short_description = _('Close article comments')
open_article_commentstatus.short_description = _('Open article comments')


# ------------------------------------------------------------
# —— 文章后台配置：列表页 / 编辑页的全部展示规则 ——
# ------------------------------------------------------------
# 【ArticlelAdmin】—— 文章模型的后台配置类（ModelAdmin 子类）
# 说明：后台每个"列表页"都由一个 ModelAdmin 子类描述：显示哪些列、怎么筛、
#       怎么搜、一页多少条、编辑页用哪个表单……它不存数据，只是一份"界面配置"；
#       真正的注册动作在 djangoblog/admin_site.py 里用
#       admin_site.register(Article, ArticlelAdmin) 完成。
# 说明：类名沿用仓库现有拼写 ArticlelAdmin（不要改，改了注册点就对不上）。
# 说明：本类没有覆写 readonly_fields / inlines / formfield_overrides /
#       get_queryset，因此这四项走 ModelAdmin 的默认行为：编辑页字段都可写、
#       不挂任何内联子表、各字段用默认控件、列表查的是 Article 的默认查询集。
class ArticlelAdmin(admin.ModelAdmin):
    # 文章管理后台配置类：定义文章在 Admin 里的列表展示、搜索、过滤方式
    list_per_page = 20
    # 列表每页显示 20 条
    # 说明：列表页底部分页器按这个数字切页；调大能少翻页，但单页查询更重。
    search_fields = ('body', 'title')
    # 支持按文章正文和标题搜索
    # 说明：列表页顶部会出现搜索框，底层是 body/title 的 LIKE '%关键词%' 模糊匹配，
    #       多个字段之间是"或"的关系。
    form = ArticleForm
    # 使用上面定义的文章表单
    list_display = (
        'id',
        'title',
        'author',
        'link_to_category',
        'creation_time',
        'views',
        'status',
        'type',
        'article_order')
    # 列表页显示的字段：编号、标题、作者、分类链接、创建时间、浏览量、状态、类型、排序
    # 说明：每一项对应列表里"一列"，写字段名就显示该字段的值，写方法名就调用该方法
    #       来生成单元格（如 link_to_category）；表头文字取自字段的 verbose_name
    #       或方法的 short_description。
    list_display_links = ('id', 'title')
    # 点击"编号"或"标题"可进入文章编辑页
    # 说明：没列进来的列只是纯文本，点了不跳转；不写这一项时默认只有第一列可点。
    list_filter = ('status', 'type', 'category')
    # 列表右侧的筛选栏：按状态、类型、分类筛选
    # 说明：status/type 是 choices 字段→自动生成下拉；category 是外键→按分类逐条列出。
    #       点一下就是一次 queryset.filter(...)，条件写进 URL 的 ?status=... 里，可收藏可回退。
    date_hierarchy = 'creation_time'
    # 顶部按创建时间提供日期层级导航
    # 说明：界面呈现为"2024 › 十月 › 20"的逐级钻取，本质是按 creation_time 做年月日范围过滤。
    filter_horizontal = ('tags',)
    # 标签字段用横向选择器，方便多选
    # 说明：多对多字段默认是"按住 Ctrl 多选"的列表框，这里换成左右双栏穿梭框
    #       （左"可用"、右"已选"），带搜索，标签一多也好找。
    exclude = ('creation_time', 'last_modify_time')
    # 隐藏创建时间和最后修改时间字段（系统自动记录）
    # 说明：exclude 是把字段从编辑表单里"整条去掉"（不是只读）；creation_time 由
    #       auto_now_add 在新建时自动写、last_modify_time 由 auto_now 每次保存刷新，
    #       都不该让用户手填。
    view_on_site = True
    # 提供"在网站中查看"按钮
    # 说明：置 True 后编辑页右上出现该按钮，点击时 Django 调本类的
    #       get_view_on_site_url() 取目标地址；那里返回 None 按钮就会自动隐藏。
    actions = [
        makr_article_publish,
        draft_article,
        close_article_commentstatus,
        open_article_commentstatus]
    # 列表页可用的批量操作：发布、草稿、关评论、开评论
    # 说明：界面上表现为列表页左上角的"动作"下拉框：勾选若干行→选动作→点"执行"。
    raw_id_fields = ('author', 'category',)
    # 作者和分类使用原始 ID 输入框，避免大量选项卡顿
    # 说明：外键默认会把整张表查出来渲染成下拉框，用户量一大后台就卡；这里改成
    #       "ID 文本框 + 放大镜"，点放大镜弹窗里搜索选择。

    def link_to_category(self, obj):
        # 自定义列：把文章所属分类显示为可点击的后台链接
        # 参数：obj（Article）：当前这一行对应的文章对象
        # 返回：SafeString（已被标记为安全的 HTML 片段）
        # 说明：list_display 里写方法名时，后台会为每一行调用一次本方法，
        #       返回值按 HTML 渲染——所以这里返回"分类名 + 跳到分类编辑页"的 <a>。
        info = (obj.category._meta.app_label, obj.category._meta.model_name)
        # 取分类的应用名和模型名，用于拼后台 URL
        # 说明：_meta 是 Django 挂在每个模型上的元信息对象；这里得到
        #       app_label='blog'、model_name='category'。
        link = reverse('admin:%s_%s_change' % info, args=(obj.category.id,))
        # 生成跳转到该分类编辑页的链接
        # 说明：后台 URL 名字的规范是 admin:<app_label>_<model_name>_<动作>，
        #       动作 change 表示"修改"，args 传主键；reverse 据此反查出形如
        #       /admin/blog/category/3/change/ 的真实路径，站点换前缀也不会失效。
        return format_html(u'<a href="%s">%s</a>' % (link, obj.category.name))
        # 返回带链接的分类名称
        # 说明：format_html 的用途是"我确定这段是 HTML，请安全地交给模板"——
        #       返回的 SafeString 在模板里不再被二次转义；标准写法是
        #       format_html(模板, *参数)（参数会被自动转义），本行先用 % 拼好再传入。

    link_to_category.short_description = _('category')
    # 该列的列头显示为"分类"

    def get_form(self, request, obj=None, **kwargs):
        # 自定义后台表单：限制作者下拉框只显示超级管理员
        # 参数：request（HttpRequest）：本次请求，可据登录用户做权限判断
        #       obj（Article 或 None）：正在编辑的文章，None 表示新增
        #       **kwargs：后台可能透传的 fields/exclude 等参数，原样交给父类
        # 返回：动态生成的 ModelForm 类
        form = super(ArticlelAdmin, self).get_form(request, obj, **kwargs)
        # 先调用父类生成标准表单
        # 说明：必须这一步——父类内部用 modelform_factory 按 model 的字段生成
        #       Form 类，form.base_fields 这时才存在；跳过父类直接改会直接报错。
        form.base_fields['author'].queryset = get_user_model(
        ).objects.filter(is_superuser=True)
        # 把"作者"字段的候选用户过滤为超管，避免普通用户可选
        # 说明：base_fields 是"类级别"的字段字典，改其中字段的 queryset 就等于改
        #       下拉框的候选集；get_form 每次请求都重新生成 Form 类，
        #       所以这里的改动不会串到别的请求上。
        return form

    def save_model(self, request, obj, form, change):
        # 保存文章时的钩子（当前未附加额外逻辑，仅调用父类保存）
        # 参数：change（bool）：True 表示改已有文章，False 表示新建
        # 说明：后台点"保存"时，框架先做表单校验，再调本方法落库；父类里做的事
        #       就是 obj.save()（多对多关系由随后的 save_related 处理）。
        super(ArticlelAdmin, self).save_model(request, obj, form, change)

    def get_view_on_site_url(self, obj=None):
        # 自定义"在网站中查看"跳转地址：有文章返回文章完整 URL，否则返回站点域名
        # 参数：obj（Article 或 None）：当前编辑对象，None 表示列表页/新增页
        # 返回：str：前台文章完整 URL 或站点域名
        # 说明：这是 view_on_site 功能的取址钩子，只有点按钮时才会被调用。
        if obj:
            url = obj.get_full_url()
            # 文章存在：使用文章的完整链接
            return url
        else:
            from djangoblog.utils import get_current_site
            # 文章不存在：导入工具函数获取当前站点
            # 说明：放在函数内做延迟导入，是为了避开模块加载期的循环依赖
            #       （djangoblog.utils 会反过来用到 blog 的模型）。
            site = get_current_site().domain
            # 返回站点域名
            return site


class TagAdmin(admin.ModelAdmin):
    # 标签管理后台：隐藏自动生成的字段，只保留标签名
    # 说明：slug（URL 别名）和两个时间字段都由模型自动生成，后台不让用户改；
    #       用 exclude 从表单里去掉，比设成 readonly_fields 更省版面。
    exclude = ('slug', 'last_mod_time', 'creation_time')


class CategoryAdmin(admin.ModelAdmin):
    # 分类管理后台：列表显示分类名、父分类、排序索引；隐藏自动字段
    # 说明：parent_category 是自关联外键，用来组织父子分类；index 是排序序号，
    #       前台按它决定分类的展示顺序。
    list_display = ('name', 'parent_category', 'index')
    exclude = ('slug', 'last_mod_time', 'creation_time')


class LinksAdmin(admin.ModelAdmin):
    # 友链管理后台：隐藏自动生成的时间字段
    # 说明：列表页沿用默认列（模型 __str__ 的返回值），这里只裁掉自动时间字段。
    exclude = ('last_mod_time', 'creation_time')


class SideBarAdmin(admin.ModelAdmin):
    # 侧边栏管理后台：列表显示名称、内容、是否启用、排序序号
    # 说明：侧边栏条目（如"最新文章""标签云"）里 is_enable 控制是否上线，
    #       sequence 决定它们在前台的先后顺序。
    list_display = ('name', 'content', 'is_enable', 'sequence')
    exclude = ('last_mod_time', 'creation_time')


# ------------------------------------------------------------
# —— 博客全局设置：单例（整个站点只允许一条配置） ——
# ------------------------------------------------------------
# 【BlogSettingsAdmin】—— 把"只能有一条"的全局设置做成单例后台
# 说明：BlogSettings 存站点名、备案号、每页文章数等全局项，业务上只允许一条，
#       于是这里用三个钩子把后台"逼"成单例：不许加、不许删、进列表直奔编辑页。
class BlogSettingsAdmin(admin.ModelAdmin):
    """单例配置Admin - 直接跳转到编辑页面"""
    # 博客全局设置：只允许存在一条配置，进入列表直接跳到编辑页

    def has_add_permission(self, request):
        """如果已经存在配置，则禁止添加"""
        # 已存在设置记录时，不允许再新增，保证"单例"
        # 说明：返回 False 时后台连"增加"按钮都不显示，直接访问新增 URL 也会被拦。
        #       用 exists() 而不是 count()，数据库只要"存不存在"，不用全表计数。
        return not BlogSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        """禁止删除配置"""
        # 全局设置不允许删除
        # 说明：返回 False 后，编辑页的"删除"按钮和列表页的批量删除都消失，
        #       避免误操作把站点配置清空。
        return False

    def changelist_view(self, request, extra_context=None):
        """列表页直接跳转到编辑页面"""
        # 覆写列表页：不再展示列表，而是直接进入编辑/新增页
        # 说明：这是官方提供的"自定义列表页视图"钩子；这里不渲染模板，只返回
        #       重定向响应（HttpResponseRedirect，浏览器会收到 302 再跳一次）。
        # 参数：extra_context（dict 或 None）：框架给的额外模板变量，这里用不上
        from django.http import HttpResponseRedirect
        # 导入重定向响应
        obj = BlogSettings.objects.first()
        # 取第一条（唯一）设置记录
        if obj:
            # 已存在设置：跳转到该记录的编辑页
            return HttpResponseRedirect(
                reverse('admin:blog_blogsettings_change', args=[obj.pk])
            )
        # 如果不存在配置，跳转到添加页面
        # 说明：URL 名同样是 admin:<app_label>_<model_name>_<动作>：blog + blogsettings +
        #       add/change；一条记录都没有时去新增页，用户就不用先看一个空列表。
        return HttpResponseRedirect(
            reverse('admin:blog_blogsettings_add')
        )

    def save_model(self, request, obj, form, change):
        """保存设置时清除缓存"""
        # 保存全局设置后自动清空缓存，让新设置立即生效
        super().save_model(request, obj, form, change)
        # 先调用父类完成保存
        # 确保缓存被清除
        from djangoblog.utils import cache
        # 导入项目缓存对象
        cache.clear()
        # 清空全部缓存，避免旧设置残留
        # 说明：站点设置被 djangoblog.utils.cache 缓存着，前台取设置优先读缓存；
        #       后台改完若不清，前台会一直显示旧值。clear() 清的是整个缓存后端，
        #       所以其他缓存项也会一起失效重算。
        self.message_user(request, '设置已保存，缓存已清除')
        # 后台弹出保存成功的提示
