#!/usr/bin/env python3
"""OPTIONAL GROBID enrichment. The primary pipeline is `pdf_extract.py` (PyMuPDF
full text, no Docker); run this only if you want structured references / section
headers on top of the full text.

It locates an already-ingested paper in the vault by `arxiv_id` (matching the
`arxiv_id` field inside `raw/meta/*.json`), runs the PDF in `raw/paper/` through a
GROBID server, and merges `grobid_abstract` / `sections` / `references` back into
that same meta json. Filenames stay title-slug based (see `vault_io.slugify`).

Requires a running GROBID server: `docker run --rm -p 8070:8070 lfoppiano/grobid`.

  python grobid_extract.py --arxiv-id 2604.03515 --direction agent-harness
  python grobid_extract.py --arxiv-id 2604.03515 --vault data/vaults/agent-harness
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import vault_io  # noqa: E402

TEI = {"t": "http://www.tei-c.org/ns/1.0"}


def find_meta_by_arxiv(vault: vault_io.Vault, arxiv_id: str) -> Path | None:
    for p in vault.raw_meta.glob("*.json"):
        try:
            if json.loads(p.read_text(encoding="utf-8")).get("arxiv_id") == arxiv_id:
                return p
        except (ValueError, OSError):
            continue
    return None


def run_grobid(pdf: Path, grobid_url: str) -> str:
    boundary = "----autoresearchboundary"
    body = bytearray()
    body += f"--{boundary}\r\n".encode()
    body += b'Content-Disposition: form-data; name="input"; filename="paper.pdf"\r\n'
    body += b"Content-Type: application/pdf\r\n\r\n"
    body += pdf.read_bytes()
    body += f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        f"{grobid_url}/api/processFulltextDocument",
        data=bytes(body),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(req, timeout=300) as r:
        return r.read().decode("utf-8")


def parse_tei(tei: str) -> dict:
    root = ET.fromstring(tei)

    def first_text(xpath):
        el = root.find(xpath, TEI)
        return "".join(el.itertext()).strip() if el is not None else ""

    abstract = first_text(".//t:abstract")
    sections = ["".join(h.itertext()).strip()
                for h in root.findall(".//t:body//t:head", TEI)]
    refs = []
    for b in root.findall(".//t:listBibl/t:biblStruct", TEI):
        t = b.find(".//t:title", TEI)
        if t is not None:
            refs.append("".join(t.itertext()).strip())
    return {"grobid_abstract": abstract,
            "sections": [s for s in sections if s][:60],
            "references": refs[:200]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arxiv-id", required=True)
    ap.add_argument("--direction")
    ap.add_argument("--vault")
    ap.add_argument("--registry")
    ap.add_argument("--grobid-url", default="http://localhost:8070")
    args = ap.parse_args()

    v = vault_io.resolve_vault(direction=args.direction, vault=args.vault,
                               registry=args.registry)
    meta_path = find_meta_by_arxiv(v, args.arxiv_id)
    if meta_path is None:
        raise SystemExit(f"{args.arxiv_id} not found in {v.raw_meta} — run pdf_extract.py first")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    pdf_rel = meta.get("pdf_path")
    pdf = (v.root / pdf_rel) if pdf_rel else (v.raw_paper / f"{meta_path.stem}.pdf")
    if not pdf.exists():
        raise SystemExit(f"PDF missing: {pdf} — run pdf_extract.py first")

    meta.update(parse_tei(run_grobid(pdf, args.grobid_url)))
    meta["grobid"] = True
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"grobid-enriched -> {meta_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
