param(
  [ValidateSet('probe','pn-diode')]
  [string]$Mode = 'pn-diode',
  [string]$HostName = '192.168.137.131',
  [string]$User = 'tcad',
  [string]$RemoteRoot = '/home/tcad/codex_runs',
  [string]$LocalOut = '.\sentaurus_runs',
  [switch]$NoDownload
)

$ErrorActionPreference = 'Stop'
$target = "$User@$HostName"
$scriptName = "codex_sentaurus_runner_$([guid]::NewGuid().ToString('N')).sh"
$remoteScript = "/tmp/$scriptName"
$tmp = Join-Path ([IO.Path]::GetTempPath()) $scriptName

$bash = @'
set -euo pipefail
REMOTE_ROOT="${1:-$HOME/codex_runs}"
MODE="${2:-pn-diode}"
SENT_ROOT=/usr/synopsys/sentaurus/W-2024.09
SCL_BIN=/usr/synopsys/scl/scl2023/linux64/bin
export PATH="$SENT_ROOT/bin:$SCL_BIN:$PATH"
export LM_LICENSE_FILE="${LM_LICENSE_FILE:-27000@sentaurus}"
export SNPSLMD_LICENSE_FILE="${SNPSLMD_LICENSE_FILE:-27000@sentaurus}"

probe() {
  echo "HOST=$(hostname)"
  echo "USER=$USER"
  echo "SDE=$(command -v sde || true)"
  echo "SDEVICE=$(command -v sdevice || true)"
  echo "SWB=$(command -v swb || true)"
  lmutil lmstat -a -c 27000@sentaurus 2>&1 | sed -n '1,45p' || true
}

ensure_license() {
  if ! lmutil lmstat -a -c 27000@sentaurus 2>&1 | grep -q 'snpslmd: UP'; then
    echo 'license: snpslmd not UP, running lmreread'
    lmutil lmreread -c /usr/synopsys/scl/scl2023/synopsys.dat >/dev/null 2>&1 || true
    sleep 2
  fi
  lmutil lmstat -a -c 27000@sentaurus 2>&1 | grep -q 'snpslmd: UP'
}

if [ "$MODE" = probe ]; then
  probe
  exit 0
fi

