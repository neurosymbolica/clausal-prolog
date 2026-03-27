"""clausal.modules.py.re — Regex predicates for Clausal.

Provides Match, Search, Replace, Split, and findall as importable
predicate objects for use in .clausal files via::

    -import_from(py.re, [Match, Search, Replace, Split, findall])

Or via module import::

    -import_module(py.re)
    # then use py.re.Match(...), py.re.findall(...), etc.

Binding modes
-------------
- **Boolean** — ``Match(r"\\d+", S)`` / ``Search(r"\\d+", S)`` — succeeds/fails
- **Explicit groups** — ``Match(pat, S, G)`` — G is a dict of named groups
  (or tuple of positional groups if no named groups)
- **Auto-binding** (via goal expansion) — ``Match(r"(?P<YEAR>\\d{4})", S)``
  auto-binds ALLCAPS/leading-underscore named groups to clause variables

Auto-binding is handled by ``clausal.logic.goal_expansion`` at compile
time; the predicates here just do the runtime work.
"""

from __future__ import annotations

from clausal.modules.py import _import_stdlib, ModulePredicate, simple_to_trampoline
_re = _import_stdlib("re")

from typing import Any

from clausal.logic.variables import Var, deref, is_var, unify
from clausal.logic.trampoline import DONE, StepGenerator


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


# ── findall ──────────────────────────────────────────────────────────────────


def _findall_3(this_generator, parent, pat, string, match_var, trail):
    """findall/3: nondeterministic — one solution per non-overlapping match.

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

Match = ModulePredicate("Match")
Match._register(2, simple_to_trampoline(_match_2))
Match._register(3, simple_to_trampoline(_match_3))

Search = ModulePredicate("Search")
Search._register(2, simple_to_trampoline(_search_2))
Search._register(3, simple_to_trampoline(_search_3))

Replace = ModulePredicate("Replace")
Replace._register(4, simple_to_trampoline(_replace_4))

Split = ModulePredicate("Split")
Split._register(3, simple_to_trampoline(_split_3))

findall = ModulePredicate("findall")
findall._register(3, _findall_3)
