from pathlib import Path
import argparse
import csv
import json
import re
import time
import urllib.parse
import urllib.request
import urllib.error
import sys

ROOT = Path(__file__).resolve().parents[1]
KEYWORDS = ROOT / "02_search" / "keywords.yml"
OUT_JSONL = ROOT / "03_metadata" / "openalex_results.jsonl"
OUT_CSV = ROOT / "03_metadata" / "openalex_results.csv"
PDF_DIR = ROOT / "04_pdfs"


def read_queries(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    queries = []
    in_queries = False
    for line in text.splitlines():
        if line.strip() == "queries:":
            in_queries = True
            continue
        if in_queries and re.match(r"^[A-Za-z_]+:", line):
            break
        m = re.match(r"\s*-\s*['\"]?(.*?)['\"]?\s*$", line)
        if in_queries and m:
            queries.append(m.group(1))
    return queries


def get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "VDMOS_TID_Research/0.1 (mailto:example@example.com)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def search(query: str, per_page: int) -> list[dict]:
    params = urllib.parse.urlencode({"search": query, "per-page": per_page})
    data = get_json(f"https://api.openalex.org/works?{params}")
    return data.get("results", [])


def simplify(item: dict, query: str) -> dict:
    loc = item.get("best_oa_location") or {}
    authors = "; ".join(a.get("author", {}).get("display_name", "") for a in item.get("authorships", [])[:8])
    primary = item.get("primary_location") or {}
    source = primary.get("source") or {}
    return {
        "query": query,
        "title": item.get("title") or "",
        "year": item.get("publication_year") or "",
        "doi": item.get("doi") or "",
        "openalex_id": item.get("id") or "",
        "venue": source.get("display_name", ""),
        "authors": authors,
        "cited_by_count": item.get("cited_by_count") or 0,
        "is_oa": item.get("open_access", {}).get("is_oa", False),
        "pdf_url": loc.get("pdf_url") or "",
        "landing_page_url": loc.get("landing_page_url") or "",
    }


def safe_name(title: str) -> str:
    return re.sub(r"[^A-Za-z0-9\u4e00-\u9fff]+", "_", title).strip("_")[:120] or "paper"


def download_pdf(row: dict) -> str:
    url = row.get("pdf_url")
    if not url:
        return ""
    PDF_DIR.mkdir(exist_ok=True)
    dst = PDF_DIR / f"{safe_name(str(row.get('title', 'paper')))}.pdf"
    if dst.exists():
        return str(dst.relative_to(ROOT))
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "VDMOS_TID_Research/0.1"})
        with urllib.request.urlopen(req, timeout=45) as r:
            data = r.read(30_000_000)
        if data[:4] != b"%PDF":
            return ""
        dst.write_bytes(data)
        return str(dst.relative_to(ROOT))
    except Exception:
        return ""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-results", type=int, default=20)
    ap.add_argument("--download", action="store_true")
    args = ap.parse_args()

    rows = []
    seen = set()
    per_query = max(1, min(args.max_results, 50))
    for q in read_queries(KEYWORDS):
        try:
            items = search(q, per_query)
        except urllib.error.HTTPError as e:
            print(f"warning: OpenAlex query failed ({e.code}) for {q}", file=sys.stderr)
            continue
        except Exception as e:
            print(f"warning: OpenAlex query failed ({e}) for {q}", file=sys.stderr)
            continue
        for item in items:
            row = simplify(item, q)
            key = row["doi"] or row["openalex_id"] or row["title"].lower()
            if key in seen:
                continue
            seen.add(key)
            if args.download:
                row["local_pdf"] = download_pdf(row)
            rows.append(row)
        time.sleep(0.2)

    OUT_JSONL.parent.mkdir(exist_ok=True)
    with OUT_JSONL.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    with OUT_CSV.open("w", newline="", encoding="utf-8-sig") as f:
        fields = list(rows[0]) if rows else ["title"]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"results: {len(rows)}")
    print(f"jsonl: {OUT_JSONL}")
    print(f"csv: {OUT_CSV}")


if __name__ == "__main__":
    main()
