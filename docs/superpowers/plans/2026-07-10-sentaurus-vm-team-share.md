# Sentaurus VM Team Share Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a portable team setup bundle that starts the VMware/SSH path from Windows, restores the guest network/SSH path, installs the selected Codex Skills, documents first-time setup, and publishes the verified package to GitHub.

**Architecture:** Keep setup artifacts under one `team_setup/` directory. Two focused startup scripts own the Windows and CentOS sides, one installer owns Skill copying, and one README is the human entry point; the ZIP is generated from the checked-in Skill source tree rather than maintained separately.

**Tech Stack:** Windows PowerShell 5.1+, VMware Workstation `vmrun`, Windows OpenSSH, CentOS 7 Bash/systemd/NetworkManager, Codex CLI, Git.

---

## File map

- Create `team_setup/README.md`: complete team installation and troubleshooting guide.
- Create `team_setup/start-sentaurus-vm.ps1`: Windows administrator startup, VM/IP discovery, SSH config, and connection probe.
- Create `team_setup/guest-start-ssh-bridge.sh`: CentOS network, firewall, SSH, and Sentaurus checks.
- Create `team_setup/install-team-environment.ps1`: offline Skill validation and installation.
- Create `team_setup/codex-bootstrap-prompt.md`: prompt that a teammate sends to Codex for machine-local setup.
- Copy selected Skill sources into `team_setup/skills/`.
- Generate `team_setup/codex-skills-bundle.zip` from `team_setup/skills/`.
- Modify `README.md`: add a short link to the team setup guide.

### Task 1: Add the Windows host startup script

**Files:**
- Create: `team_setup/start-sentaurus-vm.ps1`

- [ ] **Step 1: Create a parsing check that initially fails**

Run before the file exists:

```powershell
$errors = $null
[void][System.Management.Automation.Language.Parser]::ParseFile(
  (Resolve-Path .\team_setup\start-sentaurus-vm.ps1),
  [ref]$null,
  [ref]$errors
)
if ($errors) { throw ($errors | Out-String) }
```

Expected: failure because the script does not exist.

- [ ] **Step 2: Implement the minimum host startup script**

The script must expose:

```powershell
[CmdletBinding()]
param(
  [string]$VmxPath,
  [string]$VmrunPath,
  [string]$VmIp = '192.168.137.131',
  [string]$VmUser = 'tcad',
  [int]$SshPort = 22,
  [string]$SshAlias = 'sentaurus-vm',
  [switch]$CheckOnly
)
```

Implement these concrete operations:

1. Locate `vmrun.exe` from the explicit parameter or these existing paths:
   - `D:\Application\vmware\vmrun.exe`
   - `C:\Program Files (x86)\VMware\VMware Workstation\vmrun.exe`
   - `C:\Program Files\VMware\VMware Workstation\vmrun.exe`
2. In non-check mode, require an elevated Windows process and start `VMAuthdService`, `VMnetDHCP`, and `VMware NAT Service` when present.
3. If `VmxPath` is supplied, resolve it, start it with `vmrun start <vmx> nogui` only when absent from `vmrun list`, and use `vmrun getGuestIPAddress <vmx> -wait` when it returns an IPv4 address.
4. Wait up to 60 seconds for `<VmIp>:<SshPort>` using `System.Net.Sockets.TcpClient`.
5. In non-check mode, generate `~/.ssh/id_ed25519` with `ssh-keygen` only when missing.
6. Replace only the marker-delimited block below in `~/.ssh/config`, preserving all unrelated entries:

```text
# BEGIN VDMOS SENTAURUS VM
Host sentaurus-vm
    HostName 192.168.137.131
    User tcad
    Port 22
    IdentityFile C:/Users/<user>/.ssh/id_ed25519
    IdentitiesOnly yes
    ServerAliveInterval 30
    ServerAliveCountMax 3
# END VDMOS SENTAURUS VM
```

7. Run this final non-interactive verification and print a first-key-install hint if it fails:

```powershell
ssh -o BatchMode=yes -o ConnectTimeout=5 sentaurus-vm 'echo SSH_OK; hostname; whoami; command -v sdevice'
```

`-CheckOnly` must inspect tools, services, paths, TCP 22, and current SSH connectivity without starting services/VMs or writing files.

- [ ] **Step 3: Run syntax and no-write checks**

