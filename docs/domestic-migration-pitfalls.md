# Cube Studio 信创国产化迁移 — 踩坑记录

> 日期：2026-07-30
> 基座：Ubuntu 22.04/20.04 → Kylin v10 SP3

---

## 1. Kylin 系统 Python 版本

**现象**：以为 Kylin SP3 自带 Python 3.9，实际 `python3 --version` 输出 3.7.10。

**结论**：Kylin SP3 系统 Python 是 3.7，项目需要 3.9，必须用 Miniconda 单独安装。

```dockerfile
# 正确做法
COPY packages/Miniconda3-*-Linux-x86_64.sh /tmp/
RUN bash /tmp/Miniconda3-*-Linux-x86_64.sh -b
RUN conda create -y -n python39 python=3.9
ENV PATH=/root/miniconda3/envs/python39/bin:${PATH}
```

---

## 2. start.sh shebang 错误

**现象**：前端 Pod CrashLoopBackOff，日志 `exec /start.sh: exec format error`。

**根因**：`install/docker/dockerFrontend/start.sh` 第一行是 `# /bin/bash`，缺少感叹号 `!`，不是合法 shebang。内核把它当二进制执行，报格式错误。

**修复**：`# /bin/bash` → `#!/bin/bash`。

**教训**：任何 COPY 到镜像里的脚本都要确认 shebang 正确。

---

## 3. COPY 覆盖文件后丢失执行权限

**现象**：修完 shebang 重新 COPY start.sh 后报 `permission denied`。

**根因**：Docker `COPY` 会覆盖目标文件，但不会保留源文件的执行权限（取决于 Docker 版本和源文件权限）。`Dockerfile-base.kylin` 里有 `RUN chmod +x /start.sh`，但临时 Dockerfile 只 COPY 忘了 chmod。

**修复**：COPY 后必须显式 `RUN chmod +x /start.sh`。

---

## 4. ConfigMap 挂载的文件是只读的

**现象**：前端 Pod 日志 `sed: 无法重命名 /etc/nginx/conf.d/sedXXXXX：设备或资源忙`。

**根因**：K8s ConfigMap `nginx-configmap` 把 `default.conf` 挂载到 `/etc/nginx/conf.d/default.conf`，以 subPath 方式挂载的文件是只读的。start.sh 里的 `sed -i` 尝试原地修改只读文件。

**修复**：
```bash
# 旧
sed -i 's/APP_ROOT/${APP_ROOT}/' /etc/nginx/conf.d/default.conf
# 新
sed -i 's/APP_ROOT/${APP_ROOT}/' /etc/nginx/conf.d/default.conf 2>/dev/null || true
```

**教训**：有 ConfigMap 挂载的配置文件不要做原地修改。

---

## 5. 日志目录未创建

**现象**：sed 过了后 nginx 又报 `open() "/data/log/nginx/access.log" failed (2: No such file or directory)`。

**根因**：老 Ubuntu 前端基础镜像预建了 `/data/log/nginx/`，Kylin 从零 `yum install nginx` 没建这个目录。

**修复**：start.sh 开头加 `mkdir -p /data/log/nginx`。

---

## 6. Miniconda OpenSSL 库版本冲突（★ 最坑）

**现象**：schedule/worker Pod 报 `ImportError: /root/miniconda3/lib/libcrypto.so.3: version OPENSSL_3.3.0 not found`，但 `python -c "import ssl"` 在本地 Docker 能过。

**排查过程**：
1. `docker run` 测 `import ssl` → OK
2. `docker run` 测 `from celery.bin.celery import main` → OK
3. K8s Pod `import celery` → OK
4. K8s Pod `from celery.bin.celery import main` → 崩
5. 用 `LD_DEBUG=files` 追踪找到元凶

**根因**：Miniconda 有两层 OpenSSL 库：

| 路径 | libcrypto.so.3 | OPENSSL_3.3.0 |
|------|---------------|---------------|
| `/root/miniconda3/lib/` (base) | 有 | **无** |
| `/root/miniconda3/envs/python39/lib/` (env) | 有 | **有** |

`celery.bin.celery` 的 import 链路触发了 `libgssapi_krb5.so.2`（Kerberos）加载，它依赖的 `libcrypto.so.3` 优先从 base 目录加载（旧版，没有 OPENSSL_3.3.0）。当 `_ssl.so` 需要 OPENSSL_3.3.0 时，libcrypto 已经被旧版锁死在内存里了。

`import celery` 不会触发 `libgssapi_krb5`，所以能过；`from celery.bin.celery import main` 会触发，所以崩。

**修复**：
```dockerfile
# Dockerfile.tmp.backend-base
ENV LD_LIBRARY_PATH=/root/miniconda3/envs/python39/lib:${LD_LIBRARY_PATH}
RUN rm -f /root/miniconda3/lib/libssl.so* /root/miniconda3/lib/libcrypto.so*
```

1. `LD_LIBRARY_PATH` 让 env lib 优先
2. 删除 base 里的冲突库（krb5 失去 base 的旧 libcrypto 后会自动 fallback 到 env 的新版）

**教训**：Miniconda base 和 env 两套库版本可能不一致。始终确保 env lib 在 `LD_LIBRARY_PATH` 最前面，或清理 base 冲突库。

---

## 7. setuptools 82.x 移除了 pkg_resources

**现象**：schedule Pod 报 `ModuleNotFoundError: No module named 'pkg_resources'`。

