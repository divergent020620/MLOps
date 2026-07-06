# docker build -t ccr.ccs.tencentyun.com/cube-studio/kubeflow-dashboard-frontend:2026.03.01 -f install/docker/dockerFrontend/Dockerfile .
# docker buildx build --platform linux/amd64,linux/arm64 -t ccr.ccs.tencentyun.com/cube-studio/kubeflow-dashboard-frontend:2026.03.01 -f install/docker/dockerFrontend/Dockerfile . --push

FROM ccr.ccs.tencentyun.com/cube-studio/kubeflow-dashboard-frontend:2026.03.01

# 仅替换更新后的前端构建产物（包含 HDFS 浏览器 + 配置页面）
COPY ./myapp/static/appbuilder/frontend /data/web/frontend
RUN rm -rf /data/web/frontend/manifest.json /data/web/frontend/robots.txt