```powershell
$before = if (Test-Path $HOME\.ssh\config) { (Get-FileHash $HOME\.ssh\config).Hash } else { '' }
$errors = $null
[void][System.Management.Automation.Language.Parser]::ParseFile(
  (Resolve-Path .\team_setup\start-sentaurus-vm.ps1),
  [ref]$null,
  [ref]$errors
)
if ($errors) { throw ($errors | Out-String) }
.\team_setup\start-sentaurus-vm.ps1 -CheckOnly -VmIp 192.168.137.131
$after = if (Test-Path $HOME\.ssh\config) { (Get-FileHash $HOME\.ssh\config).Hash } else { '' }
if ($before -ne $after) { throw '-CheckOnly modified SSH config' }
```

Expected: parser reports no errors, live TCP/SSH checks pass on the current machine, and SSH config hash is unchanged.

### Task 2: Add the CentOS guest bridge script

**Files:**
- Create: `team_setup/guest-start-ssh-bridge.sh`

- [ ] **Step 1: Create the shell syntax check that initially fails**

```powershell
ssh sentaurus-vm 'bash -n -s' < .\team_setup\guest-start-ssh-bridge.sh
```

Expected: failure because the script does not exist.

- [ ] **Step 2: Implement the guest script**

Use this interface:

```bash
sudo bash guest-start-ssh-bridge.sh [interface]
sudo bash guest-start-ssh-bridge.sh --check [interface]
```

The implementation must:

- use `set -euo pipefail`;
- default the interface to `ens33`;
- in start mode require root, run `systemctl enable --now NetworkManager`, connect the interface with `nmcli dev connect`, run `systemctl enable --now sshd`, and allow the `ssh` service through active `firewalld`;
- in check mode perform no writes;
- locate `ip` from `/sbin/ip` or PATH because the current non-login SSH PATH does not include `/sbin`;
- print interface state, IPv4 address, default route, `sshd` enabled/active state, port 22 listeners, and `sdevice` location;
- return nonzero when the interface has no IPv4 address, `sshd` is inactive, port 22 is not listening, or `sdevice` is missing.

- [ ] **Step 3: Validate locally against the VM without changing it**

```powershell
Get-Content .\team_setup\guest-start-ssh-bridge.sh -Raw |
  ssh sentaurus-vm 'cat >/tmp/guest-start-ssh-bridge.sh && bash -n /tmp/guest-start-ssh-bridge.sh && bash /tmp/guest-start-ssh-bridge.sh --check ens33'
```

Expected: CentOS 7 reports `ens33` with an IPv4 address, `sshd` active, TCP 22 listening, and the Sentaurus `sdevice` path.

### Task 3: Add the offline Skill installer and source bundle

**Files:**
- Create: `team_setup/install-team-environment.ps1`
- Create directory trees under `team_setup/skills/` copied from the current installed versions.

- [ ] **Step 1: Copy exactly the approved Skill sources**

```powershell
New-Item -ItemType Directory -Force .\team_setup\skills | Out-Null
Copy-Item -Recurse -Force C:\Users\sun\.codex\plugins\cache\openai-curated\superpowers\2f1a8948 .\team_setup\skills\superpowers
Copy-Item -Recurse -Force C:\Users\sun\.codex\skills\plan-docs .\team_setup\skills\plan-docs
Copy-Item -Recurse -Force C:\Users\sun\.codex\skills\codex-workflows .\team_setup\skills\codex-workflows
Copy-Item -Recurse -Force C:\Users\sun\.codex\skills\sentaurus-vm-runner .\team_setup\skills\sentaurus-vm-runner
Copy-Item -Recurse -Force C:\Users\sun\.codex\skills\virtuoso-vm-bridge-setup .\team_setup\skills\virtuoso-vm-bridge-setup
```

Verify `superpowers/.codex-plugin/plugin.json` and every standalone `SKILL.md` exist.

- [ ] **Step 2: Implement the installer**

Expose:

```powershell
[CmdletBinding()]
param(
  [string]$CodexHome = $(if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HOME '.codex' }),
  [switch]$Force,
  [switch]$CheckOnly
)
```

Concrete behavior:

- validate the source paths and all `SKILL.md` files;
- install `plan-docs`, `codex-workflows`, `sentaurus-vm-runner`, and `virtuoso-vm-bridge-setup` to `<CodexHome>/skills/<name>`;
- install each immediate child under `team_setup/skills/superpowers/skills/` to `<CodexHome>/skills/<child-name>` for offline discovery;
- refuse existing destinations unless `-Force` is supplied;
- make `-CheckOnly` list sources, destinations, collisions, and missing prerequisites without writing;
- print that Codex must be restarted after installation;
- print that online users may install Superpowers through the Codex `/plugins` interface, but the bundled copy is the offline fallback.

