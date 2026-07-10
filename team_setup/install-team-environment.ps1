[CmdletBinding()]
param(
    [string]$CodexHome = $(if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HOME ".codex" }),
    [string]$SourceRoot,
    [switch]$Force,
    [switch]$CheckOnly
)

$ErrorActionPreference = "Stop"
if ($SourceRoot) {
    $sourceRoot = [IO.Path]::GetFullPath($SourceRoot)
} elseif (Test-Path -LiteralPath (Join-Path $PSScriptRoot "skills") -PathType Container) {
    $sourceRoot = Join-Path $PSScriptRoot "skills"
} else {
    # Standalone ZIP layout: installer and Skill directories share one root.
    $sourceRoot = $PSScriptRoot
}
$targetRoot = Join-Path $CodexHome "skills"

function Assert-Skill([string]$Path, [string]$Name) {
    if (-not (Test-Path -LiteralPath (Join-Path $Path "SKILL.md") -PathType Leaf)) {
        throw "Skill entry point missing for ${Name}: $Path\SKILL.md"
    }
}

function Assert-TargetInsideRoot([string]$Root, [string]$Target) {
    $rootFull = [IO.Path]::GetFullPath($Root).TrimEnd('\') + '\'
    $targetFull = [IO.Path]::GetFullPath($Target)
    if (-not $targetFull.StartsWith($rootFull, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing target outside Skill root: $targetFull"
    }
}

if (-not (Test-Path -LiteralPath $sourceRoot -PathType Container)) {
    throw "Bundled Skill directory missing: $sourceRoot"
}

$items = @()
foreach ($name in @("plan-docs", "codex-workflows", "sentaurus-vm-runner", "virtuoso-vm-bridge-setup")) {
    $source = Join-Path $sourceRoot $name
    Assert-Skill $source $name
    $items += [pscustomobject]@{ Name = $name; Source = $source; Target = Join-Path $targetRoot $name }
}

$superpowersSkills = Join-Path $sourceRoot "superpowers\skills"
if (-not (Test-Path -LiteralPath (Join-Path $sourceRoot "superpowers\.codex-plugin\plugin.json") -PathType Leaf)) {
    throw "Bundled Superpowers plugin manifest is missing."
}
Get-ChildItem -LiteralPath $superpowersSkills -Directory | Sort-Object Name | ForEach-Object {
    Assert-Skill $_.FullName $_.Name
    $items += [pscustomobject]@{ Name = $_.Name; Source = $_.FullName; Target = Join-Path $targetRoot $_.Name }
}

Write-Host "Source root: $sourceRoot"
Write-Host "Codex home: $CodexHome"
Write-Host "Skill target: $targetRoot"
foreach ($tool in @("git", "ssh", "ssh-keygen", "codex")) {
    $command = Get-Command $tool -ErrorAction SilentlyContinue
    if ($command) { Write-Host ("tool {0}: {1}" -f $tool, $command.Source) } else { Write-Warning "Required tool not found on PATH: $tool" }
}
$vmrunCandidates = @(
    "D:\Application\vmware\vmrun.exe",
    "C:\Program Files (x86)\VMware\VMware Workstation\vmrun.exe",
    "C:\Program Files\VMware\VMware Workstation\vmrun.exe"
)
$vmrun = $vmrunCandidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
if ($vmrun) { Write-Host "VMware vmrun: $vmrun" } else { Write-Warning "vmrun.exe not found in common VMware Workstation paths." }

$collisions = @($items | Where-Object { Test-Path -LiteralPath $_.Target })
foreach ($item in $items) {
    $state = if (Test-Path -LiteralPath $item.Target) { "EXISTS" } else { "NEW" }
    Write-Host ("[{0}] {1} -> {2}" -f $state, $item.Name, $item.Target)
}

if ($CheckOnly) {
    Write-Host "Check complete; no files were written."
    exit 0
}

if ($collisions.Count -and -not $Force) {
    throw "Existing Skill destinations found. Review them, then rerun with -Force to replace only these named Skill directories."
}

New-Item -ItemType Directory -Force -Path $targetRoot | Out-Null
foreach ($item in $items) {
    Assert-TargetInsideRoot $targetRoot $item.Target
    if (Test-Path -LiteralPath $item.Target) {
        Remove-Item -LiteralPath $item.Target -Recurse -Force
    }
    Copy-Item -LiteralPath $item.Source -Destination $item.Target -Recurse
}

Write-Host "Installed $($items.Count) Skills. Restart Codex so a new session loads them."
Write-Host "Online alternative: install Superpowers through the Codex /plugins interface; the bundled copy is the offline fallback."
