# 前端 nginx 自编译方案（替代 `yum install nginx`）

> 目标：把 `kylin-nginx.xlsx` 里由 nginx 引入的 **4 个组件**（perl、perl-libs、libXpm、libtiff）全部清零，
> 同时**不动一行 nginx 配置**——这是本方案相对 Caddy 方案的核心优势。

## 一、为什么这样能清掉

实测证据链（2026-09-20，在运行中的 `kubeflow-dashboard-frontend` 容器内查证）：

```
nginx 1.21.5
 └─ nginx-all-modules（元包，nginx 硬依赖它，无法只装主包）
     ├─ nginx-mod-http-perl
     │    └─ requires: libperl.so.5.28()(64bit), perl(:MODULE_COMPAT_5.28.3)
     │       → perl + perl-libs              【超危 ×2】
     │
     └─ nginx-mod-http-image-filter
          └─ requires: gd, libgd.so.3()(64bit)
             └─ gd-2.3.0-4.ky10
                  ├─ requires libXpm.so.4()(64bit)   → libXpm  【高危】
                  └─ requires libtiff.so.5()(64bit)  → libtiff 【高危】
```

对照两份扫描报告做差集：

| | `kylin.tar`（基座，kylin12.xlsx） | `fe-test-v1.tar`（前端，kylin-nginx.xlsx） | 差值 |
|---|---|---|---|
| 超危组件 | 0 | 2（perl, perl-libs） | **+2** |
| 高危组件 | 2（setuptools, pip） | 4（+libXpm, libtiff） | **+2** |

**基座本身干净，这 4 个全是 `yum install nginx` 带进来的。**

而这两个模块在 nginx 源码里**默认都不编译**：

| 模块 | 默认 | 引入的组件 |
|---|---|---|
| `--with-http_perl_module` | 关闭 | perl, perl-libs |
| `--with-http_image_filter_module` | 关闭（且需 libgd） | libXpm, libtiff |

所以源码编译一个**默认模块集**的 nginx，这 4 个组件自然不出现。

## 二、两个必须守住的前提

### 1. glibc 版本（最容易踩的坑）

目标运行环境是麒麟 V10 SP3 = **glibc 2.28**。glibc 只保证**向后兼容**——新环境编译的产物在旧环境跑不起来。

| 构建基底 | glibc | 可用性 |
|---|---|---|
| `rockylinux:8` / `almalinux:8` | 2.28 | ✅ 默认，正好匹配 |
| `centos:7` | 2.17 | ✅ 更保守 |
| `ubuntu:22.04` | 2.35 | ❌ 产物在麒麟上跑不起来 |
| `debian:12` | 2.36 | ❌ 同上 |

`Dockerfile.nginx-build` 里硬编码了 `rockylinux:8`，并在构建期用
`objdump -T ... | grep GLIBC_` 打印最高符号版本。**看到 > 2.28 就不要往下走。**

### 2. 运行时依赖（基座必须提供）

自编译产物是动态链接的（**有意为之**：运行时用麒麟自己的 OpenSSL，信创角度比自带 crypto 更稳）：

```
libssl.so.1.1 / libcrypto.so.1.1   ← OpenSSL 1.1.1 系列，注意不是 3.x
libpcre2-8.so.0
libz.so.1
```

`cube-studio/kylin:v10-sp3-2403` 一定有（原 nginx RPM 就依赖它们）。
**如果换成行内 py3.12 基座，必须先确认**——直接跑 `fix/行内基座盘点命令.md` 的第 7 节即可。

## 三、行外：编译

```bash
# 1. 确认当前最新稳定版（别编 1.21.x，扫描器会做二进制指纹识别）
#    https://nginx.org/en/download.html  → "Stable version"
# 2. 编译 + 打包（本机需有 docker）
cd <repo root>
bash fix/nginx-build/build_nginx.sh 1.28.0 <可选:nginx.org公布的sha256>
```

脚本做四件事：

1. 在 `rockylinux:8` 容器里编译 nginx（只编业务用到的模块）
2. 抽出 `nginx` 二进制 + `mime.types`，并**原样复制**仓库现有的
   `install/docker/dockerFrontend/{nginx.conf,nginx.80.conf,start.sh}`
3. 在 Linux 容器里做三项核验：`ldd` 无 perl/gd/libtiff/libXpm、最高 glibc 符号 ≤ 2.28、
   `nginx -t` 配置语法通过
4. 打包成 `fix/fe-nginx-kylin.tgz`（含 `SHA256SUMS.txt`）

产物落到 `fix/nginx-build/out/`：

```
nginx          自编译二进制
mime.types     nginx.conf 里 `include /etc/nginx/mime.types` 需要
nginx.conf     仓库现有主配置（未改一行）
nginx.80.conf  仓库现有站点配置（未改一行）
start.sh       仓库现有启动脚本（未改一行）
SHA256SUMS.txt
```

## 四、行内：装配

### 路线 A：docker commit（和 Caddy 方案同款，最省事）

