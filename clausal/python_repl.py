"""python_repl.py — Python REPL integrations for Clausal.

Three tiers of REPL support, from best to most compatible:

ptpython (optional)
    Full-featured REPL with syntax highlighting, smart tab completion, and
    multi-line editing.  Requires ``ptpython`` (``pip install ptpython``).
    AST transformation via ``_compile_with_flags`` override.

ClausalConsole (zero extra deps)
    ``code.InteractiveConsole`` subclass.  Same Clausal syntax support as
    ptpython, but plain readline editing.  Falls back from ptpython when it
    is not installed.

enable_python_repl (partial, existing session)
    Call from ``$PYTHONSTARTUP`` or an interactive session to inject Clausal
    names and the ``Solutions`` display hook.  **No ``*(goals)`` syntax** —
    AST transformation requires a custom REPL.

Entry points
------------
``clausal-repl`` / ``python -m clausal``
    Tries ptpython; falls back to ClausalConsole.
"""

from __future__ import annotations

import ast
import code
import sys
import warnings


# ── Shared helpers ────────────────────────────────────────────────────────────


def _install_displayhook() -> None:
    """Replace sys.displayhook so Solutions objects display interactively.

    Without this, ``repr(solutions)`` would call ``_run()`` but then
    ``print("")`` emits a trailing blank line.  The custom hook calls
    ``_run()`` directly and suppresses the empty-string printout.
    """
    from clausal.repl import Solutions
    import builtins
    _orig = sys.displayhook

    def _hook(value):
        if isinstance(value, Solutions):
            builtins._ = value
            value._run()
        else:
            _orig(value)

    sys.displayhook = _hook


def _enable_colors() -> None:
    """Enable ANSI term colours when stdout is a real TTY."""
    if not sys.stdout.isatty():
        return
    try:
        from clausal.terms import set_style, TermStyle, ANSI_COLORS
        set_style(TermStyle(colors=ANSI_COLORS))
    except Exception:
        pass


def _base_namespace() -> dict:
    """Return a namespace dict seeded with all Clausal builtins and helpers."""
    from clausal.import_hook import _simple_ast_builtins
    from clausal.terms import set_style, TermStyle, ANSI_COLORS
    ns = dict(_simple_ast_builtins)
    ns["set_style"] = set_style
    ns["TermStyle"] = TermStyle
    ns["ANSI_COLORS"] = ANSI_COLORS
    return ns


_BANNER = (
    "Clausal REPL  (*(Goal(X)) to query  |  Uppercase names → logic vars  |  Ctrl-D to exit)\n"
)


# ── ClausalConsole (zero-dependency fallback) ─────────────────────────────────


class ClausalConsole(code.InteractiveConsole):
    """Python REPL with Clausal AST transformation (``code.InteractiveConsole`` subclass).

    Supports the full ``*(goals)`` query syntax, ``--expr`` term embedding,
    and interactive ``Solutions`` display.  Uses readline for editing (no
    syntax highlighting or smart completion).

    Prefer ``launch_ptpython()`` when ptpython is available.
    """

    def __init__(self, locals=None, filename="<console>"):
        ns = _base_namespace()
        if locals:
            ns.update(locals)
        super().__init__(locals=ns, filename=filename)
        _install_displayhook()
        _enable_colors()
        # Suppress "'str' object is not callable" SyntaxWarning: the DSL uses
        # 'foo'(args) syntax intentionally; our transformer rewrites it before
        # bytecode generation, but ast.parse() still triggers the warning.
        warnings.filterwarnings(
            "ignore",
            message="'str' object is not callable",
            category=SyntaxWarning,
        )

    def runsource(self, source, filename="<input>", symbol="single"):
        """Parse → transform → compile → run one source unit.

        Returns ``True`` (need more input) or ``False`` (executed/error).
        """
        import codeop

        # Completeness check via codeop.  Our special syntax (e.g. ``*(goals)``)
        # parses as valid AST but fails bytecode compilation; codeop raises
        # SyntaxError for those — we catch and continue.
        std_result = _sentinel = object()
        try:
            std_result = codeop.compile_command(source, filename, symbol)
        except SyntaxError:
            pass
        except (OverflowError, ValueError):
            self.showtraceback()
            return False

        if std_result is None:
            return True  # Incomplete — need more input

        try:
            tree = ast.parse(source, filename, symbol)
        except SyntaxError:
            self.showsyntaxerror(filename)
            return False

        from clausal.import_hook import _FreshEmbedTransformer
        try:
            transformed = _FreshEmbedTransformer().visit(tree)
            ast.fix_missing_locations(transformed)
        except Exception:
            self.showtraceback()
            return False

        try:
            code_obj = compile(transformed, filename, symbol)
        except SyntaxError:
            self.showsyntaxerror(filename)
            return False

        self.runcode(code_obj)
        return False


