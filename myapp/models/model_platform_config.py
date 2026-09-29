# -*- coding: utf-8 -*-
"""
平台全局配置数据模型
- 存储全局 hostAliases 和 DNS 配置（只有一条记录 id=1）
- Admin 可增删改查
"""
from flask_appbuilder import Model
from myapp.models.helpers import AuditMixinNullable
from myapp.models.base import MyappModelBase
from sqlalchemy import Column, Integer, Text


class PlatformConfig(Model, AuditMixinNullable, MyappModelBase):
    """
    平台全局配置表
    - AuditMixinNullable 提供: created_on, changed_on, created_by_fk, changed_by_fk
    - MyappModelBase 提供 label_columns 中文标签映射
    """
    __tablename__ = 'platform_config'

    id = Column(Integer, primary_key=True, autoincrement=True, comment='配置ID主键')

    # hostAliases 配置（核心）
    host_aliases = Column(Text, default='',
        comment='额外 hostAliases，每行一个映射 格式: IP host1 host2')

    # DNS 配置（预留，暂无 DNS 服务器）
    dns_nameservers = Column(Text, default='',
        comment='额外DNS nameservers，每行一个IP地址（预留）')
    dns_searches = Column(Text, default='',
        comment='额外DNS search domains，每行一个域名（预留）')
    dns_options = Column(Text, default='',
        comment='DNS options，每行一个 name:value（预留）')

    label_columns = {
        'id': 'ID',
        'host_aliases': '额外 hostAliases',
        'dns_nameservers': '额外DNS服务器（预留）',
        'dns_searches': '额外搜索域（预留）',
        'dns_options': 'DNS选项（预留）',
        'created_on': '创建时间',
        'created_by': '创建人',
        'changed_on': '修改时间',
        'changed_by': '修改人',
    }

    def __repr__(self):
        return '平台全局配置'
