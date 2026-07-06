import datetime
import re
import shutil
import traceback
import zipfile, pandas
from flask_appbuilder import action
from flask_appbuilder.baseviews import expose_api

from myapp.views.baseSQLA import MyappSQLAInterface as SQLAInterface
from wtforms.validators import DataRequired, Regexp
from myapp import app, appbuilder, event_logger
from wtforms import StringField, SelectField
from flask_appbuilder.fieldwidgets import BS3TextFieldWidget, Select2Widget, Select2ManyWidget
from myapp.forms import MyBS3TextAreaFieldWidget, MySelect2Widget, MyCommaSeparatedListField, MySelect2ManyWidget, \
    MySelectMultipleField
from flask import jsonify, Markup, make_response, flash
from .baseApi import MyappModelRestApi
from flask import g, request, redirect
import json, os, sys
from werkzeug.utils import secure_filename
import pysnooper
from sqlalchemy import or_
from flask_babel import gettext as __
from flask_babel import lazy_gettext as _
import importlib
from .base import (
    MyappFilter
)
from myapp import app, appbuilder, db
from flask_appbuilder import expose
from myapp.views.view_team import Project_Join_Filter, filter_join_org_project
from myapp.models.model_dataset import Dataset
from myapp.utils import core
conf = app.config


class Dataset_Filter(MyappFilter):
    # @pysnooper.snoop()
    def apply(self, query, func):
        if g.user.is_admin():
            return query

        return query.filter(
            or_(
                self.model.owner.contains(g.user.username),
                self.model.owner.contains('*')
            )
        )


