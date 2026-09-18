from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from blog.models import Article, Tag, Category


class Command(BaseCommand):
    help = 'replace test data with travel recommendation blog content'

    def handle(self, *args, **options):
        # 清空旧数据
        Article.objects.all().delete()
        Tag.objects.all().delete()
        Category.objects.all().delete()

        user = get_user_model().objects.filter(is_superuser=True).first()
        if not user:
            user = get_user_model().objects.first()

        # 分类
        categories = {}
        for name in ['国内游', '出境游', '旅行攻略']:
            categories[name] = Category.objects.create(name=name)

        # 标签
        tag_names = ['海岛', '美食', '亲子', '自驾', '徒步', '摄影', '避暑', '冬季', '自由行', '小众']
        tags = {}
        for name in tag_names:
            tags[name], _ = Tag.objects.get_or_create(name=name)

        # 文章
        articles = [
            {
                'title': '三亚海岛度假指南：三天两夜玩转亚龙湾',
                'category': '国内游',
                'tags': ['海岛', '亲子', '避暑'],
                'body': '''# 三亚海岛度假指南

三亚是冬季避寒、夏季看海的绝佳去处。这篇攻略带你三天两夜玩转亚龙湾。

## 行前准备

- 防晒霜、遮阳帽、泳衣必备
- 提前预订海景酒店
- 机票建议提前两周购买

## 行程安排

**第一天**：抵达后入住亚龙湾，傍晚海边散步看日落。

**第二天**：上午潜水或摩托艇，下午逛热带天堂森林公园。

**第三天**：免税店购物，下午返程。

## 美食推荐

清补凉、海鲜大排档、椰子鸡都是必尝项目。
''',
            },
            {
                'title': '云南大理丽江自由行攻略：遇见风花雪月',
                'category': '国内游',
                'tags': ['摄影', '自由行', '小众'],
                'body': '''# 云南大理丽江自由行攻略

云南是很多人的诗和远方，大理的风花雪月更是令人神往。

## 最佳季节

3-5 月和 9-11 月，气候宜人，游客相对较少。

## 大理必去

洱海环湖、崇圣寺三塔、喜洲古镇、双廊。

## 丽江必去

丽江古城、玉龙雪山、束河古镇、泸沽湖。

## 小贴士

海拔较高，注意防晒和保暖，尊重当地少数民族风俗。
''',
            },
            {
                'title': '新疆伊犁自驾路线推荐：一路都是风景',
                'category': '国内游',
                'tags': ['自驾', '摄影'],
                'body': '''# 新疆伊犁自驾路线推荐

伊犁河谷被称为"塞外江南"，自驾是最佳游玩方式。

## 推荐路线

乌鲁木齐 → 赛里木湖 → 果子沟 → 霍尔果斯 → 那拉提草原 → 独库公路。

## 沿途亮点

赛里木湖的蓝、那拉提的草原、独库公路的四季变化，每一帧都是壁纸。

## 注意事项

提前检查车况，准备充足补给，部分路段信号弱。
''',
            },
            {
                'title': '日本关西美食之旅：大阪京都奈良吃个遍',
                'category': '出境游',
                'tags': ['美食', '自由行'],
                'body': '''# 日本关西美食之旅

关西是日本美食的天堂，大阪、京都、奈良各有特色。

## 大阪

章鱼烧、大阪烧、道顿堀的招牌蟹料理。

## 京都

抹茶甜品、豆腐料理、京怀石料理。

## 奈良

大佛布丁、柿叶寿司。

## 交通

购买关西周游券，跨城市移动非常划算。
''',
            },
            {
                'title': '泰国清迈亲子游：带娃也能轻松玩',
                'category': '出境游',
                'tags': ['亲子', '美食'],
                'body': '''# 泰国清迈亲子游

清迈节奏慢、物价低，非常适合带娃旅行。

## 适合孩子的项目

大象营、夜间动物园、亲子厨艺课。

## 美食

芒果糯米饭、泰北咖喱面、夜市小吃。

## 住宿建议

选择古城附近或宁曼路一带，出行方便。
''',
            },
            {
                'title': '冬季去北海道看雪：温泉与滑雪的正确打开方式',
                'category': '出境游',
                'tags': ['冬季', '摄影'],
                'body': '''# 冬季北海道看雪

冬天的北海道是滑雪和温泉爱好者的天堂。

## 滑雪场推荐

二世古、留寿都、星野度假村。

## 温泉

登别温泉、洞爷湖温泉，雪中泡汤体验极佳。

## 注意事项

冬季路滑注意保暖，提前预订交通和住宿。
''',
            },
            {
                'title': '徒步入门指南：第一次徒步需要准备什么',
                'category': '旅行攻略',
                'tags': ['徒步', '攻略'],
                'body': '''# 徒步入门指南

徒步既能锻炼身体又能亲近自然，新手入门需做好充分准备。

## 装备清单

登山鞋、冲锋衣、登山杖、头灯、急救包、充足的水和食物。

## 路线选择

新手从 5-10 公里的成熟路线开始，循序渐进。

## 安全须知

结伴出行，告知亲友行程，关注天气变化。
''',
            },
            {
                'title': '旅行摄影技巧：手机也能拍出大片',
                'category': '旅行攻略',
                'tags': ['摄影', '攻略'],
                'body': '''# 旅行摄影技巧

不需要专业相机，掌握这些技巧手机也能拍出好照片。

## 构图

利用三分法、引导线、框架构图。

## 光线

日出日落是黄金时刻，逆光拍剪影，顺光拍色彩。

## 后期

适当调整曝光和饱和度，但不要过度修图。
''',
            },
        ]

        for data in articles:
            article = Article.objects.create(
                title=data['title'],
                body=data['body'],
                category=categories[data['category']],
                author=user,
                status='p',
                type='a',
            )
            for tag_name in data['tags']:
                article.tags.add(tags[tag_name])

        from djangoblog.utils import cache
        cache.clear()

        self.stdout.write(self.style.SUCCESS(
            f"Done! categories={Category.objects.count()} "
            f"tags={Tag.objects.count()} articles={Article.objects.count()}"))
