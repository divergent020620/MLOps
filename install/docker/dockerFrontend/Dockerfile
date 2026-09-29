# docker build -t ccr.ccs.tencentyun.com/cube-studio/kubeflow-dashboard-frontend:2026.03.01 -f install/docker/dockerFrontend/Dockerfile .
# docker buildx build --platform linux/amd64,linux/arm64 -t ccr.ccs.tencentyun.com/cube-studio/kubeflow-dashboard-frontend:2026.03.01 -f install/docker/dockerFrontend/Dockerfile . --push

FROM ccr.ccs.tencentyun.com/cube-studio/kubeflow-dashboard-frontend:2026.03.01

# 替换更新后的前端构建产物（包含 HDFS 浏览器 + 配置页面）
COPY ./myapp/static/appbuilder/frontend /data/web/frontend
RUN rm -rf /data/web/frontend/manifest.json /data/web/frontend/robots.txt

# 拷贝 FAB 静态文件（css/js/datepicker/select2 等），供 nginx 直接提供
COPY ./myapp/static /data/web/static
