"""Interactive solution iteration for the Clausal IPython REPL.

Provides a ``Solutions`` wrapper that displays query results one at a time,
Prolog-style, but using ``or`` as the separator between solutions.

Key bindings
------------
SPACE, n      next solution
ENTER, .      stop
ESC, q        abort
a             show all remaining solutions
"""

from __future__ import annotations

import sys
from typing import Iterator, Any


def _in_jupyter_kernel() -> bool:
    """Return True if running inside a Jupyter notebook kernel.

    Checks for ``ZMQInteractiveShell`` which is the IPython shell subclass
    used by Jupyter kernels.  Returns False for terminal IPython, plain
    Python, and non-IPython environments.
    """
    try:
        from IPython import get_ipython
        shell = get_ipython()
        if shell is None:
            return False
        return shell.__class__.__name__ == 'ZMQInteractiveShell'
    except (ImportError, AttributeError):
        return False


def _read_char() -> str:
    """Read a single keypress from the terminal without waiting for Enter.

    Returns the character, or a two-char string ``'\\x1b['`` prefix for
    arrow/escape sequences (only the bare ESC ``'\\x1b'`` is returned for a
    plain Escape press).

    Falls back to ``input()`` if stdin is not a TTY (e.g. tests, pipes).
    """
    if not sys.stdin.isatty():
        line = input()
        return line[:1] if line else '\r'

    try:
        import tty
        import termios
    except ImportError:
        # Windows or other platform without termios
        line = input()
        return line[:1] if line else '\r'

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        # If ESC, check for a following '[' (CSI sequence) and swallow it
        if ch == '\x1b':
            import select
            r, _, _ = select.select([sys.stdin], [], [], 0.05)
            if r:
                nxt = sys.stdin.read(1)
                if nxt == '[':
                    # Arrow key or similar — swallow the final byte too
                    sys.stdin.read(1)
                    return '\x1b'  # treat as plain ESC
                # Some other escape sequence — ignore the extra char
        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def _format_bindings(bindings: dict) -> str:
    """Format a binding dict as ``X is val, Y is val``, pretty-printed."""
    if not bindings:
        return "true."
    import shutil
    from clausal.terms import term_pformat, get_style
    width = shutil.get_terminal_size(fallback=(80, 24)).columns
    style = get_style()
    colors = style.colors or {}
    var_color = colors.get('var', '')
    reset = colors.get('reset', '') if var_color else ''
    parts = [(k, term_pformat(v, width=width)) for k, v in bindings.items()]
    if any("\n" in vstr for _, vstr in parts):
        return "\n".join(f"{var_color}{k}{reset} is {vstr}" for k, vstr in parts)
    return ",  ".join(f"{var_color}{k}{reset} is {vstr}" for k, vstr in parts)


def _format_bindings_html(bindings: dict) -> str:
    """Format a binding dict as HTML for Jupyter display."""
    if not bindings:
        return '<span class="clausal-atom">true.</span>'
    import html as _html
    from clausal.terms import term_pformat_html
    parts = []
    for k, v in bindings.items():
        vstr = term_pformat_html(v, width=120)
        parts.append(
            f'<span class="clausal-var">{_html.escape(k)}</span> is {vstr}'
        )
    if any("<pre>" in p for p in parts):
        return "<br>".join(parts)
    return ",&nbsp;&nbsp;".join(parts)


