#!/usr/bin/env python3
"""Download paper PDFs and extract their FULL TEXT — the source the librarian
compiles wiki pages from. This is the primary, Docker-free extraction path
(GROBID via `grobid_extract.py` is now an optional enrichment, not a hard dep).

Files are named by a readable title slug (vault_io.slugify); the stable arxiv_id
lives inside the meta json. For each candidate it:
  1. downloads the PDF        -> <vault>/raw/paper/<slug>.pdf   (immutable)
  2. extracts full text       -> <vault>/raw/text/<slug>.txt
  3. writes meta              -> <vault>/raw/meta/<slug>.json
     (arxiv_id, slug, full_text_chars, n_pages, toc, extractor; arXiv fields kept)

Text extraction uses PyMuPDF (`pip install pymupdf`). Resume-safe: a paper whose
pdf+text already exist is skipped. Single-paper failures are logged and skipped
(batch continues) per PLAN.md 3.5 graceful degradation; only argument/registry
errors abort.

  python pdf_extract.py --candidates kept.json --direction agent-harness
  python pdf_extract.py --candidates kept.json --vault data/vaults/agent-harness --limit 5
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import vault_io  # noqa: E402

# Contact email read from ARXIV_CONTACT_EMAIL (loaded from .env by run_daily_ingest.sh).
_CONTACT_EMAIL = os.environ.get("ARXIV_CONTACT_EMAIL", "research@example.com")
UA = f"auto-research-wiki/0.1 (+https://github.com/; mailto:{_CONTACT_EMAIL})"
DELAY = 3.0          # politeness between downloads
RETRIES = 4
MAX_BACKOFF = 60.0
MIN_PDF_BYTES = 1500  # smaller than this is almost certainly an error page


def _download(url: str, dest: Path) -> int:
    """Download to dest with UA + backoff. Returns bytes written."""
    backoff = DELAY
    last: Exception | None = None
    for attempt in range(RETRIES):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=120) as r:
                data = r.read()
            if len(data) < MIN_PDF_BYTES or not data[:5].startswith(b"%PDF"):
                raise ValueError(f"not a PDF ({len(data)} bytes)")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            return len(data)
        except (urllib.error.HTTPError, urllib.error.URLError,
                TimeoutError, ValueError) as exc:
            last = exc
            if attempt < RETRIES - 1:
                print(f"  retry {attempt + 1}/{RETRIES} ({exc}) in {backoff:.0f}s",
                      file=sys.stderr)
                time.sleep(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF)
    raise last  # type: ignore[misc]


def _extract_text(pdf: Path) -> tuple[str, int, list]:
    """Return (full_text, n_pages, toc) using PyMuPDF."""
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("PyMuPDF required: pip install pymupdf") from exc
    doc = fitz.open(pdf)
    try:
        parts = []
        for page in doc:
            t = page.get_text("text")
            if t:
                parts.append(t)
        toc = [[lvl, title, pno] for lvl, title, pno in doc.get_toc()]
        return ("\n".join(parts).strip(), doc.page_count, toc)
    finally:
        doc.close()


def _candidate_pdf_urls(c: dict) -> list[str]:
    """Ordered list of PDF URLs to try. arXiv's *versioned* path (…vN) sometimes
    404s even when the unversioned and export-host paths serve fine, so we fall
    back across all of them instead of failing the paper. De-duplicated, order
    preserved."""
    aid = c["arxiv_id"]
    cand = c.get("pdf_url")
    urls: list[str] = []
    if cand:
        urls.append(cand)
        # If the given URL is version-pinned (…vN), try the unversioned form too.
        stripped = re.sub(r"v\d+$", "", cand)
        if stripped != cand:
            urls.append(stripped)
    urls.append(f"https://arxiv.org/pdf/{aid}")
    urls.append(f"https://export.arxiv.org/pdf/{aid}")
    seen: set[str] = set()
    return [u for u in urls if not (u in seen or seen.add(u))]


def _download_any(urls: list[str], dest: Path) -> int:
    """Try each URL in turn; return bytes on the first success. Raises the last
    error only if all fail. A 404 on one URL falls through to the next."""
    last: Exception | None = None
    for j, url in enumerate(urls):
        try:
            return _download(url, dest)
        except (urllib.error.HTTPError, urllib.error.URLError,
                TimeoutError, ValueError) as exc:
            last = exc
            if j < len(urls) - 1:
                print(f"  url {j + 1}/{len(urls)} failed ({exc}); trying next",
                      file=sys.stderr)
    raise last  # type: ignore[misc]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidates", required=True,
                    help="JSON list with arxiv_id (+ optional pdf_url)")
    ap.add_argument("--direction")
    ap.add_argument("--vault")
    ap.add_argument("--registry")
    ap.add_argument("--limit", type=int, help="cap number processed (debug)")
    ap.add_argument("--delay", type=float, default=DELAY)
    args = ap.parse_args()

    v = vault_io.resolve_vault(direction=args.direction, vault=args.vault,
                               registry=args.registry)
    v.raw_paper.mkdir(parents=True, exist_ok=True)
    v.raw_text.mkdir(parents=True, exist_ok=True)
    v.raw_meta.mkdir(parents=True, exist_ok=True)

    cands = json.loads(Path(args.candidates).read_text(encoding="utf-8"))
    if args.limit:
        cands = cands[:args.limit]

    # Resume + naming state from what's already in the vault. Files are named by
    # title slug; the arxiv_id (the stable key) lives inside each meta json.
    done_ids: set[str] = set()
    taken: set[str] = set()
    for mp in v.raw_meta.glob("*.json"):
        taken.add(mp.stem)
        try:
            md = json.loads(mp.read_text(encoding="utf-8"))
            if md.get("arxiv_id") and md.get("full_text_chars"):
                done_ids.add(md["arxiv_id"])
        except (ValueError, OSError):
            pass

    done, skipped, failed = 0, 0, []
    for i, c in enumerate(cands, 1):
        aid = c["arxiv_id"]
        tag = f"[{i}/{len(cands)}] {aid}"
        if aid in done_ids:
            skipped += 1
            print(f"{tag} skip (already extracted)", file=sys.stderr)
            continue

        slug = vault_io.unique_slug(c.get("title", "") or aid, taken)
        pdf = v.raw_paper / f"{slug}.pdf"
        txt = v.raw_text / f"{slug}.txt"
        meta_path = v.raw_meta / f"{slug}.json"
        try:
            if not pdf.exists():
                n = _download_any(_candidate_pdf_urls(c), pdf)
                print(f"{tag} pdf {n} bytes", file=sys.stderr)
                time.sleep(args.delay)
            text, n_pages, toc = _extract_text(pdf)
            if len(text) < 200:
                raise ValueError(f"extracted text too short ({len(text)} chars)")
            txt.write_text(text, encoding="utf-8")

            meta = dict(c)
            meta["arxiv_id"] = aid
            meta["slug"] = slug
            meta.update({
                "full_text_chars": len(text),
                "n_pages": n_pages,
                "toc": toc,
                "extractor": "pymupdf",
                "text_path": str(txt.relative_to(v.root)),
                "pdf_path": str(pdf.relative_to(v.root)),
            })
            meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                                 encoding="utf-8")
            done_ids.add(aid)
            done += 1
            print(f"{tag} -> {slug} ({len(text)} chars / {n_pages}p)", file=sys.stderr)
        except Exception as exc:  # noqa: BLE001 — degrade, don't abort batch
            failed.append((aid, str(exc)))
            print(f"{tag} FAILED: {exc}", file=sys.stderr)
            if pdf.exists() and not txt.exists() and pdf.stat().st_size < MIN_PDF_BYTES:
                pdf.unlink(missing_ok=True)  # drop junk so a re-run retries

    print(f"\ndone={done} skipped={skipped} failed={len(failed)}", file=sys.stderr)
    if failed:
        print("failures:", file=sys.stderr)
        for aid, err in failed:
            print(f"  {aid}: {err}", file=sys.stderr)
    # machine-readable summary on stdout
    print(json.dumps({"done": done, "skipped": skipped,
                      "failed": [f[0] for f in failed]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
