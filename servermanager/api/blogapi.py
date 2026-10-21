# -*- coding: utf-8 -*-
"""#wxy servermanager/api/blogapi.py：微信机器人访问博客业务数据的门面。

对 robot.py 屏蔽 ORM/Haystack 细节，只暴露机器人需要的四个查询：
搜索文章 / 全部分类 / 某分类文章 / 最新文章，统一限制最多返回 8 条。
"""
from haystack.query import SearchQuerySet

from blog.models import Article, Category


class BlogApi:
    """#wxy 面向微信公众号的博客只读数据 API。"""

    def __init__(self):
        # #wxy 初始化一个空的 Haystack 查询集；一次最多取 8 条，避免图文消息过长
        self.searchqueryset = SearchQuerySet()
        self.searchqueryset.auto_query('')
        self.__max_takecount__ = 8

    def search_articles(self, query):
        """#wxy ?关键字：Haystack 全文检索，load_all() 后切片取前 8 条。"""
        sqs = self.searchqueryset.auto_query(query)
        sqs = sqs.load_all()
        return sqs[:self.__max_takecount__]

    def get_category_lists(self):
        """#wxy category：返回全部分类（用于拼分类目录文本）。"""
        return Category.objects.all()

    def get_category_articles(self, categoryname):
        """#wxy category-xxx：按分类名过滤文章，取前 8 条；无文章返回 None。"""
        articles = Article.objects.filter(category__name=categoryname)
        if articles:
            return articles[:self.__max_takecount__]
        return None

    def get_recent_articles(self):
        """#wxy recent：取最新 8 篇文章。"""
        return Article.objects.all()[:self.__max_takecount__]
