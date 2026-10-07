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
    """Execute term instances as a Prolog-style conjunction on a shared
    trail and yield one binding dict per combined solution.

    Used by the ``*A, B, C`` query syntax rewrite.

    *_varnames* maps user-written variable names to their Var objects so that
    binding keys use the names the user wrote (e.g. ``ROWS``) rather than the
    predicate field names (e.g. ``rows``).

    Each *goal* must be term-shaped (``is_term_instance``: a ``PredicateMeta``
    instance or a ``@dataclass`` instance) AND satisfy the ``_get_dispatch()``
    duck-typed protocol on its class (see ``predicate.py:_dispatch_at``'s
    docstring) — the funnel widens the *shape* check from "must be
    ``PredicateMeta``" to "must be term-shaped", fixing a latent bug where a
    hand-built ``@dataclass`` goal implementing the same ``_get_dispatch()``
    contract PredicateMeta instances use was rejected outright instead of
    driven. ``cls._get_dispatch()`` itself is untouched, so a term-shaped
    goal whose class does *not* implement the protocol still fails — just
    later, with ``AttributeError``, at the dispatch call below rather than
    at this guard.
    """
    from clausal.logic.predicate import is_term_instance, term_field_names, term_field_values
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
        if not is_term_instance(goal):
            raise TypeError(f"_conj: expected predicate instances, got {type(goal)}")
        for f in term_field_names(goal):
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
        args = list(term_field_values(goal))
        for _ in _drive_trampoline(dispatch, trail, *args):
            yield from _run(rest)

    def _gen():
        for _ in _run(list(goals)):
            yield {f: _walk(v) for f, v in var_fields.items()}

    return _gen()


def _is_goal_value(x) -> bool:
    """True for a goal written as a VALUE: a cell (``("between", 1, 3, X)``,
    what ``clausal.between(1, 3, X)`` builds) or a bare ``str`` (an atom goal
    or a predicate handle such as ``m.pred``).

    Both are iterable, and iterating them is always wrong here: a cell walks
    its functor and arguments, a ``str`` walks its characters, and neither
    ever runs the goal -- a silently wrong answer, not an error.
    """
    from clausal.logic.cells import compound_cell_shape
    return type(x) is str or compound_cell_shape(x)[0]


def _iter_from_goal_value(goal, _varnames, module):
    """Solve a cell/str *goal* with ``solve`` and yield binding dicts.

    The module is resolved EAGERLY, so a goal that has none -- an unqualified
    cell with no ``module=`` -- raises solve's own ``existence_error(module,
    ...)`` when ``Solutions`` is constructed, not later inside a display hook.
    A module-qualified cell ``(":", M, G)`` names its own module.

    Bindings are reported for the goal's variables in left-to-right order,
    keyed by the names in *_varnames* where the caller supplied them and by
    the variable's own name (``_0``) otherwise.
    """
    from clausal.logic.solve import (
        _resolved_goal_and_module, solve, _deref_walk,
    )
    from clausal.logic.builtins.inspection import _collect_vars_impl

    goal, resolved = _resolved_goal_and_module(goal, module, "Solutions")
    found: list = []
    _collect_vars_impl(goal, found)
    id_to_name = {id(v): n for n, v in (_varnames or {}).items()}
    named = {id_to_name.get(id(v), str(v)): v for v in found}
    # Caller-named variables the walk did not reach (already bound, or
    # outside the goal) are still reported, as the instance path does.
    for n, v in (_varnames or {}).items():
        named.setdefault(n, v)

    def _gen():
        for _ in solve(goal, resolved):
            yield {n: _deref_walk(v) for n, v in named.items()}

    return _gen()


def _iter_from_goal(goal_or_iter, _varnames=None, module=None):
    """If given a term instance, drive it and yield binding dicts.
    A cell or a ``str`` is a goal VALUE and is solved (see
    :func:`_iter_from_goal_value`; *module* is the module that answers it).
    Otherwise pass through as an iterator.

    *_varnames* maps user-written variable names to their Var objects so that
    binding keys use the names the user wrote rather than predicate field names.

    ``True`` is treated as a goal that succeeds once with no bindings (displays
    as ``True``).  ``False`` is treated as a goal that fails immediately
    (displays as ``False``).

    Sanctioned funnel-migration behavior fix (see ``_conj``'s docstring for
    the full rationale): the entry guard used to require ``isinstance(type(x),
    PredicateMeta)`` specifically, which meant a term instance that duck-types
    the ``_get_dispatch()`` protocol without being a ``PredicateMeta``
    instance (e.g. a hand-built ``@dataclass`` goal) was rejected with
    ``TypeError`` instead of driven — a crash on a term shape the rest of the
    engine (``solve.py``, the builtin registry) already drives via
    ``hasattr(x, '_get_dispatch')`` duck typing. Widening the guard to
    ``is_term_instance`` (PredicateMeta instance OR dataclass instance) fixes
    that; ``cls._get_dispatch()`` itself is unchanged, so a term-shaped value
    whose class does not implement the protocol still fails, just with
    ``AttributeError`` at the dispatch call instead of at this guard.
    """
    from clausal.logic.predicate import is_term_instance, term_field_names, term_field_values
    if not is_term_instance(goal_or_iter):
        if module is not None and not _is_goal_value(goal_or_iter):
            # roborev Low on slice 3: ``module=`` used to be dropped here
            # silently.  Only a goal VALUE is solved against a module; True/
            # False, an iterator of binding dicts and a term instance are not.
            raise TypeError(
                f"Solutions(module=...) applies to a goal value (a cell, or an "
                f"atom or handle str); got {type(goal_or_iter).__name__}: "
                f"{goal_or_iter!r}.  Drop module=, or pass the goal as a cell.")
        if goal_or_iter is True:
            return iter([{}])
        if goal_or_iter is False:
            return iter([])
        if _is_goal_value(goal_or_iter):
            return _iter_from_goal_value(goal_or_iter, _varnames, module)
        try:
            return iter(goal_or_iter)
        except TypeError:
            raise TypeError(
                f"Solutions expects a goal (a cell, an atom or handle str, "
                f"True/False, a term instance) or an iterator of binding "
                f"dicts, "
                f"got {type(goal_or_iter).__name__}: {goal_or_iter!r}\n"
                f"Hint: Python's 'is' is an identity test, not unification."
            ) from None

    from clausal.logic.variables import Trail, is_var, Var
    from clausal.logic.variables import walk as _walk
    from clausal.logic.solve import _drive_trampoline

    id_to_name = {id(v): n for n, v in (_varnames or {}).items()}
    cls = type(goal_or_iter)
    dispatch = cls._get_dispatch()
    fields = term_field_names(goal_or_iter)
    args = list(term_field_values(goal_or_iter))
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
    from clausal.logic.solve import solve, _deref_walk
    module = Module("_ipython_query", module_dict=ns)
    return (
        {name: _deref_walk(var) for name, var in variables.items()}
        for _ in solve(goal, module)
    )


