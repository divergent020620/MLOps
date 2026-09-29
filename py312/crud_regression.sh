#!/bin/bash
# FAB 5.2.2 CRUD 回归: JWT 登录 -> 全量视图 GET list/_info -> announcement 增删改查闭环
# 前提: cube312:local 已跑 gunicorn (docker run -d --name cube312-app -p 8090:80 ...)
set -u
BASE=http://localhost:8090
OUT_LOG_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG="$OUT_LOG_DIR/crud_regression.log"
: > "$LOG"

echo "=== 登录 ===" | tee -a "$LOG"
TOKEN=$(curl -s -X POST $BASE/api/v1/security/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin","provider":"db","refresh":true}' \
  | python -c "import sys,json;print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null)
if [ -z "$TOKEN" ]; then echo "断言失败: 登录未获 token" | tee -a "$LOG"; exit 1; fi
echo "OK token=${TOKEN:0:20}..." | tee -a "$LOG"

VIEWS="aitalk_modelview announcement_modelview chat_modelview dataset_modelview dimension_table_modelview docker_modelview etl_pipeline_modelview etl_task_modelview images_modelview inferenceservice_modelview job_template_fab_modelview job_template_modelview log_modelview metadata_metric_modelview metadata_table_modelview model_market nni_modelview notebook_modelview pipeline_modelview platform_config_modelview project_modelview project_user_modelview repository_modelview runhistory_modelview service_modelview task_modelview total_resource training_model_modelview workflow_modelview"

echo "=== [1] 全量 GET list (page_size=5) ===" | tee -a "$LOG"
for v in $VIEWS; do
  code=$(curl -s -o /tmp/resp.json -w "%{http_code}" -H "Authorization: Bearer $TOKEN" "$BASE/$v/api/?page_size=5")
  detail=$(python -c "
import json
d=json.load(open('/tmp/resp.json'))
r=d.get('result') or d.get('result')
if isinstance(r,list):
    total=d.get('count') or len(r); print('count=%s'%total)
else:
    print(str(r)[:70])
" 2>/dev/null || echo "?")
  printf "%-42s HTTP %s  %s\n" "$v" "$code" "$detail" | tee -a "$LOG"
done

echo "=== [2] 全量 GET _info ===" | tee -a "$LOG"
for v in $VIEWS; do
  code=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $TOKEN" "$BASE/$v/api/_info")
  printf "%-42s HTTP %s\n" "$v" "$code" | tee -a "$LOG"
done

echo "=== [3] announcement 增删改查闭环 ===" | tee -a "$LOG"
# Add
ADD=$(curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"title":"py312-regress-temp","content":"regression test payload"}' "$BASE/announcement_modelview/api/")
NEW_ID=$(echo "$ADD" | python -c "import sys,json;d=json.load(sys.stdin);r=d.get('result',{});print(r.get('id','') if isinstance(r,dict) else '')" 2>/dev/null)
echo "create -> id=$NEW_ID  raw=${ADD:0:80}" | tee -a "$LOG"
if [ -n "$NEW_ID" ]; then
  # Show
  code=$(curl -s -o /tmp/resp.json -w "%{http_code}" -H "Authorization: Bearer $TOKEN" "$BASE/announcement_modelview/api/$NEW_ID")
  echo "show #$NEW_ID  HTTP $code  $(head -c 90 /tmp/resp.json)" | tee -a "$LOG"
  # Update
  code=$(curl -s -o /tmp/resp.json -w "%{http_code}" -X PUT -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
    -d '{"title":"py312-regress-updated"}' "$BASE/announcement_modelview/api/$NEW_ID")
  echo "update HTTP $code  $(head -c 90 /tmp/resp.json)" | tee -a "$LOG"
  # Delete
  code=$(curl -s -o /tmp/resp.json -w "%{http_code}" -X DELETE -H "Authorization: Bearer $TOKEN" "$BASE/announcement_modelview/api/$NEW_ID")
  echo "delete HTTP $code  $(head -c 90 /tmp/resp.json)" | tee -a "$LOG"
  # 最终验证 GET 应为 404
  code=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $TOKEN" "$BASE/announcement_modelview/api/$NEW_ID")
  echo "verify-deleted HTTP $code (期望 404)" | tee -a "$LOG"
else
  echo "断言失败: 创建未返回 id, 原始响应: $ADD" | tee -a "$LOG"
fi
echo "=== 回归完成 ===" | tee -a "$LOG"
