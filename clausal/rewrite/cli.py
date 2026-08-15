"""``clausal-rewrite`` -- apply Clausal rewrite rules, then format.

    clausal-rewrite src/                    rewrite every .clausal file under src/
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
import sys
from pathlib import Path

from clausal.fmt.cli import clausal_files
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
    return sorted(
        path.stem for path in RULES_DIR.glob("*.clausal")
        if not path.stem.startswith("_")
    )


def rule_paths(names: list[str]) -> list[Path]:
    paths = []
    for name in names:
        path = RULES_DIR / f"{name}.clausal"
        if not path.is_file():
            raise UnknownRule(
                f"unknown rule class: {name} "
                f"(available: {', '.join(default_rule_names())})"
            )
        paths.append(path)
    return paths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="clausal-rewrite",
        description="Apply Clausal rewrite rules to .clausal source, then format it.",
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