class Solutions:
    """Interactive solution iterator for the Clausal REPL.

    Wrap any iterator of binding dicts (as returned by ``query()``)::

        X = Var()
        Solutions(query(goal, {"X": X}, module))

    or pass a GOAL -- a cell, such as the one a builtin's term constructor builds, or
    a module-qualified cell -- with the module that answers it::

        Solutions(between(1, 3, X := Var()), module=m)
        Solutions(("pred", X := Var()), module=m)
        Solutions((":", m, ("pred", X := Var())))

    A cell is solved, never iterated (iterating it would walk the tuple's
    elements and bind nothing).  An unqualified cell with no ``module=``
    raises ``existence_error(module, ...)`` here, at construction.
    ``module=`` with anything that is NOT a goal value (True/False, an
    iterator of binding dicts, a term instance) is a ``TypeError``, never
    silently ignored.

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
                 limit=None, module=None):
        self._iter = _iter_from_goal(goal_or_iter, _varnames=_varnames,
                                     module=module)
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

        self._refuse_if_driven_async()
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

    # ------------------------------------------------------------------
    # asyncio (clausal.aio)
    # ------------------------------------------------------------------

    def __aiter__(self):
        """``async for bindings in Solutions(...)``: answers on the event loop.

        A predicate that waits (``library(asyncio)``, an async adapter) frees
        the loop instead of refusing to block it.
        """
        return self._driver()

    def _driver(self):
        """The one async driver of this Solutions' answers: a second driver
        over the same synchronous generator would resume its parked frames
        under another query's engine state."""
        from clausal.aio import adrive  # noqa: PLC0415
        driver = getattr(self, "_async_driver", None)
        if driver is None or driver[0] is not self._iter:
            driver = self._async_driver = (self._iter, adrive(self._iter))
        return driver[1]

    async def aclose(self):
        """Close the async driver, if any (after a ``break`` out of
        ``async for``), so the query's tables are released at once."""
        driver = getattr(self, "_async_driver", None)
        if driver is not None:
            await driver[1].aclose()

    def _refuse_if_driven_async(self):
        """A synchronous display may not take over answers an async driver
        is part-way through: it would resume the query's parked frames
        outside the query."""
        import inspect  # noqa: PLC0415
        driver = getattr(self, "_async_driver", None)
        if (driver is not None and driver[0] is self._iter
                and inspect.getasyncgenstate(driver[1])
                in (inspect.AGEN_SUSPENDED, inspect.AGEN_RUNNING)):
            raise RuntimeError(
                "this Solutions is being read asynchronously (async for); "
                "finish it or `await solutions.aclose()` before displaying "
                "it synchronously, or display it with `await solutions`")

    def __await__(self):
        """``await Solutions(...)``: fetch the answers to show on the event
        loop, then display as usual.  This is the form for a Jupyter cell,
        whose kernel always has a loop running: a plain ``Solutions(...)``
        cannot wait there."""
        return self._prefetch().__await__()

    async def _prefetch(self):
        limit = (self._limit if self._limit is not None
                 else self.DEFAULT_JUPYTER_LIMIT)
        fetched = []
        answers = self._driver()
        try:
            # One past the limit, so the display can still say "more".
            async for bindings in answers:
                fetched.append(bindings)
                if len(fetched) > limit:
                    break
        finally:
            await answers.aclose()
        self._iter = iter(fetched)
        return self

    def __repr__(self):
        """Fallback for non-IPython contexts (plain Python, repr())."""
        self._run()
        return ""

    # ------------------------------------------------------------------
    # Interactive loop
    # ------------------------------------------------------------------

    def _run(self):
        self._refuse_if_driven_async()
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
                print("# No more solutions.")
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
                print("# No more solutions.")
                return
            else:
                # Unknown key — treat as next.
                pending = look_ahead
                continue
