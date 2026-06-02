#!/usr/bin/env python3
"""Repo & direction administration — the deterministic cold-start plumbing.

The fetch/extract scripts assume a data repo (registry + vault) already exists.
This script is what *creates* it, so a freshly-installed skill can go from
nothing to a ready-to-ingest vault without hand-editing YAML. Four subcommands:

  init-repo   create the data/ tree (data/directions, data/vaults) and an empty
              registry.yaml. Idempotent — safe to re-run. Run this once.
  new         register a research direction and build its empty vault skeleton
              (CLAUDE.md + research_direction.md + state.json + raw/ + wiki/ +
              report/). After this, run `init` (backfill) then daily `ingest`.
  list        show every registered direction and its state at a glance.
  status      detailed counts for one direction (papers, text, figures, reports).

Home (the dir holding data/) is resolved by vault_io.resolve_home:
  --home <path>  ->  $AUTORESEARCH_HOME  ->  detected repo root  ->  ~/.research-wiki
Pick the registry path the same way unless you pass --registry explicitly.

  python vault_admin.py init-repo
  python vault_admin.py new --slug llm-agents --title "LLM Agents" \
      --categories cs.AI cs.CL --keywords "agent harness" "tool use" \
      --threshold 0.6 --bootstrap-months 6 --direction-file rd.md
  python vault_admin.py list
  python vault_admin.py status --direction llm-agents
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import vault_io  # noqa: E402

ASSETS = Path(__file__).resolve().parent.parent / "assets"
CLAUDE_TEMPLATE = ASSETS / "CLAUDE.vault.md"

RD_STUB = """\
# 研究方向：{title}

## 一句话
<用一两句话精确描述这个方向研究什么。越具体越好——具体到目标论文、问题、方法层级。>

## 我关注什么（in-scope）
- <子主题 1：要收录哪类论文/贡献>
- <子主题 2>

## 我不关注什么（out-of-scope，明确排除）
- <明确排除项，例如：纯模型训练/微调、与本方向无关的垂直应用>

## 判定准则（给 relevance 打分用）
- <一篇论文满足什么条件算 in-scope？落在哪类贡献上就排除？>

