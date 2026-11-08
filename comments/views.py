# Create your views here.
from django.core.exceptions import ValidationError  # 业务校验异常
from django.db import IntegrityError, transaction  # 并发写入的兜底与事务
from django.http import HttpResponseRedirect, JsonResponse  # 页面跳转 / JSON 响应
from django.shortcuts import get_object_or_404  # 查对象，不存在则返回404
from django.views import View  # Django 基础视图类

from accounts.models import BlogUser  # 自定义用户模型
from blog.models import Article  # 文章模型
from djangoblog.base_views import AuthenticatedFormView  # 自带登录校验 + CSRF 保护的基类视图
from .forms import CommentForm  # 评论提交表单
from .models import Comment, CommentReaction  # 评论与表情反应模型

# #jxr 本模块提供两个视图：
# #jxr 1) CommentPostView：文章详情页发表/回复评论（表单类视图，继承 AuthenticatedFormView）
# #jxr 2) CommentReactionView：评论表情反应 API（GET 查统计 / POST 切换表情）


class CommentPostView(AuthenticatedFormView):
    """
    评论提交视图（发表/回复评论）
    使用 AuthenticatedFormView 基类，自动提供：
    - 登录验证（未登录用户会被重定向）
    - CSRF 保护
    """
    form_class = CommentForm                     # 使用的表单类
    template_name = 'blog/article_detail.html'   # 渲染模板：文章详情页

    def get(self, request, *args, **kwargs):
        """GET 请求：不展示表单，直接跳回文章详情页的评论区"""
        article_id = self.kwargs['article_id']
        article = get_object_or_404(Article, pk=article_id)  # 根据ID查文章，不存在则404
        url = article.get_absolute_url()
        return HttpResponseRedirect(url + "#comments")        # 跳转到文章页评论锚点

    def form_invalid(self, form):
        """表单校验不通过时：带着错误信息重新渲染文章详情页"""
        article_id = self.kwargs['article_id']
        article = get_object_or_404(Article, pk=article_id)

        return self.render_to_response({
            'form': form,
            'article': article
        })

    def form_valid(self, form):
        """提交的数据验证合法后的逻辑：保存评论"""
        user = self.request.user
        author = BlogUser.objects.get(pk=user.pk)   # 获取当前登录用户
        article_id = self.kwargs['article_id']
        article = get_object_or_404(Article, pk=article_id)

        # #jxr 文章关闭评论的两种状态：comment_status='c'（评论功能关闭）或 status='c'（文章关闭）
        if article.comment_status == 'c' or article.status == 'c':  # 文章已关闭评论
            raise ValidationError("该文章评论已关闭.")
        comment = form.save(False)        # 先不写入数据库
        comment.article = article         # 绑定所属文章
        from djangoblog.utils import get_blog_setting  # #jxr 延迟导入：获取站点配置工具
        blog_setting = get_blog_setting()

        # #jxr 按站点“先审后发”配置决定初始审核状态：
        # #jxr - 需要审核：待审 + 不展示，等管理员在后台通过/拒绝
        # #jxr - 不需审核：直接通过 + 展示
        if blog_setting.comment_need_review:
            comment.review_status = Comment.REVIEW_STATUS_PENDING
            comment.is_enable = False
        else:
            comment.review_status = Comment.REVIEW_STATUS_APPROVED
            comment.is_enable = True
        comment.author = author           # 绑定评论作者

        if form.cleaned_data['parent_comment_id']:  # 如果是回复某条评论（楼中楼）
            parent_comment = Comment.objects.get(
                pk=form.cleaned_data['parent_comment_id'])
            comment.parent_comment = parent_comment  # 绑定父评论

        comment.save(True)                 # 正式保存评论
        return HttpResponseRedirect(      # 跳回文章页并定位到新评论位置
            "%s#div-comment-%d" %
            (article.get_absolute_url(), comment.pk))


class CommentReactionView(View):
    """
    评论 Emoji 反应 API（点赞/表情回应）
    GET  /comment/<comment_id>/react  - 获取 reactions（公开）
    POST /comment/<comment_id>/react  - 切换 reaction（需要登录）
    """
    # #jxr 设计要点：
    # #jxr - GET 公开：任何人可查看某条已审核评论的表情统计
    # #jxr - POST 需登录：未登录返回 401；同一用户对同一表情再点一次即"取消"（切换语义）
    # #jxr - 本视图是纯 JSON 接口：任何异常分支（评论不存在/类型非法/未登录）都返回 JSON，
    # #jxr   不能把 HTML 404 页塞给前端，否则前端 res.json() 解析失败会退化成“操作失败，请重试”

    @staticmethod
    def _comment_not_found_response():
        """#jxr 统一的“评论不存在”响应：状态码 404，保持 JSON 契约。"""
        return JsonResponse({
            'success': False,
            'error': 'Comment not found'
        }, status=404)

    @staticmethod
    def _get_visible_comment(comment_id):
        """#jxr 只允许对“已通过审核”的评论回应；查不到返回 None（包含待审/拒绝的评论）。"""
        return Comment.objects.filter(id=comment_id, is_enable=True).first()

    @staticmethod
    def _reactions_payload(comment, user):
        """#jxr 组装接口返回体，GET 与 POST 共用，避免两处字段不一致。"""
        return {
            'success': True,
            'reactions': comment.get_reactions_summary(user),
            'available_reactions': CommentReaction.available_reaction_types(),
        }

    def get(self, request, comment_id):
        """获取评论的 reactions 数据（公开访问）"""
        comment = self._get_visible_comment(comment_id)
        if comment is None:
            return self._comment_not_found_response()

        # 传递用户信息，如果未登录则传递 None
        user = request.user if request.user.is_authenticated else None
        return JsonResponse(self._reactions_payload(comment, user))

    def post(self, request, comment_id):
        # POST 需要登录验证
        if not request.user.is_authenticated:
            return JsonResponse({
                'success': False,
                'error': 'Authentication required'
            }, status=401)

        # 获取评论（只有已启用的评论才能点赞）
        comment = self._get_visible_comment(comment_id)
        if comment is None:
            return self._comment_not_found_response()

        # 获取 reaction 类型（前端传的 emoji），顺手去掉可能的首尾空白
        reaction_type = (request.POST.get('reaction_type') or '').strip()

        # 验证 reaction_type 是否合法（必须是预设表情之一）
        if reaction_type not in CommentReaction.available_reaction_types():
            return JsonResponse({
                'success': False,
                'error': 'Invalid reaction type'
            }, status=400)

        # #jxr 切换语义：已存在则删除（取消），不存在则新增。
        # #jxr 原来用 get_or_create 再判断 created，两个请求同时到达时可能都尝试 INSERT，
        # #jxr 触发唯一约束报错；这里改为“先查后写”并放进事务 + 捕获 IntegrityError：
        # #jxr 并发下另一个请求已经创建，就按“已添加”返回，不再把 500 抛给前端。
        try:
            with transaction.atomic():
                reaction = CommentReaction.objects.filter(
                    comment=comment, user=request.user, reaction_type=reaction_type).first()
                if reaction is not None:
                    reaction.delete()
                    action = 'removed'
                else:
                    CommentReaction.objects.create(
                        comment=comment, user=request.user, reaction_type=reaction_type)
                    action = 'added'
        except IntegrityError:
            # #jxr 极端并发：唯一约束挡下了重复插入，说明该表情此刻已存在
            action = 'added'

        payload = self._reactions_payload(comment, request.user)
        payload['action'] = action
        return JsonResponse(payload)
