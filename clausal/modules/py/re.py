"""clausal.modules.py.re — Regex predicates for Clausal.

Provides match, search, replace, split, and findall as importable
predicate objects for use in .clausal files via::

    -import_from(py.re, [match, search, replace, split, findall])

Or via module import::

    -import_module(py.re)
    # then use py.re.match(...), py.re.findall(...), etc.

Binding modes
-------------
- **Boolean** — ``match(r"\\d+", S)`` / ``search(r"\\d+", S)`` — succeeds/fails
- **Explicit groups** — ``match(pat, S, G)`` — G is a dict of named groups
  (or tuple of positional groups if no named groups)
- **Auto-binding** (via goal expansion) — ``match(r"(?P<YEAR>\\d{4})", S)``
  auto-binds ALLCAPS/leading-underscore named groups to clause variables

Auto-binding is handled by ``clausal.logic.goal_expansion`` at compile
time; the predicates here just do the runtime work.
"""

from __future__ import annotations

from clausal.modules.py import (
    ModulePredicate,
    _import_stdlib,
    expect_type,
    simple_to_trampoline,
    to_text,
)
_re = _import_stdlib("re")

from typing import Any

from clausal.logic.cells import chars, is_chars, chars_text  # stage 1: the chars carrier
from clausal.logic.atoms import is_atom as _term_is_atom, spelling as _atom_spelling
from clausal.logic.variables import Var, deref, is_var, unify
from clausal.logic.trampoline import DONE, StepGenerator
from clausal.logic.runtime._seg_helpers import maybe_promote_to_str


# ── Helpers ──────────────────────────────────────────────────────────────────

# Sentinel kept for the call sites' checks; since RULED 2026-10-02
# ``_coerce_subject`` raises instead of answering it (never a repr scan).
_NO_SUBJECT = object()


def _coerce_subject(string: Any, pred: str, arg: int) -> Any:
    """Resolve a match/search/replace/split subject to a ``str``.

    Never ``str()``-coerces an arbitrary term (F002): an unbound Var used to
    match its own internal name ("_23"), and a char-list matched the repr
    brackets/quotes. Instead:

    - unbound Var → ``instantiation_error`` (no repr scanning);
    - ``str`` → itself;
    - a ``SegString``/``SegList`` that walks to a ``str`` → that ``str``;
    - a list/tuple of 1-char strings → joined ``str`` (strings-as-lists
      Liskov, docs/strings_as_lists.md); empty list → "";
    - anything else (int, non-char list, …) → ``type_error(text, S)``
      (RULED 2026-10-02: the value was bound, so this is an ill-typed call,
      not a mode signal).  *pred* is the registered predicate name/arity
      and *arg* the 1-based argument position, both carried by the error.
    """
    s = deref(string)
    if is_var(s):
        expect_type(s, str, pred, arg=arg)   # raises instantiation_error
    # THE FLIP (spec §9.4): an ATOM is text here too -- ``match(P, hello)``
    # and ``match(P, "hello")`` under ``-double_quotes(chars)`` hand over the
    # same ``str``.  Before the tuple arm, which would otherwise see the
    # arity-0 cell as a 1-element sequence.
    if _term_is_atom(s):
        return _atom_spelling(s)
    walk = getattr(s, "__walk__", None)
    if callable(walk):
        s = walk()
    if is_chars(s):
        return chars_text(s)           # stage 1: a chars string is its text here
    if isinstance(s, str):
        return s                       # STAGE 2: an atom -- its spelling is the subject text
    if isinstance(s, (list, tuple)):
        if not s:
            return ""
        promoted = maybe_promote_to_str([deref(e) for e in s])
        if is_chars(promoted):
            return chars_text(promoted)    # stage 1: the promotion funnel answers the carrier
        if isinstance(promoted, str):
            return promoted
    expect_type(s, str, pred, arg=arg)   # raises type_error(text, S)
    raise AssertionError("unreachable: expect_type raised")


def _compile_pattern(pat: Any, pred: str = "") -> "_re.Pattern":
    """Compile a pattern, accepting a pre-compiled pattern, a string or an ATOM.

    THE FLIP (spec §9.4): ``r"\\d+"`` in a ``.clausal`` file is an atom under
    ``-double_quotes(atom)`` (and a string under the chars default), so the
    text funnel ``to_text`` is
    what turns it back into the ``str`` ``re`` wants -- never ``str()``,
    which would compile the tuple repr.

    ``to_text`` answers ``None`` for anything that is not text (a compound, a
    number, an unbound Var).  Handing that straight to ``re.compile`` died
    with a raw Python ``TypeError`` -- the one failure mode a term-level
    builtin must never produce -- so it is the documented
    ``type_error(text, …)`` here, exactly as in ``py/sqlite._text``: a
    pattern position is unambiguously text, so a non-text pattern is an
    ill-typed call, not a mode signal.  An unbound pattern is an
    ``instantiation_error``.  *pred* (``"match/2"``) is the error's context.
    """
    if isinstance(pat, _re.Pattern):
        return pat
    text = to_text(pat)
    if text is None:
        expect_type(deref(pat), str, f"{pred or 'py.re'}", arg=1)   # raises
    return _re.compile(text)