# ── ptpython integration ──────────────────────────────────────────────────────


def _make_clausal_compile(repl):
    """Return a ``_compile_with_flags`` replacement for a ptpython PythonRepl.

    The returned function is bound over *repl* so it can call
    ``repl.get_compiler_flags()``.  It applies Clausal's AST transformers
    between parsing and bytecode compilation.

    Mode promotion
    ~~~~~~~~~~~~~~
    ptpython falls back to ``"exec"`` mode when ``"eval"`` fails.  In
    ``"exec"`` mode Python discards bare expression results — ``sys.displayhook``
    is never called, so ``Solutions`` would silently vanish.  We promote
    single-expression statements to ``"single"`` mode, which emits
    ``CALL_INTRINSIC_1 (INTRINSIC_PRINT)`` (a.k.a. PRINT_EXPR) and calls
    ``sys.displayhook``, matching interactive-REPL behaviour.

    Multi-statement code stays in ``"exec"`` mode (``"single"`` only accepts
    one statement).
    """
    from clausal.import_hook import _FreshEmbedTransformer

    def _compile_with_flags(code: str, mode: str):
        # Parse to AST.  Let SyntaxError propagate — in eval mode this
        # triggers ptpython's eval→exec fallback (e.g. *(goals) fails as eval).
        tree = ast.parse(code, "<stdin>", mode)

        # Apply Clausal transformers.  Errors fall back to the original tree.
        try:
            transformed = _FreshEmbedTransformer().visit(tree)
            ast.fix_missing_locations(transformed)
        except Exception:
            transformed = tree

        # Promote single bare-expression statements from "exec" to "single"
        # so that sys.displayhook is called (making Solutions interactive).
        # compile() with mode="single" requires an Interactive node, not Module.
        if (mode == "exec"
                and len(transformed.body) == 1
                and isinstance(transformed.body[0], ast.Expr)):
            transformed = ast.fix_missing_locations(
                ast.Interactive(body=transformed.body)
            )
            effective_mode = "single"
        else:
            effective_mode = mode

        return compile(
            transformed,
            "<stdin>",
            effective_mode,
            flags=repl.get_compiler_flags(),
            dont_inherit=True,
        )

    return _compile_with_flags


def _configure_clausal_repl(repl) -> None:
    """Configure a ptpython PythonRepl for Clausal use.

    - Patches ``_compile_with_flags`` with Clausal AST transformation
    - Injects Clausal names and colour helpers into the repl namespace
    - Enables ANSI colours (if TTY) and useful ptpython UI defaults
    """
    # Install AST transformer hook
    repl._compile_with_flags = _make_clausal_compile(repl)

    # Inject Clausal names
    ns = repl.get_globals()
    ns.update(_base_namespace())

    # Enable ANSI term colours
    _enable_colors()

    # Nice UI defaults
    repl.show_signature = True
    repl.show_docstring = False   # keeps output clean
    repl.enable_fuzzy_completion = True
    repl.highlight_matching_parenthesis = True

    # Suppress the SyntaxWarning (same reason as ClausalConsole)
    warnings.filterwarnings(
        "ignore",
        message="'str' object is not callable",
        category=SyntaxWarning,
    )


def launch_ptpython(user_globals: dict | None = None) -> None:
    """Launch a ptpython REPL with full Clausal integration.

    :param user_globals: Extra names to inject into the REPL namespace.
    :raises ImportError: If ptpython is not installed.
    """
    from ptpython.repl import embed  # raises ImportError if not installed

    import os

    ns = _base_namespace()
    if user_globals:
        ns.update(user_globals)

    _install_displayhook()

    history_file = os.path.expanduser("~/.clausal_history")

    print(_BANNER, end="")

    embed(
        globals=ns,
        title="Clausal",
        history_filename=history_file,
        configure=_configure_clausal_repl,
    )


# ── Partial integration (existing session) ────────────────────────────────────


def enable_python_repl(user_globals: dict) -> None:
    """Inject Clausal names and display hook into an existing REPL session.

    Provides Clausal names in scope and interactive ``Solutions`` display,
    but **not** the ``*(goals)`` query syntax (which requires a custom REPL
    with AST transformation).

    Use ``clausal-repl`` / ``python -m clausal`` for the full experience.
    Useful in ``$PYTHONSTARTUP`` for partial setup::

        from clausal.python_repl import enable_python_repl
        enable_python_repl(globals())
    """
    user_globals.update(_base_namespace())
    _install_displayhook()
    _enable_colors()


# ── Entry point ───────────────────────────────────────────────────────────────


def main() -> None:
    """Launch the Clausal REPL (``clausal-repl`` / ``python -m clausal``)."""
    try:
        launch_ptpython()
    except ImportError:
        console = ClausalConsole()
        console.interact(banner=_BANNER, exitmsg="")


if __name__ == "__main__":
    main()
