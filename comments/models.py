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
    # #jxr - is_enable：展示开关，默认 False（新评论需管理员审核通过后才对外展示）
    # #jxr - review_status：审核状态三态（待审/通过/拒绝），与 is_enable 保持同步；
    # #jxr   对外可见性仍以 is_enable 为准，这样 article.comment_list()、模板过滤等旧链路无需改动

    # #jxr 审核状态常量：既用于 choices，也供视图/后台/测试直接引用，避免手写字符串
    REVIEW_STATUS_PENDING = 'pending'
    REVIEW_STATUS_APPROVED = 'approved'
    REVIEW_STATUS_REJECTED = 'rejected'
    REVIEW_STATUS_CHOICES = [
        (REVIEW_STATUS_PENDING, _('Pending review')),
        (REVIEW_STATUS_APPROVED, _('Approved')),
        (REVIEW_STATUS_REJECTED, _('Rejected')),
    ]

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
    review_status = models.CharField(  # #jxr 三态审核状态：待审 / 通过 / 拒绝
        _('review status'),
        max_length=10,
        choices=REVIEW_STATUS_CHOICES,
        default=REVIEW_STATUS_PENDING,
        db_index=True,  # #jxr 后台按状态筛选、批量操作都要走这个字段，单独建索引
        help_text=_('Pending review / approved / rejected, kept in sync with enable.'))

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

    # ==================== #jxr 审核状态：三态与 is_enable 的同步 ====================

    @property
    def is_approved(self):
        """#jxr 是否已通过审核（等价于前台可见）。"""
        return bool(self.is_enable)

    def _sync_review_status(self):
        """#jxr 保存前把 review_status 与 is_enable 对齐。

        规则（兼容项目里历史写法“只改 is_enable”的代码）：
        - 本次修改里 review_status 有变化 → 以 review_status 为准推 is_enable；
        - 只有 is_enable 变化 → 由 is_enable 反推 review_status（True→通过，False→待审）；
        - 新建对象两者都没显式给 → 默认待审（is_enable=False）。
        """
        previous = None
        if self.pk:
            # #jxr 只有已入库的对象才需要对比旧值；多一次 SELECT 换取两种写法都能自洽
            previous = (type(self)._default_manager
                        .filter(pk=self.pk)
                        .values('is_enable', 'review_status')
                        .first())

        if previous is None:
            status_changed = self.review_status != self.REVIEW_STATUS_PENDING
            enable_changed = bool(self.is_enable)
        else:
            status_changed = self.review_status != previous['review_status']
            enable_changed = bool(self.is_enable) != bool(previous['is_enable'])

        if status_changed:
            # #jxr 状态是“主”，展示开关是“从”：通过→可见，其余→不可见
            self.is_enable = self.review_status == self.REVIEW_STATUS_APPROVED
        elif enable_changed:
            # #jxr 兼容旧代码：直接改 is_enable 时自动补出对应状态
            self.review_status = (self.REVIEW_STATUS_APPROVED if self.is_enable
                                  else self.REVIEW_STATUS_PENDING)

        # #jxr 返回“审核状态或展示状态是否发生了变化”，save() 据此决定要不要清缓存
        return status_changed or enable_changed

    def save(self, *args, **kwargs):
        """#jxr 重写 save，保证任何入口写入后三态与展示开关都是一致的。"""
        update_fields = kwargs.get('update_fields')
        visibility_changed = False
        if update_fields is None:
            visibility_changed = self._sync_review_status()
        else:
            fields = set(update_fields)
            if 'review_status' in fields or 'is_enable' in fields:
                visibility_changed = self._sync_review_status()
                # #jxr 同步可能改到另一个字段，必须一起写进 update_fields，否则落库不完整
                fields.update({'review_status', 'is_enable'})
                kwargs['update_fields'] = fields
        super().save(*args, **kwargs)

        # #jxr 任何入口（后台批量动作、后台修改表单、approve()/reject()、脚本）只要
        # #jxr 改动了审核/展示状态，就立刻失效该文章的评论缓存与侧边栏“近期评论”缓存。
        # #jxr 只靠 blog_signals 是不够的：它只在 is_enable 为真时清缓存，把评论改成
        # #jxr 拒绝/待审时不会触发，前台就会出现“后台已改、页面还是旧数据”。
        if visibility_changed:
            from comments.utils import invalidate_article_comment_cache
            invalidate_article_comment_cache(self.article)

    def approve(self, save=True):
        """#jxr 审核通过：置为“通过”并对外可见。"""
        self.review_status = self.REVIEW_STATUS_APPROVED
        self.is_enable = True
        self.last_modify_time = now()
        if save:
            self.save()
        return self

    def reject(self, save=True):
        """#jxr 审核拒绝：置为“拒绝”并对外隐藏。"""
        self.review_status = self.REVIEW_STATUS_REJECTED
        self.is_enable = False
        self.last_modify_time = now()
        if save:
            self.save()
        return self

    def reset_to_pending(self, save=True):
        """#jxr 打回待审：置为“待审”并对外隐藏（用于误操作撤回）。"""
        self.review_status = self.REVIEW_STATUS_PENDING
        self.is_enable = False
        self.last_modify_time = now()
        if save:
            self.save()
        return self

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
