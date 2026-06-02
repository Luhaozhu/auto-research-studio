#!/usr/bin/env python3
"""Cold-start seed expansion (used only by `init`).

Takes the recent-window candidates from arxiv_fetch --months and expands them
into a richer seed set so the vault starts with a real map of the field:

  1. survey tagging  - flag candidates whose title/abstract reads as a
     survey/review/overview (the best seed nodes / field map).
  2. citation snowball - for the top seed papers + surveys, walk Semantic
     Scholar references to pull in highly-cited foundational works that may
     predate the time window.

Output: merged, deduped candidate list, each tagged source=recent|survey|snowball.
Relevance filtering happens *after* this step.

  python bootstrap_seed.py --candidates recent.json --top 30 --min-citations 50 --out seed.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import semantic_scholar as s2  # noqa: E402

SURVEY_RE = re.compile(r"\b(survey|review|overview|a tutorial)\b", re.I)


def tag_surveys(cands: list[dict]) -> None:
    for c in cands:
        text = c["title"] + " " + c.get("abstract", "")
        c["source"] = "survey" if SURVEY_RE.search(text) else "recent"


def snowball(seed_ids: list[str], min_citations: int, per_paper: int) -> dict[str, dict]:
    found: dict[str, dict] = {}
    for aid in seed_ids:
        try:
            refs = s2.get_references(aid, limit=per_paper)
        except Exception as e:  # noqa: BLE001 - network best-effort
            print(f"  snowball skip {aid}: {e}", file=sys.stderr)
            continue
        for r in refs:
            rid = s2.arxiv_id_of(r)
            if not rid or (r.get("citationCount") or 0) < min_citations:
                continue
            found.setdefault(rid, {
                "arxiv_id": rid,
                "title": r.get("title", ""),
                "abstract": "",
                "authors": [],
                "categories": [],
                "published": str(r.get("year", "")),
                "pdf_url": f"https://arxiv.org/pdf/{rid}",
                "source": "snowball",
                "citationCount": r.get("citationCount"),
            })
    return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidates", required=True, help="recent-window candidates JSON")
    ap.add_argument("--top", type=int, default=30, help="seed papers to snowball from")
    ap.add_argument("--min-citations", type=int, default=50)
    ap.add_argument("--per-paper", type=int, default=40)
    ap.add_argument("--no-snowball", action="store_true")
    ap.add_argument("--out")
    args = ap.parse_args()

    cands = json.loads(Path(args.candidates).read_text(encoding="utf-8"))
    tag_surveys(cands)
    by_id = {c["arxiv_id"]: c for c in cands}

    if not args.no_snowball:
        # seed = surveys first, then the rest, capped at --top
        seeds = [c["arxiv_id"] for c in cands if c["source"] == "survey"]
        seeds += [c["arxiv_id"] for c in cands if c["source"] != "survey"]
        seeds = seeds[: args.top]
        for rid, rec in snowball(seeds, args.min_citations, args.per_paper).items():
            by_id.setdefault(rid, rec)

    merged = list(by_id.values())
    payload = json.dumps(merged, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(payload, encoding="utf-8")
        n = {k: sum(1 for c in merged if c["source"] == k)
             for k in ("recent", "survey", "snowball")}
        print(f"{len(merged)} seed candidates {n} -> {args.out}", file=sys.stderr)
    else:
        print(payload)


if __name__ == "__main__":
    main()
