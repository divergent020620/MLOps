# -*- coding: utf-8 -*-
"""
公告数据模型
用于存储系统公告，支持 Markdown 格式内容。
仅管理员可新增/编辑/删除，所有登录用户可查看。
只允许一条公告处于生效状态（is_active=True），在 view 层 pre_add/pre_update 钩子中保证。
"""

from flask_appbuilder import Model
from myapp.models.helpers import AuditMixinNullable
from myapp.models.base import MyappModelBase
from sqlalchemy import Column, Integer, String, Text, Boolean


class Announcement(Model, AuditMixinNullable, MyappModelBase):
    """
    系统公告表
    - AuditMixinNullable 自动提供审计字段: created_on, changed_on, created_by_fk, changed_by_fk
    - MyappModelBase 提供 label_columns 中文标签映射
    """
    __tablename__ = 'announcement'  # 对应数据库表名

    # 主键ID，自增
    id = Column(Integer, primary_key=True, autoincrement=True, comment='公告ID主键')

    # 公告标题（必填，最长200字符）
    title = Column(String(200), nullable=False, comment='公告标题')

    # 公告正文，Markdown 格式文本，最大 65536 字符（TEXT 类型）
    content = Column(Text(65536), default='', comment='公告内容（Markdown格式）')

    # 是否当前生效公告。
    # 同一时间只允许一条公告生效：在 view 层的 pre_add / pre_update 钩子中，
    # 若新公告/编辑后公告 is_active=True，会先将所有旧公告的 is_active 置为 False。
    is_active = Column(Boolean, default=False, comment='是否当前生效公告')

    # 中文标签 —— 用于前端表格列表头、表单字段名显示
    label_columns = {
        'id': 'ID',
        'title': '公告标题',
        'content': '公告内容（Markdown）',
        'is_active': '是否生效',
        'created_on': '创建时间',
        'created_by': '创建人',
        'changed_on': '修改时间',
        'changed_by': '修改人',
    }
