---
name: sentaurus-vm-runner
description: Run Synopsys Sentaurus TCAD simulations on the local Linux VM over SSH. Use when the user asks Codex to connect to tcad@192.168.137.131, start or diagnose Sentaurus/SDevice/SDE/SWB, run PN diode or other TCAD examples, recover FlexNet license daemon issues, copy simulation artifacts back to Windows, or automate repeatable Sentaurus experiments from Codex.
---

# Sentaurus VM Runner

## Quick path

Use `scripts/run_pn_diode.ps1` first for smoke tests and the built-in 3D PN diode example:

```powershell
# Probe SSH, Sentaurus commands, and FlexNet status only
powershell -ExecutionPolicy Bypass -File "$env:CODEX_HOME\skills\sentaurus-vm-runner\scripts\run_pn_diode.ps1" -Mode probe

# Run the official 3D diode example and download artifacts
powershell -ExecutionPolicy Bypass -File "$env:CODEX_HOME\skills\sentaurus-vm-runner\scripts\run_pn_diode.ps1" -Mode pn-diode -LocalOut .\sentaurus_runs
```

Default VM: `tcad@192.168.137.131`. Default Sentaurus root: `/usr/synopsys/sentaurus/W-2024.09`.

## Workflow

1. Start with `-Mode probe` unless a fresh probe was already run in this turn.
2. If `swb`/`sdevice` reports FlexNet daemon down, run `lmutil lmreread -c /usr/synopsys/scl/scl2023/synopsys.dat`; no sudo is required on this VM.
3. Prefer headless direct runs over Workbench GUI:
   - `sde -e -l <scheme>.cmd` for mesh/structure generation.
   - `sdevice <deck>.cmd` for electrical simulation.
   - Avoid relying on `swb` over plain SSH; it needs `$DISPLAY`.
4. Put remote runs under `/home/tcad/codex_runs/<case>_<timestamp>` and copy compact artifacts back to the workspace.
5. Report evidence: remote run directory, local artifact directory, final contact-current lines, and whether license status was recovered.

## Known-good built-in example

Use this official application-library case for PN diode smoke tests:

```text
/usr/synopsys/sentaurus/W-2024.09/tcad/W-2024.09/Applications_Library/GettingStarted/sdevice/3Ddiode_demo
```

Documentation redirect:

```text
/usr/synopsys/sentaurus/W-2024.09/tcad/W-2024.09/Sentaurus_Training/sd/sd_9.html
```

Read `references/pn-diode.md` only when modifying the diode flow or explaining the generated artifacts.

## Guardrails

- Check file size before whole-file reads of logs or `.cmd` decks over 500 lines.
- Redact license signatures and keys if printing license files.
- Do not edit `/usr/synopsys/...` examples in place; copy to `~/codex_runs` first.
- If the VM IP changes, update command parameters; do not change the skill for one-off IP drift.