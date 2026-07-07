param(
  [string]$Query = "VDMOS total ionizing dose",
  [int]$Limit = 20
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$out = Join-Path $Root "03_metadata\paper_search_mcp.txt"

# ponytail: wrapper only; exact command differs by paper-search-mcp install mode.
$cmd = Get-Command paper-search-mcp -ErrorAction SilentlyContinue
if (-not $cmd) {
  "paper-search-mcp not found. Install/configure https://github.com/openags/paper-search-mcp, then adapt this wrapper to its local CLI command." | Set-Content -LiteralPath $out -Encoding UTF8
  Get-Content -LiteralPath $out
  exit 0
}

& paper-search-mcp search --query $Query --limit $Limit | Tee-Object -FilePath $out
