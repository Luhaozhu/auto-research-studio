"""Vault / registry IO helpers shared across auto-research skills.

This is the single coupling point between skills: the *vault directory format*
(the data contract in PLAN.md section 2). Skills never import each other; they
all speak this format. Master copy lives in shared/lib/ and is vendored into
each skill via shared/vendor.sh.

Resolution order for locating a vault:
  1. explicit --vault <path>           (no registry needed -> skill is standalone)
  2. --direction <slug> + registry     (convenience routing across directions)

The "home" is the directory that holds the `data/` tree (registry + vaults).
A fresh install has no home yet; `vault_admin.py init-repo` creates one. Home
resolution (resolve_home) lets `--direction` work with no flags once a repo
exists, so the everyday commands stay short.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _yaml():
    try:
        import yaml  # PyYAML, imported lazily so registry-free use needs no dep
        return yaml
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("PyYAML required for registry use: pip install pyyaml") from exc


# --------------------------------------------------------------------------- #
# Home (the directory that holds the data/ tree)
# --------------------------------------------------------------------------- #
def resolve_home(explicit: str | None = None) -> Path:
    """Locate the research-wiki data home — the dir that contains `data/`.

    Order: explicit arg -> $AUTORESEARCH_HOME -> nearest ancestor of this file
    that already has a `data/` tree -> nearest ancestor that holds a `skills/`
    dir (i.e. the repo root of a normal install) -> ~/.research-wiki.
    Always returns a path; never creates it. `init-repo` is what creates it.
    """
    if explicit:
        return Path(explicit).expanduser().resolve()
    env = os.environ.get("AUTORESEARCH_HOME")
    if env:
        return Path(env).expanduser().resolve()
    here = Path(__file__).resolve()
    for anc in here.parents:  # prefer an existing data/ tree
        if (anc / "data" / "directions").exists() or (anc / "data" / "vaults").exists():
            return anc
    for anc in here.parents:  # else the repo root that holds skills/
        if (anc / "skills").is_dir():
            return anc
    return Path.home() / ".research-wiki"


def home_registry(home: Path) -> Path:
    return home / "data" / "directions" / "registry.yaml"


def home_vaults(home: Path) -> Path:
    return home / "data" / "vaults"


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #
def find_registry(explicit: str | None = None) -> Path | None:
    """Locate registry.yaml.

    Order: explicit arg -> $AUTORESEARCH_REGISTRY -> the registry under the
    resolved home (if it exists) -> None. The home fallback is what lets routine
    `--direction <slug>` commands run with no `--registry` flag after init-repo.
    """
    if explicit:
        return Path(explicit).expanduser().resolve()
    env = os.environ.get("AUTORESEARCH_REGISTRY")
    if env:
        return Path(env).expanduser().resolve()
    reg = home_registry(resolve_home())
    if reg.exists():
        return reg
    return None


def load_registry(registry_path: Path) -> dict[str, Any]:
    with open(registry_path, "r", encoding="utf-8") as fh:
        return _yaml().safe_load(fh) or {}


def registry_repo_root(registry_path: Path) -> Path:
    # data/directions/registry.yaml -> repo root is three levels up
    return registry_path.parent.parent.parent


# --------------------------------------------------------------------------- #
# Vault resolution
# --------------------------------------------------------------------------- #
def resolve_vault(
    *,
    direction: str | None = None,
    vault: str | None = None,
    registry: str | None = None,
) -> "Vault":
    """Resolve a Vault from either an explicit path or a registry slug."""
    if vault:
        return Vault(Path(vault).expanduser().resolve())

    reg_path = find_registry(registry)
    if not reg_path or not reg_path.exists():
        raise SystemExit(
            "No --vault given and no registry found. Run "
            "`vault_admin.py init-repo` first to create the data repo, or pass "
            "--vault <path> / --registry <path> / set $AUTORESEARCH_HOME."
        )
    reg = load_registry(reg_path)
    slug = direction or reg.get("default")
    if not slug:
        raise SystemExit("No --direction given and registry has no 'default'.")

    entry = next((d for d in reg.get("directions", []) if d.get("slug") == slug), None)
    if entry is None:
        raise SystemExit(f"Direction '{slug}' not found in registry.")

    vault_path = (registry_repo_root(reg_path) / entry["vault"]).resolve()
    return Vault(vault_path, slug=slug, registry_entry=entry, registry_path=reg_path)


# --------------------------------------------------------------------------- #
# Vault object
# --------------------------------------------------------------------------- #
@dataclass
class Vault:
    root: Path
    slug: str | None = None
    registry_entry: dict[str, Any] | None = None
    registry_path: Path | None = None

    # --- structural paths (PLAN.md section 2.1) ---
    @property
    def claude_md(self) -> Path: return self.root / "CLAUDE.md"
    @property
    def research_direction(self) -> Path: return self.root / "research_direction.md"
    @property
    def state_json(self) -> Path: return self.root / "state.json"
    @property
    def raw_paper(self) -> Path: return self.root / "raw" / "paper"
    @property
    def raw_pdf(self) -> Path: return self.raw_paper  # back-compat alias
    @property
    def raw_text(self) -> Path: return self.root / "raw" / "text"
    @property
    def raw_figures(self) -> Path: return self.root / "raw" / "figures"
    @property
    def raw_meta(self) -> Path: return self.root / "raw" / "meta"
    @property
    def wiki(self) -> Path: return self.root / "wiki"
    @property
    def index_md(self) -> Path: return self.wiki / "index.md"
    @property
    def log_md(self) -> Path: return self.wiki / "log.md"
    @property
    def papers(self) -> Path: return self.wiki / "papers"
    @property
    def surveys(self) -> Path: return self.wiki / "surveys"
    @property
    def concepts(self) -> Path: return self.wiki / "concepts"
    @property
    def ideas(self) -> Path: return self.wiki / "ideas"
    @property
    def report(self) -> Path: return self.root / "report"

    def report_for(self, date_str: str) -> Path:
        """Path of the daily briefing for a given YYYY-MM-DD."""
        return self.report / f"{date_str}.md"

    def ensure_skeleton(self) -> None:
        """Create the empty directory structure for a fresh vault."""
        for p in (self.raw_paper, self.raw_text, self.raw_figures, self.raw_meta,
                  self.papers, self.surveys, self.concepts, self.ideas, self.report):
            p.mkdir(parents=True, exist_ok=True)
        if not self.index_md.exists():
            self.index_md.write_text("# Index\n\n", encoding="utf-8")
        if not self.log_md.exists():
            self.log_md.write_text("# Log\n\n", encoding="utf-8")

    # --- state ---
    def read_state(self) -> dict[str, Any]:
        if self.state_json.exists():
            return json.loads(self.state_json.read_text(encoding="utf-8"))
        return {"initialized": False, "last_ingest": None, "paper_count": 0}

    def write_state(self, state: dict[str, Any]) -> None:
        self.state_json.write_text(
            json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # --- log (append-only, parseable prefix) ---
    def append_log(self, kind: str, message: str) -> None:
        today = _dt.date.today().isoformat()
        line = f"## [{today}] {kind} | {message}\n"
        with open(self.log_md, "a", encoding="utf-8") as fh:
            fh.write(line)


# --------------------------------------------------------------------------- #
# Filenames — human-readable title slugs (the stable arxiv_id lives in
# frontmatter / meta json, not in the filename).
# --------------------------------------------------------------------------- #
import re as _re


def slugify(title: str, *, max_len: int = 72, fallback: str = "untitled") -> str:
    """Turn a paper title into a filesystem-safe, readable slug.

    "HARBOR: Automated Harness Optimization" -> "harbor-automated-harness-optimization"
    Lowercased ASCII words joined by hyphens, truncated at a word boundary.
    """
    import unicodedata
    norm = unicodedata.normalize("NFKD", title or "")
    norm = norm.encode("ascii", "ignore").decode("ascii")
    norm = _re.sub(r"[^a-zA-Z0-9]+", "-", norm).strip("-").lower()
    if not norm:
        return fallback
    if len(norm) <= max_len:
        return norm
    cut = norm[:max_len]
    if "-" in cut:
        cut = cut.rsplit("-", 1)[0]  # don't end mid-word
    return cut or norm[:max_len]


def unique_slug(title: str, taken: set[str], **kw) -> str:
    """slugify + de-duplicate against an existing set (appends -2, -3, ...)."""
    base = slugify(title, **kw)
    slug, n = base, 2
    while slug in taken:
        slug = f"{base}-{n}"
        n += 1
    taken.add(slug)
    return slug
