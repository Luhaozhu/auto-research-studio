#!/usr/bin/env python3
"""Fetch arXiv candidates for a research direction. Two modes:

  --since YYYY-MM-DD   incremental daily update (stops at the watermark)
  --months N           backfill window for cold-start `init`

The arXiv query is built from the direction's **categories only** (the category
listing index is realtime). Keywords are applied as a *local* pre-screen on the
fetched title+abstract — NOT ANDed into the server query — because arXiv's
full-text (`all:"..."`) index lags ~a day for new papers, so a server-side
keyword AND silently drops the very newest papers (this caused a daily run to
report 0 while 300+ same-day papers existed). `--since` mode also re-scans
`--lookback-days` (default 1) before the watermark to catch late-announced
papers; downstream dedup against state removes already-ingested ones. A 0/low
yield prints a loud WARNING rather than silently looking "done".

Honors arXiv's 3s inter-request delay. Emits a JSON list to stdout or --out.

  python arxiv_fetch.py --direction llm-agentic-research --months 6 --out cands.json
  python arxiv_fetch.py --categories cs.LG cs.AI --keywords "research agent" --since 2026-05-01
  python arxiv_fetch.py --direction agent-harness --no-keyword-filter   # full daily volume
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import vault_io  # noqa: E402

ARXIV_API = "https://export.arxiv.org/api/query"
NS = {"a": "http://www.w3.org/2005/Atom"}
PAGE = 200            # results per request; bigger page = fewer requests = fewer 3s waits
DELAY = 3.0           # arXiv HARD limit: ≤1 request / 3s per IP — cannot go faster
# arXiv rate-limits requests without a descriptive User-Agent (HTTP 429).
# Contact email is read from ARXIV_CONTACT_EMAIL (loaded from .env by run_daily_ingest.sh).
_CONTACT_EMAIL = os.environ.get("ARXIV_CONTACT_EMAIL", "research@example.com")
UA = f"auto-research-wiki/0.1 (+https://github.com/; mailto:{_CONTACT_EMAIL})"
RETRIES = 5
MAX_BACKOFF = 60.0
_last_request_ts = 0.0


def _throttle() -> None:
    """Gate requests to arXiv's ≤1-per-3s rule by *time since the last request*,
    not a blind per-call sleep: time already spent parsing the previous response
    counts toward the 3s gap, so we never wait longer than required (and never
    go faster than allowed). Shared across every page of a fetch."""
    global _last_request_ts
    wait = DELAY - (time.monotonic() - _last_request_ts)
    if wait > 0:
        time.sleep(wait)
    _last_request_ts = time.monotonic()


def _read_url(url: str) -> bytes:
    """GET with a polite UA and exponential backoff on 429/503/transient errors."""
    backoff = DELAY
    last_exc: Exception | None = None
    for attempt in range(RETRIES):
        _throttle()  # enforce ≤1 req / 3s by elapsed time, before every attempt
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            last_exc = exc
            if exc.code in (429, 503) and attempt < RETRIES - 1:
                ra = exc.headers.get("Retry-After") if exc.headers else None
                wait = float(ra) if ra and ra.isdigit() else backoff
                print(f"arxiv {exc.code}, backing off {wait:.0f}s "
                      f"(attempt {attempt + 1}/{RETRIES})", file=sys.stderr)
                time.sleep(wait)
                backoff = min(backoff * 2, MAX_BACKOFF)
                continue
            raise
        except (urllib.error.URLError, TimeoutError) as exc:
            last_exc = exc
            if attempt < RETRIES - 1:
                print(f"arxiv transient error ({exc}), retry in {backoff:.0f}s",
                      file=sys.stderr)
                time.sleep(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF)
                continue
            raise
    raise last_exc  # pragma: no cover


def build_query(categories: list[str], keywords: list[str]) -> str:
    """Build the arXiv search query.

    IMPORTANT: keywords are **not** ANDed into the server query. arXiv's
    full-text field (`all:"..."`) is served from an index that lags ~a day for
    freshly-submitted papers, while the category listing (`cat:`) is realtime.
    ANDing the two therefore *silently drops the newest papers* — the exact bug
    that made a daily `--since` run return 0 while 300+ same-day papers existed.
    So we query by category only (realtime) and narrow by keyword **locally**,
    on the fetched title+abstract, where there is no index lag (see
    `prescreen_keywords`). Keywords are used in the server query only as a
    fallback when no categories are given.
    """
    cat = " OR ".join(f"cat:{c}" for c in categories) if categories else ""
    if cat:
        return cat
    kw = " OR ".join(f'all:"{k}"' for k in keywords) if keywords else ""
    return kw


# Tokens too generic to filter on (would keep ~everything for the wrong reason).
# Note: domain-core tokens like "agent"/"agentic" are intentionally NOT here —
# they are exactly the signal we want, and matching them as substrings keeps the
# pre-screen high-recall (e.g. "agent" matches "multi-agent" and "agentic").
_STOP_TOKENS = {
    "the", "and", "for", "via", "use", "new", "with", "from", "into",
    "system", "systems", "design", "designs", "automated", "automatic",
    "learning", "model", "models", "based", "using", "method", "methods",
    "approach", "approaches", "task", "tasks", "language", "large",
    "framework", "frameworks",
    # split-fragment substrings that are too broad on their own — the full
    # phrase ("multi-agent", "self-improving") still matches as a phrase, and
    # "agent" already catches "multi-agent"/"agentic".
    "multi", "self",
}


def _keyword_signals(keywords: list[str]) -> tuple[list[str], set[str]]:
    """Derive (phrases, tokens) for the local pre-screen from the direction's
    keywords. Phrases match as substrings; tokens (len>=3, non-generic) catch
    morphological variants (e.g. token 'agent' matches 'multi-agent'/'agentic')."""
    phrases: list[str] = []
    tokens: set[str] = set()
    for k in keywords:
        kl = " ".join(k.lower().split())
        if not kl:
            continue
        phrases.append(kl)
        for w in re.split(r"[^a-z0-9+]+", kl):
            if len(w) >= 3 and w not in _STOP_TOKENS:
                tokens.add(w)
    return phrases, tokens


def prescreen_keywords(cands: list[dict], keywords: list[str]) -> tuple[list[dict], list[dict]]:
    """Lenient, lag-free local relevance pre-screen on title+abstract.

    Runs on the already-fetched text (no arXiv index lag), so it can never hide
    a brand-new paper the way the old server-side keyword AND did. A candidate
    is kept if any keyword phrase OR any non-generic keyword token appears in its
    title+abstract. Returns (kept, dropped) — the caller logs the drop count so
    truncation is never silent.
    """
    phrases, tokens = _keyword_signals(keywords)
    if not phrases and not tokens:
        return cands, []
    kept, dropped = [], []
    for c in cands:
        hay = f"{c.get('title', '')} {c.get('abstract', '')}".lower()
        if any(p in hay for p in phrases) or any(t in hay for t in tokens):
            kept.append(c)
        else:
            dropped.append(c)
    return kept, dropped


def _text(node, tag):
    el = node.find(f"a:{tag}", NS)
    return (el.text or "").strip() if el is not None else ""


def parse_entry(entry) -> dict:
    raw_id = _text(entry, "id")  # http://arxiv.org/abs/2504.08066v2
    arxiv_id = raw_id.rsplit("/", 1)[-1].split("v")[0]
    pdf_url = next(
        (l.get("href") for l in entry.findall("a:link", NS) if l.get("title") == "pdf"),
        f"https://arxiv.org/pdf/{arxiv_id}",
    )
    return {
        "arxiv_id": arxiv_id,
        "title": " ".join(_text(entry, "title").split()),
        "abstract": " ".join(_text(entry, "summary").split()),
        "authors": [_text(a, "name") for a in entry.findall("a:author", NS)],
        "categories": [c.get("term") for c in entry.findall("a:category", NS)],
        "published": _text(entry, "published")[:10],
        "pdf_url": pdf_url,
    }


def fetch(query: str, cutoff: dt.date, max_results: int) -> list[dict]:
    out: list[dict] = []
    start = 0
    while len(out) < max_results:
        params = {
            "search_query": query,
            "start": start,
            "max_results": PAGE,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
        url = f"{ARXIV_API}?{urllib.parse.urlencode(params)}"
        root = ET.fromstring(_read_url(url))
        entries = root.findall("a:entry", NS)
        if not entries:
            break
        stop = False
        for e in entries:
            rec = parse_entry(e)
            pub = dt.date.fromisoformat(rec["published"]) if rec["published"] else None
            if pub and pub < cutoff:
                stop = True
                break
            out.append(rec)
        if stop or len(entries) < PAGE:
            break
        start += PAGE
        # pacing handled by _throttle() inside _read_url (next iteration)
    return out[:max_results]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--direction")
    ap.add_argument("--vault")
    ap.add_argument("--registry")
    ap.add_argument("--categories", nargs="*", default=[])
    ap.add_argument("--keywords", nargs="*", default=[])
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--since", help="YYYY-MM-DD incremental watermark")
    g.add_argument("--months", type=int, help="backfill window in months")
    ap.add_argument("--max-results", type=int, default=400)
    ap.add_argument("--lookback-days", type=int, default=1,
                    help="in --since mode, re-scan this many extra days before the "
                         "watermark to catch late-announced/cross-listed papers "
                         "(downstream dedup against state removes already-ingested). "
                         "Default 1; set 0 to scan strictly from the watermark.")
    ap.add_argument("--no-keyword-filter", action="store_true",
                    help="skip the local keyword pre-screen and return every "
                         "category candidate (use when keywords might be too "
                         "narrow, or to inspect the full daily volume).")
    ap.add_argument("--out")
    args = ap.parse_args()

    cats, kws = args.categories, args.keywords
    if args.direction or args.vault:
        v = vault_io.resolve_vault(direction=args.direction, vault=args.vault,
                                   registry=args.registry)
        entry = v.registry_entry or {}
        ax = entry.get("arxiv", {})
        cats = cats or ax.get("categories", [])
        kws = kws or ax.get("keywords", [])
        if not args.since and not args.months:
            st = v.read_state()
            args.since = st.get("last_ingest")

    if not (cats or kws):
        ap.error("need --categories/--keywords (or a registry direction that has them)")

    if args.months:
        cutoff = dt.date.today() - dt.timedelta(days=30 * args.months)
    elif args.since:
        cutoff = dt.date.fromisoformat(args.since) - dt.timedelta(days=max(0, args.lookback_days))
    else:
        cutoff = dt.date.today() - dt.timedelta(days=7)  # default daily-ish

    query = build_query(cats, kws)
    fetched = fetch(query, cutoff, args.max_results)

    # Local, lag-free keyword pre-screen (NOT a server-side AND — see build_query).
    if kws and not args.no_keyword_filter:
        cands, dropped = prescreen_keywords(fetched, kws)
        if dropped:
            print(f"local keyword pre-screen: kept {len(cands)}, dropped "
                  f"{len(dropped)} of {len(fetched)} (off-topic by title+abstract; "
                  f"pass --no-keyword-filter to keep all)", file=sys.stderr)
    else:
        cands = fetched

    # No-silent-failure: a 0/low yield usually means the watermark is at/ahead of
    # the newest available paper (or categories are wrong) — say so loudly.
    if not cands:
        hint = (f"0 candidates. Newest available may predate the cutoff "
                f"({cutoff.isoformat()}).")
        if args.since:
            hint += (" If a daily run, the watermark may be ahead of the source —"
                     " try a wider --since, a larger --lookback-days, or "
                     "--no-keyword-filter to sanity-check.")
        print(f"WARNING: {hint}", file=sys.stderr)
    elif fetched and len(fetched) >= args.max_results:
        print(f"NOTE: hit --max-results={args.max_results}; there may be more "
              f"candidates past the cap (raise --max-results to be exhaustive).",
              file=sys.stderr)

    payload = json.dumps(cands, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(payload, encoding="utf-8")
        print(f"{len(cands)} candidates -> {args.out}", file=sys.stderr)
    else:
        print(payload)


if __name__ == "__main__":
    main()
