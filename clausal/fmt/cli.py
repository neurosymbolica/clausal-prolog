"""``clausal-fmt`` -- format ``.clausal`` files in place, or check them.

    clausal-fmt src/                 rewrite every .clausal file under src/
    clausal-fmt --check src/         exit 1 if any file would change
    clausal-fmt --diff  src/         print what would change, write nothing

A file the formatter cannot handle -- a syntax error, or a comment it would
have lost -- is reported on stderr and left exactly as it was; the run then
exits 2.  Refusing is always better than half-formatting someone's source.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from clausal.fmt.comments import CommentLeakError
from clausal.fmt.emit import ArrowRenderError, format_source
from clausal.fmt.verify import unified_diff

SUFFIX = ".clausal"


def clausal_files(paths: list[str]) -> list[Path]:
    """Every ``.clausal`` file named, or found under a named directory."""
    found: list[Path] = []
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            found.extend(sorted(path.rglob(f"*{SUFFIX}")))
        else:
            found.append(path)
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="clausal-fmt", description="Format .clausal source."
    )
    parser.add_argument("paths", nargs="+", help="files or directories")
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit 1 if any file would change; write nothing",
    )
    parser.add_argument(
        "--diff", action="store_true", help="print a unified diff; write nothing"
    )
    args = parser.parse_args(argv)

    changed = 0
    failed = 0
    for path in clausal_files(args.paths):
        try:
            source = path.read_text()
            formatted = format_source(source)
        except (OSError, SyntaxError, CommentLeakError, ArrowRenderError) as error:
            print(f"{path}: {type(error).__name__}: {error}", file=sys.stderr)
            failed += 1
            continue
        if formatted == source:
            continue
        changed += 1
        if args.diff:
            sys.stdout.write(
                unified_diff(source, formatted, str(path), f"{path} (formatted)")
            )
        elif not args.check:
            path.write_text(formatted)

    if failed:
        return 2
    if changed and (args.check or args.diff):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
