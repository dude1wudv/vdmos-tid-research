# AGENTS.md

## Project Defaults

- Explain and write study notes in Simplified Chinese unless asked otherwise.
- Keep root clean. Put private packages, VM logs, raw run outputs, and large TCAD artifacts under ignored `local_runtime/`.
- Before reading large PDFs, decks, logs, or generated files, check size or line count first; use ranges/search instead of whole-file reads.

## Paper Reading

Use `academic-research-suite` Paper Reading Notes Mode. Use the `pdf` skill for PDFs.

Trigger examples: `读论文`, `继续读论文`, `一段一段读`, `边读边记笔记`, `翻译并解释这篇论文`, or any paper path/DOI/title with guided reading, translation, Q&A, explanation, or Markdown notes.

Workflow:

1. Locate the paper and inspect PDF size/page count first.
2. Create or reuse `<paper-stem>.reading-notes.md` and `<paper-stem>.workbook.md` next to the paper.
3. Read 1-2 pages or one logical subsection per chunk.
4. In chat, give position, concise explanation, key terms, VDMOS/TID relevance, and next suggested chunk.
5. Append the same chunk to notes before replying. Append user Q&A to `.reading-notes.md`.

## Sentaurus / TCAD

- Use `sentaurus-vm-runner` for VM probes, Sentaurus launches, SDE/SDevice runs, and artifact copies.
- Default VM: `tcad@192.168.137.131`; default Sentaurus root: `/usr/synopsys/sentaurus/W-2024.09`.
- Prefer isolated remote runs under `/home/tcad/codex_runs/<case>_<timestamp>`.
- Use `swbunpack -d <folder> <package.gzp>` for Workbench packages; do not unpack `.gzp` manually unless diagnosing.
- For GUI Workbench on the VM desktop, use `DISPLAY=:0.0 swb <project-dir>`.
- Report evidence: remote path, local artifact path, license status, node status, and any convergence warnings.
