"""Unified CLI for bidirectional clausal ↔ Prolog translation.

Usage
-----
# Clausal → Prolog
python -m clausal.tools.translate input.clausal --to swi -o output.pl
python -m clausal.tools.translate input.clausal --to scryer -o output.pl

# Prolog → Clausal
python -m clausal.tools.translate input.pl --to clausal -o output.clausal

# Auto-detect direction from file extension
python -m clausal.tools.translate input.clausal          # → stdout as ISO Prolog
python -m clausal.tools.translate input.pl               # → stdout as clausal

# Roundtrip check
python -m clausal.tools.translate --roundtrip input.clausal --dialect swi
python -m clausal.tools.translate --roundtrip input.pl --dialect swi
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from clausal.tools.clausal_to_prolog import clausal_source_to_prolog
from clausal.tools.prolog_dialect import Dialect
from clausal.tools.prolog_to_clausal import prolog_to_clausal


_DIALECT_FACTORIES = {
    "iso": Dialect.iso,
    "swi": Dialect.swi,
    "scryer": Dialect.scryer,
}


def _detect_direction(path: str | None, to_flag: str | None) -> str:
    """Return ``'clausal_to_prolog'`` or ``'prolog_to_clausal'``.

    Uses *to_flag* first; falls back to file extension heuristics.
    """
    if to_flag == "clausal":
        return "prolog_to_clausal"
    if to_flag in _DIALECT_FACTORIES:
        return "clausal_to_prolog"

    if path:
        ext = Path(path).suffix.lower()
        if ext == ".pl":
            return "prolog_to_clausal"
        if ext in (".clausal",):
            return "clausal_to_prolog"

    # Default: treat as clausal → prolog (ISO)
    return "clausal_to_prolog"


def translate(source: str, *, direction: str, dialect: Dialect) -> str:
    """Translate *source* in the given *direction* using *dialect*."""
    if direction == "clausal_to_prolog":
        return clausal_source_to_prolog(source, dialect=dialect)
    else:
        return prolog_to_clausal(source, dialect=dialect)


def roundtrip(source: str, *, direction: str, dialect: Dialect) -> tuple[bool, str, str]:
    """Translate *source* there and back; return ``(ok, first, second)``.

    *direction* is the **first** leg of the trip (detected from the input).
    Returns the two intermediate texts and whether the final result matches
    the original source.
    """
    first = translate(source, direction=direction, dialect=dialect)
    reverse = (
        "prolog_to_clausal" if direction == "clausal_to_prolog"
        else "clausal_to_prolog"
    )
    second = translate(first, direction=reverse, dialect=dialect)
    return (second == source, first, second)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="clausal-translate",
        description="Bidirectional clausal ↔ Prolog translation.",
    )
    parser.add_argument(
        "input", nargs="?", default=None,
        help="Input file (.clausal or .pl); reads stdin if omitted.",
    )
    parser.add_argument(
        "-o", "--output", default=None,
        help="Output file; writes stdout if omitted.",
    )
    parser.add_argument(
        "--to", dest="to", default=None,
        choices=["clausal", "iso", "swi", "scryer"],
        help=(
            "Target format. 'clausal' translates Prolog→clausal; "
            "'iso'/'swi'/'scryer' translate clausal→Prolog. "
            "Auto-detected from file extension if omitted."
        ),
    )
    parser.add_argument(
        "--dialect", default=None,
        choices=["iso", "swi", "scryer"],
        help="Prolog dialect (default: iso for clausal→prolog, swi for prolog→clausal).",
    )
    parser.add_argument(
        "--roundtrip", action="store_true",
        help="Translate there and back; exit 0 if roundtrip reproduces the original.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point.  Returns exit code (0 = success)."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    # --- Read input --------------------------------------------------------
    if args.input is None:
        source = sys.stdin.read()
    else:
        source = Path(args.input).read_text(encoding="utf-8")

    # --- Direction ---------------------------------------------------------
    direction = _detect_direction(args.input, args.to)

    # --- Dialect -----------------------------------------------------------
    if args.dialect:
        dialect = _DIALECT_FACTORIES[args.dialect]()
    elif args.to and args.to in _DIALECT_FACTORIES:
        dialect = _DIALECT_FACTORIES[args.to]()
    elif direction == "prolog_to_clausal":
        dialect = Dialect.swi()
    else:
        dialect = Dialect.iso()

    # --- Execute -----------------------------------------------------------
    if args.roundtrip:
        ok, first, second = roundtrip(source, direction=direction, dialect=dialect)
        if ok:
            print("Roundtrip OK", file=sys.stderr)
            return 0
        else:
            print("Roundtrip FAILED — output differs from input.", file=sys.stderr)
            print("--- first leg ---", file=sys.stderr)
            sys.stderr.write(first[:2000])
            print("\n--- second leg ---", file=sys.stderr)
            sys.stderr.write(second[:2000])
            print(file=sys.stderr)
            return 1
    else:
        result = translate(source, direction=direction, dialect=dialect)
        if args.output:
            Path(args.output).write_text(result, encoding="utf-8")
        else:
            sys.stdout.write(result)
        return 0


if __name__ == "__main__":
    sys.exit(main())
