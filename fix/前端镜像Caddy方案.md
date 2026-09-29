# 前端镜像 Caddy 方案(替代 nginx,行外+行内完整流程)

> 背景:麒麟源 nginx(1.21.5)老版本 + 全模块含 perl 超危(9.8)+ openssl 必降级(实测),行内源码不可控。
> 结论:用 **Caddy 官方预编译二进制**(Go 静态,零编译零 rpm 零降级),替换 nginx。
> 语义与 `install/docker/dockerFrontend/nginx.80.conf` 完全等价(静态 /frontend/ + /static/appbuilder/,其余反代含 WebSocket)。

## ✅ 实机进度(2026-09-07)

| 环节 | 状态 |
|---|---|
| 行外:caddy v2.9.1 下载/解压 | ✅ 已由 Claude 在本地 Windows 完成(`fix/caddy-build/`) |
| 行外:Caddyfile 编写 | ✅ 已写(`fix/caddy-build/Caddyfile`,与 nginx.80.conf 等价) |
| 行外:打包 `fe-caddy-kylin.tgz` | ✅ **产物:`fix/fe-caddy-kylin.tgz`(14MB,内含 caddy + Caddyfile)** |
| 行外:version / fmt 验证 | ⏳ 跳过(Windows 不能跑 Linux 二进制)→ **移到行内验证** |
| 行内:装配 → 送评 | ⏳ 待执行(见下方) |
| 前端产物 /data/web | ⏳ 待合流(未打包,后续 docker cp) |

---

## 一、行外(已完成,产物就绪)

原命令归档(无需重跑,仅当需改 Caddyfile 时参考):

```bash
mkdir -p /tmp/caddy-build && cd /tmp/caddy-build
curl -sL https://github.com/caddyserver/caddy/releases/download/v2.9.1/caddy_2.9.1_linux_amd64.tar.gz -o caddy.tar.gz
tar xzf caddy.tar.gz && ./caddy version
# Caddyfile 见 fix/caddy-build/Caddyfile
tar czf fe-caddy-kylin.tgz caddy Caddyfile
```

**改配置后重打包**:编辑 `fix/caddy-build/Caddyfile` → `cd fix/caddy-build && tar czf ../fe-caddy-kylin.tgz caddy Caddyfile`

## 二、行内(待执行)

### 1. 起容器

```bash
docker run -d --name fe-caddy01 <行内基座镜像:tag> bash -c "sleep 3600"
```

### 2. 拷入并部署(此版先不含前端产物)

```bash
docker cp fe-caddy-kylin.tgz fe-caddy01:/tmp/
docker exec -i fe-caddy01 bash -c '
set -e
mkdir -p /tmp/fe && tar xzf /tmp/fe-caddy-kylin.tgz -C /tmp/fe
cp /tmp/fe/caddy /usr/local/bin/caddy && chmod +x /usr/local/bin/caddy
mkdir -p /etc/caddy /data/web /data/log/caddy
cp /tmp/fe/Caddyfile /etc/caddy/Caddyfile
ls -l /usr/local/bin/caddy
'
# 前端产物(后续合流): docker cp <frontend-dist>/. fe-caddy01:/data/web/
```

### 3. 验证(version/fmt/试启动,在行内做)

```bash
docker exec -i fe-caddy01 bash -c '/usr/local/bin/caddy version'
docker exec -i fe-caddy01 bash -c '/usr/local/bin/caddy fmt /etc/caddy/Caddyfile --diff && echo "语法 OK"'
docker exec -i fe-caddy01 bash -c 'timeout 6 /usr/local/bin/caddy run --config /etc/caddy/Caddyfile 2>&1 | grep -i "server running" || true'
```
预期:`v2.9.1` + `语法 OK` + server running(超时退出正常)。

### 4. commit + save(新 tag)

```bash
docker stop fe-caddy01
docker commit fe-caddy01 <registry>/kubeflow-dashboard-frontend:fe-caddy-v1
docker save -o fe-caddy-v1.tar <registry>/kubeflow-dashboard-frontend:fe-caddy-v1
docker rm fe-caddy01
```

### 5. 启动方式变更(部署/entrypoint 层级,后续同步)

```bash
# 原: nginx -g "daemon off;"
# 改: /usr/local/bin/caddy run --config /etc/caddy/Caddyfile
```

---

## Caddyfile(当前内容,与 nginx.80.conf 等价)

```
:80 {
	# / -> /frontend/ 永久重定向
	redir / /frontend/ permanent

	# 静态资源(等价 nginx: root /data/web + try_files 回退)
	handle /frontend/* /static/appbuilder/* {
		root * /data/web
		file_server
		try_files {path} {path}/ /frontend/index.html
	}

	# html 不缓存(等价 add_header Cache-Control no-cache)
	@html path_regexp \.html$
	header @html Cache-Control "no-cache, no-store"
	header @html Pragma "no-cache"

	# 兜底:反代到后端(WebSocket 自动透传,无需配置)
	handle {
		reverse_proxy http://kubeflow-dashboard.infra {
			transport http {
				dial_timeout 30s
				read_timeout 3600s
				write_timeout 3600s
			}
			header_up Host {http.request.host}
			header_up X-Real-IP {remote_ip}
		}
	}

	log {
		output file /data/log/caddy/access.log
	}
}
```

---

## 评估预期与观察

| 项 | 预期 |
|---|---|
| caddy 二进制 | 平台按文件特征识别 v2.9.1(2024/25 版本,CVE 面小,大概率零报) |
| 系统层 | 与 kylin12.xlsx 同款:仅 py3.7 的 pip 20.2.2 / setuptools 44.1.1(已知,暂不处理) |
| perl / libtiff / libXpm / openssl 降级 | **全部不存在**(零 rpm 新增,零降级) |

送评达标即前端定稿;nginx 相关(kylin-nginx.xlsx 全部问题)随本方案废止。

## FAQ/备选

- **caddy 二进制官网拉不到?** → 已就绪(`fix/caddy-build/caddy`),用行内网闸传文件走审核流程即可。
- **Caddy 需要 root 绑 80?** 基座容器 root 运行,`caddy run` 即可(与 nginx 同级,无 CAP 问题)。
- **反代目标名** `kubeflow-dashboard.infra`:按行内实际 Service 名调整(改 Caddyfile 一行 → 重打包,或行内改 /etc/caddy/Caddyfile)。
- **要上 SSL?** Caddy 自动证书需要外网 ACME,行内/内网环境用 http + 行内网关(ingress/istio)补 TLS。
