---
name: virtuoso-vm-bridge-setup
description: Use when setting up or repairing host-to-VM control of Cadence Virtuoso through VMware, CentOS/Linux SSH, virtuoso-bridge-lite, Spectre, SKILL CIW load, or when errors mention NO-CARRIER, VMware NAT/DHCP stopped, daemon NO RESPONSE, RBStop in bash, or WinError 10054.
---

# Virtuoso VM Bridge Setup

## Overview

Set up a host machine to control Cadence Virtuoso running inside a VMware Linux VM. Treat remote desktop and bridge as separate layers:

- Remote desktop/VMware console: human GUI operation and CIW paste.
- SSH: file transfer, tunnel, and Spectre checks.
- `virtuoso-bridge-lite`: SKILL execution, screenshots, windows, snapshots, and automation.

Never type SKILL into a Linux shell. `RBStop()` and `load("...virtuoso_setup.il")` must run in the Virtuoso CIW.

## Core Workflow

1. Inspect host tools:
   - `python --version`
   - `git --version`
   - `ssh -V`
   - `uv --version`
   - `Get-Service VMnetDHCP,"VMware NAT Service"`
2. Locate running VM:
   - Use `vmrun list`.
   - Read the `.vmx` for `guestOS`, `ethernet0.connectionType`, `ethernet0.present`, and `ethernet0.startConnected`.
3. Fix VM network before bridge work:
   - In guest, `ip -4 addr` must show a VMware NIC such as `ens33` with an IP on `VMnet8` NAT, often `192.168.137.x`.
   - If only `lo` and `virbr0` appear, VMware NIC is missing or disconnected.
   - If `ens33` shows `NO-CARRIER`, check VMware UI "Connected / Connect at power on" and host `VMware NAT Service` plus `VMware DHCP Service`.
4. Verify guest SSH:
   - `sshd` active in guest.
   - `ss -lntp | grep ':22'` in guest.
   - `Test-NetConnection <vm-ip> -Port 22` on host.
   - If ping works but port 22 fails, inspect guest firewall: `firewall-cmd --list-all`.
5. Configure SSH key login:
   - Generate host key if missing: `ssh-keygen -t ed25519 -N "" -f "$env:USERPROFILE\.ssh\id_ed25519"`.
   - Append host public key to `/home/<user>/.ssh/authorized_keys`.
   - Verify: `ssh -o BatchMode=yes <user>@<vm-ip> "echo SSH_OK && hostname && whoami"`.
6. Install `virtuoso-bridge-lite` on host:
   - Clone or update under the active workspace, e.g. `<workspace>\virtuoso-bridge-lite`.
   - Run `uv venv .venv`.
   - Run `uv pip install -e .`.
   - Verify `.venv\Scripts\virtuoso-bridge.exe --help`.
7. Initialize and start bridge:
   - `.venv\Scripts\virtuoso-bridge.exe init <user>@<vm-ip> --force`
   - `.venv\Scripts\virtuoso-bridge.exe start`
   - `.venv\Scripts\virtuoso-bridge.exe status`
8. Load daemon in Virtuoso:
   - If status says `[daemon] NO RESPONSE`, copy the exact `load("...virtuoso_setup.il")` line.
   - Paste it into Virtuoso CIW, not terminal.
   - If CIW says an old daemon is running, run in CIW:
     ```skill
     RBStop()
     load("/tmp/virtuoso_bridge_<remote_user>/<client_id>/virtuoso_bridge/virtuoso_setup.il")
     ```
9. Verify end to end:
   - `.venv\Scripts\virtuoso-bridge.exe status`
   - `.venv\Scripts\virtuoso-bridge.exe eval '1+2'`
   - `.venv\Scripts\virtuoso-bridge.exe screenshot`
   - Optional: `.venv\Scripts\virtuoso-bridge.exe windows`

## Quick Diagnosis

| Symptom | Likely Cause | Next Check |
|---|---|---|
| Guest IP is only `127.0.0.1` and `192.168.122.1` | Only loopback and libvirt bridge, no VMware NIC IP | `ip link`, VMX ethernet config |
| `ens33` is `NO-CARRIER` | VMware virtual cable disconnected or NAT/DHCP service stopped | VMware UI connected checkbox, `Get-Service VMnetDHCP,"VMware NAT Service"` |
| DHCPDISCOVER no offers | Host VMware DHCP/NAT service stopped or wrong network mode | Start services as admin or repair VMnet8 |
| Ping works, SSH times out | Guest firewall or sshd not listening | `ss -lntp`, `firewall-cmd --list-all` |
| SSH asks for password | Key not installed or permissions wrong | `authorized_keys`, chmod 700/600, `restorecon` |
| bridge `[tunnel] running`, `[daemon] NO RESPONSE` | CIW has not loaded setup file | Paste `load(...)` in Virtuoso CIW |
| `-bash: syntax error near unexpected token load` | SKILL pasted into Linux terminal | Switch to Virtuoso CIW |
| `WinError 10054` during status | Tunnel exists but daemon closed/missing | Load setup in CIW, then status again |

## VMware Guest Operations

Use `vmrun` when VMware Tools is running and credentials are available. Do not print passwords in final answers.

```powershell
$vmrun = "D:\Application\vmware\vmrun.exe"
$vmx = "<path-to-vmx>"
& $vmrun list
& $vmrun checkToolsState $vmx
& $vmrun getGuestIPAddress $vmx -wait
```

For guest diagnostics, write output to `/tmp`, then copy it back:

```powershell
$script = @'
{
echo "=== ip ==="; ip -4 addr
echo "=== link ==="; ip link
echo "=== sshd ==="; systemctl status sshd --no-pager
echo "=== listen ==="; ss -lntp | grep ":22" || true
echo "=== firewall ==="; firewall-cmd --list-all 2>&1 || true
} > /tmp/codex_vm_diag.txt 2>&1
'@
& $vmrun -gu root -gp "<password>" runScriptInGuest $vmx /bin/bash $script
& $vmrun -gu root -gp "<password>" CopyFileFromGuestToHost $vmx /tmp/codex_vm_diag.txt .\tmp\codex_vm_diag.txt
```

## Common Commands

Host:

```powershell
Test-NetConnection <vm-ip> -Port 22
ssh -o BatchMode=yes -o ConnectTimeout=5 <user>@<vm-ip> "echo SSH_OK"
.\.venv\Scripts\virtuoso-bridge.exe init <user>@<vm-ip> --force
.\.venv\Scripts\virtuoso-bridge.exe start
.\.venv\Scripts\virtuoso-bridge.exe status
.\.venv\Scripts\virtuoso-bridge.exe eval '1+2'
```

Guest:

```bash
ip -4 addr
ip link
systemctl status sshd --no-pager
ss -lntp | grep ':22'
firewall-cmd --list-all
nmcli dev status
nmcli dev connect ens33
nmcli con up ens33
```

## Safety

- Do not expose passwords, license files, PDK paths with secrets, private keys, or full license server credentials.
- Do not edit VMX while the VM is running unless the change is known hot-pluggable.
- Do not treat Virtuoso installation, PDK installation, license activation, SSH, and bridge as one failure. Verify each layer separately.
- If service start needs Windows admin rights, ask the user to run the exact command in elevated PowerShell.
