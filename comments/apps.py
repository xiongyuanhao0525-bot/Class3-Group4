from django.apps import AppConfig

# #jxr comments app 的应用配置类：向 Django 声明该 app 的应用名


class CommentsConfig(AppConfig):
    name = 'comments'  # #jxr 应用名：与 comments 包目录名一致
