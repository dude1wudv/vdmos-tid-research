---
name: sentaurus-parallel-core-scheduler
description: Automatically schedule independent Sentaurus SDevice simulations on separate VM CPU cores with one thread per case. Use for every project SDevice run, parameter sweep, LET scan, temperature scan, bias scan, or concurrent TCAD batch. Keep mesh/restart dependency chains serial and launch project cases through scripts/run_igbt_seb_case.ps1 so core leasing is enforced and audited.
---

# Sentaurus Parallel Core Scheduler

Use this project skill whenever starting or resuming an SDevice simulation. The scheduling rule is automatic at the runner boundary; callers normally do not choose CPU cores.

## Required execution path

Run project SDevice cases through `scripts/run_igbt_seb_case.ps1` with its defaults:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_igbt_seb_case.ps1 `
  -CaseId <case-id> `
  -AttemptId <attempt-id> `
  -ExecutionMode PARALLEL_EXPLORATORY `
  -DeckPath <deck.cmd> `
  -ParameterPath <sdevice.par> `
  -MeshPath <mesh.tdr> `
  -Threads 1
```

Do not pass `-CpuCore` for normal work. With `-Threads 1`, the runner automatically acquires an exclusive VM core lease, launches `sdevice --threads 1` through `taskset`, verifies affinity, records evidence, and releases the lease on exit.

## Decide whether cases may run concurrently

Cases may run concurrently only when all conditions hold:

- every required mesh, parameter, restart, and deck input already exists;
- no case consumes an output that another running case is still producing;
- each case uses the runner's isolated local and remote run directories;
- each case is a separate SDevice process with `-Threads 1`;
- the VM-side lease succeeds for every case.

Keep these chains serial:

```text
mesh generation -> DC calibration -> restart creation -> dependent transient -> extraction
```

Independent parameter points after their shared immutable parent inputs exist may run in parallel:

```text
completed restart -> LET 1.5 transient
                  -> LET 15 transient
                  -> LET 150 transient
```

## Fail-closed rules

- Never start a bare concurrent `sdevice` command.
- Never use `-DisableAutoCpuLease` for concurrent work.
- Use explicit `-CpuCore <n>` only for recovery or compatibility work with recorded justification.
- If allocation reports no safe core, wait for a lease to release; do not bypass the allocator.
- Preserve failed run manifests and `runner_error.txt`; do not silently retry under the same run ID.
- Do not infer independence only from different case names. Verify the input/output dependency direction first.

## Project files

- Policy: `config/sentaurus-core-policy.json`
- Atomic VM lease manager: `scripts/sdevice_core_lease.sh`
- Enforced runner: `scripts/run_igbt_seb_case.ps1`
- Scheduling semantics and recovery: `team_setup/skills/sentaurus-vm-runner/references/core-scheduling.md`
- Team-installable skill: `team_setup/skills/sentaurus-vm-runner/SKILL.md`

The current `max_8_single_thread_sdevice` throughput profile reserves core 0 for the VM/system and allows **at most eight** managed single-thread SDevice jobs. The allocator discovers the VM's online CPUs dynamically; the number eight is a concurrency ceiling, not a claim that the VM has exactly eight CPUs or that cores `0-7` are the candidate set. It excludes affinity occupied by unmanaged SDevice processes, excludes existing leases, and stores leases under the configured VM cache directory. A fully occupied/unsafe VM fails closed. Change policy only when the VM resource budget changes, not per simulation.

## Evidence required at closure

For each run, report and retain:

- `allocation_mode` and `cpu_core`;
- `sdevice_threads=1`;
- `lease_acquired=true` and `lease_released=true`;
- `affinity_verification=VERIFIED`;
- lifecycle, exit code, wall time, run ID, and input hashes.

A run is not considered safely scheduled if affinity or lease evidence is missing, unless it is an explicitly documented legacy run created before this scheduler.