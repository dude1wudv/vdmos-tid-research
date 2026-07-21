[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string] $CaseId,
    [Parameter(Mandatory)] [string] $AttemptId,
    [ValidateSet('PARALLEL_EXPLORATORY', 'SERIAL_CONFIRMATORY', 'DIAGNOSTIC_CLOSURE')]
    [string] $ExecutionMode = 'SERIAL_CONFIRMATORY',
    [string] $LocalRunRoot = '',
    [string] $RemoteRunRoot = '/home/tcad/codex_runs',
    [Parameter(Mandatory)] [string] $DeckPath,
    [Parameter(Mandatory)] [string] $ParameterPath,
    [string] $MetadataPath,
    [Parameter(Mandatory)] [string] $MeshPath,
    [string] $RestartMainPath,
    [string] $RestartCircuitPath,
    [int] $TimeoutSeconds = 3600,
    [ValidateRange(1, 2147483647)] [int] $Threads = 1,
    [int] $CpuCore = -1,
    [switch] $DisableAutoCpuLease,
    [string] $CorePolicyPath = '',
    [string] $VmUserHost = 'tcad@192.168.137.131',
    [string] $SentaurusRoot = '/usr/synopsys/sentaurus/W-2024.09',
    [switch] $IncludeLargeArtifacts,
    [string[]] $LargeArtifactPattern = @(),
    [string] $ParentRunId = 'NA',
    [string] $WorkerId = $env:COMPUTERNAME
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-Sha256Hex {
    param([Parameter(Mandatory)] [string] $Path)
    return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
}

function Get-UtcIso {
    return [DateTime]::UtcNow.ToString('o')
}

function Set-Utf8NoBomContent {
    param(
        [Parameter(Mandatory)] [string] $Path,
        [Parameter(Mandatory)] [AllowEmptyString()] [string] $Value
    )
    $encoding = New-Object System.Text.UTF8Encoding($false)
    [IO.File]::WriteAllText([IO.Path]::GetFullPath($Path), $Value, $encoding)
}

function ConvertTo-JsonFile {
    param(
        [Parameter(Mandatory)] $Value,
        [Parameter(Mandatory)] [string] $Path
    )
    $json = $Value | ConvertTo-Json -Depth 8
    Set-Utf8NoBomContent -Path $Path -Value ($json + "`n")
}

function Write-CsvFragment {
    param(
        [Parameter(Mandatory)] [string] $Path,
        [Parameter(Mandatory)] [string[]] $Headers,
        [Parameter(Mandatory)] [AllowEmptyCollection()] [hashtable[]] $Rows
    )
    $lines = @($Headers -join ',')
    foreach ($row in $Rows) {
        $values = foreach ($header in $Headers) {
            $value = if ($row.ContainsKey($header)) { [string] $row[$header] } else { 'NA' }
            '"' + $value.Replace('"', '""') + '"'
        }
        $lines += ($values -join ',')
    }
    Set-Utf8NoBomContent -Path $Path -Value (($lines -join "`n") + "`n")
}

function Invoke-RemoteScript {
    param([Parameter(Mandatory)] [string] $Script)
    $normalizedScript = $Script.Replace("`r`n", "`n").Replace("`r", "`n")
    $encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($normalizedScript))
    & ssh $VmUserHost "printf %s $encoded | base64 -d | bash" 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Remote command failed with exit code $LASTEXITCODE."
    }
}

