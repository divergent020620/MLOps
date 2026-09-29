# 创新实验室部署Tips

> 适用环境：麒麟 V10 SP1 Tercel（glibc 2.28）


## 1. 基础环境配置

### 1.1 配置 yum 源

麒麟公开源（清华镜像不可用，用官方源）：

```bash
cat > /etc/yum.repos.d/kylin.repo << 'EOF'
[ks10-adv-os]
name = Kylin Linux Advanced Server 10 - Os
baseurl = https://update.cs2c.com.cn/NS/V10/V10SP1/os/adv/lic/base/$basearch/
enabled = 1
gpgcheck = 0

[ks10-adv-updates]
name = Kylin Linux Advanced Server 10 - Updates
baseurl = https://update.cs2c.com.cn/NS/V10/V10SP1/os/adv/lic/updates/$basearch/
enabled = 1
gpgcheck = 0
EOF
```


### 1.2 配置 DNS

```bash
nmcli connection modify "ens3" ipv4.dns "114.114.114.114 223.5.5.5"
nmcli connection up "ens3"
```


### 1.3 关闭 SSL 证书验证

麒麟 V10 默认缺少 CA 证书，各工具报 SSL 错误时统一关闭验证：

```bash
# curl：加 -k 跳过验证，加 -L 跟随重定向
curl -k -L -O <url>

# npm
npm config set strict-ssl false

# git
git config --global http.sslVerify false

# conda
conda config --set ssl_verify false
```

> **提示：** curl 不加 `-L` 只会下载到 HTML 重定向页（154 字节），必须加 `-L` 跟随重定向。


## 2. 系统库修复(Vscode连接需求)

### 2.1 安装 Miniconda

后续 libstdc++ 替换和 OpenSSL 3 安装都依赖 conda，先装好 Miniconda：

```bash
curl -k -L -O https://mirrors.tuna.tsinghua.edu.cn/anaconda/miniconda/Miniconda3-latest-Linux-x86_64.sh
bash Miniconda3-latest-Linux-x86_64.sh -b -p /opt/miniconda3
/opt/miniconda3/bin/conda init bash
source ~/.bashrc
```


### 2.2 libstdc++ 升级（解决 GLIBCXX 版本不足）

**现象：** `This machine does not meet Visual Studio Code Server's prerequisites, expected GLIBCXX >= v3.4.25`（系统只有 v3.4.24）

**解决：** 用 conda 自带的新版 libstdc++ 替换系统库：

```bash
cp /usr/lib64/libstdc++.so.6 /usr/lib64/libstdc++.so.6.bak
cp /opt/miniconda3/lib/libstdc++.so.6 /usr/lib64/libstdc++.so.6
```


### 2.4 VSCode Server 离线安装（内网环境）

**现象：** VSCode Remote SSH 连接时报 `ServerDownloadFailed` / `UnpackFailed` / `LocalDownloadFailed`，因为内网无法访问 `update.code.visualstudio.com`。

**核心原理：**
- VSCode Server 安装脚本通过 wget 在远程机器下载，但内网 DNS 解析不了微软 CDN
- 新版 VSCode (1.129+, Remote SSH 0.124+) 需要两个组件：**Server** + **CLI 工具**
- Windows 端设置 `remote.SSH.localServerDownload: off` 避免从客户端下载（Windows 也访问不了）
- VSCode 版本与 commit id 一一绑定，升级 VSCode 后 commit id 会变，需要重新下载

**解决步骤：**

1. 在能上网的机器，从浏览器下载两个文件（注意替换 commit id，与 VSCode 日志中的一致）：

| 组件 | 下载地址 | 文件名 |
|------|----------|--------|
| Server | `https://update.code.visualstudio.com/commit:<commit_id>/server-linux-x64/stable` | `vscode-server-linux-x64.tar.gz` |
| CLI | `https://update.code.visualstudio.com/commit:<commit_id>/cli-alpine-x64/stable` | `vscode_cli_alpine_x64_cli.tar.gz` |

2. 上传到服务器 `/tmp/`：

```powershell
scp ./vscode-server-linux-x64.tar.gz hacadm@<ip>:/tmp/
scp ./vscode_cli_alpine_x64_cli.tar.gz hacadm@<ip>:/tmp/
```

3. 在服务器上安装：

