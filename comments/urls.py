from django.urls import path

from . import views

app_name = "comments"  # #jxr 命名空间，模板/重定向中用 comments:postcomment 等引用
urlpatterns = [
    # #jxr 发表/回复评论：POST 到文章详情页评论提交接口
    path(
        'article/<int:article_id>/postcomment',
        views.CommentPostView.as_view(),
        name='postcomment'),
    # #jxr 评论表情反应 API：GET 查统计 / POST 切换表情（点赞/取消）
    path(
        'comment/<int:comment_id>/react',
        views.CommentReactionView.as_view(),
        name='comment_react'),
]
