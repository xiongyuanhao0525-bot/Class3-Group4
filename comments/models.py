from collections import Counter  # #jxr 表情汇总用计数器，避免逐表情再查一轮

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

    # ==================== #jxr 表情回应汇总 ====================

    def get_reactions_summary(self, user=None):
        """#jxr 汇总该评论的表情回应：每种表情的数量、前若干位用户、当前用户是否点过。

        原实现是“先按表情分组，再对每种表情各查一次用户列表 + 各查一次 exists”，
        一条评论最多 8 种表情时要发 17 条 SQL；本实现改为：
        - 1 条 SQL 取回全部回应（按表情、时间排序），在内存里分组计数；
        - 登录用户再补 1 条 SQL 取“我点过哪些表情”。
        同时顺序固定为“先点的在前”，用户预览列表不再随数据库返回顺序漂移。
        """
        queryset = CommentReaction.objects.filter(comment=self)

        # #jxr values_list 直接取昵称/用户名，避免 select_related 把整行用户对象取回来
        rows = list(
            queryset.order_by('reaction_type', 'created_at', 'id').values_list(
                'reaction_type', 'user__nickname', 'user__username'))

        counts = Counter()
        user_previews = {}
        for reaction_type, nickname, username in rows:
            counts[reaction_type] += 1
            names = user_previews.setdefault(reaction_type, [])
            if len(names) < CommentReaction.USER_PREVIEW_LIMIT:
                names.append(nickname or username)

        reacted_types = set()
        if user is not None and getattr(user, 'is_authenticated', False):
            reacted_types = set(
                queryset.filter(user=user).values_list('reaction_type', flat=True))

        # #jxr 固定按 REACTION_CHOICES 的顺序输出全部表情（没有回应的也返回 count=0），
        # #jxr 前端可以直接按 key 取值，取消最后一个回应后也不会出现“键突然消失”
        return {
            reaction_type: {
                'count': counts.get(reaction_type, 0),
                'has_reacted': reaction_type in reacted_types,
                'users': user_previews.get(reaction_type, []),
            }
            for reaction_type in CommentReaction.available_reaction_types()
        }


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
    # #jxr 汇总时每种表情最多回传多少个用户名，避免接口响应过大
    USER_PREVIEW_LIMIT = 10

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

    @classmethod
    def available_reaction_types(cls):
        """#jxr 当前支持的表情列表，API 回传给前端，避免前端再写死一份。"""
        return [choice[0] for choice in cls.REACTION_CHOICES]
