#!/usr/bin/env python3
"""Relevance filtering against the research direction.

Scoring (0-1) is a *judgment* task -> done by the agent (Claude reading the
direction + abstracts), not hardcoded. This script is the deterministic glue
around that judgment, with three modes:

  emit       prepare a scoring worksheet (direction + candidate abstracts) for
             the agent to fill in. Output: worksheet.json
  apply      given the agent's scores {arxiv_id: 0-1}, keep those >= threshold.
  heuristic  cheap keyword-overlap fallback score (no LLM) for smoke tests.

  python relevance_filter.py emit --candidates cands.json --direction-file rd.md
  python relevance_filter.py apply --candidates cands.json --scores scores.json --threshold 0.6
  python relevance_filter.py heuristic --candidates cands.json --keywords agent research
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def load(p: str) -> list[dict]:
    return json.loads(Path(p).read_text(encoding="utf-8"))


def cmd_emit(args):
    cands = load(args.candidates)
    direction = Path(args.direction_file).read_text(encoding="utf-8")
    worksheet = {
        "research_direction": direction,
        "instructions": (
            "Score each candidate 0.0-1.0 for relevance to the research "
            "direction. Be strict; 0.6+ means clearly on-topic. Return JSON "
            "{arxiv_id: score}."
        ),
        "candidates": [
            {"arxiv_id": c["arxiv_id"], "title": c["title"],
             "abstract": c.get("abstract", "")}
            for c in cands
        ],
    }
    out = args.out or "worksheet.json"
    Path(out).write_text(json.dumps(worksheet, ensure_ascii=False, indent=2),
                         encoding="utf-8")
    print(f"worksheet ({len(cands)} candidates) -> {out}", file=sys.stderr)


def cmd_apply(args):
    cands = {c["arxiv_id"]: c for c in load(args.candidates)}
    scores = json.loads(Path(args.scores).read_text(encoding="utf-8"))
    kept = []
    for aid, score in scores.items():
        if score >= args.threshold and aid in cands:
            c = dict(cands[aid])
            c["relevance_score"] = round(float(score), 3)
            kept.append(c)
    kept.sort(key=lambda c: c["relevance_score"], reverse=True)
    out = json.dumps(kept, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(out, encoding="utf-8")
        print(f"{len(kept)}/{len(cands)} kept -> {args.out}", file=sys.stderr)
    else:
        print(out)


def cmd_heuristic(args):
    cands = load(args.candidates)
    kw = [k.lower() for k in args.keywords]
    for c in cands:
        text = (c["title"] + " " + c.get("abstract", "")).lower()
        hits = sum(1 for k in kw if re.search(rf"\b{re.escape(k)}", text))
        c["relevance_score"] = round(hits / max(len(kw), 1), 3)
    kept = [c for c in cands if c["relevance_score"] >= args.threshold]
    kept.sort(key=lambda c: c["relevance_score"], reverse=True)
    print(json.dumps(kept, ensure_ascii=False, indent=2))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("emit"); e.set_defaults(fn=cmd_emit)
    e.add_argument("--candidates", required=True)
    e.add_argument("--direction-file", required=True)
    e.add_argument("--out")

    a = sub.add_parser("apply"); a.set_defaults(fn=cmd_apply)
    a.add_argument("--candidates", required=True)
    a.add_argument("--scores", required=True)
    a.add_argument("--threshold", type=float, default=0.6)
    a.add_argument("--out")

    h = sub.add_parser("heuristic"); h.set_defaults(fn=cmd_heuristic)
    h.add_argument("--candidates", required=True)
    h.add_argument("--keywords", nargs="+", required=True)
    h.add_argument("--threshold", type=float, default=0.34)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
