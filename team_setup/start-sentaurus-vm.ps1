[CmdletBinding()]
param(
    [string]$VmxPath,
    [string]$VmrunPath,
    [string]$VmIp = "192.168.137.131",
    [string]$VmUser = "tcad",
    [int]$SshPort = 22,
    [string]$SshAlias = "sentaurus-vm",
    [switch]$CheckOnly
)

$ErrorActionPreference = "Stop"

function Test-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Find-Vmrun([string]$ExplicitPath) {
    $candidates = @(
        $ExplicitPath,
        "D:\Application\vmware\vmrun.exe",
        "C:\Program Files (x86)\VMware\VMware Workstation\vmrun.exe",
        "C:\Program Files\VMware\VMware Workstation\vmrun.exe"
    ) | Where-Object { $_ }

    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }
    throw "vmrun.exe not found. Pass -VmrunPath explicitly."
}

function Test-TcpPort([string]$HostName, [int]$Port, [int]$TimeoutMs = 1000) {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $result = $client.BeginConnect($HostName, $Port, $null, $null)
        return $result.AsyncWaitHandle.WaitOne($TimeoutMs) -and $client.Connected
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

function Wait-TcpPort([string]$HostName, [int]$Port, [int]$TimeoutSeconds = 60) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        if (Test-TcpPort $HostName $Port) { return $true }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)
    return $false
}

$vmrun = Find-Vmrun $VmrunPath
Write-Host "vmrun: $vmrun"
if (-not $CheckOnly -and -not (Test-Administrator)) {
    throw "Run this script in Administrator PowerShell."
}

$serviceNames = @("VMAuthdService", "VMnetDHCP", "VMware NAT Service")
foreach ($name in $serviceNames) {
    $service = Get-Service -Name $name -ErrorAction SilentlyContinue
    if (-not $service) {
        Write-Warning "VMware service not found: $name"
        continue
    }
    Write-Host ("service {0}: {1}" -f $name, $service.Status)
    if (-not $CheckOnly -and $service.Status -ne "Running") {
        if (-not (Test-Administrator)) {
            throw "Run this script in Administrator PowerShell to start VMware services."
        }
        Start-Service -Name $name
        (Get-Service -Name $name).WaitForStatus("Running", (New-TimeSpan -Seconds 15))
    }
}

$running = @(& $vmrun list 2>&1)
if ($LASTEXITCODE -ne 0) { throw "vmrun list failed: $($running -join ' ')" }
$runningVmx = @($running | Select-Object -Skip 1 | Where-Object { $_ -and $_ -notmatch '^Total running VMs:' })
Write-Host "running VMs: $($runningVmx.Count)"

if (-not $VmxPath) {
    if ($runningVmx.Count -eq 1) {
        $VmxPath = $runningVmx[0]
        Write-Host "using the only running VM: $VmxPath"
    } elseif ($runningVmx.Count -gt 1) {
        throw "Multiple VMs are running. Pass -VmxPath explicitly."
    } elseif (-not $CheckOnly) {
        throw "No VM is running. Pass -VmxPath so the script can start it."
    }
}

if ($VmxPath) {
    if (-not (Test-Path -LiteralPath $VmxPath -PathType Leaf)) {
        throw "VMX not found: $VmxPath"
    }
    $VmxPath = (Resolve-Path -LiteralPath $VmxPath).Path
    if ($VmxPath -notin $runningVmx) {
        if ($CheckOnly) {
            Write-Warning "VM is not running: $VmxPath"
        } else {
            Write-Host "starting VM..."
            & $vmrun start $VmxPath nogui
            if ($LASTEXITCODE -ne 0) { throw "vmrun start failed." }
        }
    }

    if (-not $CheckOnly -or $VmxPath -in $runningVmx) {
        $detectedRaw = & $vmrun getGuestIPAddress $VmxPath -wait 2>$null | Select-Object -Last 1
        $detectedIp = if ($detectedRaw) { $detectedRaw.Trim() } else { "" }
        if ($detectedIp -match '^\d{1,3}(\.\d{1,3}){3}$') {
            $VmIp = $detectedIp
            Write-Host "VMware Tools IP: $VmIp"
        } else {
            Write-Warning "Could not get a guest IPv4 address; using $VmIp"
        }
    }
}

if ($CheckOnly) {
    $tcpOpen = Test-TcpPort $VmIp $SshPort 1500
} else {
    $tcpOpen = Wait-TcpPort $VmIp $SshPort 60
}
Write-Host "TCP ${VmIp}:${SshPort}: $tcpOpen"
if (-not $tcpOpen) {
    throw "SSH port is not reachable. Start team_setup/guest-start-ssh-bridge.sh in the VM console."
}

$ssh = Get-Command ssh -ErrorAction SilentlyContinue
$sshKeygen = Get-Command ssh-keygen -ErrorAction SilentlyContinue
if (-not $ssh) { throw "Windows OpenSSH Client is missing." }
if (-not $sshKeygen) { throw "ssh-keygen is missing." }

$sshDir = Join-Path $HOME ".ssh"
$keyPath = Join-Path $sshDir "id_ed25519"
$configPath = Join-Path $sshDir "config"
if (-not $CheckOnly) {
    New-Item -ItemType Directory -Force -Path $sshDir | Out-Null
    if (-not (Test-Path -LiteralPath $keyPath)) {
        & $sshKeygen.Source -t ed25519 -N '""' -f $keyPath
        if ($LASTEXITCODE -ne 0) { throw "ssh-keygen failed." }
    }

    $identityPath = $keyPath.Replace('\', '/')
    $begin = "# BEGIN VDMOS SENTAURUS VM"
    $end = "# END VDMOS SENTAURUS VM"
    $block = @"
$begin
Host $SshAlias
    HostName $VmIp
    User $VmUser
    Port $SshPort
    IdentityFile $identityPath
    IdentitiesOnly yes
    ServerAliveInterval 30
    ServerAliveCountMax 3
$end
"@
    $existing = if (Test-Path -LiteralPath $configPath) { [IO.File]::ReadAllText($configPath) } else { "" }
    $pattern = "(?s)" + [regex]::Escape($begin) + ".*?" + [regex]::Escape($end) + "\r?\n?"
    $unmanaged = [regex]::Replace($existing, $pattern, "").Trim()
    $updated = $block.Trim() + [Environment]::NewLine
    if ($unmanaged) { $updated += [Environment]::NewLine + $unmanaged + [Environment]::NewLine }
    [IO.File]::WriteAllText($configPath, $updated, (New-Object Text.UTF8Encoding($false)))
    Write-Host "SSH alias updated: $SshAlias ($configPath)"
}

$target = if ($CheckOnly) { "$VmUser@$VmIp" } else { $SshAlias }
$sshArgs = @("-o", "BatchMode=yes", "-o", "ConnectTimeout=5")
if ($CheckOnly) {
    # ponytail: an isolated known-hosts sink keeps CheckOnly genuinely write-free.
    $sshArgs += @("-o", "UserKnownHostsFile=NUL", "-o", "GlobalKnownHostsFile=NUL", "-o", "StrictHostKeyChecking=no", "-o", "UpdateHostKeys=no", "-o", "LogLevel=ERROR")
}
$sshArgs += @("-p", $SshPort, $target, 'echo SSH_OK; hostname; whoami; command -v sdevice')
& $ssh.Source @sshArgs
if ($LASTEXITCODE -ne 0) {
    Write-Warning "SSH key login is not ready. Follow the first-key installation section in team_setup/README.md."
} else {
    Write-Host "Sentaurus VM SSH verification passed."
}
