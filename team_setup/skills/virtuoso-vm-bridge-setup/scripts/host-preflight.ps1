param(
  [string]$VmIp,
  [string]$VmUser = "IC",
  [string]$BridgeRoot
)

$ErrorActionPreference = "Continue"

Write-Host "== Host tools =="
python --version
git --version
cmd /c "ssh -V 2>&1"
uv --version

Write-Host "`n== VMware services =="
Get-Service VMnetDHCP,"VMware NAT Service" -ErrorAction SilentlyContinue |
  Select-Object Name,Status,DisplayName

if ($VmIp) {
  Write-Host "`n== VM connectivity =="
  Test-NetConnection $VmIp -Port 22 |
    Select-Object ComputerName,RemoteAddress,TcpTestSucceeded,PingSucceeded
  ssh -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=accept-new "$VmUser@$VmIp" "echo SSH_OK && hostname && whoami"
}

if ($BridgeRoot -and (Test-Path -LiteralPath $BridgeRoot)) {
  Write-Host "`n== Bridge CLI =="
  Push-Location $BridgeRoot
  if (Test-Path ".\.venv\Scripts\virtuoso-bridge.exe") {
    .\.venv\Scripts\virtuoso-bridge.exe --help | Select-Object -First 12
  } else {
    Write-Host "Bridge venv CLI not found at $BridgeRoot\.venv\Scripts\virtuoso-bridge.exe"
  }
  Pop-Location
} elseif ($BridgeRoot) {
  Write-Warning "Bridge root not found: $BridgeRoot"
} else {
  Write-Host "`nBridgeRoot not supplied; skipping Virtuoso bridge CLI check."
}
