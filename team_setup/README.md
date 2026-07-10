# 小组安装说明：Windows + VMware + Sentaurus + Codex

本目录用于把本仓库的 Sentaurus/VDMOS 仿真工作流复制到小组成员的 Windows 电脑。最终连接链路是：

```text
Windows 管理员 PowerShell
  └─ VMware NAT/DHCP 服务 + vmrun
       └─ CentOS 7 VM 的 ens33
            └─ sshd 默认端口 22
                 └─ ssh sentaurus-vm / 本地 Codex
```

这里的“桥”是 **VMware NAT/DHCP + VM 虚拟网卡 + SSH**。NAT 模式不会自动把 VM 的 SSH 端口暴露到公共互联网。Sentaurus 本身不需要额外的桥接 daemon；`virtuoso-bridge-lite` 也不是 Sentaurus SSH 仿真的前置条件。

## 1. 不随仓库分发的内容

每位成员需要自行合法准备：

- Windows 10/11；
- VMware Workstation 和可启动的团队 Sentaurus VM；
- Git、Codex CLI；
- Windows OpenSSH Client；
- 有效的本地 Sentaurus 安装与许可证环境。

仓库不包含 VMware、VM 镜像、Sentaurus 安装包、许可证、密码或 SSH 私钥。不要把 `.vmx` 所在目录、私钥、许可证文件和大型仿真输出提交到 Git。

## 2. 克隆仓库

```powershell
git clone https://github.com/dude1wudv/vdmos-tid-research.git
cd vdmos-tid-research
```

如果已克隆：

```powershell
git pull --ff-only origin main
```

## 3. 首次启动顺序

首次配置建议按以下顺序：

1. 在 Windows 管理员 PowerShell 启动 VMware 服务和 VM。
2. 如果 TCP 22 尚未就绪，在 VMware 控制台进入 VM，启动 `ens33 + sshd`。
3. 在 Windows 安装 SSH 公钥。
4. 再次运行 Windows 启动脚本，写入 `sentaurus-vm` SSH 别名并自动验证。
5. 安装离线 Skill，重启 Codex。

以后日常使用通常只需运行 Windows 启动脚本，然后执行 `ssh sentaurus-vm`。

## 4. Windows 管理员 PowerShell 启动

右键 PowerShell，选择“以管理员身份运行”：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
cd D:\path\to\vdmos-tid-research
.\team_setup\start-sentaurus-vm.ps1 -VmxPath 'D:\path\to\Sentaurus.vmx'
```

脚本会：

- 查找 `vmrun.exe`；
- 启动 `VMAuthdService`、`VMnetDHCP`、`VMware NAT Service`；
- 启动指定 VM（已运行时不重复启动）；
- 通过 VMware Tools 自动获取 VM IPv4 地址；
- 获取失败时使用默认 `192.168.137.131`；
- 等待 SSH 默认端口 `22`；
- 生成缺失的 `~/.ssh/id_ed25519`；
- 只替换 `~/.ssh/config` 中带标记的 `sentaurus-vm` 配置块；
- 验证 `hostname`、`whoami` 和 `sdevice`。

常用参数：

```powershell
# 只检查，不启动服务/VM，也不写 SSH 配置
.\team_setup\start-sentaurus-vm.ps1 -CheckOnly

# VMware 不在常见目录
.\team_setup\start-sentaurus-vm.ps1 `
  -VmrunPath 'D:\VMware\vmrun.exe' `
  -VmxPath 'D:\VM\Sentaurus.vmx'

# VM 使用其他地址、用户或 SSH 端口
.\team_setup\start-sentaurus-vm.ps1 `
  -VmxPath 'D:\VM\Sentaurus.vmx' `
  -VmIp '192.168.137.150' `
  -VmUser 'tcad' `
  -SshPort 22
