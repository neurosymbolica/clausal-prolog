"""Validate that every *source* repo path named in an audit prompt exists.

Extracts backtick-quoted tokens that look like FULL repo paths (start with a
known top-level dir AND end in a code extension or '/') and asserts each exists
relative to the repo root. This catches stale source-under-audit paths before a
session is launched.

Deliberately skips:
- the audit's own OUTPUT roots (findings.md, per-subsystem test files, todos) —
  those are created by the audit sessions, so they legitimately don't exist yet;
- prompt-template tokens still containing `{{...}}`;
- glob/brace/placeholder shorthand (`*`, `{`, `<`), bare fragments (`terms.py`,
  `optimisations/`), and absolute clausify refs.

Usage: python scripts/audit_2026_07_05/check_prompt_paths.py <prompt.md>...
Exit 0 if all paths resolve, 1 otherwise (prints the misses).
"""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CODE_EXT = (".py", ".c", ".h", ".md", ".clausal")
ROOTS = ("clausal/", "tests/", "docs/", "todo/", "scripts/",
         "packages/", "prolog_backends/", "benchmarks/")
# audit-output roots: created by the sessions, not required to exist now
SKIP_PREFIXES = (
    "tests/audit_2026_07_05/",
    "docs/superpowers/audits/2026-07-05-fable-partition/",
    "todo/audit-2026-07-05/",
)
BACKTICK = re.compile(r"`([^`]+)`")


def candidate_paths(text):
    for tok in BACKTICK.findall(text):
        tok = "".join(tok.split())  # collapse markdown line-wraps inside `...`
        base = re.sub(r":\d+(-\d+)?$", "", tok)  # strip :line refs
        if not base.startswith(ROOTS):
            continue
        if not (base.endswith("/") or base.endswith(CODE_EXT)):
            continue
        if any(c in base for c in "*{<"):  # globs, braces, <placeholders>
            continue
        if base.startswith(SKIP_PREFIXES):
            continue
        yield base


def main(argv):
    misses = []
    for prompt in argv:
        text = Path(prompt).read_text()
        for p in candidate_paths(text):
            if not (REPO / p).exists():
                misses.append((prompt, p))
    if misses:
        print("MISSING PATHS:")
        for prompt, p in misses:
            print(f"  {prompt}: {p}")
        return 1
    print(f"OK: all repo paths in {len(argv)} prompt(s) resolve")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
