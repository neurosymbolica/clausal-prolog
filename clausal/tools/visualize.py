"""clausal.tools.visualize — pretty-print compiled predicate code.

Two output modes:
  'source'  — unparse the generated ``ast.FunctionDef`` to Python source using
              ``ast.unparse``; optionally reformatted with ``black`` if available.
  'ast'     — render the AST node tree using ``astpretty`` if available, falling
              back to ``ast.dump`` with indentation.

Public API
----------
    predicate_ast(functor, arity, clauses, db, *, trampoline=False)
        → ast.FunctionDef

    predicate_to_source(functor, arity, clauses, db, *, trampoline=False)
        → str

    show(functor, arity, clauses, db, *, trampoline=False, mode='source')
        → None   (prints to stdout)

CLI usage
---------
    python -m clausal.tools.visualize   (interactive; prompts for functor/arity)

In tests, call ``show()`` directly and capture output with pytest's ``-s`` flag
or ``capsys``.
"""

from __future__ import annotations

import ast
import sys
from typing import Any

from clausal.logic.compiler import (
    compile_predicate_ast,
    compile_predicate_trampoline_ast,
)
from clausal.logic.database import Clause, Database


def predicate_ast(
    functor: str,
    arity: int,
    clauses: list[Clause],
    db: Database,
    *,
    trampoline: bool = False,
) -> ast.FunctionDef:
    """Return the ``ast.FunctionDef`` for the compiled predicate.

    Parameters
    ----------
    functor:     predicate name
    arity:       predicate arity
    clauses:     clause list (from ``db.clauses_for(functor, arity)``)
    db:          the database — used for dispatch lookups in body compilation
    trampoline:  if True, use the stack-safe trampoline compilation strategy;
                 if False (default), use the simple/short-stack strategy
    """
    if trampoline:
        return compile_predicate_trampoline_ast(functor, arity, clauses, db)
    return compile_predicate_ast(functor, arity, clauses, db)


def predicate_to_source(
    functor: str,
    arity: int,
    clauses: list[Clause],
    db: Database,
    *,
    trampoline: bool = False,
) -> str:
    """Compile the predicate and return the generated source code as a string.

    Uses ``ast.unparse`` to convert the FunctionDef back to Python source.
    If ``black`` is installed it is used to auto-format the output; otherwise
    the raw ``ast.unparse`` output (compact but valid Python) is returned.
    """
    func_def = predicate_ast(functor, arity, clauses, db, trampoline=trampoline)
    raw = ast.unparse(func_def)

    # Try black for nicer formatting
    try:
        import black
        raw = black.format_str(raw, mode=black.Mode())
    except (ImportError, Exception):
        pass

    return raw


def predicate_to_ast_str(
    functor: str,
    arity: int,
    clauses: list[Clause],
    db: Database,
    *,
    trampoline: bool = False,
) -> str:
    """Return the AST node tree as a string.

    Uses ``astpretty`` if available; falls back to ``ast.dump`` with indentation.
    """
    func_def = predicate_ast(functor, arity, clauses, db, trampoline=trampoline)

    try:
        import io
        import astpretty  # type: ignore[import]
        buf = io.StringIO()
        astpretty.pprint(func_def, file=buf)
        return buf.getvalue()
    except (ImportError, Exception):
        return ast.dump(func_def, indent=2)


def show(
    functor: str,
    arity: int,
    clauses: list[Clause],
    db: Database,
    *,
    trampoline: bool = False,
    mode: str = "source",
) -> None:
    """Print the compiled predicate to stdout.

    Parameters
    ----------
    functor, arity, clauses, db:
        As for ``predicate_ast``.
    trampoline:
        If True, use trampoline compilation strategy.
    mode:
        ``'source'`` (default) — Python source via ``ast.unparse`` / black.
        ``'ast'``              — AST node tree via astpretty / ast.dump.
    """
    strategy = "trampoline" if trampoline else "simple"
    header = f"# {functor}/{arity}  [{strategy} mode]"
    print(header)
    print("# " + "-" * (len(header) - 2))
    if mode == "source":
        print(predicate_to_source(functor, arity, clauses, db, trampoline=trampoline))
    elif mode == "ast":
        print(predicate_to_ast_str(functor, arity, clauses, db, trampoline=trampoline))
    else:
        raise ValueError(f"Unknown mode {mode!r}; expected 'source' or 'ast'")


# ── CLI entry point ────────────────────────────────────────────────────────────


def _cli_main() -> None:  # pragma: no cover
    """Interactive CLI: build a tiny predicate and display it.

    Usage::

        python -m clausal.tools.visualize

    Or pass arguments on the command line::

        python -m clausal.tools.visualize --help
    """
    import argparse
    from clausal.logic.variables import Var
    from clausal.logic.database import Clause, Database
    from clausal.terms import Is, Compound

    parser = argparse.ArgumentParser(
        description="Show compiled clausal predicate source code.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Show the always-fail stub for an empty predicate
  python -m clausal.tools.visualize --functor foo --arity 2

  # Trampoline mode
  python -m clausal.tools.visualize --functor foo --arity 1 --trampoline

  # AST tree instead of source
  python -m clausal.tools.visualize --functor foo --arity 1 --mode ast
""",
    )
    parser.add_argument("--functor", default="demo", help="Predicate name")
    parser.add_argument("--arity", type=int, default=1, help="Predicate arity")
    parser.add_argument("--trampoline", action="store_true", help="Use trampoline mode")
    parser.add_argument("--mode", default="source", choices=["source", "ast"])
    args = parser.parse_args()

    db = Database()
    # Build a small demo predicate: demo(X) :- X = 42.
    x = Var()
    db.assertz(Clause(
        head=Compound(args.functor, tuple(Var() for _ in range(args.arity))),
        body=[],
    ))
    clauses = db.clauses_for(args.functor, args.arity)
    show(args.functor, args.arity, clauses, db, trampoline=args.trampoline, mode=args.mode)


if __name__ == "__main__":  # pragma: no cover
    _cli_main()