```

如果只有一台 VM 已经运行，可以省略 `-VmxPath`，脚本会自动选择它。若 VM 尚未运行，必须传入 `.vmx` 路径。

## 5. 在 VM 终端启动 SSH“桥”

### 5.1 把脚本放进 VM

首次还不能 SSH 时，可使用 VMware Shared Folders，把 Windows 仓库共享给 VM，然后在 VM 控制台复制：

```bash
cp "/mnt/hgfs/<共享目录>/team_setup/guest-start-ssh-bridge.sh" ~/
```

如果密码 SSH 已临时可用，也可从 Windows 执行：

先把 Windows 启动脚本输出的实际地址填入变量，再复制：

```powershell
$vmIp = '<启动脚本输出的实际 IPv4>'
scp .\team_setup\guest-start-ssh-bridge.sh "tcad@${vmIp}:/home/tcad/"
```

### 5.2 启动网络、sshd 和端口 22

在 VM 的 VMware 控制台终端执行：

```bash
cd /home/tcad
sudo bash guest-start-ssh-bridge.sh ens33
```

脚本针对当前参考 VM 的 **CentOS 7 + NetworkManager + ens33**，会：

- 启动并启用 NetworkManager；
- 连接 `ens33`；
- 启动并启用 `sshd`；
- 在已启用的 `firewalld` 中放行 `ssh` 服务；
- 显示 IPv4、默认路由、端口 22 和 `sdevice` 状态。

仅检查，不修改 VM：

```bash
bash guest-start-ssh-bridge.sh --check ens33
```

手工排查命令：

```bash
sudo systemctl enable --now NetworkManager
sudo nmcli dev connect ens33
sudo systemctl enable --now sshd
sudo firewall-cmd --permanent --add-service=ssh
sudo firewall-cmd --reload
/sbin/ip -br -4 addr
/usr/sbin/ss -lnt | grep ':22'
command -v sdevice
```

如果网卡不是 `ens33`，先运行 `nmcli dev status`，再把实际名称传给脚本。

## 6. 首次安装 SSH 密钥

在 Windows PowerShell 执行。命令会提示输入一次 VM 用户密码，但不会保存密码：

使用 Windows 启动脚本显示的实际 VM 地址：

```powershell
$vmIp = '<启动脚本输出的实际 IPv4>'
if (-not (Test-Path "$HOME\.ssh\id_ed25519")) {
    ssh-keygen -t ed25519 -N '""' -f "$HOME\.ssh\id_ed25519"
}
Get-Content "$HOME\.ssh\id_ed25519.pub" |
    ssh "tcad@$vmIp" 'umask 077; mkdir -p ~/.ssh; cat >> ~/.ssh/authorized_keys; chmod 700 ~/.ssh; chmod 600 ~/.ssh/authorized_keys'
```

随后重新运行 Windows 启动脚本，让它写入自动发现的 IP：

```powershell
.\team_setup\start-sentaurus-vm.ps1 -VmxPath 'D:\path\to\Sentaurus.vmx'
```

验证免密别名：

```powershell
ssh -o BatchMode=yes sentaurus-vm 'echo SSH_OK; hostname; whoami; command -v sdevice'
```

预期看到 `SSH_OK`、VM 主机名、`tcad` 和 `sdevice` 路径。

## 7. 安装 Codex Skill

共享包包含：

- Superpowers 完整插件源及离线 Skill；
- `plan-docs`；
- `codex-workflows`；
- `sentaurus-vm-runner`；
- `virtuoso-vm-bridge-setup`（用于 VMware/SSH 分层排障）。

先检查目标和冲突：

```powershell
.\team_setup\install-team-environment.ps1 -CheckOnly
```

首次安装：

```powershell
.\team_setup\install-team-environment.ps1
```

如果同名 Skill 已存在，脚本会停止。确认要用仓库版本替换这些同名目录后：

```powershell
.\team_setup\install-team-environment.ps1 -Force
```

默认安装到 `$CODEX_HOME\skills`；未设置 `CODEX_HOME` 时安装到 `~\.codex\skills`。也可以测试到独立目录：

```powershell
.\team_setup\install-team-environment.ps1 -CodexHome 'D:\CodexHome'
```

安装后必须关闭并重新启动 Codex；正在运行的会话不会自动加载新 Skill。在线环境也可通过 Codex 的 `/plugins` 界面安装 Superpowers，仓库副本是离线回退。

离线完整包位于：

```text
team_setup/codex-skills-bundle.zip
```

ZIP 内包含安装器、说明、提示词以及 Skill。单独分发后可直接解压并安装：

```powershell
Expand-Archive .\codex-skills-bundle.zip .\codex-team-setup
.\codex-team-setup\install-team-environment.ps1 -CheckOnly
.\codex-team-setup\install-team-environment.ps1
```

## 8. Sentaurus 与许可证探测

连接 VM：

```powershell
ssh sentaurus-vm
```

VM 内检查：

```bash
command -v sde
command -v sdevice
command -v swb
/usr/synopsys/scl/scl2023/linux64/bin/lmutil lmstat \
  -c /usr/synopsys/scl/scl2023/synopsys.dat
