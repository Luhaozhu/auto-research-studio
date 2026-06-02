#!/usr/bin/env python3
"""Extract each paper's KEY ARCHITECTURE FIGURE from its PDF into the vault.

Heuristic (PyMuPDF, no Docker): scan the first pages for figure captions, prefer
one whose caption mentions architecture/framework/overview/pipeline/… (else the
lowest-numbered figure, i.e. the teaser/Figure 1). Crop the graphics region
*above* that caption (union of vector drawings + raster images) and render it to
`raw/figures/<slug>.png`. Writes a sidecar `raw/figures/<slug>.json`
{slug, fig_label, caption, page, method}. Resume-safe; failures logged & skipped.

  python figure_extract.py --direction agent-harness            # all papers
  python figure_extract.py --vault data/vaults/agent-harness --slug harbor-... --force
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import vault_io  # noqa: E402

ZOOM = 2.0
MAX_SCAN_PAGES = 30
ARCH_KW = re.compile(r"(architect|framework|overview|pipeline|workflow|"
                     r"\bsystem\b|approach|method|design|our model|the model)", re.I)
# A real caption ends the figure number with a separator (": " / " | " / ". Word"),
# never a bare space — that would also match in-text references ("Figure 1 shows…").
CAP_RE = re.compile(r"^\s*(fig(?:ure|\.|)?)\s*(\d+)\s*[:|│.]", re.I)
MAX_FIG_HEIGHT = 560      # pt, how far above the caption a figure may extend
MIN_W = MIN_H = 45        # reject slivers / inline icons


def _caption_candidates(doc):
    """Yield (page_idx, caption_bbox, fignum, caption_text, kw_score)."""
    import fitz  # noqa: F401
    out = []
    for pi in range(min(MAX_SCAN_PAGES, doc.page_count)):
        page = doc[pi]
        for b in page.get_text("blocks"):
            x0, y0, x1, y1, text = b[0], b[1], b[2], b[3], b[4]
            m = CAP_RE.match(text)
            if not m:
                continue
            fignum = int(m.group(2))
            kw = 1 if ARCH_KW.search(text[:300]) else 0
            out.append((pi, (x0, y0, x1, y1), fignum, " ".join(text.split())[:240], kw))
    return out


def _choose(cands):
    """Bias toward the teaser/architecture: among the first 3 figures, prefer one
    whose caption mentions architecture/framework/…; otherwise Figure 1."""
    if not cands:
        return None
    early = [c for c in cands if c[2] <= 3] or cands
    kw = [c for c in early if c[4] == 1]
    pool = kw or early
    return sorted(pool, key=lambda c: (c[2], c[0]))[0]


VGAP = 85   # max vertical gap (pt) bridging graphics into one figure cluster


def _figure_bbox(page, cap_bbox):
    """Cluster the graphics directly above the caption into the figure bbox.

    Builds upward from the caption, bridging gaps < VGAP, so a separate block
    higher up (title rules, a prior paragraph's underline) is excluded. Then
    extends horizontally to swallow figure-internal panels (code blocks, labels)
    that vertically overlap the cluster.
    """
    import fitz
    cx0, cy0, cx1, cy1 = cap_bbox
    pr = page.rect
    outer_top = max(pr.y0, cy0 - MAX_FIG_HEIGHT)
    rects = []
    for d in page.get_drawings():
        r = d.get("rect")
        if r is None or r.width <= 3 or r.height <= 3:
            continue
        if r.y1 <= cy0 + 2 and r.y0 >= outer_top - 2:
            if r.width >= pr.width * 0.98 and r.height >= pr.height * 0.5:
                continue  # page-background box
            rects.append(fitz.Rect(r))
    for im in page.get_image_info():
        bb = im.get("bbox")
        if not bb:
            continue
        r = fitz.Rect(bb)
        if r.y1 <= cy0 + 2 and r.y0 >= outer_top - 2 and r.width > 8 and r.height > 8:
            rects.append(r)
    if not rects:
        return None
    # cluster contiguously upward from the caption
    rects.sort(key=lambda r: r.y1, reverse=True)
    cluster = [rects[0]]
    top = rects[0].y0
    for r in rects[1:]:
        if top - r.y1 <= VGAP:
            cluster.append(r)
            top = min(top, r.y0)
        elif r.y0 >= top:        # nested inside current span, keep
            cluster.append(r)
        else:
            break
    u = fitz.Rect(cluster[0])
    for r in cluster[1:]:
        u |= r
    # swallow figure-internal text panels (code blocks, node labels) that
    # vertically overlap the graphics cluster
    for b in page.get_text("blocks"):
        bx0, by0, bx1, by1 = b[0], b[1], b[2], b[3]
        if by1 <= cy0 and by0 < u.y1 - 4 and by1 > u.y0 + 4:
            u |= fitz.Rect(bx0, max(by0, u.y0), bx1, min(by1, u.y1))
    u |= fitz.Rect(min(u.x0, cx0), u.y0, max(u.x1, cx1), u.y1)  # ≥ caption span
    u = u & pr
    u.y1 = min(u.y1, cy0 - 1)
    u.x0 = max(pr.x0, u.x0 - 4); u.y0 = max(pr.y0, u.y0 - 4)
    u.x1 = min(pr.x1, u.x1 + 4)
    return u


def _largest_image_bbox(doc):
    import fitz
    best = None
    for pi in range(min(5, doc.page_count)):
        for im in doc[pi].get_image_info():
            bb = im.get("bbox")
            if not bb:
                continue
            r = fitz.Rect(bb)
            if r.width >= MIN_W and r.height >= MIN_H and (best is None or r.get_area() > best[1].get_area()):
                best = (pi, r)
    return best


def extract_one(pdf: Path, png: Path, meta_title: str):
    import fitz
    doc = fitz.open(pdf)
    try:
        chosen = _choose(_caption_candidates(doc))
        method = label = caption = None
        clip = page = None
        if chosen:
            pi, cap_bbox, fignum, caption, _ = chosen
            page = doc[pi]
            clip = _figure_bbox(page, cap_bbox)
            label = f"Figure {fignum}"
            method = "caption-region"
        if clip is None or clip.width < MIN_W or clip.height < MIN_H:
            fb = _largest_image_bbox(doc)
            if fb is None:
                return None
            pi, clip = fb
            page = doc[pi]
            label = label or "embedded image"
            method = "largest-image"
            caption = caption or ""
        pix = page.get_pixmap(clip=clip, matrix=fitz.Matrix(ZOOM, ZOOM))
        png.parent.mkdir(parents=True, exist_ok=True)
        pix.save(png)
        return {"fig_label": label, "caption": caption, "page": page.number + 1,
                "method": method, "w": pix.width, "h": pix.height}
    finally:
        doc.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--direction")
    ap.add_argument("--vault")
    ap.add_argument("--registry")
    ap.add_argument("--slug", help="only this slug (else all papers with a PDF)")
    ap.add_argument("--force", action="store_true", help="re-extract even if png exists")
    args = ap.parse_args()

    v = vault_io.resolve_vault(direction=args.direction, vault=args.vault,
                               registry=args.registry)
    figdir = v.raw_figures
    metas = sorted(v.raw_meta.glob("*.json"))
    if args.slug:
        metas = [m for m in metas if m.stem == args.slug]

    done = skipped = 0
    failed = []
    for m in metas:
        d = json.loads(m.read_text(encoding="utf-8"))
        slug = d.get("slug", m.stem)
        png = figdir / f"{slug}.png"
        side = figdir / f"{slug}.json"
        if png.exists() and not args.force:
            skipped += 1
            continue
        pdf = v.root / d.get("pdf_path", f"raw/paper/{slug}.pdf")
        if not pdf.exists():
            failed.append((slug, "no pdf"))
            continue
        try:
            info = extract_one(pdf, png, d.get("title", ""))
            if info is None:
                failed.append((slug, "no figure found"))
                continue
            info["slug"] = slug
            side.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
            done += 1
            print(f"{slug}: {info['fig_label']} p{info['page']} "
                  f"{info['w']}x{info['h']} ({info['method']})", file=sys.stderr)
        except Exception as exc:  # noqa: BLE001
            failed.append((slug, str(exc)))
            print(f"{slug}: FAILED {exc}", file=sys.stderr)

    print(f"\ndone={done} skipped={skipped} failed={len(failed)}", file=sys.stderr)
    for s, e in failed:
        print(f"  {s}: {e}", file=sys.stderr)
    print(json.dumps({"done": done, "skipped": skipped,
                      "failed": [f[0] for f in failed]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
