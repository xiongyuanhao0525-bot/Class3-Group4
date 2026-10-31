from django import template

register = template.Library()  # #jxr 模板标签注册器


# #jxr 本文件提供两个模板标签，用于在模板中渲染评论树：
# #jxr 1) parse_commenttree：递归取出一级评论下的全部子评论（楼中楼扁平化）
# #jxr 2) show_comment_item：渲染单条评论条目（区分是否为子评论以控制缩进层级）


@register.simple_tag
def parse_commenttree(commentlist, comment):
    """获得当前评论子评论的列表
        用法: {% parse_commenttree article_comments comment as childcomments %}
    """
    datas = []

    def parse(c):
        # #jxr 递归函数：先取当前评论的直接子评论，再逐层深入孙评论
        childs = commentlist.filter(parent_comment=c, is_enable=True)  # #jxr 只取已审核的子评论
        for child in childs:
            datas.append(child)
            parse(child)  # #jxr 递归：继续展开 child 的下一层

    parse(comment)
    return datas


@register.inclusion_tag('comments/tags/comment_item.html')
def show_comment_item(comment, ischild):
    """评论"""
    depth = 1 if ischild else 2  # #jxr 子评论缩进1级，顶级评论缩进2级（配合模板CSS样式）
    return {
        'comment_item': comment,
        'depth': depth
    }
