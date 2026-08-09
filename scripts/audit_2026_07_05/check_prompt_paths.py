"""Validate that every *source* repo path named in an audit prompt exists.

Two passes:

1. **Full-path pass (errors).** Backtick tokens that look like FULL repo paths
   (start with a known top-level dir AND end in a code extension or '/') must
   exist relative to the repo root. A miss is an error (exit 1).

2. **Bare-fragment pass (warnings).** Backtick tokens that name a source file by
   a bare fragment (e.g. `_trampoline.c`, `foo.py`) — i.e. tokens the full-path
   pass skips because they lack a root prefix — are checked by *basename*: if no
   file with that basename exists anywhere in the repo, that is almost certainly
   a stale reference. It is reported as a WARNING (does not fail by default,
   since bare fragments are legitimate shorthand), and becomes an error under
   ``--strict``. This is a safety net for the false-negative class the full-path
   pass cannot see; it will NOT catch a bare fragment whose basename happens to
   exist elsewhere (an ambiguous-but-real path) — those need a full path.

Deliberately skips in BOTH passes:
- the audit's own OUTPUT roots (findings.md, per-subsystem test files, todos) —
  created by the audit sessions, so they legitimately don't exist yet;
- prompt-template tokens still containing `{{...}}`;
- glob/brace/placeholder shorthand (`*`, `{`, `<`) and absolute external refs.

The bare-fragment warning pass is restricted to SOURCE extensions
(`.py`/`.c`/`.h`/`.clausal`) — not `.md` — because prose freely names external
or conceptual `.md` files (`MEMORY.md`, `findings.md`) that need not live in the
repo.

Usage: python scripts/audit_2026_07_05/check_prompt_paths.py [--strict] <prompt.md>...
Exit 0 if all full paths resolve (and, under --strict, no bare-fragment
warnings); 1 otherwise.
"""
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CODE_EXT = (".py", ".c", ".h", ".md", ".clausal")
SRC_EXT = (".py", ".c", ".h", ".clausal")  # warning pass ignores .md
ROOTS = ("clausal/", "tests/", "docs/", "todo/", "scripts/",
         "packages/", "prolog_backends/", "benchmarks/")
# audit-output roots: created by the sessions, not required to exist now
SKIP_PREFIXES = (
    "tests/audit_2026_07_05/",
    "docs/superpowers/audits/2026-07-05-fable-partition/",
    "todo/audit-2026-07-05/",
)
# directories excluded when indexing repo basenames (vendored / generated)
PRUNE_DIRS = {
    ".git", "venv", "build", "dist", "site", "node_modules",
    "__pycache__", ".pytest_cache", "clausal.egg-info", ".superpowers",
}
BACKTICK = re.compile(r"`([^`]+)`")


def _normalise(tok):
    tok = "".join(tok.split())               # collapse markdown line-wraps
    return re.sub(r":\d+(-\d+)?$", "", tok)  # strip :line refs


def _placeholder(base):
    return any(c in base for c in "*{<")


def candidate_paths(text):
    """Full repo-path tokens that MUST exist (error on miss)."""
    for tok in BACKTICK.findall(text):
        base = _normalise(tok)
        if not base.startswith(ROOTS):
            continue
        if not (base.endswith("/") or base.endswith(CODE_EXT)):
            continue
        if _placeholder(base):
            continue
        if base.startswith(SKIP_PREFIXES):
            continue
        yield base


def bare_fragments(text):
    """Bare source-file fragments (no root prefix) to basename-check (warn)."""
    for tok in BACKTICK.findall(text):
        base = _normalise(tok)
        if base.startswith(ROOTS):
            continue  # handled by the full-path pass
        if not base.endswith(SRC_EXT):
            continue
        if _placeholder(base):
            continue
        # require a real stem before the extension — skip bare extension
        # mentions like `.c` / `.clausal` (which are not filenames)
        if not os.path.basename(base).rsplit(".", 1)[0]:
            continue
        yield base


def repo_basenames():
    names = set()
    for dirpath, dirnames, filenames in os.walk(REPO):
        dirnames[:] = [d for d in dirnames if d not in PRUNE_DIRS]
        names.update(filenames)
    return names


def main(argv):
    strict = "--strict" in argv
    prompts = [a for a in argv if a != "--strict"]

    misses = []
    for prompt in prompts:
        text = Path(prompt).read_text()
        for p in candidate_paths(text):
            if not (REPO / p).exists():
                misses.append((prompt, p))

    names = repo_basenames()
    warnings = []
    for prompt in prompts:
        text = Path(prompt).read_text()
        for frag in bare_fragments(text):
            if os.path.basename(frag) not in names:
                warnings.append((prompt, frag))

    if warnings:
        print("WARNINGS (bare fragment names no file in repo):")
        for prompt, frag in warnings:
            print(f"  {prompt}: {frag}")

    if misses:
        print("MISSING PATHS:")
        for prompt, p in misses:
            print(f"  {prompt}: {p}")

    failed = bool(misses) or (strict and bool(warnings))
    if failed:
        return 1
    suffix = f" ({len(warnings)} warning(s))" if warnings else ""
    print(f"OK: all repo paths in {len(prompts)} prompt(s) resolve{suffix}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
