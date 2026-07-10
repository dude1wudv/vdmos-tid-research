# VDMOS TID Research

A minimal literature-research workspace for VDMOS / power MOSFET total ionizing dose (TID) studies.

## Contents

```text
01_seed_papers/    Seed-paper reading notes and derived study materials (raw PDFs excluded)
02_search/         Search keywords and query strings
03_metadata/       OpenAlex/Crossref/Semantic Scholar style metadata outputs
05_notes/          Manual or generated close-reading notes
papers/            ARIS/research-wiki style paper cards
06_synthesis/      Literature matrix, mechanism map, and synthesis notes
docs/vm_setup/     Reproducible VM/Sentaurus setup notes
scripts/           Import/search/analysis helper scripts
prompts/           Reusable paper-analysis prompts
local_runtime/     Ignored local VM logs, packages, and simulation outputs
```

## Quick start

```powershell
python scripts\search_openalex.py --max-results 20
```

Optional: place locally obtained PDFs in `00_inbox/` or `01_seed_papers/` and import them with:

```powershell
python scripts\import_seed_papers.py
```

## Scope

Current focus:

- VDMOS / power MOSFET / trench power MOSFET device structures;
- total ionizing dose effects in MOS/VDMOS devices;
- threshold-voltage shift, leakage, mobility, subthreshold swing, and on-resistance degradation;
- oxide trapped charge, interface traps, border traps, annealing, and bias-condition mechanisms.

Raw paper PDFs and local VM/Sentaurus simulation artifacts stay under ignored local folders unless intentionally promoted into tracked docs.

## 小组环境安装

Windows、VMware、SSH、Sentaurus 和 Codex Skill 的小组共享配置见 [`team_setup/README.md`](team_setup/README.md)。