def _conj(*goals, _varnames=None):
    """Execute predicate instances as a Prolog-style conjunction on a shared
    trail and yield one binding dict per combined solution.

    Used by the ``*A, B, C`` query syntax rewrite.

    *_varnames* maps user-written variable names to their Var objects so that
    binding keys use the names the user wrote (e.g. ``ROWS``) rather than the
    predicate field names (e.g. ``rows``).
    """
    from clausal.logic.predicate import PredicateMeta
    from clausal.logic.variables import Trail, Var
    from clausal.logic.variables import walk as _walk
    from clausal.logic.solve import _drive_trampoline

    trail = Trail()
    id_to_name = {id(v): n for n, v in (_varnames or {}).items()}

    # Collect Var fields across all goals; last occurrence wins so that
    # a meaningful field name (e.g. 'rows') beats a generic one ('arg_1')
    # when the same Var appears in multiple goals.
    seen: dict[int, tuple[str, object]] = {}
    for goal in goals:
        if not isinstance(type(goal), PredicateMeta):
            raise TypeError(f"_conj: expected predicate instances, got {type(goal)}")
        for f in type(goal)._fields:
            v = getattr(goal, f)
            if isinstance(v, Var):
                seen[id(v)] = (id_to_name.get(id(v), f), v)
    var_fields = {f: v for f, v in seen.values()}

    def _run(remaining):
        if not remaining:
            yield
            return
        goal = remaining[0]
        rest = remaining[1:]
        cls = type(goal)
        dispatch = cls._get_dispatch()
        args = [getattr(goal, f) for f in cls._fields]
        for _ in _drive_trampoline(dispatch, trail, *args):
            yield from _run(rest)

    def _gen():
        for _ in _run(list(goals)):
            yield {f: _walk(v) for f, v in var_fields.items()}

    return _gen()


def _iter_from_goal(goal_or_iter, _varnames=None):
    """If given a predicate instance, drive it and yield binding dicts.
    Otherwise pass through as an iterator.

    *_varnames* maps user-written variable names to their Var objects so that
    binding keys use the names the user wrote rather than predicate field names.

    ``True`` is treated as a goal that succeeds once with no bindings (displays
    as ``True``).  ``False`` is treated as a goal that fails immediately
    (displays as ``False``).
    """
    from clausal.logic.predicate import PredicateMeta
    if not isinstance(type(goal_or_iter), PredicateMeta):
        if goal_or_iter is True:
            return iter([{}])
        if goal_or_iter is False:
            return iter([])
        try:
            return iter(goal_or_iter)
        except TypeError:
            raise TypeError(
                f"Solutions expects a predicate instance or iterator, "
                f"got {type(goal_or_iter).__name__}: {goal_or_iter!r}\n"
                f"Hint: Python's 'is' is an identity test, not unification."
            ) from None

    from clausal.logic.variables import Trail, is_var, Var
    from clausal.logic.variables import walk as _walk
    from clausal.logic.solve import _drive_trampoline

    id_to_name = {id(v): n for n, v in (_varnames or {}).items()}
    cls = type(goal_or_iter)
    dispatch = cls._get_dispatch()
    fields = cls._fields
    args = [getattr(goal_or_iter, f) for f in fields]
    var_fields = {
        id_to_name.get(id(getattr(goal_or_iter, f)), f): getattr(goal_or_iter, f)
        for f in fields if isinstance(getattr(goal_or_iter, f), Var)
    }
    trail = Trail()

    def _gen():
        for _ in _drive_trampoline(dispatch, trail, *args):
            yield {f: _walk(v) for f, v in var_fields.items()}

    return _gen()


def _run_ipython_goal(goal, variables: dict, ns: dict):
    """Drive a goal term as a zero-arity query and yield binding dicts.

    *goal* is a simple_ast term (already compiled by TermTransformer).
    *variables* maps user-written variable names to their Var objects.
    *ns* is the IPython namespace (used as the logic module's global dict).
    """
    from clausal.logic.database import Module
    from clausal.logic.solve import query
    module = Module("_ipython_query", module_dict=ns)
    return query(goal, variables, module)


