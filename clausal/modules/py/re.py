"""clausal.modules.py.re — Regex predicates for Clausal.

Provides Match, Search, Replace, Split, and FindAll as importable
predicate objects for use in .clausal files via::

    -import_from(py.re, [Match, Search, Replace, Split, FindAll])

Or via module import::

    -import_module(py.re)
    # then use py.re.Match(...), py.re.FindAll(...), etc.

Binding modes
-------------
- **Boolean** — ``Match(r"\\d+", S)`` / ``Search(r"\\d+", S)`` — succeeds/fails
- **Explicit groups** — ``Match(pat, S, G)`` — G is a dict of named groups
  (or tuple of positional groups if no named groups)
- **Auto-binding** (via goal expansion) — ``Match(r"(?P<YEAR>\\d{4})", S)``
  auto-binds ALLCAPS/trailing-underscore named groups to clause variables

Auto-binding is handled by ``clausal.logic.goal_expansion`` at compile
time; the predicates here just do the runtime work.
"""

from __future__ import annotations

from clausal.modules.py import _import_stdlib
_re = _import_stdlib("re")

from typing import Any, Callable

from clausal.logic.variables import Var, deref, is_var, unify
from clausal.logic.trampoline import DONE, StepGenerator


# ── Dispatch adapter ────────────────────────────────────────────────────────


class _RegexPredicate:
    """Adapter with ``_get_dispatch()`` for a regex predicate.

    Supports multi-arity dispatch (e.g. Match/2 + Match/3).
    """

    __slots__ = ("_name", "_dispatch_fns")

    def __init__(self, name: str) -> None:
        self._name = name
        self._dispatch_fns: dict[int, Callable] = {}

    def _register(self, arity: int, fn: Callable) -> None:
        self._dispatch_fns[arity] = fn

    def _get_dispatch(self) -> Callable:
        if len(self._dispatch_fns) == 1:
            return next(iter(self._dispatch_fns.values()))
        return self._multi_dispatch

    def _multi_dispatch(self, this_generator, parent, *args):
        arity = len(args) - 1  # exclude trail
        fn = self._dispatch_fns.get(arity)
        if fn is None:
            yield (parent, DONE)
            return
        yield from fn(this_generator, parent, *args)

    def __repr__(self) -> str:
        arities = sorted(self._dispatch_fns)
        return f"re.{self._name}/{arities}"


# ── Helpers ──────────────────────────────────────────────────────────────────


def _compile_pattern(pat: Any) -> "_re.Pattern":
    """Compile a pattern, accepting both strings and pre-compiled patterns."""
    if isinstance(pat, _re.Pattern):
        return pat
    return _re.compile(pat)


def _groups_dict(m: "_re.Match") -> dict | tuple:
    """Extract groups from a match object.

    If there are named groups, returns a dict (named group name → value).
    Otherwise returns a tuple of positional groups.
    """
    gd = m.groupdict()
    if gd:
        return gd
    groups = m.groups()
    if groups:
        return groups
    return {}


# ── Simple-mode wrapper ─────────────────────────────────────────────────────


def _simple_to_trampoline(simple_fn):
    """Wrap a simple-mode fn(*args, trail, k) → trampoline protocol."""
    def trampoline_fn(this_generator, parent, *args):
        for _ in simple_fn(*args, None):
            yield (parent, None)
        yield (parent, DONE)
    return trampoline_fn


# ── Match ────────────────────────────────────────────────────────────────────


def _match_2(pat, string, trail, k):
    """Match/2: boolean test — re.match(pattern, string)."""
    pat = deref(pat)
    string = deref(string)
    compiled = _compile_pattern(pat)
    m = compiled.match(str(string))
    if m is not None:
        yield None


def _match_3(pat, string, groups, trail, k):
    """Match/3: explicit group extraction — re.match(pattern, string) → groups dict."""
    pat = deref(pat)
    string = deref(string)
    compiled = _compile_pattern(pat)
    m = compiled.match(str(string))
    if m is not None:
        result = _groups_dict(m)
        if unify(groups, result, trail):
            yield None


# ── Search ───────────────────────────────────────────────────────────────────


def _search_2(pat, string, trail, k):
    """Search/2: boolean test — re.search(pattern, string)."""
    pat = deref(pat)
    string = deref(string)
    compiled = _compile_pattern(pat)
    m = compiled.search(str(string))
    if m is not None:
        yield None


def _search_3(pat, string, groups, trail, k):
    """Search/3: explicit group extraction — re.search(pattern, string) → groups dict."""
    pat = deref(pat)
    string = deref(string)
    compiled = _compile_pattern(pat)
    m = compiled.search(str(string))
    if m is not None:
        result = _groups_dict(m)
        if unify(groups, result, trail):
            yield None


# ── Replace ──────────────────────────────────────────────────────────────────


def _replace_4(pat, repl, string, result, trail, k):
    """Replace/4: re.sub(pattern, replacement, string) → result."""
    pat = deref(pat)
    repl = deref(repl)
    string = deref(string)
    compiled = _compile_pattern(pat)
    out = compiled.sub(repl, str(string))
    if unify(result, out, trail):
        yield None


# ── Split ────────────────────────────────────────────────────────────────────


def _split_3(pat, string, parts, trail, k):
    """Split/3: re.split(pattern, string) → parts list."""
    pat = deref(pat)
    string = deref(string)
    compiled = _compile_pattern(pat)
    out = compiled.split(str(string))
    if unify(parts, out, trail):
        yield None


# ── FindAll ──────────────────────────────────────────────────────────────────


def _findall_3(this_generator, parent, pat, string, match_var, trail):
    """FindAll/3: nondeterministic — one solution per non-overlapping match.

    No groups → each match is a string.
    Groups → each match is a tuple of group strings.
    """
    pat = deref(pat)
    string = deref(string)
    compiled = _compile_pattern(pat)
    matches = compiled.finditer(str(string))
    for m in matches:
        mark = trail.mark()
        groups = m.groups()
        if groups:
            value = groups if len(groups) > 1 else groups[0]
        else:
            value = m.group()
        if unify(match_var, value, trail):
            yield (parent, None)
        trail.undo(mark)
    yield (parent, DONE)


# ── Build and export predicate objects ───────────────────────────────────────

Match = _RegexPredicate("Match")
Match._register(2, _simple_to_trampoline(_match_2))
Match._register(3, _simple_to_trampoline(_match_3))

Search = _RegexPredicate("Search")
Search._register(2, _simple_to_trampoline(_search_2))
Search._register(3, _simple_to_trampoline(_search_3))

Replace = _RegexPredicate("Replace")
Replace._register(4, _simple_to_trampoline(_replace_4))

Split = _RegexPredicate("Split")
Split._register(3, _simple_to_trampoline(_split_3))

FindAll = _RegexPredicate("FindAll")
FindAll._register(3, _findall_3)