def _out(v):
    """A regex RESULT as a term: STAGE 1 (spec 2026-09-18) -- text is the
    chars carrier, never a bare str; ``None`` (an unmatched optional group)
    stays ``None``; tuples and dicts of groups convert element-wise."""
    if type(v) is str:
        return chars(v)
    if type(v) is tuple:
        # positional groups: a PLAIN tuple, the shape a .clausal ``(A, B)``
        # literal compiles to and what ``++G[0]`` indexes.  Its slot 0 is a
        # carrier (or None), never a str, so it cannot read as a cell -- the
        # bare-str tuple it replaced COULD (review 2026-09-18, measured).
        return tuple(_out(e) for e in v)
    if type(v) is dict:
        return {k: _out(e) for k, e in v.items()}
    return v


def _groups_dict(m: "_re.Match") -> dict | tuple:
    """Extract groups from a match object.

    If there are named groups, returns a dict keyed by group name; any
    *unnamed* groups present alongside them are added under their 1-based
    positional index (int key) so mixed patterns don't silently drop the
    positional values (F006). With only positional groups, returns a tuple.
    """
    gd = m.groupdict()
    if gd:
        named_idx = set(m.re.groupindex.values())
        result: dict = dict(gd)
        for i, val in enumerate(m.groups(), start=1):
            if i not in named_idx:
                result[i] = val
        return _out(result)
    groups = m.groups()
    if groups:
        return _out(groups)
    return {}


# ── match ────────────────────────────────────────────────────────────────────


def _match_2(pat, string, trail, k):
    """match/2: boolean test — re.match(pattern, string)."""
    pat = deref(pat)
    string = _coerce_subject(string, "match/2", 2)
    if string is _NO_SUBJECT:
        return
    compiled = _compile_pattern(pat, "match/2")
    m = compiled.match(string)
    if m is not None:
        yield None


def _match_3(pat, string, groups, trail, k):
    """match/3: explicit group extraction — re.match(pattern, string) → groups dict."""
    pat = deref(pat)
    string = _coerce_subject(string, "match/3", 2)
    if string is _NO_SUBJECT:
        return
    compiled = _compile_pattern(pat, "match/3")
    m = compiled.match(string)
    if m is not None:
        result = _groups_dict(m)
        if unify(groups, result, trail):
            yield None


# ── search ───────────────────────────────────────────────────────────────────


def _search_2(pat, string, trail, k):
    """search/2: boolean test — re.search(pattern, string)."""
    pat = deref(pat)
    string = _coerce_subject(string, "search/2", 2)
    if string is _NO_SUBJECT:
        return
    compiled = _compile_pattern(pat, "search/2")
    m = compiled.search(string)
    if m is not None:
        yield None


def _search_3(pat, string, groups, trail, k):
    """search/3: explicit group extraction — re.search(pattern, string) → groups dict."""
    pat = deref(pat)
    string = _coerce_subject(string, "search/3", 2)
    if string is _NO_SUBJECT:
        return
    compiled = _compile_pattern(pat, "search/3")
    m = compiled.search(string)
    if m is not None:
        result = _groups_dict(m)
        if unify(groups, result, trail):
            yield None


# ── replace ──────────────────────────────────────────────────────────────────


def _replace_4(pat, repl, string, result, trail, k):
    """replace/4: re.sub(pattern, replacement, string) → result."""
    pat = deref(pat)
    repl = _coerce_subject(repl, "replace/4", 2)
    if repl is _NO_SUBJECT:
        return  # unreachable since 2026-10-02: _coerce_subject raises (F004)
    string = _coerce_subject(string, "replace/4", 3)
    if string is _NO_SUBJECT:
        return
    compiled = _compile_pattern(pat, "replace/4")
    out = _out(compiled.sub(repl, string))
    if unify(result, out, trail):
        yield None


# ── split ────────────────────────────────────────────────────────────────────


def _split_3(pat, string, parts, trail, k):
    """split/3: re.split(pattern, string) → parts list."""
    pat = deref(pat)
    string = _coerce_subject(string, "split/3", 2)
    if string is _NO_SUBJECT:
        return
    compiled = _compile_pattern(pat, "split/3")
    out = [_out(p) for p in compiled.split(string)]
    if unify(parts, out, trail):
        yield None


# ── findall ──────────────────────────────────────────────────────────────────


def _findall_3(this_generator, _proceed, _fail, _catcher, pat, string, match_var, trail):
    """findall/3: nondeterministic — one solution per non-overlapping match.

    Mirrors the ``re.findall`` oracle (F009):
    - no capturing group → each match is the whole-match string;
    - exactly one group → each match is that group's bare string;
    - two or more groups → each match is a tuple of group strings.
    """
    pat = deref(pat)
    string = _coerce_subject(string, "findall/3", 2)
    if string is _NO_SUBJECT:
        yield (_fail, DONE)
        return
    compiled = _compile_pattern(pat, "findall/3")
    matches = compiled.finditer(string)
    for m in matches:
        mark = trail.mark()
        groups = m.groups()
        if groups:
            value = groups if len(groups) > 1 else groups[0]
        else:
            value = m.group()
        if unify(match_var, _out(value), trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


# ── Build and export predicate objects ───────────────────────────────────────

match = ModulePredicate("match")
match._register(2, simple_to_trampoline(_match_2))
match._register(3, simple_to_trampoline(_match_3))

search = ModulePredicate("search")
search._register(2, simple_to_trampoline(_search_2))
search._register(3, simple_to_trampoline(_search_3))

replace = ModulePredicate("replace")
replace._register(4, simple_to_trampoline(_replace_4))

split = ModulePredicate("split")
split._register(3, simple_to_trampoline(_split_3))

findall = ModulePredicate("findall")
findall._register(3, _findall_3)
