# Sentaurus VM Notes

## Current VM

- SSH: `tcad@192.168.137.131`
- Sentaurus root: `/usr/synopsys/sentaurus/W-2024.09`
- Workbench GUI display: `DISPLAY=:0.0`
- License check command:

```bash
/usr/synopsys/scl/scl2023/linux64/bin/lmutil lmstat -c /usr/synopsys/scl/scl2023/synopsys.dat
```

## Trench VDMOS TID Example

Local package is ignored at:

```text
local_runtime/tcad_projects/Trench VDMOS.gzp
```

Imported on the VM at:

```text
/home/tcad/codex_runs/trench_vdmos_tid_20260707_230904/stdb/CTD03N004
```

Workbench launch:

```bash
DISPLAY=:0.0 /usr/synopsys/sentaurus/W-2024.09/bin/swb /home/tcad/codex_runs/trench_vdmos_tid_20260707_230904/stdb/CTD03N004
```

Package import pattern:

```bash
mkdir -p /home/tcad/codex_runs/<case>/stdb
swbunpack -d /home/tcad/codex_runs/<case>/stdb <package.gzp>
```

## Project Flow

- `sde_dvs.cmd`: geometry, doping, contacts, and mesh for the trench-gate VDMOS.
- `sdevice_des.cmd`: baseline Id-Vg simulation with fixed interface charge.
- `TID_des.cmd`: TID sweep using oxide/interface charge parameters `Not` and `Nit`.
- Main bias flow: set `Vd=0.1 V`, initialize `Vg=-2 V`, then sweep `Vg` to `5 V`.

Observed quick-read result: increasing `Not/Nit` shifts the apparent threshold negative for the valid Id-Vg nodes. `n18_des.log` contains `Solve for t=0 does not converge`; treat that node carefully before using it as physics evidence.
