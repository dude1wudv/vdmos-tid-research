from pathlib import Path
import csv
import re

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "01_seed_papers"
PAPERS = ROOT / "papers"
MATRIX = ROOT / "06_synthesis" / "literature_matrix.csv"

ROLES = {
    "01_device_background": "VDMOS / trench power MOSFET device background",
    "02_tid_foundation": "Total ionizing dose foundation",
    "03_vdmos_tid": "VDMOS under total ionizing dose",
}


def slug(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9\u4e00-\u9fff]+", "_", name).strip("_")
    return s[:100] or "paper"


def title_from_pdf(pdf: Path) -> str:
    return pdf.stem.replace("_", " ")


def make_note(pdf: Path, role: str) -> Path:
    rel = pdf.relative_to(ROOT).as_posix()
    out = PAPERS / f"{slug(pdf.stem)}.md"
    if out.exists():
        return out
    out.write_text(f"""# {title_from_pdf(pdf)}

- Source PDF: `{rel}`
- Role: {role}
- Status: unread

## Bibliographic metadata

- Authors:
- Year:
- Venue:
- DOI:
- Keywords:

## Reading checklist

- [ ] Device type identified
- [ ] Irradiation source / dose / dose rate extracted
- [ ] Bias / temperature / annealing conditions extracted
- [ ] Electrical degradation metrics extracted
- [ ] TID mechanism claims separated from evidence
- [ ] Reusable experiment flow summarized

## Analysis

### 1. Paper positioning

### 2. Device type

### 3. Irradiation experiment

### 4. Measurement metrics

### 5. Mechanism attribution

### 6. Key figures and tables

### 7. Reproducible experiment flow

### 8. Value for VDMOS TID research

### 9. Glossary

### 10. Unverified items

""", encoding="utf-8")
    return out


def main() -> None:
    PAPERS.mkdir(exist_ok=True)
    rows = []
    for folder, role in ROLES.items():
        for pdf in sorted((SEED / folder).glob("*.pdf")):
            note = make_note(pdf, role)
            rows.append({
                "title": title_from_pdf(pdf),
                "role": role,
                "pdf_path": pdf.relative_to(ROOT).as_posix(),
                "note_path": note.relative_to(ROOT).as_posix(),
                "device": "",
                "tid_conditions": "",
                "metrics": "",
                "mechanisms": "",
                "status": "unread",
            })
    MATRIX.parent.mkdir(exist_ok=True)
    with MATRIX.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["title"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"seed papers: {len(rows)}")
    print(f"matrix: {MATRIX}")


if __name__ == "__main__":
    main()
