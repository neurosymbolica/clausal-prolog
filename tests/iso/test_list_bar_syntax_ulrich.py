"""The list-bracket ``|`` is ISO 6.3.5's dedicated list head/tail separator,
fixed by the list-bracket grammar rule itself -- NOT a parse of ``|`` as a
general operator.  It must mean the same thing regardless of any ``op/3``
declaration for the atom ``|``, found by a diagnostic sweep against Ciao's
``iso_tests_parsing_lexing`` corpus (cross-check only; the ISO grammar text
is the authority here) and confirmed directly against the ISO 6.3.5 list
syntax rule, 2026-10-15.

Two concrete defects in ``clausal/tools/prolog_parser.py``'s ``_parse_list``,
both triggered only when a custom ``|`` operator's priority is within the
999 budget a list item/tail is parsed at (``op(999, xfy, '|')`` is the
sharpest repro):

* ``[a|[]]`` used to read as a ONE-ELEMENT list holding the compound
  ``'|'(a,[])`` -- the bar was parsed via the general operator-precedence
  expression grammar (through ``_parse_term``'s infix-operator loop, fed by
  ``_operator_name_from_token`` mapping the BAR token to the name ``"|"``
  unconditionally) instead of being read as the fixed list separator.  So
  ``[a|[]] = [a]`` -- which must succeed per ISO 6.3.5 regardless of the
  op/3 declaration -- used to FAIL.
* ``[a|b|c]`` (two bars at the same list's nesting level) used to be
  ACCEPTED as a chained structure (``'|'(a, '|'(b,c))`` inside a one-element
  list) once a custom ``|`` operator made the general expression grammar
  reach the second bar too.  ISO's list grammar permits exactly one
  ``'|' arg`` after the items, so this must be a syntax error, with or
  without the custom op.

Fix: ``self._bar_reserved``, set while parsing the direct items/tail of one
``[...]`` and suspended inside any fully bracketed subform (``(...)``,
``f(...)``, ``{...}``, each bounded by its own closer) so ``|`` still works
as a genuine operator there, and restored the instant the list's own ``]``
is consumed (so ``[a] | c`` right after a list reads the ``|`` normally --
see ``test_bar_after_list_close_*`` below).  ``_operator_name_from_token``
refuses to name BAR as an operator while it is set, so the generic
infix/postfix loop in ``_parse_term`` can never claim it; ``_parse_list`` is
left to raise its own "Expected ']'" error on a second bare bar.

Declaring ``|`` as an operator at a priority <=999 is itself ISO-illegal
(Ulrich's conformity suite row #72 expects ``permission_error`` -- exactly
*because* such a declaration would collide with the list syntax this file
is about) and Clausal is gaining its own permission check for it in a
separate, unrelated landing.  So the goal-execution rows below that load a
``:- op(...).`` directive through a ``.pl`` file use the LEGAL priority 1100
(``'|'``'s own natural precedence class, shared with ``;``/``->``) --
Scryer accepts this declaration too (confirmed below), unlike 999.  The
priority actually needed to pin the two defects above (<=999, so a list
item/tail's own 999 budget can reach it) is tested separately, directly
against the parser with a hand-built ``OperatorTable``, bypassing any
op/3-directive-level permission check entirely (``test_boundary_prec999_*``).

Also checked and NOT touched by the fix: Clausal has no default ``|``-as-
``;`` synonym at all (none of ``iso_default``/``swi_default``/
``scryer_default``/``scryer_builtin_default``/``gprolog_default``/
``trealla_default`` define an operator entry for the atom ``|``) -- bare
``|`` in goal position, outside ``[...]``, is a SYNTAX ERROR unless the
program declares its own ``|`` operator via ``op/3``, exactly like any other
undeclared symbol would be.  Once a program does declare one, ``|`` works
as that ordinary operator everywhere outside ``[...]``, including right
after a list's closing ``]`` -- the fix is scoped to inside the brackets
only, for exactly the duration of that one list's items/tail parse.
"""

from __future__ import annotations

import importlib
import shutil
import sys

import pytest

from clausal import import_hook as ih
from clausal.tools.prolog_parser import ParseError, parse_term
from clausal.tools.prolog_operators import OperatorTable

from .conftest import run_scryer
from .test_iso_answers_scryer import _engine_answers, _scryer_answers

#: `|`'s own natural precedence class (shared with `;` 1100 xfy / `->` 1050
#: xfy) -- LEGAL to declare, unlike <=999 (Ulrich #72; Clausal is gaining its
#: own permission check for that range in a separate landing).
_BAR_OP = (":- op(1100, xfy, '|').",)