function ConvertTo-PosixQuoted {
    param([Parameter(Mandatory)] [string] $Value)
    return "'" + $Value.Replace("'", "'`"'`"'") + "'"
}

function ConvertFrom-KeyValueLines {
    param([Parameter(Mandatory)] [string[]] $Lines)
    $result = @{}
    foreach ($line in $Lines) {
        if ($line -match '^([A-Za-z_][A-Za-z0-9_]*)=(.*)$') { $result[$Matches[1]] = $Matches[2] }
    }
    return $result
}

function Invoke-RemoteLeaseScript {
    param(
        [Parameter(Mandatory)] [string] $RemoteScriptPath,
        [Parameter(Mandatory)] [string] $Arguments
    )
    return Invoke-RemoteScript "set -euo pipefail; bash $(ConvertTo-PosixQuoted $RemoteScriptPath) $Arguments"
}

function Get-MetadataValue {
    param(
        $Metadata,
        [Parameter(Mandatory)] [string] $Name,
        $Default = 'NA'
    )
    if ($null -eq $Metadata) { return $Default }
    $property = $Metadata.PSObject.Properties[$Name]
    if ($null -eq $property -or $null -eq $property.Value -or [string]::IsNullOrWhiteSpace([string] $property.Value)) {
        return $Default
    }
    return $property.Value
}

function Test-LargeArtifactSelected {
    param(
        [Parameter(Mandatory)] [string] $Name,
        [AllowEmptyCollection()] [string[]] $Patterns = @()
    )
    foreach ($pattern in $Patterns) {
        if ($Name -like $pattern) { return $true }
    }
    return $false
}

function Get-FileRecord {
    param(
        [Parameter(Mandatory)] [string] $Path,
        [Parameter(Mandatory)] [string] $RelativePath
    )
    $item = Get-Item -LiteralPath $Path
    return [ordered]@{
        relative_path = $RelativePath.Replace('\', '/')
        sha256 = Get-Sha256Hex $Path
        size_bytes = [int64] $item.Length
    }
}

function New-RunFragments {
    param(
        [Parameter(Mandatory)] [string] $FragmentDir,
        [Parameter(Mandatory)] [System.Collections.IDictionary] $Manifest
    )
    New-Item -ItemType Directory -Path $FragmentDir -ErrorAction Stop | Out-Null
    $lifecycle = [string] $Manifest.lifecycle
    $exitCode = [string] $Manifest.exit_code
    $duration = [string] $Manifest.wall_time_seconds
    $eventRow = @{
        start_time = $Manifest.started_at; end_time = $Manifest.ended_at; phase = 'execution'
        case_id = $Manifest.case_id; event_type = 'run_closure'; tool = 'sdevice'
        action_summary = 'Isolated Sentaurus run closure'; reason_summary = 'Private worker archive'
        expected_result = 'Preserve auditable run artifacts'; observed_result = $lifecycle
        exit_code = $exitCode; duration_s = $duration; evidence_path = 'run_manifest.json'
        human_intervention = 'false'; decision_scope = $Manifest.execution_mode
    }
    Write-CsvFragment (Join-Path $FragmentDir 'codex_events.csv') @(
        'start_time','end_time','phase','case_id','event_type','tool','action_summary','reason_summary',
        'expected_result','observed_result','exit_code','duration_s','evidence_path','human_intervention','decision_scope'
    ) @($eventRow)

    $inputByName = @{}
    foreach ($record in $Manifest.inputs) { $inputByName[[IO.Path]::GetFileName($record.relative_path)] = $record.sha256 }
    $caseRow = @{
        case_id = $Manifest.case_id; attempt_id = $Manifest.attempt_id; parent_run_id = $Manifest.parent_run_id
        phase = 'execution'; target_bias_v = $Manifest.target_bias_v; actual_bias_v = $Manifest.actual_bias_v
        target_vce_v = $Manifest.target_vce_v; actual_vce_v = $Manifest.actual_vce_v
        let_mev_cm2_mg = $Manifest.let_mev_cm2_mg; let_pc_um = $Manifest.let_f_pc_um
        y_um = $Manifest.track_y_um; length_um = $Manifest.track_length_um; wt_um = $Manifest.wt_hi_um
        s_s = $Manifest.heavy_ion_time_s; final_time_s = $Manifest.final_time_s; time_end_s = $Manifest.time_end_s; mesh_variant = $Manifest.mesh_variant
        tmax_k = $Manifest.t_steady_max_k; t1680_s = 'NA'; t2500_s = 'NA'; peak_ic_a_um = 'NA'; peak_power_w_um = 'NA'
        status = $lifecycle; run_dir = 'private_run_dir'; deck_sha256 = $inputByName[[IO.Path]::GetFileName($Manifest.deck_path)]
        mesh_sha256 = $inputByName[[IO.Path]::GetFileName($Manifest.mesh_path)]; plt_file = 'NA'; log_file = 'artifacts/stdout.log'
        tdr_file = $Manifest.exact_final_tdr; notes = "device_family=$($Manifest.device_family); parent_restart_sha256=$($Manifest.parent_restart_main_sha256)"
    }
    Write-CsvFragment (Join-Path $FragmentDir 'case_summary.csv') @(
        'case_id','attempt_id','parent_run_id','phase','target_bias_v','actual_bias_v','target_vce_v','actual_vce_v','let_mev_cm2_mg','let_pc_um',
        'y_um','length_um','wt_um','s_s','final_time_s','time_end_s','mesh_variant','tmax_k','t1680_s','t2500_s',
        'peak_ic_a_um','peak_power_w_um','status','run_dir','deck_sha256','mesh_sha256','plt_file','log_file','tdr_file','notes'
    ) @($caseRow)

    $artifactRows = @()
    foreach ($artifact in $Manifest.artifacts) {
        $artifactRows += @{
            case_id = $Manifest.case_id; attempt_id = $Manifest.attempt_id; kind = 'run_output'
            local_path = $artifact.relative_path; remote_path = 'private_remote_run'
            sha256 = $artifact.sha256; size_bytes = $artifact.size_bytes; generated_at = $Manifest.ended_at
            publicable = 'false'; source_command_id = 'NA'
        }
    }
    Write-CsvFragment (Join-Path $FragmentDir 'artifact_manifest.csv') @(
        'case_id','attempt_id','kind','local_path','remote_path','sha256','size_bytes','generated_at','publicable','source_command_id'
    ) $artifactRows
    Write-CsvFragment (Join-Path $FragmentDir 'tuning_steps.csv') @(
        'case_id','parent_run_id','parameter','old_value','new_value','allowed_by_plan','trigger_evidence',
        'hypothesis','expected_effect','actual_effect','status_before','status_after','accepted'
    ) @()

    $provenanceRow = @{
        run_id = $Manifest.run_id; case_id = $Manifest.case_id; attempt_id = $Manifest.attempt_id
        device_family = $Manifest.device_family; t_init_k = $Manifest.t_init_k; t_steady_k = $Manifest.t_steady_k
        target_bias_v = $Manifest.target_bias_v; actual_bias_v = $Manifest.actual_bias_v
        target_vce_v = $Manifest.target_vce_v; actual_vce_v = $Manifest.actual_vce_v
        parent_restart_main_sha256 = $Manifest.parent_restart_main_sha256
        parent_restart_circuit_sha256 = $Manifest.parent_restart_circuit_sha256
        exact_final_tdr = $Manifest.exact_final_tdr; exact_final_tdr_sha256 = $Manifest.exact_final_tdr_sha256
        exact_2p1ns_tdr = $Manifest.exact_2p1ns_tdr; exact_2p1ns_tdr_sha256 = $Manifest.exact_2p1ns_tdr_sha256
        field_audit_sha256 = $Manifest.field_audit_sha256; extraction_sha256 = $Manifest.extraction_sha256
        screenshot_manifest_sha256 = $Manifest.screenshot_manifest_sha256
        allocation_mode = $Manifest.allocation_mode; cpu_core = $Manifest.cpu_core; sdevice_threads = $Manifest.sdevice_threads
        lease_acquired = $Manifest.lease_acquired; lease_released = $Manifest.lease_released
        affinity_verification = $Manifest.affinity_verification; exit_code = $Manifest.exit_code
        wall_time_seconds = $Manifest.wall_time_seconds
    }
    Write-CsvFragment (Join-Path $FragmentDir 'run_provenance.csv') @(
        'run_id','case_id','attempt_id','device_family','t_init_k','t_steady_k','target_bias_v','actual_bias_v','target_vce_v','actual_vce_v',
        'parent_restart_main_sha256','parent_restart_circuit_sha256','exact_final_tdr','exact_final_tdr_sha256','exact_2p1ns_tdr','exact_2p1ns_tdr_sha256',
        'field_audit_sha256','extraction_sha256','screenshot_manifest_sha256','allocation_mode','cpu_core',
        'sdevice_threads','lease_acquired','lease_released','affinity_verification','exit_code','wall_time_seconds'
    ) @($provenanceRow)
}

if ([string]::IsNullOrWhiteSpace($WorkerId)) { $WorkerId = 'NA' }
if ($TimeoutSeconds -lt 1) { throw 'TimeoutSeconds must be positive.' }
if ($Threads -lt 1) { throw 'Threads must be a positive integer.' }
if ($CpuCore -lt -1) { throw 'CpuCore must be -1 or a non-negative remote core index.' }
if ($ExecutionMode -ne 'SERIAL_CONFIRMATORY' -and $Threads -eq 1) {
    Write-Warning 'Non-serial execution mode is recorded as provenance; SDevice still uses one thread.'
}
if ([string]::IsNullOrWhiteSpace($CorePolicyPath)) {
    $CorePolicyPath = Join-Path (Split-Path -Parent $PSScriptRoot) 'config\sentaurus-core-policy.json'
}
$resolvedCorePolicy = Resolve-Path -LiteralPath $CorePolicyPath -ErrorAction SilentlyContinue
if ($null -eq $resolvedCorePolicy -or -not (Test-Path -LiteralPath $resolvedCorePolicy.Path -PathType Leaf)) {
    throw "Core policy file does not exist: $CorePolicyPath"
}
$CorePolicyPath = $resolvedCorePolicy.Path
try { $corePolicy = Get-Content -LiteralPath $CorePolicyPath -Raw | ConvertFrom-Json -ErrorAction Stop } catch { throw "Invalid core policy JSON: $($_.Exception.Message)" }
if ($null -eq $corePolicy.enabled -or $null -eq $corePolicy.reserved_cores -or $null -eq $corePolicy.max_managed_slots -or $null -eq $corePolicy.lease_root -or $null -eq $corePolicy.lock_timeout_seconds -or $null -eq $corePolicy.unmanaged_process_policy) {
    throw 'Core policy is missing required fields.'
}
if ($corePolicy.unmanaged_process_policy -ne 'exclude_affinity') { throw 'Unsupported unmanaged_process_policy; fail closed.' }
$reservedCores = @($corePolicy.reserved_cores | ForEach-Object { [int] $_ })
if (@($reservedCores | Where-Object { $_ -lt 0 }).Count -gt 0) { throw 'reserved_cores must contain only non-negative integers.' }
$policyReservedCsv = $reservedCores -join ','
$policyReservedQuoted = if ([string]::IsNullOrEmpty($policyReservedCsv)) { "''" } else { ConvertTo-PosixQuoted $policyReservedCsv }
$policyLeaseRoot = [string] $corePolicy.lease_root
$policyMaxSlots = [int] $corePolicy.max_managed_slots
$policyLockTimeout = [int] $corePolicy.lock_timeout_seconds
if ($policyMaxSlots -lt 1 -or $policyLockTimeout -lt 1) { throw 'Core policy slot and lock timeout values must be positive.' }
$policyHash = Get-Sha256Hex $CorePolicyPath
$autoLeaseEnabled = ([bool] $corePolicy.enabled -and $CpuCore -eq -1 -and $Threads -eq 1 -and -not $DisableAutoCpuLease)
if (-not [bool] $corePolicy.enabled -and $CpuCore -eq -1 -and -not $DisableAutoCpuLease) {
    throw 'Automatic CPU leasing is disabled by policy; use an explicit CpuCore or the deliberate DisableAutoCpuLease escape hatch.'
}
$allocationMode = if ($autoLeaseEnabled) { 'AUTO_LEASE' } elseif ($CpuCore -ge 0) { 'EXPLICIT_CPU_CORE' } elseif ($DisableAutoCpuLease) { 'AUTO_LEASE_DISABLED' } else { 'MULTI_THREAD_UNPINNED' }
$restartProvided = -not [string]::IsNullOrWhiteSpace($RestartMainPath)
if ($restartProvided -ne (-not [string]::IsNullOrWhiteSpace($RestartCircuitPath))) {
    throw 'RestartMainPath and RestartCircuitPath must be supplied as a matched pair.'
}

$inputSpecs = @(
    @{ label = 'deck'; path = $DeckPath },
    @{ label = 'parameter'; path = $ParameterPath },
    @{ label = 'mesh'; path = $MeshPath }
)
if (-not [string]::IsNullOrWhiteSpace($MetadataPath)) {
    $inputSpecs += @{ label = 'metadata'; path = $MetadataPath }
}
if ($restartProvided) {
    $inputSpecs += @{ label = 'restart_main'; path = $RestartMainPath }
    $inputSpecs += @{ label = 'restart_circuit'; path = $RestartCircuitPath }
}
foreach ($spec in $inputSpecs) {
    $resolved = Resolve-Path -LiteralPath $spec.path -ErrorAction SilentlyContinue
    if ($null -eq $resolved -or -not (Test-Path -LiteralPath $resolved -PathType Leaf)) {
        throw "Required $($spec.label) input does not exist: $($spec.path)"
    }
    $spec.path = $resolved.Path
}
$names = @($inputSpecs | ForEach-Object { [IO.Path]::GetFileName($_.path) })
if (($names | Select-Object -Unique).Count -ne $names.Count) {
    throw 'Input leaf names must be unique because SDevice resolves them in one remote input directory.'
}
foreach ($pattern in $LargeArtifactPattern) {
    if ([string]::IsNullOrWhiteSpace($pattern) -or $pattern -match '[/\\]') {
        throw "LargeArtifactPattern must be a leaf-name wildcard: $pattern"
    }
}

$physicalMetadata = $null
if (-not [string]::IsNullOrWhiteSpace($MetadataPath)) {
    $metadataSpec = $inputSpecs | Where-Object { $_.label -eq 'metadata' } | Select-Object -First 1
    try { $physicalMetadata = Get-Content -LiteralPath $metadataSpec.path -Raw | ConvertFrom-Json -ErrorAction Stop } catch { throw "Invalid case metadata JSON: $($_.Exception.Message)" }
}
$deviceFamily = [string] (Get-MetadataValue $physicalMetadata 'device_family')
$tInitK = [string] (Get-MetadataValue $physicalMetadata 't_init_k')
$tSteadyK = [string] (Get-MetadataValue $physicalMetadata 't_steady_k')
$tSteadyMaxK = [string] (Get-MetadataValue $physicalMetadata 't_steady_max_k')
$targetVceV = [string] (Get-MetadataValue $physicalMetadata 'target_vce_v')
$actualVceV = [string] (Get-MetadataValue $physicalMetadata 'actual_vce_v')
$targetBiasV = [string] (Get-MetadataValue $physicalMetadata 'target_bias_v' $targetVceV)
$actualBiasV = [string] (Get-MetadataValue $physicalMetadata 'actual_bias_v' $actualVceV)
$letValue = [string] (Get-MetadataValue $physicalMetadata 'let_mev_cm2_mg')
$letFValue = [string] (Get-MetadataValue $physicalMetadata 'let_f_pc_um')
$trackYValue = [string] (Get-MetadataValue $physicalMetadata 'track_y_um')
$trackLengthValue = [string] (Get-MetadataValue $physicalMetadata 'length_um')
$wtHiValue = [string] (Get-MetadataValue $physicalMetadata 'wt_hi_um')
$heavyIonTimeValue = [string] (Get-MetadataValue $physicalMetadata 'strike_time_s')
$timeEndValue = [string] (Get-MetadataValue $physicalMetadata 'total_time_s')
$finalTimeValue = [string] (Get-MetadataValue $physicalMetadata 'final_time_s' $timeEndValue)
$meshVariantValue = [string] (Get-MetadataValue $physicalMetadata 'mesh_variant')
$exactTdrExpected = [string] (Get-MetadataValue $physicalMetadata 'exact_final_tdr' (Get-MetadataValue $physicalMetadata 'exact_2p1ns_tdr'))
$fieldAuditHash = [string] (Get-MetadataValue $physicalMetadata 'field_audit_sha256')
$extractionHash = [string] (Get-MetadataValue $physicalMetadata 'extraction_sha256')
$screenshotManifestHash = [string] (Get-MetadataValue $physicalMetadata 'screenshot_manifest_sha256')
$campaignId = [string] (Get-MetadataValue $physicalMetadata 'campaign_id')
$publicationProfile = [string] (Get-MetadataValue $physicalMetadata 'publication_profile')
$structureId = [string] (Get-MetadataValue $physicalMetadata 'structure_id')
$highTerminalName = [string] (Get-MetadataValue $physicalMetadata 'high_terminal_name')
$biasQuantity = [string] (Get-MetadataValue $physicalMetadata 'bias_quantity')
$targetBlockingVoltage = [string] (Get-MetadataValue $physicalMetadata 'target_blocking_voltage_v')
$actualBlockingVoltage = [string] (Get-MetadataValue $physicalMetadata 'actual_blocking_voltage_v')
$ratedVoltage = [string] (Get-MetadataValue $physicalMetadata 'rated_voltage_v')
$bvStaticVoltage = [string] (Get-MetadataValue $physicalMetadata 'bv_static_v')
$bvCriterion = [string] (Get-MetadataValue $physicalMetadata 'bv_criterion')
$deratingBasis = Get-MetadataValue $physicalMetadata 'derating_basis'
$parentRestartIds = Get-MetadataValue $physicalMetadata 'parent_restart_ids' @()
$parentRestartHashes = Get-MetadataValue $physicalMetadata 'parent_restart_hashes' @()
$terminationReason = [string] (Get-MetadataValue $physicalMetadata 'termination_reason')
$parentRestartMainSha = 'NA'
$parentRestartCircuitSha = 'NA'
if ($restartProvided) {
    $parentRestartMainSha = Get-Sha256Hex (($inputSpecs | Where-Object { $_.label -eq 'restart_main' } | Select-Object -First 1).path)
    $parentRestartCircuitSha = Get-Sha256Hex (($inputSpecs | Where-Object { $_.label -eq 'restart_circuit' } | Select-Object -First 1).path)
}

$stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')
$runId = '{0}__{1}__{2}__{3}' -f $CaseId, $AttemptId, $stamp, ([Guid]::NewGuid().ToString('N').Substring(0, 8))
if ($runId -notmatch '^[A-Za-z0-9][A-Za-z0-9_.-]*$') { throw 'CaseId and AttemptId must yield a portable run identifier.' }
$resolvedLocalRunRoot = Resolve-Path -LiteralPath $LocalRunRoot -ErrorAction SilentlyContinue
if ($null -ne $resolvedLocalRunRoot) {
    $LocalRunRoot = $resolvedLocalRunRoot.Path
}
else {
    $LocalRunRoot = [IO.Path]::GetFullPath($LocalRunRoot)
}
$localRunDir = Join-Path $LocalRunRoot $runId
$remoteRunDir = "$RemoteRunRoot/$runId"
if (Test-Path -LiteralPath $localRunDir) { throw "Refusing existing local run directory: $localRunDir" }
New-Item -ItemType Directory -Path $localRunDir -ErrorAction Stop | Out-Null
New-Item -ItemType Directory -Path (Join-Path $localRunDir 'artifacts') -ErrorAction Stop | Out-Null
New-Item -ItemType Directory -Path (Join-Path $localRunDir 'inputs') -ErrorAction Stop | Out-Null
foreach ($spec in $inputSpecs) {
    Copy-Item -LiteralPath $spec.path -Destination (Join-Path $localRunDir ('inputs\' + [IO.Path]::GetFileName($spec.path))) -ErrorAction Stop
}

$startedAt = Get-UtcIso
$affinityCommand = ''
$leaseCore = 'NA'
$leaseToken = 'NA'
$leaseAcquired = $false
$leaseReleased = $false
$affinityVerification = 'NOT_REQUESTED'
$remoteLeaseScript = "$remoteRunDir/sdevice_core_lease.sh"
$remoteDeck = [IO.Path]::GetFileName($DeckPath)
$endedAt = 'NA'
$lifecycle = 'FAILED'
$exitCode = 'NA'
$wallSeconds = 'NA'
$probeSummary = 'NOT_RUN'
$artifacts = @()
$inputs = @($inputSpecs | ForEach-Object {
    $name = [IO.Path]::GetFileName($_.path)
    Get-FileRecord (Join-Path $localRunDir "inputs\$name") (Join-Path 'inputs' $name)
})
try {
    $sdevicePath = "$SentaurusRoot/bin/sdevice"
    $localLeaseScript = Join-Path $PSScriptRoot 'sdevice_core_lease.sh'
    if (-not (Test-Path -LiteralPath $localLeaseScript -PathType Leaf)) { throw "Lease script is missing: $localLeaseScript" }
    Invoke-RemoteScript "set -euo pipefail; test ! -e $(ConvertTo-PosixQuoted $remoteRunDir); test -d $(ConvertTo-PosixQuoted $RemoteRunRoot); test -x $(ConvertTo-PosixQuoted $sdevicePath); command -v flock > /dev/null; getconf _NPROCESSORS_ONLN > /dev/null; ps -eo pid=,comm= | head -n 1 > /dev/null; if command -v lmutil > /dev/null; then lmutil lmstat -c /usr/synopsys/scl/scl2023/synopsys.dat 2>/dev/null | grep -Eq 'UP|Users of'; else true; fi"
    $probeSummary = 'SSH_SDEVICE_RESOURCE_LICENSE_PROBE_OK'
    Invoke-RemoteScript "set -euo pipefail; mkdir $(ConvertTo-PosixQuoted $remoteRunDir); mkdir $(ConvertTo-PosixQuoted "$remoteRunDir/inputs")"
    & scp -- $localLeaseScript "${VmUserHost}:$remoteRunDir/sdevice_core_lease.sh" 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Upload failed for sdevice core lease script.' }
    Invoke-RemoteScript "set -euo pipefail; tr -d '\r' < $(ConvertTo-PosixQuoted $remoteLeaseScript) > $(ConvertTo-PosixQuoted "$remoteLeaseScript.lf"); mv $(ConvertTo-PosixQuoted "$remoteLeaseScript.lf") $(ConvertTo-PosixQuoted $remoteLeaseScript); chmod 700 $(ConvertTo-PosixQuoted $remoteLeaseScript)"
    foreach ($spec in $inputSpecs) {
        & scp -- $spec.path "${VmUserHost}:$remoteRunDir/inputs/" 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Upload failed for $($spec.path)." }
    }
    $remoteCommand = @'
set -euo pipefail
cd __INPUT_DIR__
export PATH=/usr/bin:/bin:__BIN_DIR__:$PATH
lease_active=0
lease_core=''
lease_token=''
release_lease() {
    set +e
    if [ "$lease_active" = 1 ]; then
        if bash __LEASE_SCRIPT__ release --lease-root __LEASE_ROOT__ --core "$lease_core" --token "$lease_token" > __LEASE_RELEASE__ 2>&1; then
            printf 'released=true\n' >> __LEASE_RELEASE__
        else
            printf 'released=false\n' >> __LEASE_RELEASE__
        fi
    fi
}
trap release_lease EXIT
if __AUTO_LEASE__; then
    lease_result=$(bash __LEASE_SCRIPT__ acquire --lease-root __LEASE_ROOT__ --reserved-cores __RESERVED_CORES__ --max-managed-slots __MAX_MANAGED_SLOTS__ --lock-timeout-seconds __LOCK_TIMEOUT__ --remote-run-dir __RUN_DIR__ --owner-pid "$$")
    printf '%s\n' "$lease_result" > __LEASE_STATE__
    lease_core=$(sed -n 's/^core=//p' __LEASE_STATE__ | head -n 1)
    lease_token=$(sed -n 's/^token=//p' __LEASE_STATE__ | head -n 1)
    case "$lease_core" in ''|*[!0-9]*) exit 70 ;; esac
    case "$lease_token" in ????????*) ;; *) exit 70 ;; esac
    affinity="taskset --cpu-list $lease_core"
    lease_active=1
else
    affinity='__AFFINITY__'
fi
online=$(getconf _NPROCESSORS_ONLN)
if [ -n "$affinity" ]; then
    requested_core=$(printf '%s' "$affinity" | sed -n 's/.*--cpu-list \([0-9][0-9]*\).*/\1/p')
    [ -n "$requested_core" ] && [ "$requested_core" -lt "$online" ] || exit 71
fi
start=$(date +%s)
set +e
# Run in the background so an acquired lease can be rebound to the actual SDevice PID.
timeout --signal=INT --kill-after=60s __TIMEOUT__ $affinity sdevice --threads __THREADS__ __DECK__ > __STDOUT__ 2> __STDERR__ &
runner_pid=$!
set -e
if [ "$lease_active" = 1 ]; then
    for n in $(seq 1 20); do
        sdevice_pid=$(pgrep -P "$runner_pid" -x sdevice || true)
        [ -n "$sdevice_pid" ] && break
        sleep 0.1
    done
    if [ -n "${sdevice_pid:-}" ]; then
        bash __LEASE_SCRIPT__ bind --lease-root __LEASE_ROOT__ --core "$lease_core" --token "$lease_token" --owner-pid "$sdevice_pid" >> __LEASE_STATE__
        actual_affinity=$(taskset -pc "$sdevice_pid" | sed -n 's/.*: //p' | tail -n 1)
        if [ "$actual_affinity" = "$lease_core" ]; then printf 'affinity_verification=VERIFIED\n' >> __LEASE_STATE__; else printf 'affinity_verification=MISMATCH:%s\n' "$actual_affinity" >> __LEASE_STATE__; exit 72; fi
    else
        printf 'affinity_verification=PROCESS_EXITED_BEFORE_BIND\n' >> __LEASE_STATE__
    fi
fi
set +e
wait "$runner_pid"
code=$?
set -e
end=$(date +%s)
printf '%s\n' "$code" > __EXIT_CODE__
printf '%s\n' "$((end-start))" > __WALL_TIME__
find . -maxdepth 1 -type f \( -name '*.plt' -o -name '*.log' -o -name '*.txt' -o -name '*.tdr' -o -name '*.sav' \) -printf '%f\n' | sort > __AVAILABLE__
exit 0
'@
    $remoteCommand = $remoteCommand.Replace('__INPUT_DIR__', (ConvertTo-PosixQuoted "$remoteRunDir/inputs"))
    $remoteCommand = $remoteCommand.Replace('__BIN_DIR__', (ConvertTo-PosixQuoted "$SentaurusRoot/bin"))
    $remoteCommand = $remoteCommand.Replace('__LEASE_SCRIPT__', (ConvertTo-PosixQuoted $remoteLeaseScript))
    $remoteCommand = $remoteCommand.Replace('__LEASE_ROOT__', (ConvertTo-PosixQuoted $policyLeaseRoot))
    $remoteCommand = $remoteCommand.Replace('__RESERVED_CORES__', $policyReservedQuoted)
    $remoteCommand = $remoteCommand.Replace('__MAX_MANAGED_SLOTS__', [string]$policyMaxSlots)
    $remoteCommand = $remoteCommand.Replace('__LOCK_TIMEOUT__', [string]$policyLockTimeout)
    $remoteCommand = $remoteCommand.Replace('__RUN_DIR__', (ConvertTo-PosixQuoted $remoteRunDir))
    $remoteCommand = $remoteCommand.Replace('__AUTO_LEASE__', $(if ($autoLeaseEnabled) { 'true' } else { 'false' }))
    $remoteCommand = $remoteCommand.Replace('__TIMEOUT__', [string]$TimeoutSeconds)
    $remoteCommand = $remoteCommand.Replace('__AFFINITY__', $(if ($CpuCore -ge 0) { "taskset --cpu-list $CpuCore" } else { '' }))
    $remoteCommand = $remoteCommand.Replace('__THREADS__', [string]$Threads)
    $remoteCommand = $remoteCommand.Replace('__DECK__', (ConvertTo-PosixQuoted $remoteDeck))
    $remoteCommand = $remoteCommand.Replace('__STDOUT__', (ConvertTo-PosixQuoted "$remoteRunDir/stdout.log"))
    $remoteCommand = $remoteCommand.Replace('__STDERR__', (ConvertTo-PosixQuoted "$remoteRunDir/stderr.log"))
    $remoteCommand = $remoteCommand.Replace('__EXIT_CODE__', (ConvertTo-PosixQuoted "$remoteRunDir/exit_code.txt"))
    $remoteCommand = $remoteCommand.Replace('__WALL_TIME__', (ConvertTo-PosixQuoted "$remoteRunDir/wall_time_seconds.txt"))
    $remoteCommand = $remoteCommand.Replace('__AVAILABLE__', (ConvertTo-PosixQuoted "$remoteRunDir/available_outputs.txt"))
    $remoteCommand = $remoteCommand.Replace('__LEASE_STATE__', (ConvertTo-PosixQuoted "$remoteRunDir/lease_state.txt"))
    $remoteCommand = $remoteCommand.Replace('__LEASE_RELEASE__', (ConvertTo-PosixQuoted "$remoteRunDir/lease_release.txt"))
    Invoke-RemoteScript $remoteCommand
    & scp -- "${VmUserHost}:$remoteRunDir/lease_state.txt" (Join-Path $localRunDir 'artifacts\lease_state.txt') 2>&1 | Out-Null
    if (Test-Path -LiteralPath (Join-Path $localRunDir 'artifacts\lease_state.txt')) {
        $leaseState = ConvertFrom-KeyValueLines (Get-Content -LiteralPath (Join-Path $localRunDir 'artifacts\lease_state.txt'))
        if ($leaseState.ContainsKey('core')) { $leaseCore = $leaseState.core; $CpuCore = [int] $leaseCore }
        if ($leaseState.ContainsKey('token')) { $leaseToken = $leaseState.token; $leaseAcquired = $true }
        if ($leaseState.ContainsKey('affinity_verification')) { $affinityVerification = $leaseState.affinity_verification }
    }
    & scp -- "${VmUserHost}:$remoteRunDir/lease_release.txt" (Join-Path $localRunDir 'artifacts\lease_release.txt') 2>&1 | Out-Null
    if (Test-Path -LiteralPath (Join-Path $localRunDir 'artifacts\lease_release.txt')) {
        $leaseRelease = ConvertFrom-KeyValueLines (Get-Content -LiteralPath (Join-Path $localRunDir 'artifacts\lease_release.txt'))
        if ($leaseRelease['released'] -eq 'true') { $leaseReleased = $true }
    }
    & scp -- "${VmUserHost}:$remoteRunDir/stdout.log" (Join-Path $localRunDir 'artifacts\stdout.log') 2>&1 | Out-Null
    & scp -- "${VmUserHost}:$remoteRunDir/stderr.log" (Join-Path $localRunDir 'artifacts\stderr.log') 2>&1 | Out-Null
    & scp -- "${VmUserHost}:$remoteRunDir/exit_code.txt" (Join-Path $localRunDir 'artifacts\exit_code.txt') 2>&1 | Out-Null
    & scp -- "${VmUserHost}:$remoteRunDir/wall_time_seconds.txt" (Join-Path $localRunDir 'artifacts\wall_time_seconds.txt') 2>&1 | Out-Null
    & scp -- "${VmUserHost}:$remoteRunDir/available_outputs.txt" (Join-Path $localRunDir 'artifacts\available_outputs.txt') 2>&1 | Out-Null
    $exitCode = (Get-Content -LiteralPath (Join-Path $localRunDir 'artifacts\exit_code.txt') -Raw).Trim()
    $wallSeconds = (Get-Content -LiteralPath (Join-Path $localRunDir 'artifacts\wall_time_seconds.txt') -Raw).Trim()
    if ($exitCode -eq '124') { $lifecycle = 'TIMED_OUT' } elseif ($exitCode -eq '0') { $lifecycle = 'SUCCEEDED' } else { $lifecycle = 'FAILED' }
    $available = Get-Content -LiteralPath (Join-Path $localRunDir 'artifacts\available_outputs.txt')
    foreach ($name in $available) {
        $isLarge = $name -match '\.(tdr|sav)$'
        $selectedLarge = $isLarge -and (Test-LargeArtifactSelected -Name $name -Patterns $LargeArtifactPattern)
        if ($isLarge -and -not $IncludeLargeArtifacts -and -not $selectedLarge) { continue }
        if ($name -match '^[A-Za-z0-9_.-]+$') {
            & scp -- "${VmUserHost}:$remoteRunDir/inputs/$name" (Join-Path $localRunDir "artifacts\$name") 2>&1 | Out-Null
        }
    }
}
catch {
    $failure = $_.Exception.Message
    Set-Utf8NoBomContent -Path (Join-Path $localRunDir 'artifacts\runner_error.txt') -Value ($failure + "`n")
}
finally {
    if ($leaseAcquired -and -not $leaseReleased -and $leaseCore -match '^\d+$' -and $leaseToken -match '^[a-f0-9]{32}$') {
        try {
            $releaseOutput = Invoke-RemoteLeaseScript -RemoteScriptPath $remoteLeaseScript -Arguments ("release --lease-root " + (ConvertTo-PosixQuoted $policyLeaseRoot) + " --core $leaseCore --token " + (ConvertTo-PosixQuoted $leaseToken))
            $releaseResult = ConvertFrom-KeyValueLines $releaseOutput
            if ($releaseResult['released'] -eq 'true') { $leaseReleased = $true }
        }
        catch {
            # The remote wrapper trap normally releases; preserve the original runner failure if this fallback cannot connect.
        }
    }
    $endedAt = Get-UtcIso
    $artifactDir = Join-Path $localRunDir 'artifacts'
    foreach ($file in Get-ChildItem -LiteralPath $artifactDir -File -ErrorAction SilentlyContinue) {
        $artifacts += Get-FileRecord $file.FullName (Join-Path 'artifacts' $file.Name)
    }
    $exactTdrHash = 'NA'
    if ($exactTdrExpected -ne 'NA') {
        $exactLeaf = [IO.Path]::GetFileName($exactTdrExpected)
        $exactRecord = $artifacts | Where-Object { [IO.Path]::GetFileName($_.relative_path) -eq $exactLeaf } | Select-Object -First 1
        if ($null -ne $exactRecord) { $exactTdrHash = $exactRecord.sha256 }
    }
    $manifest = [ordered]@{
        schema_version = 'sdevice_run_manifest/v1'; schema_extensions = @('igbt_seb_run_manifest/v1', 'igbt_mosfet_seb_paper/v1')
        run_id = $runId; execution_mode = $ExecutionMode
        worker_id = $WorkerId; case_id = $CaseId; attempt_id = $AttemptId; parent_run_id = $ParentRunId
        lifecycle = $lifecycle; started_at = $startedAt; ended_at = $endedAt; exit_code = $exitCode
        wall_time_seconds = $wallSeconds; local_run_dir = $localRunDir; remote_run_dir = $remoteRunDir
        sdevice_threads = $Threads; allocation_mode = $allocationMode
        cpu_core = if ($CpuCore -ge 0) { $CpuCore } else { 'UNPINNED' }
        lease_token = $leaseToken; lease_acquired = $leaseAcquired; lease_released = $leaseReleased
        lease_policy_path = $CorePolicyPath; lease_policy_sha256 = $policyHash; affinity_verification = $affinityVerification
        scheduling_evidence = [ordered]@{
            allocation_mode = $allocationMode; cpu_core = if ($CpuCore -ge 0) { $CpuCore } else { 'UNPINNED' }
            sdevice_threads = $Threads; lease_acquired = $leaseAcquired; lease_released = $leaseReleased
            affinity_verification = $affinityVerification; exit_code = $exitCode; wall_time_seconds = $wallSeconds
        }
        sdevice_command = "sdevice --threads $Threads $remoteDeck"
        deck_path = $DeckPath; parameter_path = $ParameterPath; metadata_path = $MetadataPath
        mesh_path = $MeshPath; probe_summary = $probeSummary; artifact_selection_patterns = @($LargeArtifactPattern)
        device_family = $deviceFamily; t_init_k = $tInitK; t_steady_k = $tSteadyK; t_steady_max_k = $tSteadyMaxK
        case_schema = [ordered]@{
            campaign_id = $campaignId; publication_profile = $publicationProfile; structure_id = $structureId
            device_family = $deviceFamily; high_terminal_name = $highTerminalName; bias_quantity = $biasQuantity
            target_bias_v = $targetBiasV; actual_bias_v = $actualBiasV; final_time_s = $finalTimeValue
            exact_final_tdr = $exactTdrExpected
            target_blocking_voltage_v = $targetBlockingVoltage; actual_blocking_voltage_v = $actualBlockingVoltage
            rated_voltage_v = $ratedVoltage; bv_static_v = $bvStaticVoltage; bv_criterion = $bvCriterion
            derating_basis = $deratingBasis; parent_restart_ids = @($parentRestartIds); parent_restart_hashes = @($parentRestartHashes)
            termination_reason = $terminationReason
        }
        target_bias_v = $targetBiasV; actual_bias_v = $actualBiasV
        target_vce_v = $targetVceV; actual_vce_v = $actualVceV
        let_mev_cm2_mg = $letValue; let_f_pc_um = $letFValue; track_y_um = $trackYValue
        track_length_um = $trackLengthValue; wt_hi_um = $wtHiValue; heavy_ion_time_s = $heavyIonTimeValue
        final_time_s = $finalTimeValue; time_end_s = $timeEndValue; mesh_variant = $meshVariantValue
        parent_restart_main_sha256 = $parentRestartMainSha; parent_restart_circuit_sha256 = $parentRestartCircuitSha
        exact_final_tdr = $exactTdrExpected; exact_final_tdr_sha256 = $exactTdrHash
        exact_2p1ns_tdr = $exactTdrExpected; exact_2p1ns_tdr_sha256 = $exactTdrHash
        field_audit_sha256 = $fieldAuditHash; extraction_sha256 = $extractionHash
        screenshot_manifest_sha256 = $screenshotManifestHash
        inputs = $inputs; artifacts = $artifacts
    }
    ConvertTo-JsonFile $manifest (Join-Path $localRunDir 'run_manifest.json')
    New-RunFragments (Join-Path $localRunDir 'fragments') $manifest
}
Write-Output "run_id=$runId lifecycle=$lifecycle local_run_dir=$localRunDir"
if ($lifecycle -eq 'FAILED') { exit 1 }