**根因**：`Dockerfile-base.kylin` 里 `pip install --upgrade setuptools` 升到 82.0.1，该版本彻底移除了 `pkg_resources` 模块。Celery 5.2.2 启动依赖 `pkg_resources`。

**修复**：降级到仍包含 `pkg_resources` 的版本：
```dockerfile
RUN pip install --no-cache-dir 'setuptools==68.0.0'
```

---

## 8. ConfigMap 覆盖了镜像里的 entrypoint.sh

**现象**：反复修改 `install/docker/entrypoint.sh`、重建镜像、push、重启，但 Pod 日志完全不变。

**根因**：K8s 部署用 ConfigMap 把 overlay 的 entrypoint.sh 挂载到 `/entrypoint.sh`，覆盖了镜像里的同路径文件。

```yaml
# deploy-backend.yaml 关键行
volumes:
  - configMap:
      name: kubeflow-dashboard-config
      items:
        - key: entrypoint.sh        # ← ConfigMap 里的键
          path: entrypoint.sh       # ← 挂载为这个文件名
containers:
  - volumeMounts:
      - mountPath: /entrypoint.sh  # ← 挂载到容器这个位置
        subPath: entrypoint.sh     # ← 精确覆盖这个文件
```

**真实生效的文件**：`install/kubernetes/cube/overlays/config/entrypoint.sh`
**白改了半天的文件**：`install/docker/entrypoint.sh`（docker-compose 环境用的）

**修复**：改 overlay 下的 entrypoint.sh，更新 ConfigMap：
```bash
kubectl create configmap kubeflow-dashboard-config -n infra \
  --from-file=entrypoint.sh=install/kubernetes/cube/overlays/config/entrypoint.sh \
  ... --dry-run=client -o yaml | kubectl replace -f -
```

---

## 9. 两个 Pod 并发 db upgrade 抢 MySQL 锁

**现象**：replicas=2 时两个 Pod 都卡在 `myapp db upgrade`，崩溃重启。

**根因**：alembic 迁移时获取 MySQL 元数据锁，两个 Pod 同时执行，后到的等待锁，超时后被 K8s 杀。

**修复**：Redis 分布式锁，确保同一时刻只有一个 Pod 执行：
```python
r = redis.Redis(host=REDIS_HOST, ...)
for i in range(30):
    if r.set('cube:db-upgrade-lock', hostname, nx=True, ex=120):
        try:
            subprocess.run(['myapp', 'db', 'upgrade'])
        finally:
            r.delete('cube:db-upgrade-lock')
        break
    time.sleep(2)
```

---

## 10. Docker 构建层缓存

**现象**：改了文件重建镜像，但 `docker build` 秒过，镜像内容不变。

**根因**：Docker 的构建缓存基于 Dockerfile 指令和上下文文件 checksum。如果 COPY 的文件 checksum 没变（或 Docker 认为没变），直接复用旧层。

**修复**：`docker build --no-cache ...` 强制重建。

---

## 11. Harbor 同 tag push 后节点不重新拉

**现象**：本地镜像验证 OK，push 同 tag 后 K8s 节点拉到的还是旧的。

**根因**：即使 `imagePullPolicy: Always`，当 tag 没变且 digest 层没变时，containerd 可能复用本地缓存。

**修复**：每次改动用新 tag（kylin-20260730-v1 → v2 → v3 ...），然后 `kubectl set image`。

---

## 12. 麒麟 yum 包名与 Ubuntu apt 包名差异

| Ubuntu 包 | Kylin 包 | 备注 |
|-----------|----------|------|
| `procps` | `procps-ng` | 进程管理 |
| `dnsutils` | `bind-utils` | nslookup/dig |
| `mysql-client` | `mariadb` | 数据库客户端 |
| `libsasl2-dev` | `cyrus-sasl-devel` | SASL 编译依赖 |
| `libpq-dev` | `libpq-devel` | PostgreSQL 编译依赖 |
| `fonts-wqy-microhei` | `wqy-microhei-fonts` | 中文字体 |
| `supervisor` (apt) | `supervisor` (pip) | yum 源无此包 |
| `krb5-user libkrb5-dev` | `krb5-workstation krb5-libs krb5-devel` | Kerberos |
| `build-essential` | `gcc gcc-c++ make` | 编译工具链 |

---

## 总结

| 坑 | 根因 | 修复难度 | 预防 |
|----|------|----------|------|
| Miniconda OpenSSL 冲突 | base 和 env 两套库版本不一致 | ★★★★★ | 清理 base lib |
| ConfigMap 覆盖文件 | 不知道挂载会覆盖镜像文件 | ★★★ | 先查 K8s YAML 的 volumeMounts |
| Docker 层缓存 | `docker build` 默认缓存 COPY | ★★ | `--no-cache` |
| Harbor tag 缓存 | 同 tag push 节点不重拉 | ★★ | 每次换 tag |
| setuptools 移除 pkg_resources | pip 不锁版本导致升到最新 | ★★ | 锁版本 |
| start.sh shebang | 手误少写 `!` | ★ | 校验所有 shell 脚本 |
| 并发 db upgrade | 多副本同时迁移 | ★★★ | Redis 锁 |
| yum 包名差异 | 发行版不同 | ★★ | 逐个验证 |
| ConfigMap 只读挂载 | sed -i 只读文件 | ★ | `|| true` |
| 日志目录缺失 | 从零构建没预建目录 | ★ | mkdir -p |
