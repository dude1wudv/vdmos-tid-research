# SDevice core scheduling

## Responsibility and scope

`config/sentaurus-core-policy.json` and `scripts/sdevice_core_lease.sh` provide a project-level, VM-side lease for independent SDevice jobs. `scripts/run_igbt_seb_case.ps1` is the enforced project entry point: for `-Threads 1` and no explicit CPU override, it acquires one VM core before SDevice starts and releases it when the run exits. Other new project SDevice entry points must use this lease manager; do not start bare concurrent SDevice jobs.

Skill selection is semantic guidance, not a system hook. The actual automatic allocation boundary is every simulation launched through `run_igbt_seb_case.ps1` with its default `-CpuCore -1`.

## State and allocation

Lease files are stored on the VM under the policy `lease_root`, protected by `flock`. Each file records a core, opaque token, owner PID, remote run directory, and creation time. Allocation is fail-closed: it removes reserved cores; caps managed slots; examines online cores on the VM; then removes cores in every unmanaged SDevice affinity. A fully unpinned unmanaged SDevice excludes all its allowed cores, so no managed job starts.

No TTL exists. Stale lease cleanup deletes only files whose recorded owner PID does not exist. The runner initially records its remote wrapper PID and then binds the lease to the SDevice PID after it starts; this prevents time-based recovery of a still-running job after an SSH interruption.

## Throughput profile

The active `max_8_single_thread_sdevice` policy reserves core 0 for VM/system work and sets `max_managed_slots` to 8. This is a maximum number of independent, single-thread SDevice jobs, **not** a VM topology declaration: the allocator discovers all online guest CPUs dynamically and may select any safe non-reserved CPU. It excludes existing leases and every CPU in an unmanaged SDevice process's affinity before allocation. If fewer than eight safe CPUs remain, new jobs fail closed rather than sharing a core.

## Parallel versus dependent work

Independent cases may run concurrently only as separate single-thread jobs (`sdevice --threads 1`) using leases. Cases that consume another case's mesh, restart state, or extracted result are a dependency chain and must run serially. `-CpuCore <n>` remains an explicit compatibility/debug override; `-DisableAutoCpuLease` is an explicit unpinned escape hatch and must not be used for concurrent runs.

## Manifest evidence

The runner manifest records `allocation_mode`, `cpu_core`, `lease_token`, `lease_acquired`, `lease_released`, `lease_policy_path`, `lease_policy_sha256`, and `affinity_verification`, in addition to thread count and normal run evidence. An acquire error aborts rather than running without affinity.

## Recovery and operator commands

Inspect state without modifying jobs:

```bash
bash sdevice_core_lease.sh status \
  --lease-root /home/tcad/.cache/vdmos-sdevice-core-leases \
  --lock-timeout-seconds 20
```

A release needs both the exact core and token returned by `acquire`:

```bash
bash sdevice_core_lease.sh release \
  --lease-root /home/tcad/.cache/vdmos-sdevice-core-leases \
  --core 4 --token <32-hex-token>
```

Never delete a lease just because it is old. First check its owner process and run directory; only a lease with a missing owner PID is automatically recoverable.