```bash
mkdir -p /tmp/fe-nginx && tar xzf fe-nginx-kylin.tgz -C /tmp/fe-nginx
docker run -d --name fe-nginx01 <基座镜像:tag> bash -c "sleep 3600"

docker exec -i fe-nginx01 bash -c '
set -e
groupadd -r nginx 2>/dev/null || true
useradd -r -g nginx -s /sbin/nologin nginx 2>/dev/null || true
mkdir -p /usr/local/nginx/sbin /etc/nginx/conf.d /data/log/nginx /var/log/nginx /data/web
# 二进制与配置
cp /tmp/fe-nginx/nginx        /usr/local/nginx/sbin/nginx
cp /tmp/fe-nginx/mime.types   /etc/nginx/mime.types
cp /tmp/fe-nginx/nginx.conf   /etc/nginx/nginx.conf
cp /tmp/fe-nginx/nginx.80.conf /etc/nginx/conf.d/default.conf
cp /tmp/fe-nginx/start.sh     /start.sh
chmod +x /usr/local/nginx/sbin/nginx /start.sh
ln -sf /usr/local/nginx/sbin/nginx /usr/sbin/nginx
/usr/local/nginx/sbin/nginx -v
/usr/local/nginx/sbin/nginx -t
'

# 前端产物（若尚未合流）
docker cp <frontend-dist>/. fe-nginx01:/data/web/frontend

docker stop fe-nginx01
docker commit fe-nginx01 <registry>/kubeflow-dashboard-frontend:kylin-nginx-v1
docker save -o fe-nginx-v1.tar <registry>/kubeflow-dashboard-frontend:kylin-nginx-v1
```

### 路线 B：Dockerfile 装配（可复现，推荐长期用）

```bash
# 把 out/ 和 fe-nginx-kylin.tgz 传进行内后
docker build --network=none \
  --build-arg BASE_IMAGE=192.168.11.12/cube-studio/kylin:v10-sp3-2403 \
  -t 192.168.11.12/cube-studio/kubeflow-dashboard-frontend:kylin-nginx-v1 \
  -f fix/nginx-build/Dockerfile.nginx-kylin .
```

`Dockerfile.nginx-kylin` 里带了三道构建期断言（缺运行时库 / 链接被禁组件 / 配置语法错误
都会让构建失败），和 py312 Dockerfile 的冒烟断言是同一个思路。

## 五、验收清单

- [ ] 构建日志里 `ldd` 输出**不含** perl / libgd / libtiff / libXpm
- [ ] 构建日志里最高 glibc 符号版本 **≤ 2.28**
- [ ] `nginx -v` 版本号是预期的最新稳定版（不是 1.21.x）
- [ ] `nginx -t` 通过
- [ ] 容器起来后 `rpm -qa | grep -E "^perl|libXpm|libtiff"` **无输出**
      （前提是没保留原 RPM nginx；如果基座自带，需另处理）
- [ ] 送评后对比 `kylin-nginx.xlsx`：超危 2→0、高危 4→2

> 最后剩的 2 个高危（setuptools 44.1.1、pip 20.2.2）**和 nginx 无关**，是基座
> `/usr/local/lib/python3.7/site-packages/` 自带的，前端镜像根本不需要 Python。
> 要清零就删目录，和 `后端v2.xlsx` 里那批是同一个问题。

## 六、和 Caddy 方案的关系

两条路都能清掉同样 4 个组件，**不冲突，互为备选**：

| | 本方案（自编译 nginx） | Caddy（`fix/前端镜像Caddy方案.md`） |
|---|---|---|
| 清掉 4 个组件 | ✅ | ✅ |
| 配置迁移风险 | **零**（nginx.conf / nginx.80.conf 原样用） | 需重写；已发现 `Origin` 头未等价翻译 |
| 构建工作量 | 中（本目录已备好脚本） | 已完成 |
| 信创角度 | 动态链接麒麟 OpenSSL | 自带 Go crypto |
| 扫描识别 | 按指纹认 nginx，**必须编最新版** | 认 caddy v2.9.1 |

**建议：本方案优先**（配置零改动，风险最低），Caddy 作为已就绪的兜底。

## 七、常见问题

**Q: 编最新版会不会和现有配置不兼容？**
A: `nginx.conf` / `nginx.80.conf` 用的都是十几年的稳定指令（`proxy_pass`、`try_files`、
`limit_conn_zone`、`gzip`），1.21 → 最新版无破坏性变更。脚本里的 `nginx -t` 已覆盖语法层。

**Q: 为什么不直接编成完全静态（`-static`）？**
A: 一是要静态链接 OpenSSL/PCRE2/zlib 很折腾；二是**动态链接麒麟 OpenSSL 在信创评审上更站得住**——
用的是行内认可的加密库，不是自带的。除非基座确实缺那些 .so，否则不必静态。

**Q: 编译出来的 nginx 会被扫描器认出来吗？**
A: 会。扫描器做**二进制指纹识别**（Caddy 文档里"平台按文件特征识别 v2.9.1"就是证据），
所以它仍会被识别为 nginx，并按 nginx 的版本报 CVE。**这正是不编 1.21.x 的原因**——
编最新稳定版才能让 nginx 自身的 CVE 面最小。

**Q: 原来的 RPM nginx 还留着会怎样？**
A: 会同时存在两个 nginx，且 rpm 数据库里仍有 `nginx-1.21.5` 及其模块依赖，
扫描结果不会改善。装配时必须是从**干净的基座**开始，不要 `yum install nginx`。
