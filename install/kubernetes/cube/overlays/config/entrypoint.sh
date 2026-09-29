#!/bin/bash

set -ex

echo "=== [entrypoint] START $(date) hostname=$(hostname) ==="

echo "=== [entrypoint] symlinks ==="
rm -f /home/myapp/myapp/static/mnt
mkdir -p /data/k8s/kubeflow/pipeline/workspace
ln -s /data/k8s/kubeflow/pipeline/workspace /home/myapp/myapp/static/mnt

rm -f /home/myapp/myapp/static/dataset
mkdir -p /data/k8s/kubeflow/dataset
ln -s /data/k8s/kubeflow/dataset /home/myapp/myapp/static/

rm -f /home/myapp/myapp/static/aihub
ln -s /cube-studio/aihub /home/myapp/myapp/static/

rm -f /home/myapp/myapp/static/global
ln -s /data/k8s/kubeflow/global /home/myapp/myapp/static/

echo "=== [entrypoint] create_db ==="
export FLASK_APP=myapp:app
python myapp/create_db.py

echo "=== [entrypoint] db upgrade ==="
python -c "
import redis, os, subprocess, time
r = redis.Redis(host=os.environ['REDIS_HOST'], port=int(os.environ.get('REDIS_PORT','6379')), password=os.environ.get('REDIS_PASSWORD',''))
print(f'[entrypoint] redis connected, trying lock...')
for i in range(30):
    if r.set('cube:db-upgrade-lock', os.environ.get('HOSTNAME','unknown'), nx=True, ex=120):
        print(f'[entrypoint] lock acquired at attempt {i}')
        try:
            subprocess.run(['myapp', 'db', 'upgrade'], check=True)
            print('[entrypoint] db upgrade done (this pod held the lock)')
        except Exception as e:
            print(f'[entrypoint] db upgrade failed: {e}')
        finally:
            r.delete('cube:db-upgrade-lock')
        break
    print(f'[entrypoint] lock held by another pod, retry {i}/30')
    time.sleep(2)
else:
    print('[entrypoint] db upgrade lock not acquired within 60s, continuing')
"

echo "=== [entrypoint] fab create-admin ==="
myapp fab create-admin --username admin --firstname admin --lastname admin --email admin@tencent.com --password admin || true

echo "=== [entrypoint] init ==="
myapp init || true

echo "=== [entrypoint] 幂等补缺表(FAB5 新增表如 user_attribute/service_pipeline; 行内旧库无则补齐) ==="
python - <<'PYEOF' || true
from myapp import app, db
from flask_appbuilder import Model
import myapp.models.user_attributes  # 注册 user_attribute(FAB Model 表), 不进 db.metadata
with app.app_context():
    db.create_all()
    Model.metadata.create_all(db.engine)
print("ensure tables done")
PYEOF

if [ "$STAGE" = "build" ]; then
  echo "=== [entrypoint] STAGE=build ==="
  cd /home/myapp/myapp/frontend && npm install && npm run build
  cd /home/myapp/myapp/vision && npm install && npm run build
  cd /home/myapp/myapp/visionPlus && yarn && npm run build
elif [ "$STAGE" = "dev" ]; then
  echo "=== [entrypoint] STAGE=dev ==="
  export FLASK_APP=myapp:app
  python myapp/check_tables.py
  python myapp/run.py

elif [ "$STAGE" = "prod" ]; then
  echo "=== [entrypoint] STAGE=prod, starting gunicorn ==="
  export FLASK_APP=myapp:app
  python myapp/check_tables.py
  gunicorn --bind  0.0.0.0:80 --workers 20 --worker-class=gevent --timeout 300 --limit-request-line 0 --limit-request-field_size 0 --log-level=info --access-logfile - --error-logfile - --capture-output myapp:app
else
    myapp --help
fi