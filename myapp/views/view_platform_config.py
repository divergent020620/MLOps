# -*- coding: utf-8 -*-
"""
平台全局配置 API 视图
- 继承 MyappModelRestApi 提供标准 CRUD
- 仅 Admin 可新增/编辑/删除
- 自定义端点: dns_detect (读取本机DNS), dns_apply_all (更新所有Pod)
"""
import time
from flask import g
from flask_babel import lazy_gettext as _
from flask_appbuilder import expose
from flask_appbuilder.models.sqla.interface import SQLAInterface
from wtforms import StringField

from myapp.models.model_platform_config import PlatformConfig
from myapp.views.baseApi import MyappModelRestApi
from myapp.forms import MyBS3TextAreaFieldWidget
from myapp import appbuilder, conf, db


class PlatformConfig_ModelView_Api(MyappModelRestApi):
    """平台配置管理 API"""

    datamodel = SQLAInterface(PlatformConfig)
    route_base = '/platform_config_modelview/api'
    label_title = '平台配置'
    primary_key = 'id'

    base_permissions = ['can_add', 'can_show', 'can_edit', 'can_list', 'can_delete']
    base_order = ('id', 'desc')
    order_columns = ['id', 'created_on', 'changed_on']

    list_columns = ['id', 'host_aliases', 'dns_nameservers', 'dns_searches', 'dns_options',
                    'created_on', 'created_by', 'changed_on', 'changed_by']
    add_columns = ['host_aliases', 'dns_nameservers', 'dns_searches', 'dns_options']
    edit_columns = ['host_aliases', 'dns_nameservers', 'dns_searches', 'dns_options']
    show_columns = add_columns + ['created_on', 'created_by', 'changed_on', 'changed_by']

    cols_width = {
        'host_aliases': 300,
        'dns_nameservers': 200,
        'dns_searches': 200,
        'dns_options': 150,
    }

    edit_form_extra_fields = {
        'host_aliases': StringField(
            label=_('全局 hostAliases'),
            description=_('每行一条 IP host1 host2，如: 192.168.1.1 spark-master.internal'),
            widget=MyBS3TextAreaFieldWidget(rows=10),
        ),
        'dns_nameservers': StringField(
            label=_('DNS 服务器（预留）'),
            description=_('每行一个IP地址，暂无DNS服务器可留空'),
            widget=MyBS3TextAreaFieldWidget(rows=4),
        ),
        'dns_searches': StringField(
            label=_('DNS 搜索域（预留）'),
            description=_('每行一个域名'),
            widget=MyBS3TextAreaFieldWidget(rows=4),
        ),
        'dns_options': StringField(
            label=_('DNS 选项（预留）'),
            description=_('每行一个 name:value，如 ndots:5'),
            widget=MyBS3TextAreaFieldWidget(rows=4),
        ),
    }

    # ------------------------------------------------------------------
    # 权限钩子
    # ------------------------------------------------------------------
    def pre_add(self, item):
        if not g.user.is_admin():
            raise Exception('仅管理员可操作平台配置')
        existing = db.session.query(PlatformConfig).first()
        if existing:
            raise Exception('已存在平台配置记录，请使用编辑功能（列表→编辑）')

    def pre_update(self, item):
        if not g.user.is_admin():
            raise Exception('仅管理员可操作平台配置')

    def pre_delete(self, item):
        if not g.user.is_admin():
            raise Exception('仅管理员可操作平台配置')

    def post_add(self, item):
        self._refresh_config()

    def post_update(self, item):
        self._refresh_config()

    def _refresh_config(self):
        """从数据库读取配置，写入 app.config 运行时缓存"""
        try:
            config = db.session.query(PlatformConfig).filter_by(id=1).first()
            if config:
                conf['PLATFORM_HOST_ALIASES'] = config.host_aliases or ''
                conf['DNS_NAMESERVERS'] = config.dns_nameservers or ''
                conf['DNS_SEARCHES'] = config.dns_searches or ''
                conf['DNS_OPTIONS'] = config.dns_options or ''
            else:
                conf['PLATFORM_HOST_ALIASES'] = ''
                conf['DNS_NAMESERVERS'] = ''
                conf['DNS_SEARCHES'] = ''
                conf['DNS_OPTIONS'] = ''
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 自定义端点: 读取本机 /etc/resolv.conf 和 /etc/hosts
    # ------------------------------------------------------------------
    @expose('/dns_detect/', methods=['GET'])
    def dns_detect(self):
        if not g.user.is_admin():
            return self.response(403, message='仅管理员可用', status=1)

        result = {'resolv_conf': '', 'hosts': ''}
        try:
            with open('/etc/resolv.conf', 'r') as f:
                result['resolv_conf'] = f.read()
        except Exception:
            result['resolv_conf'] = ''

        try:
            with open('/etc/hosts', 'r') as f:
                result['hosts'] = f.read()
        except Exception:
            result['hosts'] = ''

        return self.response(200, data=result, message='ok', status=0)

    # ------------------------------------------------------------------
    # 自定义端点: 保存配置并滚动重启所有 Pod
    # ------------------------------------------------------------------
    @expose('/dns_apply_all/', methods=['POST'])
    def dns_apply_all(self):
        if not g.user.is_admin():
            return self.response(403, message='仅管理员可用', status=1)

        # 先刷新配置，确保最新值写入 conf
        self._refresh_config()

        # 收集所有需要检查的 namespace
        namespaces_to_check = set()
        for key in ['PIPELINE_NAMESPACE', 'NOTEBOOK_NAMESPACE', 'SERVICE_NAMESPACE',
                     'SERVICE_PIPELINE_NAMESPACE', 'AUTOML_NAMESPACE', 'AIHUB_NAMESPACE']:
            ns = conf.get(key, '')
            if ns:
                namespaces_to_check.add(ns)
        # 加上 infra / kubeflow 等基础设施 namespace
        extra = conf.get('HUBSECRET_NAMESPACE', [])
        for ns in extra:
            if ns:
                namespaces_to_check.add(ns)

        if not namespaces_to_check:
            return self.response(200, data={'restarted': [], 'failed': [], 'skipped': []},
                                message='未配置任何 namespace', status=0)

        results = {'restarted': [], 'failed': [], 'skipped': []}
        restart_ts = str(int(time.time()))

        for ns in namespaces_to_check:
            try:
                k8s_client = self._get_k8s_client()
                # 滚动重启 Deployment
                deps = k8s_client.AppsV1Api.list_namespaced_deployment(namespace=ns)
                for dep in deps.items:
                    try:
                        patch_body = {
                            "spec": {
                                "template": {
                                    "metadata": {
                                        "annotations": {
                                            "cube-studio/restartedAt": restart_ts
                                        }
                                    }
                                }
                            }
                        }
                        k8s_client.AppsV1Api.patch_namespaced_deployment(
                            name=dep.metadata.name, namespace=ns, body=patch_body)
                        results['restarted'].append(f"deployment/{ns}/{dep.metadata.name}")
                    except Exception as e:
                        results['failed'].append(f"deployment/{ns}/{dep.metadata.name}: {e}")

                # 滚动重启 StatefulSet
                stss = k8s_client.AppsV1Api.list_namespaced_stateful_set(namespace=ns)
                for sts in stss.items:
                    try:
                        patch_body = {
                            "spec": {
                                "template": {
                                    "metadata": {
                                        "annotations": {
                                            "cube-studio/restartedAt": restart_ts
                                        }
                                    }
                                }
                            }
                        }
                        k8s_client.AppsV1Api.patch_namespaced_stateful_set(
                            name=sts.metadata.name, namespace=ns, body=patch_body)
                        results['restarted'].append(f"statefulset/{ns}/{sts.metadata.name}")
                    except Exception as e:
                        results['failed'].append(f"statefulset/{ns}/{sts.metadata.name}: {e}")
            except Exception as e:
                results['skipped'].append(f"namespace/{ns}: {e}")

        total_ok = len(results['restarted'])
        total_fail = len(results['failed'])
        return self.response(200, data=results,
                            message=f'完成: {total_ok} 成功, {total_fail} 失败', status=0)

    @staticmethod
    def _get_k8s_client():
        """获取 K8s 客户端（延迟导入避免循环依赖）"""
        from myapp.utils.py.py_k8s import K8s
        return K8s()


# 注册到 Flask-AppBuilder
appbuilder.add_api(PlatformConfig_ModelView_Api)
