"""``clausal-rewrite`` -- apply Clausal rewrite rules, then format.

    clausal-rewrite src/                    rewrite every .clausal/.seam file under src/
    clausal-rewrite --check src/            exit 1 if any file would change
    clausal-rewrite --diff src/             print what would change, write nothing
    clausal-rewrite --rules head_fold f     apply only the named rule classes

Exit codes match ``clausal-fmt``: 0 clean or written, 1 something would change
under ``--check``/``--diff``, 2 a file could not be handled -- in which case
nothing was written for it, and the reason is on stderr.

Note that a rewrite run also FORMATS: the output goes through the formatter, so
a file that no rule touched still comes back house-style.  That is why
``--check`` on an unformatted file reports a change with zero rule firings.
"""

from __future__ import annotations

import argparse
import pathlib
import sys
from pathlib import Path

from clausal._suffixes import CLAUSAL_SUFFIXES, seam_suffixes_text
from clausal.fmt.cli import clausal_files, prolog_refusal
from clausal.fmt.comments import CommentLeakError
from clausal.fmt.verify import unified_diff
from clausal.rewrite.driver import RewriteError, rewrite_source

RULES_DIR = Path(__file__).parent / "rules"


class UnknownRule(Exception):
    """A ``--rules`` name with no rule file behind it."""


def default_rule_names() -> list[str]:
    """Every shipped rule class.

    Leading-underscore files are excluded: the suite keeps a deliberately
    broken copy of a rule beside the real one, to prove its legality checks
    are load-bearing, and a tool that applied it would be applying a known
    unsound rewrite.
    """
    return sorted({
        path.stem
        for suffix in CLAUSAL_SUFFIXES
        for path in RULES_DIR.glob(f"*{suffix}")
        if not path.stem.startswith("_")
    })


def rule_path(name: str) -> Path | None:
    """The file behind rule class *name*, or ``None`` if there is none.

    The one place a rule name becomes a path.  ``.clausal`` and ``.seam`` are
    aliases, so both spellings are tried, in ``CLAUSAL_SUFFIXES`` order — the
    finder's own priority, so a directory holding both twins resolves the way
    an import of the same stem would.
    """
    # A rule name is a bare stem, never a path.  `load_rules` EXECUTES what
    # this returns, so a name carrying separators (`../../tmp/evil`) would
    # otherwise reach `_load_module` from outside the rules directory.  The
    # exposure predates this function; making it the one place a name becomes
    # a path makes it the one place to enforce that.
    if name != pathlib.Path(name).name or name in ("", ".", ".."):
        return None
    for suffix in CLAUSAL_SUFFIXES:
        candidate = RULES_DIR / f"{name}{suffix}"
        if candidate.is_file():
            return candidate
    return None


def rule_paths(names: list[str]) -> list[Path]:
    paths = []
    for name in names:
        path = rule_path(name)
        if path is None:
            raise UnknownRule(
                f"unknown rule class: {name} "
                f"(available: {', '.join(default_rule_names())})"
            )
        paths.append(path)
    return paths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="clausal-rewrite",
        description=f"Apply Clausal rewrite rules to seam "
                    f"({seam_suffixes_text()}) source, then format it.",
    )
    parser.add_argument("paths", nargs="+", help="files or directories")
    parser.add_argument(
        "--rules",
        default=None,
        help="comma-separated rule classes (default: every shipped class)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit 1 if any file would change; write nothing",
    )
    parser.add_argument(
        "--diff", action="store_true", help="print a unified diff; write nothing"
    )
    args = parser.parse_args(argv)

    names = args.rules.split(",") if args.rules else default_rule_names()
    try:
        rules = rule_paths(names)
    except UnknownRule as error:
        print(str(error), file=sys.stderr)
        return 2

    changed = 0
    failed = 0
    for path in clausal_files(args.paths):
        refusal = prolog_refusal(path, "clausal-rewrite")
        if refusal is not None:
            print(refusal, file=sys.stderr)
            failed += 1
            continue
        try:
            source = path.read_text()
            result = rewrite_source(source, rules)
        except (OSError, SyntaxError, CommentLeakError, RewriteError) as error:
            print(f"{path}: {type(error).__name__}: {error}", file=sys.stderr)
            failed += 1
            continue
        if result.text == source:
            continue
        changed += 1
        if args.diff:
            sys.stdout.write(
                unified_diff(source, result.text, str(path), f"{path} (rewritten)")
            )
        elif args.check:
            print(f"would rewrite {path} ({len(result.fired)} rule firings)")
        else:
            path.write_text(result.text)

    if failed:
        return 2
    if changed and (args.check or args.diff):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
