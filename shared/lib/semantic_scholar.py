"""Minimal Semantic Scholar Graph API client.

Used for two things across skills:
  - research-wiki: fill paper `cites:` edges (citation graph).
  - idea-forge / code-to-idea reviewer: novelty check (search closest prior work).

Citation-graph grounding is a hard requirement (PLAN.md section 0.2): do NOT
reduce novelty checks to keyword soup. Master copy in shared/lib/.

Stdlib only. Optional S2 API key via $S2_API_KEY raises rate limits.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

_BASE = "https://api.semanticscholar.org/graph/v1"
_MIN_INTERVAL = 1.1  # be polite; S2 unauthenticated limits are strict
_last_call = 0.0


def _get(path: str, params: dict | None = None, retries: int = 3) -> dict:
    global _last_call
    url = f"{_BASE}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    headers = {"User-Agent": "auto-research/0.1"}
    if key := os.environ.get("S2_API_KEY"):
        headers["x-api-key"] = key

    for attempt in range(retries):
        wait = _MIN_INTERVAL - (time.time() - _last_call)
        if wait > 0:
            time.sleep(wait)
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                _last_call = time.time()
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            _last_call = time.time()
            if e.code == 429 and attempt < retries - 1:
                time.sleep(2 ** (attempt + 1))
                continue
            raise
    return {}


def get_paper(arxiv_id: str, fields: list[str] | None = None) -> dict:
    fields = fields or ["title", "year", "citationCount", "externalIds"]
    return _get(f"/paper/arXiv:{arxiv_id}", {"fields": ",".join(fields)})


def get_references(arxiv_id: str, limit: int = 50) -> list[dict]:
    fields = ["title", "year", "citationCount", "externalIds"]
    data = _get(
        f"/paper/arXiv:{arxiv_id}/references",
        {"fields": ",".join(f"citedPaper.{f}" for f in fields), "limit": limit},
    )
    return [r.get("citedPaper", {}) for r in data.get("data", [])]


def get_citations(arxiv_id: str, limit: int = 50) -> list[dict]:
    fields = ["title", "year", "citationCount", "externalIds"]
    data = _get(
        f"/paper/arXiv:{arxiv_id}/citations",
        {"fields": ",".join(f"citingPaper.{f}" for f in fields), "limit": limit},
    )
    return [r.get("citingPaper", {}) for r in data.get("data", [])]


def search(query: str, limit: int = 10) -> list[dict]:
    """Relevance search — for reviewer novelty checks (closest prior work)."""
    fields = ["title", "abstract", "year", "citationCount", "externalIds"]
    data = _get(
        "/paper/search",
        {"query": query, "limit": limit, "fields": ",".join(fields)},
    )
    return data.get("data", [])


def arxiv_id_of(paper: dict) -> str | None:
    return (paper.get("externalIds") or {}).get("ArXiv")


if __name__ == "__main__":  # tiny smoke test
    import sys
    aid = sys.argv[1] if len(sys.argv) > 1 else "2408.06292"
    p = get_paper(aid)
    print(json.dumps(p, ensure_ascii=False, indent=2))
