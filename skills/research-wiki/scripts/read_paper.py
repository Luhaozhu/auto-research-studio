#!/usr/bin/env python3
"""One-shot single-paper read — the quick path for "just read this one paper".

Unlike the direction pipeline (fetch -> score -> ingest), this takes ONE paper
by arXiv id/URL or a local PDF and does only the deterministic work: download +
full-text extract + key-figure crop, into a lightweight, registry-free `inbox/`
vault. You (or the `librarian`) then compile a single Chinese summary page from
`raw/text/<slug>.txt` into `inbox/reads/<slug>.md` using the paper schema.

No direction, no registry, no relevance scoring — it never touches existing
vaults. The inbox is a normal vault dir (raw/{paper,text,meta,figures}) plus a
`reads/` folder for the compiled summaries.

  python read_paper.py 2504.08066
  python read_paper.py https://arxiv.org/abs/2504.08066
  python read_paper.py --pdf ~/Downloads/some-paper.pdf --title "Some Paper"
  python read_paper.py 2504.08066 --inbox /tmp/my-inbox

After it runs, read inbox/raw/text/<slug>.txt and write inbox/reads/<slug>.md
(中文, paper schema from assets/CLAUDE.vault.md, incl. 局限与存疑 + 资源链接).
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE / "lib"))
import vault_io  # noqa: E402

# Reuse the deterministic plumbing already battle-tested elsewhere in the skill.
import arxiv_fetch  # noqa: E402  (_read_url, parse_entry, ARXIV_API, NS, DELAY)
import pdf_extract  # noqa: E402  (_download, _extract_text)
import figure_extract  # noqa: E402  (extract_one)

ARXIV_ID_RE = re.compile(r"(\d{4}\.\d{4,5})(?:v\d+)?")


def resolve_input(token: str | None, *, id_: str | None, url: str | None,
                  pdf: str | None) -> dict:
    """Normalize the user's input into {kind, arxiv_id?, pdf_path?}."""
    if pdf:
        return {"kind": "pdf", "pdf_path": Path(pdf).expanduser().resolve()}
    raw = id_ or url or token or ""
    m = ARXIV_ID_RE.search(raw)
    if m:
        return {"kind": "arxiv", "arxiv_id": m.group(1)}
    # a bare local path passed positionally
    p = Path(raw).expanduser()
    if raw and p.suffix.lower() == ".pdf":
        return {"kind": "pdf", "pdf_path": p.resolve()}
    raise SystemExit(
        f"could not parse input {raw!r}: pass an arXiv id (2504.08066), an "
        f"arXiv URL, or --pdf <local.pdf>")


def fetch_arxiv_meta(arxiv_id: str) -> dict:
    """Fetch a single paper's metadata from the arXiv API by id."""
    url = f"{arxiv_fetch.ARXIV_API}?id_list={arxiv_id}&max_results=1"
    root = ET.fromstring(arxiv_fetch._read_url(url))
    entry = root.find("a:entry", arxiv_fetch.NS)
    if entry is None:
        raise SystemExit(f"arXiv returned no entry for id {arxiv_id}")
    rec = arxiv_fetch.parse_entry(entry)
    if not rec.get("title"):
        raise SystemExit(f"arXiv entry for {arxiv_id} has no title (bad id?)")
    return rec


def pdf_meta_title(pdf: Path) -> str:
    try:
        import fitz
        doc = fitz.open(pdf)
        try:
            t = (doc.metadata or {}).get("title") or ""
        finally:
            doc.close()
        return " ".join(t.split())
    except Exception:  # noqa: BLE001
        return ""