- [ ] **Step 3: Test installation in a temporary Codex home**

```powershell
$temp = Join-Path $env:TEMP ('vdmos-codex-home-' + [guid]::NewGuid())
try {
  .\team_setup\install-team-environment.ps1 -CodexHome $temp -CheckOnly
  .\team_setup\install-team-environment.ps1 -CodexHome $temp
  $required = @('plan-docs','codex-workflows','sentaurus-vm-runner','virtuoso-vm-bridge-setup','using-superpowers')
  foreach ($name in $required) {
    if (-not (Test-Path (Join-Path $temp "skills\$name\SKILL.md"))) { throw "Missing installed Skill: $name" }
  }
} finally {
  if (Test-Path $temp) { Remove-Item -LiteralPath $temp -Recurse -Force }
}
```

Expected: temporary installation succeeds and all required entry points exist.

### Task 4: Write the installation guide and teammate Codex prompt

**Files:**
- Create: `team_setup/README.md`
- Create: `team_setup/codex-bootstrap-prompt.md`
- Modify: `README.md`

- [ ] **Step 1: Write the human guide**

Include exact, copyable sections for:

- prerequisites: VMware Workstation, the team VM, Codex CLI, Git, Windows OpenSSH Client, and valid local Sentaurus licensing;
- cloning `https://github.com/dude1wudv/vdmos-tid-research.git`;
- VM console command:

```bash
sudo bash team_setup/guest-start-ssh-bridge.sh ens33
```

Explain how to copy the script into the VM with VMware shared folders or `scp` after temporary password SSH is available.

- Windows administrator command:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\team_setup\start-sentaurus-vm.ps1 -VmxPath 'D:\path\to\Sentaurus.vmx'
```

- first-time key installation without storing a password:

```powershell
ssh-keygen -t ed25519 -N "" -f "$HOME\.ssh\id_ed25519"
Get-Content "$HOME\.ssh\id_ed25519.pub" | ssh tcad@192.168.137.131 'umask 077; mkdir -p ~/.ssh; cat >> ~/.ssh/authorized_keys; chmod 700 ~/.ssh; chmod 600 ~/.ssh/authorized_keys'
ssh sentaurus-vm 'echo SSH_OK; hostname; whoami; command -v sdevice'
```

- offline Skill installation and Codex restart;
- FlexNet probe and recovery commands from `sentaurus-vm-runner`;
- PN diode smoke test;
- troubleshooting table for VMware services, `NO-CARRIER`, changing IPs, blocked port 22, key permissions, `sdevice` PATH, FlexNet daemon state, and GUI `$DISPLAY` limitations.

State explicitly that the SSH bridge does not expose the VM to the public internet and that teammates must not commit VM images, keys, passwords, license files, or raw simulation outputs.

- [ ] **Step 2: Write the Codex bootstrap prompt**

The prompt must tell the teammate's Codex to:

1. read `team_setup/README.md`, `AGENTS.md`, and `docs/vm_setup/sentaurus_vm.md`;
2. inspect tools and paths instead of assuming this machine matches the author machine;
3. run installer `-CheckOnly`, then install after resolving collisions;
4. configure the VM/SSH connection without reading or printing passwords/private keys;
5. run host, guest, SSH, `sdevice`, FlexNet, and optional PN diode checks;
6. keep private/runtime artifacts ignored;
7. report commands, paths, IP, service state, SSH result, Skill destinations, and simulation evidence.

- [ ] **Step 3: Add the repository entry link**

Append a short “小组环境安装” section to root `README.md` linking to `team_setup/README.md`; do not duplicate the full guide.

- [ ] **Step 4: Check documentation references**

```powershell
$required = @(
  '.\team_setup\README.md',
  '.\team_setup\start-sentaurus-vm.ps1',
  '.\team_setup\guest-start-ssh-bridge.sh',
  '.\team_setup\install-team-environment.ps1',
  '.\team_setup\codex-bootstrap-prompt.md'
)
foreach ($path in $required) { if (-not (Test-Path $path)) { throw "Missing $path" } }
Select-String -Path .\team_setup\README.md -Pattern '管理员 PowerShell','ens33','sshd','sentaurus-vm','FlexNet','PN diode'
```

Expected: every artifact exists and every required topic is present.

### Task 5: Generate and validate the ZIP

**Files:**
- Create: `team_setup/codex-skills-bundle.zip`

- [ ] **Step 1: Generate the ZIP with .NET**

Use .NET instead of `Compress-Archive` so hidden `.codex-plugin/plugin.json` is retained:

```powershell
Add-Type -AssemblyName System.IO.Compression.FileSystem
$source = (Resolve-Path .\team_setup\skills).Path
$zip = Join-Path (Resolve-Path .\team_setup).Path 'codex-skills-bundle.zip'
if (Test-Path $zip) { Remove-Item -LiteralPath $zip }
[System.IO.Compression.ZipFile]::CreateFromDirectory(
  $source,
  $zip,
  [System.IO.Compression.CompressionLevel]::Optimal,
  $false
)
```

- [ ] **Step 2: Validate ZIP entry points**

```powershell
$archive = [System.IO.Compression.ZipFile]::OpenRead((Resolve-Path .\team_setup\codex-skills-bundle.zip))
try {
  $names = $archive.Entries.FullName -replace '\\','/'
  $required = @(
    'superpowers/.codex-plugin/plugin.json',
    'plan-docs/SKILL.md',
    'codex-workflows/SKILL.md',
    'sentaurus-vm-runner/SKILL.md',
    'virtuoso-vm-bridge-setup/SKILL.md'
  )
  foreach ($name in $required) { if ($name -notin $names) { throw "ZIP missing $name" } }
} finally { $archive.Dispose() }
```

Expected: all five required roots are present, including the hidden Superpowers plugin manifest.

### Task 6: Final verification, commit, and push

**Files:**
- All files under `team_setup/`
- Modified `README.md`
- Plan document

- [ ] **Step 1: Run all safe checks**

```powershell
$errors = $null
Get-ChildItem .\team_setup -Filter *.ps1 | ForEach-Object {
  [void][System.Management.Automation.Language.Parser]::ParseFile($_.FullName,[ref]$null,[ref]$errors)
}
if ($errors) { throw ($errors | Out-String) }
.\team_setup\start-sentaurus-vm.ps1 -CheckOnly -VmIp 192.168.137.131
.\team_setup\install-team-environment.ps1 -CheckOnly
Get-Content .\team_setup\guest-start-ssh-bridge.sh -Raw |
  ssh -o BatchMode=yes tcad@192.168.137.131 'cat >/tmp/guest-start-ssh-bridge.sh && bash -n /tmp/guest-start-ssh-bridge.sh && bash /tmp/guest-start-ssh-bridge.sh --check ens33'
