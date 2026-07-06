# -*- coding: utf-8 -*-
"""
公告管理 API 视图
- 继承 MyappModelRestApi 提供标准 CRUD 接口
- can_add / can_edit / can_delete 仅 Admin 角色可用（通过 pre_add / pre_update / pre_delete 钩子校验）
- 所有登录用户可 can_list / can_show
- 自定义 GET /latest/ 端点：返回当前生效的最新公告，供前端首页弹窗调用
- 同一时间仅允许一条公告 is_active=True：在 pre_add / pre_update 钩子中自动将旧公告置为失效
"""

from flask import g
from flask_babel import lazy_gettext as _
from flask_appbuilder import expose
from flask_appbuilder.models.sqla.interface import SQLAInterface
from wtforms import StringField

from myapp.models.model_announcement import Announcement
from myapp.forms import MyBS3TextAreaFieldWidget
from myapp.views.baseApi import MyappModelRestApi
from myapp import appbuilder, db


class Announcement_ModelView_Api(MyappModelRestApi):
    """
    公告管理 API 视图
    route_base: /announcement_modelview/api
    标准端点: GET /list/, GET /_info, POST /, PUT /<pk>, DELETE /<pk>, GET /<pk>
    自定义端点: GET /latest/  (返回当前生效公告)
    """

    # ================================================================
    # 基本配置
    # ================================================================
    datamodel = SQLAInterface(Announcement)     # 绑定数据模型
    route_base = '/announcement_modelview/api'  # API 路由前缀
    label_title = '公告管理'                      # 页面/菜单标题
    primary_key = 'id'                           # 主键字段名

    # ================================================================
    # 权限配置
    # Admin 可全部操作；普通用户通过 pre_add/pre_update/pre_delete 进一步限制
    # ================================================================
    base_permissions = ['can_add', 'can_show', 'can_edit', 'can_list', 'can_delete']

    # ================================================================
    # 列表 / 排序 / 搜索 配置
    # ================================================================
    base_order = ('id', 'desc')  # 默认按 ID 倒序排列，最新的公告靠前
    order_columns = ['id', 'created_on', 'is_active']

    list_columns = ['id', 'title', 'is_active', 'created_on', 'created_by']
    search_columns = ['title']  # 支持按标题模糊搜索

    # ================================================================
    # 新增 / 编辑 / 详情 表单字段配置
    # ================================================================
    add_columns = ['title', 'content', 'is_active']
    edit_columns = ['title', 'content', 'is_active']
    show_columns = [
        'title', 'content', 'is_active',
        'created_on', 'created_by', 'changed_on', 'changed_by'
    ]

    # 字段宽度（用于前端表格列宽）
    cols_width = {
        'title': 200,
        'content': 500,
        'is_active': 100,
    }

    # content 字段使用多行 TextArea，方便管理员输入 Markdown
    edit_form_extra_fields = {
        'content': StringField(
            label=_('公告内容（Markdown）'),
            description=_('支持 Markdown 语法：标题、加粗、表格、链接等'),
            widget=MyBS3TextAreaFieldWidget(rows=15),
        )
    }

    # ================================================================
    # 权限校验钩子 —— 限制只有管理员可以新增 / 编辑 / 删除
    # ================================================================
    def pre_add(self, item):
        """
        新增公告前执行：
        1. 校验当前用户是否为管理员，非管理员直接抛异常拒绝
        2. 若新公告设为生效，先将所有已有公告置为失效（保证唯一生效约束）
        """
        if not g.user.is_admin():
            raise Exception('仅管理员可发布公告，请联系管理员操作')

        # 如果新公告 is_active=True，则将旧的生效公告全部置为 False
        if item.is_active:
            self._deactivate_all_announcements()

    def pre_update(self, item):
        """
        编辑公告前执行：
        1. 校验当前用户是否为管理员
        2. 若编辑后 is_active=True，则将其他公告置为失效
        """
        if not g.user.is_admin():
            raise Exception('仅管理员可编辑公告，请联系管理员操作')

        if item.is_active:
            self._deactivate_all_announcements()

    def pre_delete(self, item):
        """
        删除公告前执行：校验当前用户是否为管理员
        """
        if not g.user.is_admin():
            raise Exception('仅管理员可删除公告，请联系管理员操作')

    # ================================================================
    # 辅助方法
    # ================================================================
    def _deactivate_all_announcements(self):
        """
        将所有公告的 is_active 批量更新为 False。
        使用 flush() 而非 commit()，让 FAB 框架层统一管理事务提交与回滚。
        """
        db.session.query(Announcement).update(
            {Announcement.is_active: False}
        )
        db.session.flush()

    # ================================================================
    # 自定义端点：获取当前生效的最新公告
    # 路由：GET /announcement_modelview/api/latest/
    # 供前端首页弹窗调用，无需管理员权限
    # ================================================================
    @expose('/latest/', methods=['GET'])
    def latest(self):
        """
        查询 is_active=True 且 created_on 最新的一条公告。
        返回 JSON 格式：
        - 有公告：{ "data": { id, title, content, is_active, created_on }, "status": 0 }
        - 无公告：{ "data": null, "status": 0 }
        """
        announcement = (
            db.session.query(Announcement)
            .filter(Announcement.is_active == True)  # noqa: E712 — SQLAlchemy 的布尔过滤写法
            .order_by(Announcement.created_on.desc())
            .first()
        )

        if not announcement:
            return self.response(200, data=None, message='暂无生效公告', status=0)

        # 构造返回数据，将 datetime 转为字符串避免 JSON 序列化报错
        result = {
            'id': announcement.id,
            'title': announcement.title,
            'content': announcement.content,
            'is_active': announcement.is_active,
            'created_on': (
                announcement.created_on.strftime('%Y-%m-%d %H:%M:%S')
                if announcement.created_on else None
            ),
        }
        return self.response(200, data=result, message='ok', status=0)


# ================================================================
# 注册到 Flask-AppBuilder —— 自动创建路由和权限
# ================================================================
appbuilder.add_api(Announcement_ModelView_Api)
