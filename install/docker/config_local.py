"""
Local Windows development config for Cube Studio.
Overrides install/docker/config.py settings.
Usage: set MYAPP_CONFIG=install.docker.config_local
"""
import os
from install.docker.config import *

# ============================================
# 本地数据库和 Redis 配置 (Docker 容器)
# ============================================
REDIS_HOST = '127.0.0.1'
REDIS_PORT = '6379'
REDIS_PASSWORD = 'admin'

SQLALCHEMY_DATABASE_URI = 'mysql+pymysql://root:admin@127.0.0.1:13306/kubeflow?charset=utf8mb4'

# Celery broker 和 result backend
CELERY_CONFIG = {
    'broker_url': 'redis://:admin@127.0.0.1:6379/0',
    'result_backend': 'redis://:admin@127.0.0.1:6379/0',
    'task_serializer': 'json',
    'result_serializer': 'json',
    'accept_content': ['json'],
    'timezone': 'Asia/Shanghai',
    'enable_utc': True,
}

# SocketIO 消息队列
SOCKETIO_MESSAGE_QUEUE = 'redis://:admin@127.0.0.1:6379/2'

# Cache
CACHE_CONFIG = {
    'CACHE_TYPE': 'RedisCache',
    'CACHE_REDIS_HOST': '127.0.0.1',
    'CACHE_REDIS_PORT': 6379,
    'CACHE_REDIS_URL': 'redis://:admin@127.0.0.1:6379/1',
}

# ============================================
# 本地开发设置
# ============================================
DEBUG = True
FLASK_USE_RELOAD = True
SHOW_STACKTRACE = True

MYAPP_WEBSERVER_ADDRESS = '127.0.0.1'
MYAPP_WEBSERVER_PORT = 80

# 没有 K8s 集群，跳过相关操作
HUBSECRET = []
HUBSECRET_NAMESPACE = []

# 镜像仓库配置 (本地开发保持默认即可)
REPOSITORY_ORG = 'ccr.ccs.tencentyun.com/cube-studio/'
PUSH_REPOSITORY_ORG = 'ccr.ccs.tencentyun.com/cube-studio/'