class Solutions:
    """Interactive solution iterator for the Clausal REPL.

    Wrap any iterator of binding dicts (as returned by ``query()``)::

        X = Var()
        Solutions(query(goal, {"X": X}, module))

    when evaluated in an IPython cell the solutions are presented one at a
    time, separated by ``or``, with a key-driven prompt between each.

    in_ Jupyter notebooks, all solutions (up to *limit*) are rendered as
    styled HTML via :meth:`_repr_html_`.

    Key bindings (terminal IPython only)
    -------------------------------------
    SPACE, n      next solution
    ENTER, .      stop
    ESC, q        abort
    a             show all remaining solutions
    """

    DEFAULT_JUPYTER_LIMIT = 20

    _PROMPT = "   [SPACE/n: next  |  ENTER/.: stop  |  ESC/q: abort  |  a: all]  "

    def __init__(self, goal_or_iter: Any, _varnames=None, _read=None,
                 limit=None):
        self._iter = _iter_from_goal(goal_or_iter, _varnames=_varnames)
        # Allow tests to inject a scripted key-reader.
        self._read = _read if _read is not None else _read_char
        self._limit = limit

    # ------------------------------------------------------------------
    # IPython display protocol
    # ------------------------------------------------------------------

    def _ipython_display_(self, **kwargs):
        """Called by IPython instead of repr(); drives the interactive loop.

        in_ Jupyter kernels, delegates to :meth:`_repr_html_` for rich HTML
        display.  in_ terminal IPython, uses the interactive keypress loop.
        """
        if _in_jupyter_kernel():
            from IPython.display import display, HTML
            display(HTML(self._repr_html_()))
        else:
            self._run()
        # Return None so IPython prints nothing extra.

    def _repr_html_(self) -> str:
        """Rich HTML rendering for Jupyter notebooks."""
        from clausal.terms import JUPYTER_CSS

        limit = (self._limit if self._limit is not None
                 else self.DEFAULT_JUPYTER_LIMIT)

        solutions = []
        exhausted = False
        for i, bindings in enumerate(self._iter):
            if i >= limit:
                break
            solutions.append(bindings)
        else:
            exhausted = True

        if not solutions:
            return (
                JUPYTER_CSS
                + '<div class="clausal-output">'
                + '<span class="clausal-atom">false.</span>'
                + '</div>'
            )

        parts = [_format_bindings_html(b) for b in solutions]
        body = '<br><span class="clausal-or">or</span><br>'.join(parts)

        if exhausted:
            footer = '<div class="clausal-footer">No more solutions.</div>'
        else:
            footer = (
                f'<div class="clausal-footer">'
                f'... showing first {limit} of more solutions'
                f'</div>'
            )

        return (
            JUPYTER_CSS
            + f'<div class="clausal-output">{body}{footer}</div>'
        )

    def __repr__(self):
        """Fallback for non-IPython contexts (plain Python, repr())."""
        self._run()
        return ""

    # ------------------------------------------------------------------
    # Interactive loop
    # ------------------------------------------------------------------

    def _run(self):
        first_solution = True
        pending = None  # buffered solution fetched for look-ahead

        try:
            pending = next(self._iter)
        except StopIteration:
            print("false.")
            return

        while True:
            # Print separator before every solution after the first.
            if not first_solution:
                print("or")
            first_solution = False

            print(_format_bindings(pending))

            # Peek: is there another solution?
            try:
                look_ahead = next(self._iter)
            except StopIteration:
                # This was the last solution.
                print("No more solutions.")
                return

            # There is a next solution — show prompt and wait for a key.
            sys.stdout.write(self._PROMPT)
            sys.stdout.flush()
            key = self._read()
            sys.stdout.write("\r" + " " * len(self._PROMPT) + "\r")
            sys.stdout.flush()

            if key in (' ', 'n'):
                pending = look_ahead
                continue
            elif key in ('\r', '\n', '.'):
                return
            elif key in ('\x1b', 'q'):
                return
            elif key == 'a':
                # Show all remaining (look_ahead + rest of iterator).
                print("or")
                print(_format_bindings(look_ahead))
                for sol in self._iter:
                    print("or")
                    print(_format_bindings(sol))
                print("No more solutions.")
                return
            else:
                # Unknown key — treat as next.
                pending = look_ahead
                continue