```bash
commit_id="8a7abeba6e03ea3af87bfbce9a1b7e48fed567b8"

# 安装 Server
rm -rf ~/.vscode-server/bin/${commit_id}
mkdir -p ~/.vscode-server/bin/${commit_id}
tar -xzf /tmp/vscode-server-linux-x64.tar.gz -C ~/.vscode-server/bin/${commit_id} --strip-components=1

# 安装 CLI（解压出 code 二进制，复制到 ~/.vscode-server/）
mkdir -p /tmp/vscode-cli
tar -xzf /tmp/vscode_cli_alpine_x64_cli.tar.gz -C /tmp/vscode-cli
cp /tmp/vscode-cli/code ~/.vscode-server/code-${commit_id}
chmod +x ~/.vscode-server/code-${commit_id}

# 清理
rm -rf /tmp/vscode-cli
```

4. 验证：

```bash
ls ~/.vscode-server/bin/${commit_id}/bin/code-server  # Server 二进制
file ~/.vscode-server/code-${commit_id}               # CLI 二进制（应为 ELF 可执行文件）
```

5. VSCode 设置确认：
   - `remote.SSH.localServerDownload` → **`off`**
   - `remote.SSH.lockfilesInTmp` → **`true`**

### 2.5 禁用 VSCode 自动更新

VSCode 更新后 commit id 会变，需要重新下载 Server 和 CLI，建议禁用自动更新。

**Windows 端：**

1. 文件 → 首选项 → 设置 → 搜 `update` → 将 `Update: Mode` 改为 **`none`**
2. 或直接编辑 `settings.json`：
   ```json
   "update.mode": "none"
   ```

**Linux 端（如果也装了桌面版 VSCode）：**

```bash
cat > /etc/apt/preferences.d/vscode.pref << 'EOF'
Package: code
Pin: release *
Pin-Priority: -1
EOF
```

> **注意：** 内网环境 CA 证书不全导致 wget SSL 失败是正常现象，不用管，文件已经手动安装好了。另外确保 **libstdc++**（2.2）和 **OpenSSL 3**（2.3）已修复，否则 VSCode Server 无法启动。

麒麟 SP1、SP3 官方源只有 OpenSSL 1.1.1，没有 3.x。用 conda 安装最快：

```bash
/opt/miniconda3/bin/conda install -c conda-forge openssl -y
ln -sf /opt/miniconda3/lib/libssl.so.3 /usr/lib64/libssl.so.3
ln -sf /opt/miniconda3/lib/libcrypto.so.3 /usr/lib64/libcrypto.so.3
```


## 3. SSH 与远程连接

### 3.1 开启 SSH 端口转发（AllowTcpForwarding）

**现象：** `channel 3: open failed: administratively prohibited: open failed`

**解决：**

```bash
sed -i 's/^AllowTcpForwarding no/AllowTcpForwarding yes/' /etc/ssh/sshd_config
echo 'AllowTcpForwarding yes' >> /etc/ssh/sshd_config
systemctl restart sshd
```


## 4. 工具链安装

### 4.1 Node.js 22

Claude Code / cc-switch-cli 需要 Node >= 22，麒麟源没有，从淘宝镜像下载二进制包：

```bash
curl -k -L -O https://npmmirror.com/mirrors/node/v22.14.0/node-v22.14.0-linux-x64.tar.xz
tar -xJf node-v22.14.0-linux-x64.tar.xz -C /usr/local/
ln -sf /usr/local/node-v22.14.0-linux-x64/bin/* /usr/bin/
node -v   # 应显示 v22.14.0
```


### 4.2 cc-switch-cli

cc-switch RPM 是 Electron GUI 程序，服务端缺少 `libwebkit2gtk-4.1.so.0` 和 `libssl.so.3`，无法运行。**建议用 CLI 版。**

CLI 版不依赖 GUI 库，但 glibc 版需要 >= 2.29，麒麟 V10 SP1 只有 2.28。**必须用 musl 静态编译版。**

**安装步骤：**

1. 在能上网的机器从 GitHub Release 下载 `cc-switch-cli-linux-x64-musl.tar.gz`
2. 传到服务器 `/tmp/`
3. 执行：

```bash
mkdir -p ~/.local/bin
tar -xzf /tmp/cc-switch-cli-linux-x64-musl.tar.gz -C ~/.local/bin/
chmod +x ~/.local/bin/cc-switch
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
cc-switch --version
```


### 4.3 Claude Code

```bash
npm config set strict-ssl false
npm config set registry https://registry.npmmirror.com
npm install -g @anthropic-ai/claude-code

# 确认安装路径并链接
ls /usr/local/node-v22.14.0-linux-x64/lib/node_modules/@anthropic-ai/claude-code/bin/claude.exe
ln -sf /usr/local/node-v22.14.0-linux-x64/lib/node_modules/@anthropic-ai/claude-code/bin/claude.exe /usr/bin/claude
hash -r
claude --version
```
