# 发送给组员 Codex 的配置提示词

请在当前克隆的 `vdmos-tid-research` 仓库中完成 Windows + VMware + Sentaurus VM + SSH + Codex Skill 的本机配置。

必须先阅读：

1. `AGENTS.md`
2. `team_setup/README.md`
3. `docs/vm_setup/sentaurus_vm.md`
4. `team_setup/install-team-environment.ps1`
5. `team_setup/start-sentaurus-vm.ps1`
6. `team_setup/guest-start-ssh-bridge.sh`

执行要求：

- 先检查当前电脑的 Git、Codex、Windows OpenSSH Client、VMware Workstation、`vmrun.exe`、VM `.vmx` 路径、VMware NAT/DHCP 服务和当前运行中的 VM；不要假设路径与仓库作者电脑相同。
- 先运行 `team_setup/install-team-environment.ps1 -CheckOnly`，报告安装目标和同名 Skill 冲突。没有冲突时执行安装；有冲突时比较版本与内容，只有我确认后才能使用 `-Force`。
- 安装范围必须包括仓库内的 Superpowers 离线 Skills、`plan-docs`、`codex-workflows`、`sentaurus-vm-runner` 和 `virtuoso-vm-bridge-setup`。安装完成后提醒我重启 Codex，新会话才会加载 Skill。
- 先用 `team_setup/start-sentaurus-vm.ps1 -CheckOnly` 做无写入检查。需要启动 VMware 服务时，给出准确的管理员 PowerShell 命令；不要绕过管理员权限。
- VM 尚未启动时，使用我提供的 `.vmx` 路径运行 `start-sentaurus-vm.ps1`。默认用户 `tcad`、默认 SSH 端口 `22`、回退地址 `192.168.137.131`，但应优先使用 VMware Tools 实际获取的 IP。
- 如果 VM 的网卡或 sshd 未启动，指导我在 VMware 控制台运行 `sudo bash guest-start-ssh-bridge.sh <实际网卡>`；先用 `nmcli dev status` 确认网卡名，不要盲目假设一定是 `ens33`。
- 配置 SSH 密钥登录和 `sentaurus-vm` 别名。可以读取公钥，但不得读取、显示、复制或提交 SSH 私钥；不得保存 VM 密码。
- 验证 `ssh -o BatchMode=yes sentaurus-vm`、`hostname`、`whoami`、`command -v sdevice`、NetworkManager、sshd、TCP 22 和 VM IPv4。
- 使用 `sentaurus-vm-runner` 先做 `probe`。只检查许可证状态，不读取或打印许可证文件内容。许可证 daemon 未运行时，按 README 的 `lmutil lmreread` 流程处理。
- 在我同意运行仿真后，再执行 PN diode smoke test；所有下载结果放入被忽略的 `local_runtime/`，远程运行放入 `/home/tcad/codex_runs/`。
- 不提交 VM 镜像、`.vmx`、密码、私钥、许可证文件、原始 PDF、`.gzp` 或大型 Sentaurus 输出。
- 不修改 `/usr/synopsys/...` 官方示例；复制到用户运行目录后再运行。
- 不把 Virtuoso 的 CIW daemon 当作 Sentaurus SSH 的必要条件。本任务中的“桥”是 VMware NAT/DHCP → VM 虚拟网卡 → sshd:22。

完成后请用简洁表格报告以下证据：

- 仓库绝对路径；
- Codex CLI 版本和 Skill 安装目录；
- `vmrun.exe` 与 `.vmx` 路径；
- VMware 服务状态；
- VM 实际 IPv4、网卡名和默认路由；
- sshd enabled/active 状态及端口 22；
- `ssh sentaurus-vm` 是否免密成功；
- `sdevice`、`sde`、`swb` 路径；
- FlexNet 探测结果（只报告状态，不输出许可证内容）；
- PN diode 是否运行、远程目录和本地证据目录；
- 未完成项及下一条准确命令。
