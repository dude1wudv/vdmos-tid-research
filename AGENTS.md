# Repository Guidelines

## Project Structure & Module Organization

This repository is a VDMOS / power MOSFET total ionizing dose (TID) literature and TCAD workspace. Keep tracked research outputs organized by stage:

- `01_seed_papers/`: seed-paper notes and derived reading materials; raw PDFs are ignored.
- `02_search/`: search keywords and query strings.
- `03_metadata/`: OpenAlex or paper-search metadata outputs.
- `papers/`: per-paper research cards.
- `05_notes/` and `06_synthesis/`: close-reading notes, matrices, mechanism maps, and synthesis summaries.
- `docs/`: setup notes and change logs, including Sentaurus VM documentation.
- `scripts/`: small Python and PowerShell helpers.
- `prompts/`: reusable analysis prompts.
- `local_runtime/`: ignored private packages, VM logs, raw runs, extracts, and TCAD artifacts.

## Build, Test, and Development Commands

There is no build system. Useful local commands are:

```powershell
python scripts\search_openalex.py --max-results 20
python scripts\import_seed_papers.py
powershell -ExecutionPolicy Bypass -File scripts\run_paper_search_mcp.ps1 -Query "VDMOS total ionizing dose" -Limit 20
powershell -ExecutionPolicy Bypass -File scripts\analyze_with_codex.ps1 -Model gpt-5.5
```

`search_openalex.py` refreshes `03_metadata/`; `import_seed_papers.py` creates paper cards and updates `06_synthesis/literature_matrix.csv`; the PowerShell wrappers run optional MCP/Codex-assisted analysis.

## Coding Style & Naming Conventions

Prefer short, dependency-light scripts. Current Python uses the standard library, 4-space indentation, `Path` objects, UTF-8 file I/O, and lowercase snake_case functions. Name paper notes with stable descriptive slugs, for example `Oldham_McLean_2003_...reading-notes.md`. Keep Markdown headings clear and use Chinese explanations for study notes unless asked otherwise.

## Testing Guidelines

No formal test suite exists. Validate changed scripts with the smallest safe run, for example `python scripts\search_openalex.py --max-results 2`. Before reading large PDFs, decks, logs, generated files, or Workbench packages, inspect size/page count first and use targeted ranges or search.

## New TCAD Project Workflow

When starting a new chip simulation project, use the reverse-engineered reference workflow in `docs/changes/2026-07-09-tcad-reference-workflow/` before writing decks. Treat `Trench VDMOS.gzp` as the learned reference flow, not as a file to copy blindly.

Minimum sequence:

1. Receive the chip document and first extract a parameter/unknowns table: structure, dimensions, materials, doping, electrodes, test conditions, irradiation conditions, and pre/post irradiation measured curves.
2. Build the SDE physical model from chip facts: geometry, regions, contacts, doping, mesh, and Oxide/Silicon interface placement.
3. Run and calibrate the pre-irradiation simulation first. Match the initial `Id-Vg` / Vth behavior before introducing TID damage parameters.
4. Fit the post-irradiation curve by scanning TID-equivalent parameters such as `Not` fixed oxide charge and `Nit` interface traps, while keeping the calibrated base structure stable.
5. Archive evidence for every useful run: actual `.cmd` deck, `.plt` curve, `.log` / stdout, `.tdr` where needed, parsed CSV, plots, and a Markdown report.

Do not invent missing chip parameters. Mark them as `待用户确认`, ask for the missing data, or use the reference project only as a clearly labeled temporary assumption.

## Commit & Pull Request Guidelines

Git history uses concise subjects, often Conventional Commit style such as `docs(tid): add vdmos simulation notes`. Prefer `type(scope): imperative summary` for research updates. PRs should state changed folders, source data used, generated artifacts, and whether raw/private files stayed under ignored paths. Link issues when available and include screenshots only for UI or visual TCAD evidence.

## Security, Data, and Agent-Specific Notes

Do not commit raw PDFs, VM credentials, private packages, or large Sentaurus outputs. Use `academic-research-suite` plus `pdf` for guided paper reading. Use `sentaurus-vm-runner` for VM probes and TCAD runs; default VM is `tcad@192.168.137.131`, with isolated remote runs under `/home/tcad/codex_runs/<case>_<timestamp>`.
