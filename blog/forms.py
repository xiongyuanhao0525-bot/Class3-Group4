# ============================================================
# blog/forms.py —— 博客前台的搜索表单（全文检索的输入载体）
# 作用：站内搜索页需要一个“搜索框 + 校验 + 提交给搜索引擎”的对象。Django 的 Form 就负责
#   “接住用户输入 → 按规则校验 → 清洗成 Python 数据”这一段；本文件在 Haystack 的
#   SearchForm（搜索表单基类，背后接着 SearchQuerySet 查询）之上，声明自己的搜索词字段，
#   并在 search() 里把用户搜的关键词记进日志。
# 本文件包含：
#   - BlogSearchForm：站内搜索表单；querydata 是搜索词字段（必填），search() 执行检索并打日志
# 注释人：翟旌超（软件工程 3 班 2415304340，#zjc）
# 说明：本次任务只添加中文注释，没有改动任何一行原有代码逻辑
# ============================================================

# —— Python 标准库 ——
# logging：把用户提交的搜索词打到日志里，便于观察大家都在搜什么、复现“搜不到”的问题
import logging

# —— 第三方库：Django 表单 + Haystack 搜索表单 ——
# forms：Django 表单模块，CharField 这类“字段”对象既声明输入类型，也带着校验规则；
# SearchForm：Haystack（Django 生态的全文检索抽象层）提供的搜索表单基类，
#   自带“把用户输入变成查询、交给底层引擎执行”的能力
from django import forms
from haystack.forms import SearchForm

# 本模块的日志记录器，日志里能看出是 forms 这一块打的
logger = logging.getLogger(__name__)


# 【BlogSearchForm】—— 博客站内搜索表单
# 说明：继承 SearchForm 就自动拥有执行检索的能力；本类只额外做两件事：
#   ① 声明一个必填的搜索词字段 querydata；② 重写 search()，把关键词打到日志里。
#   注意区分两个“搜索词”：父类真正拿去检索的字段按 Haystack 约定叫 q；
#   本类声明的 querydata 是页面表单用的字段。看视图 / 模板时要按字段名对号入座。
# 被谁用：blog/tests.py 里会实例化本表单并调用 search()，把搜索这条链路走一遍；
#   站点实际的 /search 路由（djangoblog/urls.py 第 71 行）用的是
#   djangoblog/elasticsearch_backend.py 里的 ElasticSearchModelSearchForm，
#   本类保留为“最简搜索表单”的实现，便于复用和测试。
class BlogSearchForm(SearchForm):
    # querydata：搜索关键词输入框
    #   CharField 渲染出来就是 <input type="text">，提交上来是字符串；
    #   required=True 表示必填 —— 请求里没带 querydata 时表单校验不通过，
    #   search() 会直接返回空结果集，避免把“无搜索条件的全量查询”打到搜索引擎上。
    #   值统一从 self.cleaned_data['querydata'] 取：cleaned_data 是校验通过并清洗后的字段字典
    querydata = forms.CharField(required=True)

    # 【search】—— 执行检索：先让父类查，表单不合法就改返回空结果集
    # 参数：无（搜索条件来自实例化表单时传进来的 data，一般是 request.GET）
    # 返回：SearchQuerySet（Haystack 的查询结果集，惰性求值 —— 真正遍历时才向搜索引擎发请求）；
    #       表单不合法时返回 no_query_found() 给的空结果集
    # 说明：第 13 行先让父类按 q 字段跑一遍查询；第 14 行的二次校验是兜底 ——
    #       只要表单不合法（例如 querydata 没填），就把父类的结果丢掉换成空结果集，
    #       这样页面拿到的永远是“可安全遍历”的对象，模板里 for 循环不会因为拿到 None 而报错。
    def search(self):
        # 父类内部会读 q 字段，拼查询交给搜索后端
        datas = super(BlogSearchForm, self).search()
        if not self.is_valid():
            # 空结果集：既不抛异常，也不会退化成返回全站文章
            return self.no_query_found()

        if self.cleaned_data['querydata']:
            # 只做记录：把用户真正输入的关键词写进日志，方便统计热门搜索、复盘“搜不到”的情况
            logger.info(self.cleaned_data['querydata'])
        return datas