git diff --check
```

- [ ] **Step 2: Scan only the new package for sensitive material**

```powershell
Get-ChildItem .\team_setup -Recurse -File |
  Where-Object Extension -ne '.zip' |
  Select-String -Pattern 'BEGIN (OPENSSH|RSA|EC) PRIVATE KEY|PASSWORD\s*=|SIGN2=|SERVER\s+\S+\s+[0-9A-F]{12}' -CaseSensitive:$false
```

Expected: no matches. Separately inspect any absolute author-machine paths and retain only documented generic examples.

- [ ] **Step 3: Review intended changes and commit**

```powershell
git status --short
git diff --stat
git add -- README.md team_setup
git commit -m 'docs(setup): add portable Sentaurus VM team environment'
```

Do not stage ignored VM images, `.gzp`, PDFs, license files, or `local_runtime/`.

- [ ] **Step 4: Push the existing and new commits**

Probe the local GitHub proxy first; if operational, use it for the push:

```powershell
$tcp = [System.Net.Sockets.TcpClient]::new()
try {
  $result = $tcp.BeginConnect('127.0.0.1',7890,$null,$null)
  $proxyOpen = $result.AsyncWaitHandle.WaitOne(1000) -and $tcp.Connected
} finally { $tcp.Dispose() }
if ($proxyOpen) {
  git -c http.proxy=http://127.0.0.1:7890 -c https.proxy=http://127.0.0.1:7890 push origin main
} else {
  git push origin main
}
```

- [ ] **Step 5: Verify publication**

```powershell
git status --short --branch
git log --oneline -4
git ls-remote origin refs/heads/main
gh repo view dude1wudv/vdmos-tid-research --json nameWithOwner,visibility,url,defaultBranchRef
```

Expected: local `main` matches `origin/main`, the implementation commit is remote, and no unintended working-tree changes remain.