#: (row, op directives, goal) -- every goal must succeed.
READ_OK = [
    # ISO 6.3.5: [a|[]] is '.'(a,[]), same as [a] -- regardless of op/3.
    ("[a|[]] = [a], no custom op (regression guard)",
     (), "[a|[]] = [a]"),
    ("[a|[]] = [a], WITH legal custom op(1100,xfy,'|')",
     _BAR_OP, "[a|[]] = [a]"),
    # The ordinary [a|T] tail-variable reading still works under a custom
    # '|' operator -- the fix must not disturb the common case.
    ("[a|T] binds T, no custom op",
     (), "X = [a|T], T = [], X == [a]"),
    ("[a|T] binds T, WITH legal custom op(1100,xfy,'|')",
     _BAR_OP, "X = [a|T], T = [], X == [a]"),
    # '|' as a genuine operator still works OUTSIDE list brackets, scoped
    # correctly -- the fix must not disable '|' as an operator everywhere.
    ("a|b outside brackets uses the declared operator",
     _BAR_OP, "X = (a|b), X == '|'(a,b)"),
    # ... and inside any fully bracketed subform NESTED in a list, which has
    # its own closer and so is unambiguous even while the enclosing list
    # has '|' reserved as its own separator.
    ("[(a|b)] -- parens inside a list still read '|' as the operator",
     _BAR_OP, "X = [(a|b)], X = [Y], Y == '|'(a,b)"),
    # f(...)'s argument is itself capped at priority 999 (ISO 6.3.3.1) --
    # same as a list item/tail -- so the bare '|' (declared at 1100) needs
    # its own parens here regardless of any list; that cap is independent
    # of this fix and applies outside list brackets too.
    ("[f((a|b))] -- compound args inside a list still read '|' as the operator",
     _BAR_OP, "X = [f((a|b))], X = [Y], Y == f('|'(a,b))"),
    ("[{a|b}] -- curly inside a list still reads '|' as the operator",
     _BAR_OP, "X = [{a|b}], X = [Y], Y == {}('|'(a,b))"),
    ("[[a|b]|c] -- nested list, each bracket keeps its own '|' reserved",
     _BAR_OP, "X = [[a|b]|c], X = [Y|Z], Y == [a|b], Z == c"),
    # The reservation must end the instant the list's own ']' closes: a '|'
    # right after it is the ordinary declared operator, applied to the
    # whole list as its left operand -- NOT swallowed into the list syntax
    # as if it were a second tail-separator. This is the one behaviour
    # `_bar_reserved`'s save/restore scoping has to get right.
    ("[a] | c right after the list's ']' is the operator, not swallowed",
     _BAR_OP, "X = ([a] | c), X == '|'([a], c)"),
]

#: (row, op directives, goal) -- every goal is a syntax error.
READ_ERR = [
    # ISO's list grammar allows exactly one bare '|' per list nesting
    # level; a second one is a syntax error, with or without a custom op.
    ("[a|b|c] is a syntax error, no custom op (regression guard)",
     (), "X = [a|b|c]"),
    ("[a|b|c] is a syntax error, WITH legal custom op(1100,xfy,'|')",
     _BAR_OP, "X = [a|b|c]"),
    # Surprising-finding check: Clausal has NO default '|'-as-';' synonym.
    # Bare '|' in goal position, outside [...], with no op/3 declaration
    # for it, is an undeclared symbol -- a syntax error, not a silent
    # disjunction.
    ("bare (a|b) outside brackets, no custom op: no ';' synonym by default",
     (), "X = (a|b)"),
]

_PRELUDES = sorted({ops for _, ops, _ in READ_OK} | {ops for _, ops, _ in READ_ERR})


def _ok_program(ops) -> str:
    rows = [(i, g) for i, (_, o, g) in enumerate(READ_OK) if o == ops]
    return "\n".join(ops) + "\n" + "".join(
        f"r{i}(R) :- {g}, R = true.\n" for i, g in rows)


@pytest.fixture(scope="module")
def loads(tmp_path_factory):
    d = tmp_path_factory.mktemp("list_bar")
    mp = pytest.MonkeyPatch()
    mp.syspath_prepend(str(d))
    mp.setenv(ih.PL_FRONTEND_ENV, "native")
    names = []

    def load(name: str, text: str):
        path = d / f"{name}.pl"
        path.write_text(text, encoding="utf-8")
        for p in d.rglob("__pycache__"):
            shutil.rmtree(p, ignore_errors=True)
        sys.modules.pop(name, None)
        names.append(name)
        importlib.invalidate_caches()
        assert ih._prolog_loader_class_for(str(path)) is ih.NativePrologLoader
        return importlib.import_module(name)
    try:
        yield load
    finally:
        for n in names:
            sys.modules.pop(n, None)
        mp.undo()