class Dataset_ModelView_base():
    label_title = _('数据集')
    datamodel = SQLAInterface(Dataset)
    base_permissions = ['can_add', 'can_show', 'can_edit', 'can_list', 'can_delete']
    # 只有 admin 可以删除数据集
    def check_delete_permission(self, item):
        return g.user.is_admin()
    check_delete_permission.__doc__ = "仅管理员可删除数据集"

    base_order = ("id", "desc")
    order_columns = ['id']
    base_filters = [["id", Dataset_Filter, lambda: []]]  # 设置权限过滤器

    add_columns = ['name', 'version', 'label', 'describe', 'url', 'download_url', 'path', 'icon', 'owner', 'features']
    search_columns = ['name', 'version', 'label', 'describe', 'source_type', 'source', 'field', 'usage','storage_class', 'file_type', 'status', 'url', 'path', 'download_url']
    spec_label_columns = {
        "subdataset": _("子数据集名称"),
        "source_type": _("来源类型"),
        "source": _("数据来源"),
        "usage": _("数据用途"),
        "research": _("研究方向"),
        "storage_class": _("存储类型"),
        "years": _("数据年份"),
        "url": _("相关网址"),
        "url_html": _("相关网址"),
        "label_html": _("中文名"),
        "path": _("容器内路径"),
        "path_html": _("容器内路径"),
        "entries_num": _("条目数量"),
        "duration": _("文件时长"),
        "price": _("价格"),
        "icon": _("预览图"),
        "icon_html": _("预览图"),
        "ops_html": _("操作"),
        "features": _("特征列"),
        "segment": _("分区"),
        "preview_html": _("数据预览"),
    }

    show_columns = ['id', 'name', 'version', 'label', 'describe', 'segment', 'source_type', 'source',
                    'industry', 'field', 'usage', 'storage_class', 'file_type', 'status', 'url',
                    'path', 'download_url', 'storage_size', 'entries_num', 'duration', 'price', 'status', 'icon',
                    'owner', 'features', 'preview_html']
    list_columns = ['icon_html', 'name', 'version', 'label_html', 'describe','owner', 'path_html', 'download_url_html', 'preview_html']

    cols_width = {
        "name": {"type": "ellip1", "width": 150},
        "label": {"type": "ellip2", "width": 200},
        "label_html": {"type": "ellip2", "width": 200},
        "version": {"type": "ellip2", "width": 100},
        "describe": {"type": "ellip2", "width": 300},
        "field": {"type": "ellip1", "width": 100},
        "source_type": {"type": "ellip1", "width": 100},
        "source": {"type": "ellip1", "width": 100},
        "industry": {"type": "ellip1", "width": 100},
        "url_html": {"type": "ellip1", "width": 200},
        "download_url_html": {"type": "ellip1", "width": 200},
        "path_html": {"type": "ellip1", "width": 200},
        "storage_class": {"type": "ellip1", "width": 100},
        "storage_size": {"type": "ellip1", "width": 100},
        "file_type": {"type": "ellip1", "width": 100},
        "owner": {"type": "ellip1", "width": 200},
        "status": {"type": "ellip1", "width": 100},
        "entries_num": {"type": "ellip1", "width": 200},
        "duration": {"type": "ellip1", "width": 100},
        "price": {"type": "ellip1", "width": 100},
        "years": {"type": "ellip2", "width": 100},
        "usage": {"type": "ellip1", "width": 200},
        "research": {"type": "ellip2", "width": 100},
        "icon_html": {"type": "ellip1", "width": 100},
        "ops_html": {"type": "ellip1", "width": 100},
    }
    features_demo = '''
rules：
{
  "column1": {
    # feature type
    "_type": "dict,list,tuple,Value,Sequence,Array2D,Array3D,Array4D,Array5D,Translation,TranslationVariableLanguages,Audio,Image,Video",

    # data type in dict,list,tuple,Value,Sequence,Array2D,Array3D,Array4D,Array5D
    "dtype": "null,bool,int8,int16,int32,int64,uint8,uint16,uint32,uint64,float16,float32,float64,time32[(s|ms)],time64[(us|ns)],timestamp[(s|ms|us|ns)],timestamp[(s|ms|us|ns),tz=(tzstring)],date32,date64,duration[(s|ms|us|ns)],decimal128(precision,scale),decimal256(precision,scale),binary,large_binary,string,large_string"

  }
}

example：
{
    "id": {
        "_type": "Value",
        "dtype": "string"
    },
    "image": {
        "_type": "Image"
    },
    "box": {
        "_type": "Value",
        "dtype": "string"
    }
}
    '''
    add_form_extra_fields = {
        "name": StringField(
            label= _('名称'),
            description= _('数据集英文名，(小写字母、数字、- 组成)，最长50个字符'),
            default='',
            widget=BS3TextFieldWidget(),
            validators=[DataRequired(), Regexp("^[a-z][a-z0-9\-]*[a-z0-9]$")]
        ),
        "version": StringField(
            label= _('版本'),
            description= _('数据集版本'),
            default='latest',
            widget=BS3TextFieldWidget(),
            validators=[DataRequired(), Regexp("[a-z0-9_\-\.]*")]
        ),
        "subdataset": StringField(
            label= _('子数据集'),
            description= _('子数据集名称，不存在子数据集，与name同值'),
            default='',
            widget=BS3TextFieldWidget(),
            validators=[]
        ),
        "label": StringField(
            label= _('标签'),
            default='',
            description='',
            widget=BS3TextFieldWidget(),
            validators=[DataRequired()]
        ),
        "describe": StringField(
            label= _('描述'),
            default='',
            description= _('数据集描述'),
            widget=MyBS3TextAreaFieldWidget(),
            validators=[DataRequired()]
        ),
        "industry": SelectField(
            label= _('行业'),
            description= _('行业分类'),
            widget=MySelect2Widget(can_input=True),
            default='',
            choices=[[_(x), _(x)] for x in
                     ['农业', '生物学', '气候+天气', '复杂网络', '计算机网络', '网络安全', '数据挑战', '地球科学', '经济学', '教育', '能源', '娱乐', '金融',
                      'GIS', '政府', '医疗', '图像处理', '机器学习', '博物馆', '自然语言', '神经科学', '物理', '前列腺癌', '心理学+认知', '公共领域', '搜索引擎',
                      '社交网络', '社会科学', '软件', '运动', '时间序列', '交通', '电子竞技']],
            validators=[]
        ),
        "field": SelectField(
            label= _('领域'),
            description='',
            widget=MySelect2Widget(can_input=True),
            choices=[[_(x), _(x)] for x in ['视觉', "语音", "自然语言",'多模态', "风控", "搜索", '推荐','广告']],
            validators=[]
        ),
        "source_type": SelectField(
            label= _('数据源类型'),
            description='',
            widget=Select2Widget(),
            default= _('开源'),
            choices=[[_(x), _(x)] for x in ["开源", "自产", "购买"]],
            validators=[]
        ),
        "source": SelectField(
            label= _('数据来源'),
            description= _('数据来源，可自己填写'),
            widget=MySelect2Widget(can_input=True),
            choices=[[_(x), _(x)] for x in
                     ['github', "kaggle", "ali", 'uci', 'aws', 'google', "company1", "label-team1", "web1"]],
            validators=[]
        ),
        "file_type": MySelectMultipleField(
            label= _('文件类型'),
            description='',
            widget=Select2ManyWidget(),
            choices=[[x, x] for x in ["png", "jpg", 'txt', 'csv', 'wav', 'mp3', 'mp4', 'nv4', 'zip', 'gz']],
        ),
        "storage_class": SelectField(
            label= _('存储类型'),
            description='',
            widget=MySelect2Widget(can_input=True),
            choices=[[_(x), _(x)] for x in ["压缩", "未压缩"]],
        ),
        "storage_size": StringField(
            label= _('存储大小'),
            description='',
            widget=BS3TextFieldWidget(),
        ),
        "owner": StringField(
            label= _('责任人'),
            default='*',
            description= _('责任人,逗号分隔的多个用户,*表示公开'),
            widget=BS3TextFieldWidget(),
            validators=[DataRequired()]
        ),
        "status": SelectField(
            label= _('状态'),
            description= _('数据集状态'),
            widget=MySelect2Widget(can_input=True),
            choices=[[_(x), _(x)] for x in ["损坏", "正常", '未购买', '已购买', '未标注', '已标注', '未校验', '已校验']],
        ),
        "url": StringField(
            label= _('相关网址'),
            description=_('关于数据集介绍或者手动下载的网址，每行一个网址'),
            widget=MyBS3TextAreaFieldWidget(rows=3),
            default=''
        ),
        "path": StringField(
            label= _('容器内路径'),
            description=_('本地文件通过notebook上传到平台内，处理后，压缩成单个压缩文件，每行一个压缩文件地址。<a target="_blank" href="/notebook_modelview/api/entry/jupyter?file_path=/mnt/{{creator}}/">上传文件</a>'),
            widget=MyBS3TextAreaFieldWidget(rows=3),
            default=''
        ),
        "download_url": StringField(
            label= _('下载地址'),
            description=_('如何数据集存储在外部，此处提供可以直接下载的链接地址，每行一个url'),
            widget=MyBS3TextAreaFieldWidget(rows=3),
            default=''
        ),
        "icon": StringField(
            label=_('预览图'),
            default='',
            description=_('可以为图片地址，svg源码，或者帮助文档链接'),
            widget=BS3TextFieldWidget(),
            validators=[]
        ),
        "features": StringField(
            label= _('特征列'),
            description= _('数据集中的列信息，要求数据集中要有data.csv文件用于表示数据集中的全部数据'),
            widget=MyBS3TextAreaFieldWidget(rows=3, tips=Markup('<pre><code>' + features_demo + "</code></pre>")),
            default=''
        )
    }
    edit_form_extra_fields = add_form_extra_fields

    import_data = True
    download_data = True

    # @pysnooper.snoop()
    def pre_add(self, item):
        if not item.owner or item.owner == '*':
            item.owner = g.user.username + ",*"
        if item.icon and '</svg>' in item.icon:
            item.icon = re.sub(r'width="\d+(\.\d+)?(px)?"', f'width="50px"', item.icon)
            item.icon = re.sub(r'height="\d+(\.\d+)?(px)?"', f'height="50px"', item.icon)
        if not item.version:
            item.version = 'latest'
        if not item.subdataset:
            item.subdataset = item.name
        item.features = json.dumps(json.loads(item.features),indent=4,ensure_ascii=False) if item.features else "{}"
        # 判断文件是否存在
        if item.path:
            new_paths = []
            paths = item.path.split("\n")
            for path in paths:
                local_path = os.path.join('/home/myapp/myapp/static/', path.lstrip('/'))
                if os.path.exists(local_path):
                    new_paths.append(path)
                else:
                    flash(path+"，文件不存在，保存时已去除", "error")
            item.path = '\n'.join(new_paths)


    def pre_update(self, item):
        self.pre_add(item)


    def check_edit_permission(self, item):
        if not g.user.is_admin() and g.user.username != item.created_by.username and g.user.username not in item.owner:
            return False
        return True
    # 将外部存储保存到本地存储中心
    @action("save_store", "备份", "备份数据到当前集群?", "fa-trash", single=True, multiple=False)
    # @pysnooper.snoop()
    def save_store(self, dataset):
        if not self.check_edit_permission(dataset):
            flash('no permission','warning')
            return
        from myapp.tasks.async_task import update_dataset
        kwargs = {
            "dataset_id": dataset.id,
        }
        update_dataset.apply_async(kwargs=kwargs)
        # update_dataset(task=None,dataset_id=item.id)


    # 将外部存储保存到本地存储中心
    @expose_api(description="下载指定数据集",url="/download/<dataset_id>", methods=["GET", "POST"])
    @expose_api(description="下载指定数据集指定分片",url="/download/<dataset_id>/<partition>", methods=["GET", "POST"])
    def download_dataset(self, dataset_id, partition=''):

        # 生成下载链接
        def path2url(path):
            if 'http://' in path or "https://" in path:
                return path
            if re.match('^/mnt/', path):
                return f'{request.host_url.strip("/")}/static{path}'
            if re.match('^/data/k8s/kubeflow/dataset', path):
                return f'{request.host_url.strip("/")}/static{path.replace("/data/k8s/kubeflow", "")}'

        dataset = db.session.query(Dataset).filter_by(id=int(dataset_id)).first()
        # 查询是否有下载权限
        if '*' not in dataset.owner and g.user.username not in dataset.owner and not g.user.is_admin():
            return make_response(("Not authorized to download dataset", 401))
        try:

            download_url = []
            if dataset.path and dataset.path.strip():
                # 如果存储在集群数据集中心
                # 如果存储在个人目录
                paths = dataset.path.split('\n')
                for path in paths:
                    download_url.append(path2url(path))

            # 如果存储在外部链接
            elif dataset.download_url and dataset.download_url.strip():
                download_url = dataset.download_url.split('\n')
            else:
                # 如果存储在对象存储中
                store_type = conf.get('STORE_TYPE', 'minio')
                params = importlib.import_module(f'myapp.utils.store.{store_type}')
                store_client = getattr(params, store_type.upper() + '_client')(**conf.get('STORE_CONFIG', {}))
                remote_file_path = f'/dataset/{dataset.name}/{dataset.version}'
                download_url = store_client.get_download_url(remote_file_path)

            if partition:
                segment = json.loads(dataset.segment) if dataset.segment else {}
                if partition in segment:
                    download_url = segment[partition]
                    download_url = [path2url(url) for url in download_url]

            return jsonify({
                "status": 0,
                "result": {
                    "store_type": conf.get('STORE_TYPE', 'minio'),
                    "download_urls": download_url
                },
                "message": "success"
            })
        except Exception as e:
            traceback.print_exc()
            return jsonify({
                "status": 1,
                "result": '',
                "message": str(e)
            })

    @expose_api(description="预览指定数据集",url="/preview/<dataset_name>", methods=["GET", "POST"])
    @expose_api(description="预览指定数据集指定版本",url="/preview/<dataset_name>/<dataset_version>", methods=["GET", 'POST'])
    @expose_api(description="预览指定数据集指定版本指定分片",url="/preview/<dataset_name>/<dataset_version>/<dataset_segment>", methods=["GET", 'POST'])
    def preview(self):
        _args = request.get_json(silent=True) or {}
        _args.update(request.args)
        _args.update(json.loads(request.args.get('form_data', {})))
        info = {}
        info.update(
            {
                "rows": [
                    {
                        "row_idx": 0,
                        "row": {
                            "col1": "",
                            "col2": "",
                            "col3": "",
                            "label1": [""],
                            "no_answer": False
                        },
                        "truncated_cells": []
                    }
                ]
            }
        )
        return jsonify(info)



    # 划分数据历史版本
    def pre_list_res(self,res):
        data=res['data']
        import itertools
        all_data={item['id']:item for item in data}
        all_last_data_id=[]
        # 按name分组，最新数据下包含其他更老的数据作为历史集合
        data = sorted(data, key=lambda x: x['name'])
        for name, group in itertools.groupby(data, key=lambda x: x['name']):
            group=list(group)
            max_id = max([x['id'] for x in group])
            all_last_data_id.append(max_id)
            for item in group:
                if item['id']!=max_id:
                    if 'children' not in all_data[max_id]:
                        all_data[max_id]['children']=[all_data[item['id']]]
                    else:
                        all_data[max_id]['children'].append(all_data[item['id']])
        # 顶层只保留最新的数据
        res['data'] = [all_data[id] for id in all_data if id in all_last_data_id]
        return res

    # 删除，把备份的数据也删除了
    def post_delete(self,dataset):
        remote_dir = f'dataset/{dataset.name}/{dataset.version if dataset.version else "latest"}/'
        remote_dir = os.path.join('/data/k8s/kubeflow/global/', remote_dir)
        if os.path.exists(remote_dir):
            # 先清理干净，因为有可能存在旧的不对的数据
            shutil.rmtree(remote_dir, ignore_errors=True)

        # 同时清理 HDFS 下载的本地文件
        datasetsavepath = conf.get('DATASET_SAVEPATH',
                                    os.path.join('/data/k8s/kubeflow', 'datasets'))
        hdfs_local_dir = os.path.join(datasetsavepath,
                                       f'{dataset.name}_{dataset.version or "latest"}')
        if os.path.exists(hdfs_local_dir):
            shutil.rmtree(hdfs_local_dir, ignore_errors=True)

    # ═══════════════════════════════════════════════════════════
    # HDFS 数据集相关操作
    # ═══════════════════════════════════════════════════════════

    # 从 HDFS 下载数据集 (异步 Celery 任务)
    @expose_api(description="触发HDFS数据集下载", url="/download_from_hdfs/<dataset_id>", methods=["POST"])
    def download_from_hdfs(self, dataset_id):
        """
        触发从 HDFS 下载 parquet 数据集的 Celery 异步任务。

        POST body:
            partition_values: ["20260620", "20260621"]  — 分区值列表
            partition_col: "dt"                          — 分区列名
            hdfs_path: "/user/hive/warehouse/db.db/table" — HDFS 源路径
        """
        dataset = db.session.query(Dataset).filter_by(id=int(dataset_id)).first()
        if not dataset:
            return jsonify({'status': 1, 'message': '数据集不存在', 'result': None})

        # 权限检查
        if not self.check_edit_permission(dataset):
            return jsonify({'status': 1, 'message': '无权限执行此操作', 'result': None})

        req_data = request.get_json(silent=True) or {}
        partition_values = req_data.get('partition_values', [])
        partition_col = req_data.get('partition_col', 'dt')
        hdfs_path = req_data.get('hdfs_path', dataset.hdfs_path or dataset.source or '')

        if not partition_values:
            return jsonify({'status': 1, 'message': '请指定分区值 partition_values', 'result': None})
        if not hdfs_path:
            return jsonify({'status': 1, 'message': '请指定HDFS路径 hdfs_path', 'result': None})

        # 更新 expand 中的 HDFS 元数据
        expand = json.loads(dataset.expand) if dataset.expand else {}
        expand['hdfs'] = {
            'full_path': hdfs_path,
            'partition_col': partition_col,
            'partition_values': partition_values,
            'download_status': 'pending',
            'download_progress': 0,
            'celery_task_id': None,
            'error_message': None,
        }
        dataset.expand = json.dumps(expand)
        dataset.source_type = dataset.source_type or 'hdfs'
        dataset.source = dataset.source or hdfs_path
        dataset.hdfs_path = dataset.hdfs_path or hdfs_path
        dataset.file_type = dataset.file_type or 'parquet'
        db.session.commit()

        # 启动 Celery 异步任务，同时传递 HDFS 连接配置和 hosts 条目（worker pod 没有本地文件）
        from myapp.tasks.hdfs_tasks import download_hdfs_dataset
        from myapp.views.view_hdfs import _load_persisted_config
        hdfs_conf = _load_persisted_config()

        # 提取后端 /etc/hosts 中 HDFS 相关的条目，传给 worker 写入
        hosts_entries = []
        if hdfs_conf.get('url'):
            from urllib.parse import urlparse
            hdfs_hostname = urlparse(hdfs_conf['url']).hostname
            if hdfs_hostname:
                try:
                    with open('/etc/hosts', 'r') as hf:
                        for line in hf:
                            stripped = line.strip()
                            if not stripped or stripped.startswith('#'):
                                continue
                            # 收集所有非 localhost 的 hosts 条目
                            if 'localhost' not in stripped and '127.0.0.1' not in stripped:
                                hosts_entries.append(stripped)
                except Exception:
                    pass

        celery_result = download_hdfs_dataset.apply_async(kwargs={
            'dataset_id': dataset.id,
            'hdfs_config': {
                'url': hdfs_conf.get('url', ''),
                'keytab_path': hdfs_conf.get('keytab_path', ''),
                'principal': hdfs_conf.get('principal', ''),
                'base_path': hdfs_conf.get('base_path', '/user/hive/warehouse'),
                'datasavepath': hdfs_conf.get('datasavepath', ''),
            },
            'hosts_entries': hosts_entries,
        })

        # 记录 task_id
        expand = json.loads(dataset.expand) if dataset.expand else {}
        expand['hdfs']['celery_task_id'] = celery_result.id
        expand['hdfs']['download_status'] = 'downloading'
        dataset.expand = json.dumps(expand)
        db.session.commit()

        return jsonify({
            'status': 0,
            'message': '下载任务已提交',
            'result': {
                'celery_task_id': celery_result.id,
                'dataset_id': dataset.id,
            }
        })

    # 查询 HDFS 下载状态
    @expose_api(description="查询HDFS数据集下载状态", url="/download_status/<dataset_id>", methods=["GET"])
    def download_status(self, dataset_id):
        """
        查询 HDFS 数据集下载进度。

        返回:
            download_status: pending|downloading|completed|failed
            download_progress: 0-100
            error_message: 错误信息 (如果有)
        """
        dataset = db.session.query(Dataset).filter_by(id=int(dataset_id)).first()
        if not dataset:
            return jsonify({'status': 1, 'message': '数据集不存在', 'result': None})

        expand = json.loads(dataset.expand) if dataset.expand else {}
        hdfs_meta = expand.get('hdfs', {})

        # 如果 Celery task_id 存在，查询 Celery 任务状态
        task_id = hdfs_meta.get('celery_task_id')
        celery_state = None
        if task_id:
            try:
                from celery.result import AsyncResult
                from myapp.tasks.celery_app import celery_app
                result = AsyncResult(task_id, app=celery_app)
                celery_state = result.state
            except Exception:
                pass

        return jsonify({
            'status': 0,
            'message': '',
            'result': {
                'download_status': hdfs_meta.get('download_status', 'unknown'),
                'download_progress': hdfs_meta.get('download_progress', 0),
                'celery_task_id': task_id,
                'celery_state': celery_state,
                'error_message': hdfs_meta.get('error_message'),
                'partition_values': hdfs_meta.get('partition_values', []),
                'full_path': hdfs_meta.get('full_path', ''),
            }
        })

    # Jupyter 加载代码生成
    @expose_api(description="生成Jupyter加载数据集代码", url="/jupyter_code/<dataset_id>", methods=["GET"])
    def jupyter_code(self, dataset_id):
        """
        返回在 Jupyter 中加载数据集的 Python 代码片段。
        """
        dataset = db.session.query(Dataset).filter_by(id=int(dataset_id)).first()
        if not dataset:
            return jsonify({'status': 1, 'message': '数据集不存在', 'result': None})

        # 权限：所有登录用户可查看
        if not g.user or not g.user.username:
            return jsonify({'status': 1, 'message': '请先登录', 'result': None})

        username = g.user.username
        dataset_name = dataset.name or f'dataset_{dataset.id}'
        dataset_version = dataset.version or 'latest'
        local_dir = f'{dataset_name}_{dataset_version}'

        # 获取 schema 信息用于展示列名
        expand = json.loads(dataset.expand) if dataset.expand else {}
        schema_cols = expand.get('schema', [])
        col_names = [c.get('name', '') for c in schema_cols[:10]] if schema_cols else []

        code_lines = [
            'import pyarrow.parquet as pq',
            'import pandas as pd',
            '',
            f'# 加载数据集: {dataset.label or dataset.name}',
            f'# 描述: {dataset.describe or ""}',
            f'# 行数: {dataset.entries_num or "未知"}, 大小: {dataset.storage_size or "未知"}',
            '',
            f"data_path = '/mnt/{username}/datasets/{local_dir}/data.parquet'",
            'pf = pq.ParquetFile(data_path)',
            '',
            '# 分批读 Row Group，避免瞬间内存尖峰 OOM',
            'dfs = []',
            'read_rgs = 10  # 每批读 10 个 row group',
            'for i in range(0, pf.metadata.num_row_groups, read_rgs):',
            '    end = min(i + read_rgs, pf.metadata.num_row_groups)',
            '    table = pf.read_row_groups(list(range(i, end)))',
            '    dfs.append(table.to_pandas())',
            '',
            'df = pd.concat(dfs, ignore_index=True)',
            '',
        ]

        if col_names:
            code_lines.append(f'# 列名: {", ".join(col_names)}')
            code_lines.append(f"# 查看前5行: df.head()")
        else:
            code_lines.append('# 查看数据概览')
            code_lines.append('print(df.info())')
            code_lines.append('print(df.head())')

        code = '\n'.join(code_lines)

        return jsonify({
            'status': 0,
            'message': '',
            'result': {
                'code': code,
                'dataset_name': dataset.name,
                'dataset_label': dataset.label or dataset.name,
                'entries_num': dataset.entries_num,
                'storage_size': dataset.storage_size,
                'columns': schema_cols,
                'local_path': f'/mnt/{username}/datasets/{local_dir}/data.parquet',
            }
        })

    # Jupyter 数据集列表 (供 JupyterLab 扩展调用)
    @expose_api(description="获取所有可用数据集列表(Jupyter)", url="/jupyter_list", methods=["GET"])
    def jupyter_list(self):
        """
        返回所有已下载完成的数据集列表，供 Jupyter 侧边栏使用。
        """
        datasets = db.session.query(Dataset).filter(
            or_(
                Dataset.owner.contains('*'),
                Dataset.owner.contains(g.user.username) if g.user and g.user.username else True,
            )
        ).all()

        result = []
        username = g.user.username if g.user else 'default'
        for ds in datasets:
            expand = json.loads(ds.expand) if ds.expand else {}
            hdfs_meta = expand.get('hdfs', {})
            # 仅跳过未下载完成的 HDFS 数据集，非 HDFS 数据集正常展示
            if ds.source_type == 'hdfs' and hdfs_meta.get('download_status') != 'completed':
                continue

            ds_name = ds.name or f'dataset_{ds.id}'
            ds_version = ds.version or 'latest'
            local_dir = f'{ds_name}_{ds_version}'
            schema_cols = expand.get('schema', [])

            result.append({
                'id': ds.id,
                'name': ds.name,
                'label': ds.label or ds.name,
                'describe': ds.describe or '',
                'source_type': ds.source_type or '',
                'source': ds.source or '',
                'storage_size': ds.storage_size or '',
                'entries_num': ds.entries_num or '',
                'file_type': ds.file_type or '',
                'status': ds.status or '',
                'columns': schema_cols,
                'local_path': f'/mnt/{username}/datasets/{local_dir}/data.parquet',
                'load_code': (
                    f"import pyarrow.parquet as pq\n"
                    f"import pandas as pd\n"
                    f"pf = pq.ParquetFile('/mnt/{username}/datasets/{local_dir}/data.parquet')\n"
                    f"dfs = []\n"
                    f"read_rgs = 10\n"
                    f"for i in range(0, pf.metadata.num_row_groups, read_rgs):\n"
                    f"    end = min(i + read_rgs, pf.metadata.num_row_groups)\n"
                    f"    table = pf.read_row_groups(list(range(i, end)))\n"
                    f"    dfs.append(table.to_pandas())\n"
                    f"df = pd.concat(dfs, ignore_index=True)\n"
                    f"print(df.info())\n"
                    f"print(df.head())"
                ),
            })

        return jsonify({
            'status': 0,
            'message': '',
            'result': result,
        })

    # 增强 preview: 支持 HDFS 数据集读取 header.json + preview.json
    @expose_api(description="预览HDFS数据集", url="/preview_hdfs/<dataset_id>", methods=["GET"])
    def preview_hdfs(self, dataset_id):
        """
        读取本地 header.json + preview.json 返回数据集预览。
        """
        dataset = db.session.query(Dataset).filter_by(id=int(dataset_id)).first()
        if not dataset:
            return jsonify({'status': 1, 'message': '数据集不存在', 'result': None})

        expand = json.loads(dataset.expand) if dataset.expand else {}

        # 优先从本地文件读取
        if dataset.path and os.path.exists(dataset.path):
            local_dir = dataset.path
        else:
            datasetsavepath = conf.get('DATASET_SAVEPATH',
                                        os.path.join('/data/k8s/kubeflow', 'datasets'))
            ds_name = dataset.name or f'dataset_{dataset.id}'
            ds_version = dataset.version or 'latest'
            local_dir = os.path.join(datasetsavepath, f'{ds_name}_{ds_version}')

        header_path = os.path.join(local_dir, 'header.json')
        preview_path = os.path.join(local_dir, 'preview.json')

        columns = []
        rows = []
        entries_num = dataset.entries_num or ''
        storage_size = dataset.storage_size or ''

        if os.path.exists(header_path):
            try:
                with open(header_path, 'r', encoding='utf-8') as f:
                    columns = json.load(f)
            except Exception:
                pass

        if os.path.exists(preview_path):
            try:
                with open(preview_path, 'r', encoding='utf-8') as f:
                    rows = json.load(f)
            except Exception:
                pass

        return jsonify({
            'status': 0,
            'message': '',
            'result': {
                'columns': columns,
                'rows': rows,
                'entries_num': entries_num,
                'storage_size': storage_size,
                'dataset_name': dataset.name,
                'dataset_label': dataset.label or dataset.name,
                'local_path': local_dir,
            }
        })


class Dataset_ModelView_Api(Dataset_ModelView_base, MyappModelRestApi):
    datamodel = SQLAInterface(Dataset)
    route_base = '/dataset_modelview/api'


appbuilder.add_api(Dataset_ModelView_Api)

