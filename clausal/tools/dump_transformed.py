"""clausal.tools.dump_transformed — dump the transformed AST of .clausal files as Python.

Reads a ``.clausal`` file, runs ``EmbedTransformer`` on it, unparses the
resulting AST back to Python source, and writes the output to a
``__transformed__/`` directory next to the source file.

Public API
----------
    dump(path, *, outdir=None) → str
        Transform *path* and write the Python source to *outdir* (default:
        ``__transformed__/`` next to the source).  Returns the output path.

    dump_source(path) → str
        Return the transformed Python source as a string (no file written).

CLI usage
---------
    python -m clausal.tools.dump_transformed FILE [FILE ...]
    python -m clausal.tools.dump_transformed tests/clausal_modules/

If given a directory, all ``.clausal`` (and ``.seam``) files in it
(non-recursive) are dumped.
"""

from __future__ import annotations

import ast
import os
import sys
import warnings

from clausal._suffixes import CLAUSAL_SUFFIXES


def dump_source(path: str) -> str:
    """Return the transformed Python source for a ``.clausal`` file."""
    from clausal.templating.term_rewriting import EmbedTransformer

    source = open(path).read()
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="'str' object is not callable",
            category=SyntaxWarning,
        )
        tree = ast.parse(source, filename=path)
    # A10-F007: pass source_lines so arrow detection is byte-faithful to
    # import_hook._parse_clausal_source. Without it, a legal Lt guard like
    # ``X< -3`` uses the column-gap heuristic and dumps a Lambda/Predicate,
    # diverging from what the import hook actually compiles.
    tree = EmbedTransformer(source_lines=source.splitlines(keepends=True)).visit(tree)
    ast.fix_missing_locations(tree)

    unparsed = ast.unparse(tree)

    # Try to format with black if available.
    # The transformed source contains $-prefixed names which aren't valid Python,
    # so we temporarily rename them for formatting, then restore them.
    # A10-F007: guard the import separately — referencing black.parsing in the
    # except tuple when `import black` itself failed raised UnboundLocalError
    # on every call in a black-less environment.
    try:
        import black
    except ImportError:
        black = None
    if black is not None:
        import re

        # Replace $name with __dollar_name__ for parsing
        dollar_names: dict[str, str] = {}
        def _replace_dollar(m: re.Match) -> str:
            orig = m.group(0)
            safe = "__dollar_" + orig[1:] + "__"
            dollar_names[safe] = orig
            return safe

        safe_source = re.sub(r"\$\w+", _replace_dollar, unparsed)
        try:
            formatted = black.format_str(safe_source, mode=black.Mode())
            # Restore $names
            for safe, orig in dollar_names.items():
                formatted = formatted.replace(safe, orig)
            unparsed = formatted
        except black.parsing.InvalidInput:
            pass

    return unparsed


def dump(path: str, *, outdir: str | None = None) -> str:
    """Transform *path* and write the result to *outdir*.

    Returns the output file path.
    """
    source = dump_source(path)

    if outdir is None:
        outdir = os.path.join(os.path.dirname(path), "__transformed__")
    os.makedirs(outdir, exist_ok=True)

    basename = os.path.splitext(os.path.basename(path))[0] + ".py"
    outpath = os.path.join(outdir, basename)
    with open(outpath, "w") as f:
        f.write(source)
        if not source.endswith("\n"):
            f.write("\n")

    return outpath


def main(argv: list[str] | None = None) -> None:
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print("Usage: python -m clausal.tools.dump_transformed FILE [FILE ...]")
        print("       python -m clausal.tools.dump_transformed DIR")
        sys.exit(1)

    paths: list[str] = []
    for arg in args:
        if os.path.isdir(arg):
            for entry in sorted(os.listdir(arg)):
                if entry.endswith(CLAUSAL_SUFFIXES):
                    paths.append(os.path.join(arg, entry))
        elif os.path.isfile(arg):
            paths.append(arg)
        else:
            print(f"warning: {arg!r} not found, skipping", file=sys.stderr)

    if not paths:
        print("No .clausal (or .seam) files found.", file=sys.stderr)
        sys.exit(1)

    for path in paths:
        outpath = dump(path)
        print(f"{path} -> {outpath}")


if __name__ == "__main__":
    main()
