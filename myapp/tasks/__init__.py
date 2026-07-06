# Celery task autodiscovery
# Celery worker 启动时 imports=('myapp.tasks',) 加载此模块，确保所有 @celery_app.task 被注册
from myapp.tasks import async_task   # noqa: F401
from myapp.tasks import schedules    # noqa: F401
from myapp.tasks import hdfs_tasks   # noqa: F401