def existing_slug_for(inbox: vault_io.Vault, arxiv_id: str | None,
                      pdf_path: Path | None) -> str | None:
    """If this paper was already read into the inbox, return its slug."""
    for mp in inbox.raw_meta.glob("*.json"):
        try:
            md = json.loads(mp.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if arxiv_id and md.get("arxiv_id") == arxiv_id:
            return md.get("slug", mp.stem)
        if pdf_path and md.get("source_pdf") == str(pdf_path):
            return md.get("slug", mp.stem)
    return None


def main():
    ap = argparse.ArgumentParser(description="One-shot single-paper read into an inbox.")
    ap.add_argument("paper", nargs="?", help="arXiv id, arXiv URL, or local .pdf path")
    ap.add_argument("--id", dest="id_", help="arXiv id (e.g. 2504.08066)")
    ap.add_argument("--url", help="arXiv abs/pdf URL")
    ap.add_argument("--pdf", help="local PDF path")
    ap.add_argument("--title", help="title override (recommended for local PDFs)")
    ap.add_argument("--home", help="data home (defaults to the resolved research-wiki home)")
    ap.add_argument("--inbox", help="inbox dir (default <home>/data/inbox)")
    ap.add_argument("--force", action="store_true", help="re-extract even if already read")
    ap.add_argument("--delay", type=float, default=pdf_extract.DELAY)
    args = ap.parse_args()

    spec = resolve_input(args.paper, id_=args.id_, url=args.url, pdf=args.pdf)

    # Inbox is a plain vault dir; registry-free so it works on a fresh install.
    if args.inbox:
        inbox_root = Path(args.inbox).expanduser().resolve()
    else:
        home = vault_io.resolve_home(args.home)
        inbox_root = home / "data" / "inbox"
    inbox = vault_io.Vault(inbox_root)
    for p in (inbox.raw_paper, inbox.raw_text, inbox.raw_meta, inbox.raw_figures,
              inbox_root / "reads"):
        p.mkdir(parents=True, exist_ok=True)

    arxiv_id = spec.get("arxiv_id")
    src_pdf = spec.get("pdf_path")

    if src_pdf and not src_pdf.exists():
        raise SystemExit(f"local PDF not found: {src_pdf}")

    existing = None if args.force else existing_slug_for(inbox, arxiv_id, src_pdf)
    if existing:
        meta_path = inbox.raw_meta / f"{existing}.json"
        print(f"already read -> {existing} (use --force to redo)", file=sys.stderr)
        print(meta_path.read_text(encoding="utf-8"))
        _print_next_step(inbox_root, existing)
        return

    # ---- build the candidate record ----------------------------------------
    if spec["kind"] == "arxiv":
        cand = fetch_arxiv_meta(arxiv_id)
        title = args.title or cand.get("title") or arxiv_id
    else:
        title = args.title or pdf_meta_title(src_pdf) or src_pdf.stem.replace("_", " ")
        cand = {"arxiv_id": None, "title": title, "abstract": "",
                "authors": [], "categories": [], "published": "",
                "source_pdf": str(src_pdf)}

    taken = {mp.stem for mp in inbox.raw_meta.glob("*.json")}
    slug = vault_io.unique_slug(title, taken)
    pdf = inbox.raw_paper / f"{slug}.pdf"
    txt = inbox.raw_text / f"{slug}.txt"
    meta_path = inbox.raw_meta / f"{slug}.json"

    # ---- get the PDF -------------------------------------------------------
    if spec["kind"] == "arxiv":
        url = cand.get("pdf_url") or f"https://arxiv.org/pdf/{arxiv_id}"
        n = pdf_extract._download(url, pdf)
        print(f"pdf {n} bytes <- {url}", file=sys.stderr)
        time.sleep(args.delay)
    else:
        shutil.copyfile(src_pdf, pdf)
        print(f"pdf copied <- {src_pdf}", file=sys.stderr)

    # ---- full text ---------------------------------------------------------
    text, n_pages, toc = pdf_extract._extract_text(pdf)
    if len(text) < 200:
        raise SystemExit(f"extracted text too short ({len(text)} chars) — bad PDF?")
    txt.write_text(text, encoding="utf-8")

    meta = dict(cand)
    meta["arxiv_id"] = arxiv_id
    meta["slug"] = slug
    meta.update({
        "full_text_chars": len(text),
        "n_pages": n_pages,
        "toc": toc,
        "extractor": "pymupdf",
        "text_path": str(txt.relative_to(inbox.root)),
        "pdf_path": str(pdf.relative_to(inbox.root)),
        "via": "read",
    })
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---- key figure (best-effort) ------------------------------------------
    fig_png = inbox.raw_figures / f"{slug}.png"
    fig_info = None
    try:
        fig_info = figure_extract.extract_one(pdf, fig_png, title)
        if fig_info:
            fig_info["slug"] = slug
            (inbox.raw_figures / f"{slug}.json").write_text(
                json.dumps(fig_info, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"figure {fig_info['fig_label']} p{fig_info['page']}", file=sys.stderr)
    except Exception as exc:  # noqa: BLE001 — figure is optional
        print(f"figure extraction skipped: {exc}", file=sys.stderr)

    print(f"read -> {slug} ({len(text)} chars / {n_pages}p)", file=sys.stderr)
    print(json.dumps({
        "slug": slug,
        "arxiv_id": arxiv_id,
        "title": title,
        "full_text_chars": len(text),
        "n_pages": n_pages,
        "figure": bool(fig_info),
        "paths": {
            "pdf": str(pdf), "text": str(txt), "meta": str(meta_path),
            "figure": str(fig_png) if fig_info else None,
            "read_page": str(inbox_root / "reads" / f"{slug}.md"),
        },
    }, ensure_ascii=False))
    _print_next_step(inbox_root, slug)


def _print_next_step(inbox_root: Path, slug: str):
    print(
        f"\nNEXT: read {inbox_root}/raw/text/{slug}.txt and compile a 中文 summary "
        f"into {inbox_root}/reads/{slug}.md using the paper schema "
        f"(TL;DR/摘要/问题动机/方法/实验/局限与存疑/可借鉴点/资源/架构图).",
        file=sys.stderr)


if __name__ == "__main__":
    main()
