from django.conf import settings  # 获取 AUTH_USER_MODEL 等全局配置
from django.db import models
from django.utils.timezone import now  # 时区感知的当前时间，作为默认创建时间
from django.utils.translation import gettext_lazy as _

from blog.models import Article  # 关联文章模型

# Create your models here.

# #jxr 评论模块包含两个模型：Comment（评论）与 CommentReaction（评论表情反应）。
# #jxr 二者构成一对多关系：一条评论可被多个用户点多种表情；回复通过自引用外键实现"楼中楼"。


class Comment(models.Model):
    """评论模型：记录用户对文章发表的评论"""
    # #jxr 字段说明：
    # #jxr - body：评论正文，最长300字，前端输入限制与之对应
    # #jxr - creation_time/last_modify_time：创建与最后修改时间，均默认当前时间
    # #jxr - author：外键指向用户表，CASCADE 级联删除（用户注销则评论一并删除）
    # #jxr - article：外键指向文章表，CASCADE 级联删除（文章删除则评论一并删除）
    # #jxr - parent_comment：自引用外键，顶级评论为 NULL，非空表示这是一条"楼中楼"回复
    # #jxr - is_enable：审核开关，默认 False（新评论需管理员审核通过后才对外展示）
    body = models.TextField('正文', max_length=300)  # 评论正文，最多300字
    creation_time = models.DateTimeField(_('creation time'), default=now)  # 评论创建时间
    last_modify_time = models.DateTimeField(_('last modify time'), default=now)  # 评论最后修改时间
    author = models.ForeignKey(  # 外键：评论作者，关联用户表；用户删除则评论级联删除
        settings.AUTH_USER_MODEL,
        verbose_name=_('author'),
        on_delete=models.CASCADE)
    article = models.ForeignKey(  # 外键：评论所属文章，关联文章表；文章删除则评论级联删除
        Article,
        verbose_name=_('article'),
        on_delete=models.CASCADE)
    parent_comment = models.ForeignKey(  # 自引用外键：父评论，实现"楼中楼"回复；顶级评论此值为空
        'self',
        verbose_name=_('parent comment'),
        blank=True,
        null=True,
        on_delete=models.CASCADE)
    is_enable = models.BooleanField(_('enable'),  # 评论是否通过审核（是否显示）
                                    default=False, blank=False, null=False)

    class Meta:
        ordering = ['-id']  # 按id倒序排列，最新评论显示在最前
        verbose_name = _('comment')
        verbose_name_plural = verbose_name
        get_latest_by = 'id'
        indexes = [
            # 优化评论列表查询：article + parent_comment + is_enable 组合索引
            models.Index(fields=['article', 'parent_comment', 'is_enable'], name='idx_art_parent_enable'),
            # 优化侧边栏评论查询：is_enable + id 组合索引
            models.Index(fields=['is_enable', '-id'], name='idx_enable_id'),
        ]

    def __str__(self):
        return self.body

    def get_reactions_summary(self, user=None):
        """
        获取评论的 reactions 统计信息：按表情分组统计数量、点赞用户列表
        """
        from django.db.models import Count  # #jxr 函数内导入，避免模块加载开销

        reactions = CommentReaction.objects.filter(  # 查出该评论的全部反应记录
            comment=self
        ).values('reaction_type').annotate(count=Count('id'))  # 按表情类型分组，统计每种表情的数量

        result = {}
        for reaction in reactions:
            emoji = reaction['reaction_type']  # 当前表情类型

            # 获取点过该表情的用户（最多10个）
            reaction_users = CommentReaction.objects.filter(
                comment=self,
                reaction_type=emoji
            ).select_related('user')[:10]  # #jxr select_related 预取用户表，避免 N+1 查询

            user_names = [r.user.nickname or r.user.username for r in reaction_users]  # 取用户昵称，没有昵称则用用户名

            # #jxr 组装该表情的汇总字典：数量、当前登录用户是否已点过、点过的用户名列表
            result[emoji] = {
                'count': reaction['count'],  # 该表情总数量
                'has_reacted': False,
                'users': user_names  # 点过该表情的用户名列表
            }

            if user and user.is_authenticated:  # 如果传入了登录用户，判断TA是否已点过该表情
                result[emoji]['has_reacted'] = CommentReaction.objects.filter(
                    comment=self,
                    user=user,
                    reaction_type=emoji
                ).exists()

        return result


class CommentReaction(models.Model):
    """
    评论反应模型：记录"哪个用户给哪条评论点了什么表情"
    """
    REACTION_CHOICES = [  # 支持的表情类型选项
        ('👍', 'thumbs_up'),
        ('👎', 'thumbs_down'),
        ('❤️', 'heart'),
        ('😄', 'laugh'),
        ('🎉', 'hooray'),
        ('😕', 'confused'),
        ('🚀', 'rocket'),
        ('👀', 'eyes'),
    ]
    # #jxr 设计要点：
    # #jxr - comment：外键关联评论，related_name='reactions' 支持 comment.reactions 反向取全部反应
    # #jxr - user：外键关联用户，记录"谁"点的
    # #jxr - reaction_type：点的哪个表情（限定在 REACTION_CHOICES 内）
    # #jxr - unique_together 联合唯一约束保证"同一用户对同一条评论的同一表情"只能存在一条记录，
    # #jxr   视图层利用该约束实现"再点一次即取消"的切换逻辑

    comment = models.ForeignKey(  # 外键：被反应的评论；评论删除则反应级联删除
        Comment,
        verbose_name=_('comment'),
        on_delete=models.CASCADE,
        related_name='reactions'  # 反向关系名：comment.reactions 可取该评论的全部反应
    )
    user = models.ForeignKey(  # 外键：做出反应的用户；用户删除则反应级联删除
        settings.AUTH_USER_MODEL,
        verbose_name=_('user'),
        on_delete=models.CASCADE
    )
    reaction_type = models.CharField(  # 反应类型：用户点的表情（如👍）
        _('reaction type'),
        max_length=10,
        choices=REACTION_CHOICES
    )
    created_at = models.DateTimeField(_('created at'), auto_now_add=True)  # 反应时间：创建时自动记录

    class Meta:
        verbose_name = _('comment reaction')
        verbose_name_plural = _('comment reactions')
        # 联合唯一约束：每个用户对同一条评论的同一表情只能点一次
        unique_together = ['comment', 'user', 'reaction_type']
        indexes = [
            # 优化反应查询：comment + reaction_type 组合索引
            models.Index(fields=['comment', 'reaction_type'], name='idx_comment_reaction'),
        ]

    def __str__(self):
        return f'{self.user.username} - {self.reaction_type} on comment {self.comment.id}'
