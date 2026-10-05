"""Unified CLI for bidirectional seam ↔ Prolog translation.

The seam side is seam (Python-syntax) source, ``.seam``.  The Prolog side is
ISO Prolog text; a ``.pl`` or Clausal Prolog (``.clausal``) input is read as
Prolog.  ``--to clausal`` writes SEAM text (the historical name of the
direction), not a Clausal Prolog file.

Usage
-----
# Seam → Prolog
python -m clausal.tools.translate input.seam --to swi -o output.pl
python -m clausal.tools.translate input.seam --to scryer -o output.pl

# Prolog → seam
python -m clausal.tools.translate input.pl --to clausal -o output.seam

# Auto-detect direction from file extension
python -m clausal.tools.translate input.seam             # → stdout as ISO Prolog
python -m clausal.tools.translate input.pl               # → stdout as seam

# Roundtrip check
python -m clausal.tools.translate --roundtrip input.seam --dialect swi
python -m clausal.tools.translate --roundtrip input.pl --dialect swi
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from clausal._suffixes import (
    CLAUSAL_SUFFIXES, prolog_suffixes, seam_suffixes_text,
    suffix_list,
)
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
        if ext in prolog_suffixes():
            return "prolog_to_clausal"
        if ext in CLAUSAL_SUFFIXES:
            return "clausal_to_prolog"

    # Default: treat as clausal → prolog (ISO)
    return "clausal_to_prolog"


def _contradiction(path: str | None, to_flag: str | None) -> str | None:
    """Why *to_flag* cannot apply to the file at *path*, or None.

    ``--to`` names the direction; a file's extension names its surface.
    When both are given and disagree, the translator would read the file in
    the wrong language and fail with a parse error about its own syntax, so
    the disagreement is refused up front.  Stdin (no *path*) and an
    extension that names no surface keep trusting ``--to``."""
    if not path or to_flag is None:
        return None
    ext = Path(path).suffix.lower()
    if ext in prolog_suffixes() and to_flag in _DIALECT_FACTORIES:
        return (f"{path} is Prolog ({ext}), but --to {to_flag} translates "
                f"seam source ({seam_suffixes_text()}) to Prolog; use "
                f"--to clausal, or omit --to, to translate it to seam source")
    if ext in CLAUSAL_SUFFIXES and to_flag == "clausal":
        dialects = "|".join(_DIALECT_FACTORIES)
        return (f"{path} is seam source ({ext}), but --to clausal "
                f"translates Prolog ({suffix_list(prolog_suffixes())}) to "
                f"seam source; use --to {dialects}, or omit --to, to "
                f"translate it to Prolog")
    return None


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
        help=f"Input file: seam ({seam_suffixes_text()}) or Prolog "
             f"({suffix_list(prolog_suffixes())}); reads stdin if omitted.",
    )
    parser.add_argument(
        "-o", "--output", default=None,
        help="Output file; writes stdout if omitted.",
    )
    parser.add_argument(
        "--to", dest="to", default=None,
        choices=["clausal", "iso", "swi", "scryer"],
        help=(
            "Target format. 'clausal' translates Prolog→seam source; "
            "'iso'/'swi'/'scryer' translate seam source→Prolog. "
            "Auto-detected from file extension if omitted."
        ),
    )
    parser.add_argument(
        "--dialect", default=None,
        choices=["iso", "swi", "scryer"],
        help="Prolog dialect (default: iso for clausal→prolog; for prolog→clausal, "
             "Scryer's operator table).",
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
    refusal = _contradiction(args.input, args.to)
    if refusal:
        parser.error(refusal)          # exit 2: a usage error

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
        dialect = Dialect.scryer_reader()
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
