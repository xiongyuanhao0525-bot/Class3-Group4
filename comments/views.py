# Create your views here.
from django.core.exceptions import ValidationError  # 业务校验异常
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
        settings = get_blog_setting()
        if not settings.comment_need_review:  # 如果站点配置不需要审核，评论直接通过
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

    def get(self, request, comment_id):
        """获取评论的 reactions 数据（公开访问）"""
        comment = get_object_or_404(Comment, id=comment_id, is_enable=True)  # 只取已通过审核的评论

        # 传递用户信息，如果未登录则传递 None
        user = request.user if request.user.is_authenticated else None
        reactions_data = comment.get_reactions_summary(user)  # 调用模型方法统计表情

        return JsonResponse({
            'success': True,
            'reactions': reactions_data
        })

    def post(self, request, comment_id):
        # POST 需要登录验证
        if not request.user.is_authenticated:
            return JsonResponse({
                'success': False,
                'error': 'Authentication required'
            }, status=401)
        # 获取评论（只有已启用的评论才能点赞）
        comment = get_object_or_404(Comment, id=comment_id, is_enable=True)

        # 获取 reaction 类型（前端传的 emoji）
        reaction_type = request.POST.get('reaction_type')

        # 验证 reaction_type 是否合法（必须是预设表情之一）
        valid_reactions = [choice[0] for choice in CommentReaction.REACTION_CHOICES]
        if reaction_type not in valid_reactions:
            return JsonResponse({
                'error': 'Invalid reaction type'
            }, status=400)

        # 切换 reaction：已存在则删除（取消点赞），否则创建
        # #jxr 依赖 models.CommentReaction 的 unique_together 唯一约束：
        # #jxr get_or_create 在记录已存在时返回 (对象, False)，此时删除即可实现"取消"
        reaction, created = CommentReaction.objects.get_or_create(
            comment=comment,
            user=request.user,
            reaction_type=reaction_type
        )

        if not created:
            # 已存在，删除它（取消点赞）
            reaction.delete()
            action = 'removed'
        else:
            action = 'added'

        # 返回该评论的所有 reactions 统计
        reactions_data = comment.get_reactions_summary(request.user)

        return JsonResponse({
            'success': True,
            'action': action,
            'reactions': reactions_data
        })