@pytest.mark.parametrize("i", range(len(READ_OK)), ids=[r[0] for r in READ_OK])
def test_read(loads, i):
    _, ops, goal = READ_OK[i]
    mod = loads(f"_list_bar_ok{i}", "\n".join(ops) + f"\nr(R) :- {goal}, R = true.\n")
    assert _engine_answers(mod, "r", 2) == ["true"]


@pytest.mark.parametrize("i", range(len(READ_ERR)), ids=[r[0] for r in READ_ERR])
def test_syntax_error(loads, i):
    _, ops, goal = READ_ERR[i]
    with pytest.raises(SyntaxError):
        loads(f"_list_bar_err{i}", "\n".join(ops) + f"\nr(R) :- {goal}, R = true.\n")


# ── Boundary pin: priority 999 itself, bypassing the op/3 permission check ──
#
# Declaring `|` at a priority <=999 through an `op/3` directive is itself
# ISO-illegal (Ulrich #72) and Clausal is gaining its own permission check
# for exactly that range in a separate landing -- so these two cases, which
# need priority 999 itself to reach the historical bug (a list item/tail is
# parsed at that same 999 budget), go straight through `parse_term` with a
# hand-built `OperatorTable`, never through a `:- op(...)` directive or a
# loaded `.pl` file.
#
# The comparison is the SAME source text parsed with and without the
# priority-999 '|' entry -- not two different texts -- because `[a|[]]` and
# `[a]` legitimately produce different (if equivalent) ASTs even when
# parsing is correct (`PList(..., tail=PList((), None))` vs `tail=None`);
# the bug is specifically that the SAME text's parse CHANGES when the op
# table gains the entry, which this isolates directly.

def _ops_999_bar() -> OperatorTable:
    t = OperatorTable.scryer_builtin_default()
    t.define(999, "xfy", "|")
    return t


def test_boundary_prec999_list_bar_not_swallowed_by_declared_op():
    plain = OperatorTable.scryer_builtin_default()
    custom = _ops_999_bar()
    assert parse_term("[a|[]]", op_table=custom) == parse_term("[a|[]]", op_table=plain)


def test_boundary_prec999_double_bar_is_syntax_error():
    for ops in (OperatorTable.scryer_builtin_default(), _ops_999_bar()):
        with pytest.raises(ParseError):
            parse_term("[a|b|c]", op_table=ops)


# ── The Scryer oracle ────────────────────────────────────────────────────
#
# Scryer accepts `:- op(1100, xfy, '|').` (confirmed by
# `test_scryer_accepts_legal_bar_operator` below) but refuses priority 999
# outright -- `error(permission_error(create,operator,'|'),load/1)`
# (`test_scryer_refuses_illegal_bar_operator`) -- so it can oracle every
# READ_OK row here (all legal priorities), but not the boundary-pin cases
# just above, which is exactly why those are measured against the ISO 6.3.5
# text directly instead. The READ_ERR rows are likewise not checked here:
# whether a second bare '|' or an undeclared bare '|' is accepted is
# dialect-specific op/3-table trivia the ISO text settles on its own.


def test_oracle_read(scryer):
    del scryer      # the fixture only asserts the binary is there
    for ops in _PRELUDES:
        idx = [i for i, (_, o, _) in enumerate(READ_OK) if o == ops]
        if not idx:
            continue
        got = _scryer_answers(_ok_program(ops), [(f"r{i}(R)", 2) for i in idx])
        assert got == [["true"]] * len(idx), [READ_OK[i][0] for i in idx]


def test_scryer_accepts_legal_bar_operator(scryer, tmp_path):
    del scryer
    pl = tmp_path / "bar_op_legal.pl"
    pl.write_text(":- op(1100, xfy, '|').\n")
    proc = run_scryer(str(pl), [], timeout=30)
    assert proc.stdout.strip() == "" and "error" not in proc.stdout, proc.stdout


def test_scryer_refuses_illegal_bar_operator(scryer, tmp_path):
    """Documents why the boundary-pin cases have no Scryer oracle check:
    Scryer refuses to let '|' be redefined at a priority <=999 (the range
    that would collide with list syntax) -- stricter than Clausal is today,
    and exactly the rule Clausal's own upcoming permission check adopts."""
    del scryer
    pl = tmp_path / "bar_op_illegal.pl"
    pl.write_text(":- op(999, xfy, '|').\n")
    proc = run_scryer(str(pl), [], timeout=30)
    assert "permission_error(create,operator,'|')" in proc.stdout, proc.stdout