ensure_license
SRC="$SENT_ROOT/tcad/W-2024.09/Applications_Library/GettingStarted/sdevice/3Ddiode_demo"
RUN="$REMOTE_ROOT/pn_diode_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$RUN"
cp "$SRC"/* "$RUN"/
cd "$RUN"
python3 - <<'PY'
from pathlib import Path
Path('sde_direct.cmd').write_text(Path('sde_dvs.cmd').read_text().replace('@node@','1'))
base = '''File {
  Grid=      "n1_msh.tdr"
  Current=   "__NAME__.plt"
  Plot=      "__NAME__.tdr"
  Output=    "__NAME__.log"
}

Electrode {
  { Name = "top"  Voltage = 0 Resist = __RES__ }
  { Name = "bottom"  Voltage = 0 }
}

Physics {
  Temperature = __TEMP__
  Mobility( PhuMob HighFieldSaturation(GradQuasiFermi) )
  Recombination (SRH __AVA__)
  EffectiveIntrinsicDensity ( BandGapNarrowing (oldSlotboom) )
  Fermi
}

Plot {
  TotalCurrent/Vector eCurrent/Vector hCurrent/Vector
  ElectricField/Vector Potential SpaceCharge
  ImpactIonization eImpactIonization hImpactIonization
}

Math {
  Transient = BE
  eMobilityAveraging = ElementEdge
  hMobilityAveraging = ElementEdge
  ElementVolumeAvalanche
  AvalFlatElementExclusion = 1.
  ParallelToInterfaceInBoundaryLayer(FullLayer -ExternalBoundary)
  ComputeGradQuasiFermiAtContacts= UseQuasiFermi
  WeightedVoronoiBox
  AutoCNPMinStepFactor = 0
  AutoNPMinStepFactor = 0
  -PlotLoadable
  SimStats
  ExitOnFailure
  Digits = 5
  ErrRef(electron) = 1e8
  ErrRef(hole) = 1e8
  Iterations = 10
  NotDamped = 100
  RHSMin = 1e-8
  EquilibriumSolution(Iterations=100)
  Extrapolate
  RefDens_eGradQuasiFermi_ElectricField_HFS = 1e8
  RefDens_hGradQuasiFermi_ElectricField_HFS = 1e8
  Method = ParDiSo
  NumberOfThreads = 4
  ParallelLicense (Wait)
  Wallclock
}

Solve {
  Coupled (Iterations = 100 LineSearchDamping = 1e-4){ Poisson }
  Coupled (Iterations = 100){ Poisson Electron Hole }
  Quasistationary (
    InitialStep = 1e-3 Increment = 1.41
    MinStep = 1e-7 MaxStep = 0.1
    Goal { Name = "top" Voltage = __VDD__ }
  ) { Coupled { Poisson Electron Hole } }
}
'''
def write(name, temp, vdd, res, ava):
    Path(name + '.cmd').write_text(base.replace('__NAME__', name).replace('__TEMP__', str(temp)).replace('__VDD__', str(vdd)).replace('__RES__', str(res)).replace('__AVA__', ava))
write('forward', 300, 10, '1', '')
write('reverse', 400, -1000, '1e7', 'Avalanche')
PY
sde -e -l sde_direct.cmd > sde_stdout.log 2>&1
sdevice forward.cmd > forward_stdout.log 2>&1
sdevice reverse.cmd > reverse_stdout.log 2>&1
cat > SUMMARY.txt <<EOF
PN diode Sentaurus run
Run dir: $RUN
Source example: $SRC
Official doc: $SENT_ROOT/tcad/W-2024.09/Sentaurus_Training/sd/sd_9.html

Forward final point:
$(grep -A4 'Contact              Voltage' forward_stdout.log | tail -4)

Reverse final point:
$(grep -A4 'Contact              Voltage' reverse_stdout.log | tail -4)
EOF
echo "$RUN" > "$REMOTE_ROOT/LAST_PN_DIODE_RUN"
echo "RUN=$RUN"
cat SUMMARY.txt
'@

[IO.File]::WriteAllText($tmp, $bash, [Text.UTF8Encoding]::new($false))
try {
  scp -q $tmp "$target`:$remoteScript"
  ssh -o BatchMode=yes -o ConnectTimeout=8 $target "bash '$remoteScript' '$RemoteRoot' '$Mode'"
  if ($Mode -eq 'pn-diode' -and -not $NoDownload) {
    $run = (ssh -o BatchMode=yes $target "cat '$RemoteRoot/LAST_PN_DIODE_RUN'").Trim()
    $name = Split-Path $run -Leaf
    $root = Resolve-Path -LiteralPath $LocalOut -ErrorAction SilentlyContinue
    if (-not $root) { $root = (New-Item -ItemType Directory -Force -Path $LocalOut).FullName }
    $dest = Join-Path $root $name
    New-Item -ItemType Directory -Force -Path $dest | Out-Null
    'SUMMARY.txt','sde_direct.cmd','forward.cmd','reverse.cmd','n1_msh.tdr','forward.plt','reverse.plt','forward.tdr','reverse.tdr','sde_stdout.log','forward_stdout.log','reverse_stdout.log' | ForEach-Object {
      scp -q "$target`:$run/$_" "$dest\"
    }
    Write-Host "LOCAL=$dest"
  }
}
finally {
  Remove-Item -LiteralPath $tmp -ErrorAction SilentlyContinue
  ssh -o BatchMode=yes -o ConnectTimeout=3 $target "rm -f '$remoteScript'" 2>$null | Out-Null
}