## 锚点工作（用于校准与 citation 雪球的种子，不限于此）
<3-8 个代表性工作/方法名，作为相关性标定与种子扩展的锚点。>
"""


def _yaml():
    try:
        import yaml
        return yaml
    except ImportError:
        raise SystemExit("PyYAML required: run `uv sync` (or pip install pyyaml).")


def _load_registry(reg_path: Path) -> dict:
    if reg_path.exists():
        return _yaml().safe_load(reg_path.read_text(encoding="utf-8")) or {}
    return {"default": None, "directions": []}


def _dump_registry(reg_path: Path, reg: dict) -> None:
    reg_path.parent.mkdir(parents=True, exist_ok=True)
    reg_path.write_text(
        _yaml().safe_dump(reg, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def _check_deps() -> list[str]:
    missing = []
    for mod, why in (("fitz", "PDF full-text + figure extraction (pymupdf)"),
                     ("yaml", "registry parsing (pyyaml)")):
        try:
            __import__(mod)
        except ImportError:
            missing.append(f"{mod} — {why}")
    return missing


# --------------------------------------------------------------------------- #
def cmd_init_repo(args):
    home = vault_io.resolve_home(args.home)
    directions = home / "data" / "directions"
    vaults = vault_io.home_vaults(home)
    directions.mkdir(parents=True, exist_ok=True)
    vaults.mkdir(parents=True, exist_ok=True)
    reg_path = args.registry and Path(args.registry).expanduser().resolve() \
        or vault_io.home_registry(home)
    created = not reg_path.exists()
    if created:
        _dump_registry(reg_path, {"default": None, "directions": []})

    print(f"home:     {home}")
    print(f"vaults:   {vaults}")
    print(f"registry: {reg_path}  ({'created' if created else 'already existed'})")
    miss = _check_deps()
    if miss:
        print("\n⚠ missing Python deps (run `uv sync` in the skill dir):")
        for m in miss:
            print(f"   - {m}")
    else:
        print("\ndeps OK (pymupdf + pyyaml importable).")
    print("\nnext: vault_admin.py new --slug <slug> --title \"...\" "
          "--categories cs.AI cs.CL --keywords \"...\"")


def cmd_new(args):
    home = vault_io.resolve_home(args.home)
    reg_path = args.registry and Path(args.registry).expanduser().resolve() \
        or vault_io.home_registry(home)
    if not reg_path.exists():
        # be forgiving: a `new` before `init-repo` still works
        (home / "data" / "directions").mkdir(parents=True, exist_ok=True)
        vault_io.home_vaults(home).mkdir(parents=True, exist_ok=True)
        _dump_registry(reg_path, {"default": None, "directions": []})

    reg = _load_registry(reg_path)
    reg.setdefault("directions", [])
    reg.setdefault("default", None)

    existing = next((d for d in reg["directions"] if d.get("slug") == args.slug), None)
    if existing and not args.force:
        raise SystemExit(
            f"direction '{args.slug}' already exists. Use --force to overwrite its "
            "registry entry (this does NOT delete vault files)."
        )

    rel_vault = f"data/vaults/{args.slug}"
    entry = {
        "slug": args.slug,
        "title": args.title,
        "vault": rel_vault,
        "status": "active",
        "initialized": False,
        "bootstrap_months": args.bootstrap_months,
        "last_ingest": None,
        "relevance_threshold": args.threshold,
        "arxiv": {
            "categories": args.categories or [],
            "keywords": args.keywords or [],
        },
        "repos": args.repos or [],
    }
    if existing:
        reg["directions"] = [entry if d is existing else d for d in reg["directions"]]
    else:
        reg["directions"].append(entry)
    if not reg.get("default"):
        reg["default"] = args.slug
    _dump_registry(reg_path, reg)

    # --- build the vault skeleton ---
    vault_path = (vault_io.registry_repo_root(reg_path) / rel_vault).resolve()
    v = vault_io.Vault(vault_path, slug=args.slug)
    v.ensure_skeleton()

    # CLAUDE.md (vault constitution) — copy the template if present
    if CLAUDE_TEMPLATE.exists() and not v.claude_md.exists():
        v.claude_md.write_text(CLAUDE_TEMPLATE.read_text(encoding="utf-8"),
                               encoding="utf-8")

    # research_direction.md — from a file, inline text, or a guided stub
    if not v.research_direction.exists() or args.force:
        if args.direction_file:
            body = Path(args.direction_file).read_text(encoding="utf-8")
        elif args.description:
            body = f"# 研究方向：{args.title}\n\n{args.description}\n"
        else:
            body = RD_STUB.format(title=args.title)
        v.research_direction.write_text(body, encoding="utf-8")

    # state.json
    if not v.state_json.exists() or args.force:
        v.write_state({"initialized": False, "last_ingest": None, "paper_count": 0})

    stub = not (args.direction_file or args.description)
    print(f"registered '{args.slug}' -> {reg_path}")
    print(f"vault skeleton: {vault_path}")
    print(f"  CLAUDE.md, research_direction.md{' (STUB — edit before init!)' if stub else ''}, "
          f"state.json, raw/, wiki/, report/")
    if stub:
        print(f"\n⚠ research_direction.md is a placeholder. Fill it in (be specific — "
              f"down to target papers/problems) BEFORE running init; relevance scoring "
              f"depends on it.\n  {v.research_direction}")
    print(f"\nnext: arxiv_fetch.py --direction {args.slug}  (then the init pipeline)")


def cmd_list(args):
    home = vault_io.resolve_home(args.home)
    reg_path = args.registry and Path(args.registry).expanduser().resolve() \
        or vault_io.home_registry(home)
    if not reg_path.exists():
        raise SystemExit(f"no registry at {reg_path}. Run `vault_admin.py init-repo`.")
    reg = _load_registry(reg_path)
    dirs = reg.get("directions", [])
    if not dirs:
        print(f"registry {reg_path} has no directions yet. Add one with `new`.")
        return
    print(f"home: {home}   default: {reg.get('default')}")
    print(f"{'slug':<24} {'status':<9} {'init':<6} {'last_ingest':<12} papers  title")
    for d in dirs:
        vault_path = (vault_io.registry_repo_root(reg_path) / d.get("vault", "")).resolve()
        st = vault_io.Vault(vault_path).read_state()
        print(f"{d.get('slug',''):<24} {d.get('status',''):<9} "
              f"{str(d.get('initialized', st.get('initialized', False))):<6} "
              f"{str(d.get('last_ingest') or st.get('last_ingest') or '-'):<12} "
              f"{st.get('paper_count', 0):<7} {d.get('title','')}")


def cmd_status(args):
    v = vault_io.resolve_vault(direction=args.direction, vault=args.vault,
                               registry=args.registry)
    def _n(p: Path, pat="*"):
        return len(list(p.glob(pat))) if p.exists() else 0
    st = v.read_state()
    print(f"vault:        {v.root}")
    print(f"initialized:  {st.get('initialized')}")
    print(f"last_ingest:  {st.get('last_ingest')}")
    print(f"paper_count:  {st.get('paper_count')}")
    print(f"raw/meta:     {_n(v.raw_meta, '*.json')}")
    print(f"raw/text:     {_n(v.raw_text, '*.txt')}")
    print(f"raw/figures:  {_n(v.raw_figures, '*.png')} png")
    print(f"wiki/papers:  {_n(v.papers, '*.md')}")
    print(f"wiki/surveys: {_n(v.surveys, '*.md')}")
    print(f"wiki/concepts:{_n(v.concepts, '*.md')}")
    print(f"reports:      {_n(v.report, '*.md')}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--home", help="data home (else $AUTORESEARCH_HOME / auto)")
        p.add_argument("--registry", help="explicit registry.yaml path")

    ir = sub.add_parser("init-repo", help="create data/ tree + empty registry")
    common(ir); ir.set_defaults(fn=cmd_init_repo)

    n = sub.add_parser("new", help="register a direction + build vault skeleton")
    common(n); n.set_defaults(fn=cmd_new)
    n.add_argument("--slug", required=True)
    n.add_argument("--title", required=True)
    n.add_argument("--categories", nargs="*", default=[])
    n.add_argument("--keywords", nargs="*", default=[])
    n.add_argument("--threshold", type=float, default=0.6)
    n.add_argument("--bootstrap-months", type=int, default=6)
    n.add_argument("--repos", nargs="*", default=[])
    n.add_argument("--direction-file", help="markdown file -> research_direction.md")
    n.add_argument("--description", help="inline text -> research_direction.md")
    n.add_argument("--force", action="store_true",
                   help="overwrite an existing direction entry / vault metadata files")

    li = sub.add_parser("list", help="list registered directions")
    common(li); li.set_defaults(fn=cmd_list)

    stt = sub.add_parser("status", help="detailed status for one direction")
    common(stt); stt.set_defaults(fn=cmd_status)
    stt.add_argument("--direction")
    stt.add_argument("--vault")

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