```

若 Sentaurus 报 FlexNet daemon 未运行，当前参考 VM 可尝试：

```bash
/usr/synopsys/scl/scl2023/linux64/bin/lmutil lmreread \
  -c /usr/synopsys/scl/scl2023/synopsys.dat
```

不要打印或提交许可证文件内容。

Windows 端使用已安装的 Skill 做只读探测：

```powershell
powershell -ExecutionPolicy Bypass -File `
  "$env:CODEX_HOME\skills\sentaurus-vm-runner\scripts\run_pn_diode.ps1" `
  -Mode probe
```

未设置 `CODEX_HOME` 时：

```powershell
powershell -ExecutionPolicy Bypass -File `
  "$HOME\.codex\skills\sentaurus-vm-runner\scripts\run_pn_diode.ps1" `
  -Mode probe
```

## 9. PN diode 最小仿真验证

```powershell
powershell -ExecutionPolicy Bypass -File `
  "$HOME\.codex\skills\sentaurus-vm-runner\scripts\run_pn_diode.ps1" `
  -Mode pn-diode `
  -LocalOut .\local_runtime\sentaurus_runs
```

远程运行目录应位于 `/home/tcad/codex_runs/`，下载结果保存在被 Git 忽略的 `local_runtime/`。不要直接修改 `/usr/synopsys/...` 下的官方示例。

## 10. 常见问题

| 现象 | 检查与处理 |
|---|---|
| `vmrun.exe not found` | 用 `-VmrunPath` 指定 VMware Workstation 的 `vmrun.exe`。 |
| VMware NAT/DHCP 服务停止 | 用管理员 PowerShell运行启动脚本；检查 `Get-Service VMnetDHCP,'VMware NAT Service'`。 |
| VM 只有 `lo`，没有 VMware IPv4 | VMware UI 勾选网卡 `Connected` 和 `Connect at power on`，确认网络模式为 NAT。 |
| `ens33 NO-CARRIER` | 检查 VMware 虚拟网线、NAT/DHCP 服务，然后在 VM 运行 `sudo nmcli dev connect ens33`。 |
| VM 地址改变 | 重新运行 Windows 启动脚本，它会用 VMware Tools 更新 `sentaurus-vm`。 |
| TCP 22 超时 | VM 内检查 `systemctl status sshd`、`ss -lnt` 和 firewalld。 |
| SSH 仍询问密码 | 检查 `~/.ssh/authorized_keys`，目录权限 700、文件权限 600。 |
| `sdevice` 找不到 | 检查 `/usr/synopsys/sentaurus/W-2024.09/bin` 是否在 PATH。 |
| FlexNet 报 daemon down | 先 `lmstat`，再运行上面的 `lmreread`；不要修改许可证内容。 |
| `swb` 无法从 SSH 打开 | Workbench GUI 需要图形显示；优先用 `sde`/`sdevice` 无头运行，或在 VM 桌面使用 `DISPLAY=:0.0`。 |
| `virtuoso-bridge-lite` daemon 无响应 | 与 Sentaurus SSH 无关；只有控制 Virtuoso CIW 时才需要该应用桥。 |

## 11. 给 Codex 自动配置

打开 [`codex-bootstrap-prompt.md`](codex-bootstrap-prompt.md)，复制其中整段提示词发送给组员电脑上的 Codex。Codex 应先做 `-CheckOnly` 和现场探测，再修改本机配置。
