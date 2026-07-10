# Sentaurus Windows-VM 小组共享环境设计

## 目标

把当前 VDMOS/TID Sentaurus 仿真工作区整理成可供小组成员克隆和复用的 Windows + VMware + CentOS 7 + SSH + Codex 环境。共享包必须包含安装说明、主机与虚拟机启动脚本、离线 Skill、安装提示词和可验证的连通性检查。

## 非目标

- 不分发 VMware、Sentaurus、许可证、虚拟机镜像或原始仿真大文件。
- 不提交密码、SSH 私钥、许可证签名和本机专用路径。
- 不把 Virtuoso 应用控制 daemon 当成 Sentaurus SSH 的必要条件。

## 共享目录

```text
team_setup/
├── README.md
├── install-team-environment.ps1
├── start-sentaurus-vm.ps1
├── guest-start-ssh-bridge.sh
├── codex-bootstrap-prompt.md
├── codex-skills-bundle.zip
└── skills/
    ├── superpowers/
    ├── plan-docs/
    ├── codex-workflows/
    ├── sentaurus-vm-runner/
    └── virtuoso-vm-bridge-setup/
```

## Skill 范围

- `superpowers`：完整插件目录，保留插件清单、资源、许可证和 Skills。
- `plan-docs`：项目规划与文档交接。
- `codex-workflows`：复杂任务编排与长上下文执行。
- `sentaurus-vm-runner`：Sentaurus SSH 探测、许可证恢复和 PN diode smoke test。
- `virtuoso-vm-bridge-setup`：复用 VMware NAT、虚拟网卡和 SSH 分层排障知识；不要求安装 Virtuoso bridge。

## Windows 启动流程

管理员 PowerShell 运行 `start-sentaurus-vm.ps1`：

1. 检查并启动 `VMAuthdService`、`VMnetDHCP`、`VMware NAT Service`。
2. 自动寻找常见位置的 `vmrun.exe`。
3. 用用户提供的 `.vmx` 路径启动 VM；已运行时保持不变。
4. 优先用 VMware Tools 获取 IP，失败时使用可覆盖的默认地址 `192.168.137.131`。
5. 等待 TCP 22。
6. 创建或更新 `~/.ssh/config` 中的 `sentaurus-vm` 条目。
7. 执行批处理 SSH、用户名、主机名和 `sdevice` 检查。

所有本机路径和连接参数均通过脚本参数传入，不把当前机器的绝对 VM 路径写成组员默认值。

## VM 启动流程

在当前已验证的 CentOS 7 VM 中运行 `guest-start-ssh-bridge.sh`：

1. 启动 NetworkManager。
2. 连接默认网卡 `ens33`，允许参数覆盖。
3. 启用并启动 `sshd`。
4. 检查端口 22、IPv4 地址和默认路由。
5. 检查 `sdevice` 是否位于 PATH 或默认 Sentaurus 根目录。

本文所称“桥”是以下连接链路，而非额外的 Sentaurus daemon：

```text
Windows VMware NAT/DHCP → VM ens33 → VM sshd:22 → Windows Codex/SSH
```

## 安装与首次连接

`install-team-environment.ps1` 负责：

- 检查 Git、OpenSSH、Codex 和 VMware 工具。
- 将仓库内 Skill 安装到 `$CODEX_HOME\skills`；未设置时使用 `~\.codex\skills`。
- 已存在同名 Skill 时先停止并提示，除非用户显式传入覆盖参数。
- 检查每个 Skill 的 `SKILL.md`。
- 提示重启 Codex，因为运行中的会话不会自动重载新 Skill。

首次 SSH 密钥安装由文档给出明确命令，脚本不保存或接收 VM 密码。

## 说明文档与 Codex 提示词

`team_setup/README.md` 按以下顺序编写：

1. 前置软件和授权边界。
2. 克隆仓库。
3. Windows 管理员 PowerShell 启动。
4. VM 终端启动网络和 SSH。
5. 首次密钥配置。
6. 自动 SSH 别名连接。
7. Skill 安装和 Codex 重启。
8. Sentaurus、FlexNet 和 PN diode smoke test。
9. 分层故障排查。

`codex-bootstrap-prompt.md` 是一段可直接发给组员 Codex 的提示词，要求其读取 README、检查机器环境、安装仓库 Skill、配置 SSH、运行无破坏验证并报告证据；禁止读取或提交密码、私钥和许可证内容。

## 验证

发布前至少验证：

- 两个 PowerShell 脚本可解析，并支持无破坏检查模式。
- VM shell 脚本通过 `bash -n`。
- 五个 Skill 目录及 `SKILL.md` 完整。
- ZIP 可展开，内容与源目录一致。
- 仓库不包含私钥、密码、许可证签名和当前 VM 的绝对路径。
- `git diff --check` 通过。
- 当前环境能够连接 `tcad@192.168.137.131:22`，并找到 `sdevice`。

## Git 发布

先单独提交本设计文档。实施完成后只暂存本次共享包文件，使用提交信息：

```text
docs(setup): add portable Sentaurus VM team environment
```

随后把当前分支已有的未推送提交与本次提交一起推送到 `origin/main`，不创建 release 或 tag。