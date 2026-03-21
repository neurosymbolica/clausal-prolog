"""Interactive solution iteration for the Clausal IPython REPL.

Provides a ``Solutions`` wrapper that displays query results one at a time,
Prolog-style, but using ``or`` as the separator between solutions.

Key bindings
------------
SPACE, n      next solution
ENTER, .      stop  (commit — prints ``.``)
ESC, q        abort (clean exit — no output)
a             show all remaining solutions
"""

from __future__ import annotations

import sys
from typing import Iterator, Any


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
    """Format a binding dict as ``X = val, Y = val``."""
    if not bindings:
        return "true."
    return ",  ".join(f"{k} = {v!r}" for k, v in bindings.items())


def _conj(*goals):
    """Execute predicate instances as a Prolog-style conjunction on a shared
    trail and yield one binding dict per combined solution.

    Used by the ``*A, B, C`` query syntax rewrite.
    """
    from clausal.logic.predicate import PredicateMeta
    from clausal.logic.variables import Trail, Var
    from clausal.logic.variables import walk as _walk
    from clausal.logic.solve import _drive_trampoline

    trail = Trail()

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
                seen[id(v)] = (f, v)
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


def _iter_from_goal(goal_or_iter):
    """If given a predicate instance, drive it and yield binding dicts.
    Otherwise pass through as an iterator."""
    from clausal.logic.predicate import PredicateMeta
    if not isinstance(type(goal_or_iter), PredicateMeta):
        return iter(goal_or_iter)

    from clausal.logic.variables import Trail, is_var, Var
    from clausal.logic.variables import walk as _walk
    from clausal.logic.solve import _drive_trampoline

    cls = type(goal_or_iter)
    dispatch = cls._get_dispatch()
    fields = cls._fields
    args = [getattr(goal_or_iter, f) for f in fields]
    var_fields = {f: getattr(goal_or_iter, f) for f in fields
                  if isinstance(getattr(goal_or_iter, f), Var)}
    trail = Trail()

    def _gen():
        for _ in _drive_trampoline(dispatch, trail, *args):
            yield {f: _walk(v) for f, v in var_fields.items()}

    return _gen()


class Solutions:
    """Interactive solution iterator for the Clausal REPL.

    Wrap any iterator of binding dicts (as returned by ``query()``)::

        X = Var()
        Solutions(query(goal, {"X": X}, module))

    When evaluated in an IPython cell the solutions are presented one at a
    time, separated by ``or``, with a key-driven prompt between each.

    Key bindings
    ------------
    SPACE, n      next solution
    ENTER, .      stop  (commit — prints ``.``)
    ESC, q        abort (clean exit — no output)
    a             show all remaining solutions
    """

    _PROMPT = "   [SPACE/n: next  |  ENTER/.: stop  |  ESC/q: abort  |  a: all]  "

    def __init__(self, goal_or_iter: Any, _read=None):
        self._iter = _iter_from_goal(goal_or_iter)
        # Allow tests to inject a scripted key-reader.
        self._read = _read if _read is not None else _read_char

    # ------------------------------------------------------------------
    # IPython display protocol
    # ------------------------------------------------------------------

    def _ipython_display_(self, **kwargs):
        """Called by IPython instead of repr(); drives the interactive loop."""
        self._run()
        # Return None so IPython prints nothing extra.

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
                print(".")
                return
            elif key in ('\x1b', 'q'):
                # Abort — no output.
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
