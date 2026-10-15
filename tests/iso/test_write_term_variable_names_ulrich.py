"""write_term/2's ``variable_names(List)`` option -- ISO 7.10 / WG17 N246.

Ulrich Neumerkel's conformity-testing page for this proposal --
https://www.complang.tuwien.ac.at/ulrich/iso-prolog/variable_names --
found that Clausal did not recognise ``variable_names(...)`` as a
write-option AT ALL (any occurrence raised ``domain_error(write_option,
variable_names(...))`` unconditionally): 53 of the page's 74 rows are
about this one option.  This file pins the engine's answer against each
IN-SCOPE row (the ``write_term/2`` rows; the page also bundles
``read_term/2``'s own ``variable_names``/``singletons`` options and
``open/4``'s ``type``/``alias`` options under the same N246 umbrella --
those are different predicates/options entirely and are out of scope
here).

Each test below is built directly at the Python term level (the pattern
``tests/test_iso_writers_scryer_layout.py`` already uses for
``write_term/2``), not through the ``.pl`` parser: this lets a goal bind
variables in EXACTLY the order the page's "/**/" shorthand implies
(earlier goals first, in one shared ``Trail``, with the top ``write_term``
goal always run last against the resulting bindings) without needing the
Prolog reader to parse Ulrich's elliptical notation.

Design recap (see ``clausal/logic/builtins/io.py``, ``_parse_variable_names``
and ``_vn_list_walk``, and ``clausal/terms.py``'s ``term_write``/``_wq_var``):

* The mechanism threading a variable's substitute name into the writer is
  the SAME one ``term_writeq(..., var_names=...)`` already used for a
  toplevel answer's variable names (``clausal/terms.py``): a
  ``dict[id(var), name]`` set on the ``_WQ_VAR_NAMES`` contextvar for the
  duration of one write.  ``write_term/2`` just builds that dict from its
  ``variable_names(List)`` option instead of the toplevel's own machinery
  building it from the query's free variables.
* A substituted name prints as its BARE spelling -- never quoted, even
  under ``quoted(true)`` -- exactly as ``_wq_var`` already behaved; only
  the normal token-adjacency spacing (``_wq_glue``) applies, which is why
  the operator-atom and comment-text rows below need no special-casing at
  all (confirmed empirically, not merely argued).
* Several rows are marked by Ulrich as ``domain_error(...) or
  instantiation_error`` -- ISO/N246 leaves the choice open.  This engine
  always prefers domain_error when a CONCLUSIVE one is available (a
  malformed element, or an improper closed tail) even alongside an
  unresolved (var) element elsewhere in the same list; search
  ``_parse_variable_names`` for the exact rule.  Each such row below is
  commented with its row number and which of the two answers this engine
  gives.
* When several ``Name=Var`` pairs alias the SAME variable (rows 13-27),
  N246 leaves the choice of which Name prints open too.  This engine
  picks the FIRST pair in list order -- pinned by rows 15/16/21/22 below.
"""

from __future__ import annotations

import contextlib
import io as _io

import pytest

from clausal.logic.database import Module
from clausal.logic.exceptions import LogicException, render_error_term
from clausal.logic.solve import solve
from clausal.logic.variables import Trail, Var, unify


@pytest.fixture
def mod():
    return Module("write_term_variable_names_ulrich")


def _bind(*pairs) -> None:
    """Unify every ``(a, b)`` pair, in order, in ONE shared trail -- so a
    later pair can build on an earlier one's binding (row 27's ``T=(1,2,3),
    T=(X,Y,Z)``), the way Ulrich's comma-separated goal prefixes do."""
    trail = Trail()
    for a, b in pairs:
        assert unify(a, b, trail), (a, b)


def _run(mod, goal) -> str:
    """The goal's ``write_term`` output, or ``"ERR:" + the error term``."""
    buf = _io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            list(solve(goal, mod))
        return buf.getvalue()
    except LogicException as exc:
        return "ERR:" + render_error_term(exc.term)


_IE = "ERR:error(instantiation_error,write_term/2)"


def _de(culprit: str) -> str:
    return f"ERR:error(domain_error(write_option,variable_names({culprit})),write_term/2)"


# ── Scenario 1 (rows 1-12, 28, 74): write_term(T,[quoted(true), ───────────
#    variable_names([N=T])])  -- a single Name=Var pair ────────────────────

def test_row1_both_unbound_is_instantiation_error(mod):
    N, T = Var(), Var()
    out = _run(mod, ("write_term", T,
                      [("quoted", "true"), ("variable_names", [("=", N, T)])]))
    assert out == _IE


def test_row2_name_x_quoted_atom(mod):
    N, T = Var(), Var()
    _bind((N, "X"))
    out = _run(mod, ("write_term", T,
                      [("quoted", "true"), ("variable_names", [("=", N, T)])]))
    assert out == "X"


def test_row3_name_aliased_to_term_is_instantiation_error(mod):
    # N=T: the pair's Name slot is now the SAME unbound var as T itself --
    # still unresolved, not an atom yet.
    N, T = Var(), Var()
    _bind((N, T))
    out = _run(mod, ("write_term", T,
                      [("quoted", "true"), ("variable_names", [("=", N, T)])]))
    assert out == _IE


def test_row4_name_underscore_prints_unquoted(mod):
    N, T = Var(), Var()
    _bind((N, "_"))
    out = _run(mod, ("write_term", T,
                      [("quoted", "true"), ("variable_names", [("=", N, T)])]))
    assert out == "_"   # NOT "'_'" -- a substituted name is never quoted


def test_row5_name_plain_atom(mod):
    N, T = Var(), Var()
    _bind((N, "x"))
    out = _run(mod, ("write_term", T,
                      [("quoted", "true"), ("variable_names", [("=", N, T)])]))
    assert out == "x"


def test_row6_name_with_operator_chars_prints_unquoted(mod):
    N, T = Var(), Var()
    _bind((N, "x+y"))
    out = _run(mod, ("write_term", T,
                      [("quoted", "true"), ("variable_names", [("=", N, T)])]))
    assert out == "x+y"   # NOT "'x+y'"


def test_row50_name_with_parens_prints_unquoted(mod):
    N, T = Var(), Var()
    _bind((N, "))"))
    out = _run(mod, ("write_term", T,
                      [("quoted", "true"), ("variable_names", [("=", N, T)])]))
    assert out == "))"


def test_row65_name_with_comment_text_prints_unquoted(mod):
    N, T = Var(), Var()
    _bind((N, "_/*.*/"))
    out = _run(mod, ("write_term", T,
                      [("quoted", "true"), ("variable_names", [("=", N, T)])]))
    assert out == "_/*.*/"


def test_row7_name_integer_is_domain_error(mod):
    N, T = Var(), Var()
    _bind((N, 7))
    out = _run(mod, ("write_term", T,
                      [("quoted", "true"), ("variable_names", [("=", N, T)])]))
    assert out == _de("[7=_]")


def test_row8_name_compound_arith_is_domain_error(mod):
    N, T = Var(), Var()
    _bind((N, ("+", 1, 2)))
    out = _run(mod, ("write_term", T,
                      [("quoted", "true"), ("variable_names", [("=", N, T)])]))
    assert out == _de("[1+2=_]")


def test_row9_name_dollar_var_compound_is_domain_error(mod):
    N, T = Var(), Var()
    _bind((N, ("$VAR", 9)))
    exc = None
    try:
        list(solve(("write_term", T,
                    [("quoted", "true"), ("variable_names", [("=", N, T)])]),
                   mod))
    except LogicException as e:
        exc = e
    assert exc is not None
    formal = exc.term[1]
    assert formal[0] == "domain_error" and formal[1] == "write_option"


def test_row10_term_bound_name_unresolved_is_instantiation_error(mod):
    # T=a (the pair's Var slot resolves to a non-var, so the pair can never
    # match a live variable node) but N is STILL unbound -- i._e. because
    # the option's own shape is unresolved, independent of what Term is.
    N = Var()
    out = _run(mod, ("write_term", "a",
                      [("quoted", "true"), ("variable_names", [("=", N, Var())])]))
    assert out == _IE


def test_row11_term_bound_pair_irrelevant_prints_term(mod):
    N, T = Var(), Var()
    _bind((T, "a"), (N, "Any"))
    out = _run(mod, ("write_term", T,
                      [("quoted", "true"), ("variable_names", [("=", N, T)])]))
    assert out == "a"


def test_row12_term_bound_to_dollar_var_compound_no_numbervars(mod):
    # numbervars(true) is NOT set, so '$VAR'(9) prints as the quoted
    # compound it is -- the variable_names pair is irrelevant (T is bound).
    N, T = Var(), Var()
    _bind((T, ("$VAR", 9)), (N, "_"))
    out = _run(mod, ("write_term", T,
                      [("quoted", "true"), ("variable_names", [("=", N, T)])]))
    assert out == "'$VAR'(9)"


def test_row74_unrelated_fresh_var_keeps_default_notation(mod):
    # T=f(_): the inner anonymous variable has no pair of its own, so it
    # keeps the engine's ordinary (impl-defined) fresh-variable spelling --
    # variable_names must not touch a variable it was not given.
    N, T, inner = Var(), Var(), Var()
    _bind((T, ("f", inner)), (N, "Bad"))
    out = _run(mod, ("write_term", T,
                      [("quoted", "true"), ("variable_names", [("=", N, T)])]))
    assert out.startswith("f(_") and out.endswith(")")
    assert "Bad" not in out


def test_row28_freeze_does_not_wake_the_coroutining_goal(mod):
    """``freeze(T, throw(g(T))), N='X', write_term(T,[...])`` -- printing a
    name substitute for T must not deref/wake its attached goal; if it did,
    this would raise ``g(T)`` instead of printing ``X``."""
    N, T = Var(), Var()
    _bind((N, "X"))
    woke = []
    try:
        for _ in solve(("freeze", T, ("throw", ("g", T))), mod):
            pass
    except LogicException:
        woke.append(True)
    assert not woke, "freeze/2's goal fired before write_term ever ran"
    out = _run(mod, ("write_term", T,
                      [("quoted", "true"), ("variable_names", [("=", N, T)])]))
    assert out == "X"


# ── Scenario 2 (rows 13-18): variable_names(['X'=X,'Y'=Y,'Z'=Z]) ──────────

def test_row14_no_aliasing_each_var_its_own_name(mod):
    X, Y, Z, T = Var(), Var(), Var(), Var()
    vn = [("=", "X", X), ("=", "Y", Y), ("=", "Z", Z)]
    _bind((T, (",", X, (",", Y, Z))))
    out = _run(mod, ("write_term", T, [("quoted", "true"), ("variable_names", vn)]))
    assert out == "X,Y,Z"


def test_row15_z_aliased_to_y_earlier_pair_wins(mod):
    X, Y, Z, T = Var(), Var(), Var(), Var()
    vn = [("=", "X", X), ("=", "Y", Y), ("=", "Z", Z)]
    _bind((Z, Y), (T, (",", X, (",", Y, Z))))
    out = _run(mod, ("write_term", T, [("quoted", "true"), ("variable_names", vn)]))
    assert out == "X,Y,Y"   # 'Y' (earlier in the list) wins over 'Z'


def test_row16_x_y_z_all_aliased_earliest_pair_wins(mod):
    X, Y, Z, T = Var(), Var(), Var(), Var()
    vn = [("=", "X", X), ("=", "Y", Y), ("=", "Z", Z)]
    _bind((Z, Y), (Y, X), (T, (",", X, (",", Y, Z))))
    out = _run(mod, ("write_term", T, [("quoted", "true"), ("variable_names", vn)]))
    assert out == "X,X,X"


def test_row17_fresh_two_tuple_y_z(mod):
    X, Y, Z, T = Var(), Var(), Var(), Var()
    vn = [("=", "X", X), ("=", "Y", Y), ("=", "Z", Z)]
    _bind((T, (",", Y, Z)))
    out = _run(mod, ("write_term", T, [("quoted", "true"), ("variable_names", vn)]))
    assert out == "Y,Z"


def test_row18_fresh_two_tuple_z_y(mod):
    X, Y, Z, T = Var(), Var(), Var(), Var()
    vn = [("=", "X", X), ("=", "Y", Y), ("=", "Z", Z)]
    _bind((T, (",", Z, Y)))
    out = _run(mod, ("write_term", T, [("quoted", "true"), ("variable_names", vn)]))
    assert out == "Z,Y"


# ── Scenario 3 (rows 19-24): variable_names(['Z'=Z,'Y'=Y,'X'=X]) ─────────
#    (the pairs list reversed -- re-confirms "first pair in list order wins")

def test_row20_no_aliasing_reversed_list(mod):
    X, Y, Z, T = Var(), Var(), Var(), Var()
    vn = [("=", "Z", Z), ("=", "Y", Y), ("=", "X", X)]
    _bind((T, (",", X, (",", Y, Z))))
    out = _run(mod, ("write_term", T, [("quoted", "true"), ("variable_names", vn)]))
    assert out == "X,Y,Z"


def test_row21_z_aliased_to_y_z_pair_wins_now(mod):
    X, Y, Z, T = Var(), Var(), Var(), Var()
    vn = [("=", "Z", Z), ("=", "Y", Y), ("=", "X", X)]
    _bind((Z, Y), (T, (",", X, (",", Y, Z))))
    out = _run(mod, ("write_term", T, [("quoted", "true"), ("variable_names", vn)]))
    assert out == "X,Z,Z"   # 'Z' is earlier than 'Y' in THIS list


def test_row22_all_aliased_z_pair_wins(mod):
    X, Y, Z, T = Var(), Var(), Var(), Var()
    vn = [("=", "Z", Z), ("=", "Y", Y), ("=", "X", X)]
    _bind((Z, Y), (Y, X), (T, (",", X, (",", Y, Z))))
    out = _run(mod, ("write_term", T, [("quoted", "true"), ("variable_names", vn)]))
    assert out == "Z,Z,Z"


def test_row23_fresh_two_tuple_y_z_reversed_list(mod):
    X, Y, Z, T = Var(), Var(), Var(), Var()
    vn = [("=", "Z", Z), ("=", "Y", Y), ("=", "X", X)]
    _bind((T, (",", Y, Z)))
    out = _run(mod, ("write_term", T, [("quoted", "true"), ("variable_names", vn)]))
    assert out == "Y,Z"


def test_row24_fresh_two_tuple_z_y_reversed_list(mod):
    X, Y, Z, T = Var(), Var(), Var(), Var()
    vn = [("=", "Z", Z), ("=", "Y", Y), ("=", "X", X)]
    _bind((T, (",", Z, Y)))
    out = _run(mod, ("write_term", T, [("quoted", "true"), ("variable_names", vn)]))
    assert out == "Z,Y"


# ── Scenario 4 (rows 25-27): variable_names(['X'=Z,'X'=Y,'X'=X]) ─────────
#    (one NAME, three different Vars -- trivial since every pair prints
#    the same name regardless of which one wins)

def test_row26_same_name_every_slot(mod):
    X, Y, Z, T = Var(), Var(), Var(), Var()
    vn = [("=", "X", Z), ("=", "X", Y), ("=", "X", X)]
    _bind((T, (",", X, (",", Y, Z))))
    out = _run(mod, ("write_term", T, [("quoted", "true"), ("variable_names", vn)]))
    assert out == "X,X,X"


def test_row27_vars_bound_to_integers_pairs_irrelevant(mod):
    X, Y, Z, T = Var(), Var(), Var(), Var()
    vn = [("=", "X", Z), ("=", "X", Y), ("=", "X", X)]
    _bind((T, (",", 1, (",", 2, 3))), (T, (",", X, (",", Y, Z))))
    out = _run(mod, ("write_term", T, [("quoted", "true"), ("variable_names", vn)]))
    assert out == "1,2,3"


# ── Scenario 5 (rows 30-36, 51-52, 63-68): validating List itself ───────

def test_row30_list_wholly_unbound_is_instantiation_error(mod):
    out = _run(mod, ("write_term", Var(), [("variable_names", Var())]))
    assert out == _IE


def test_row31_list_bound_to_integer_is_domain_error(mod):
    out = _run(mod, ("write_term", Var(), [("variable_names", 1)]))
    assert out == _de("1")


def test_row33_list_of_one_empty_list_is_domain_error(mod):
    out = _run(mod, ("write_term", Var(), [("variable_names", [[]])]))
    assert out == _de("[[]]")


def test_row34_list_bound_to_a_plain_atom_is_domain_error(mod):
    out = _run(mod, ("write_term", Var(), [("variable_names", "non_list")]))
    assert out == _de("non_list")


def test_row35_reversed_pair_plus_improper_tail_picks_domain_error(mod):
    """``[T='T'|non_list]`` -- Ulrich: domain_error OR instantiation_error,
    both conformant.  This engine's rule (``_parse_variable_names``):
    a conclusive domain_error (the IMPROPER, bound-non-list tail) wins
    over the merely-unresolved element (T='T' has an unbound Name slot)."""
    Tv = Var()
    vnterm = (".", ("=", Tv, "T"), "non_list")
    out = _run(mod, ("write_term", Var(), [("variable_names", vnterm)]))
    assert out == _de("[_='T'|non_list]")


def test_row36_wrong_functor_pair_is_domain_error(mod):
    Tv = Var()
    out = _run(mod, ("write_term", Var(), [("variable_names", [("-", Tv, "T")])]))
    assert out == _de("[_-'T']")


def test_row51_valid_pair_plus_improper_tail_is_domain_error(mod):
    Tv = Var()
    vnterm = (".", ("=", "T", Tv), "non_list")
    out = _run(mod, ("write_term", Var(), [("variable_names", vnterm)]))
    assert out == _de("['T'=_|non_list]")


def test_row52_valid_pair_plus_open_tail_is_instantiation_error(mod):
    Tv = Var()
    vnterm = (".", ("=", "T", Tv), Var())
    out = _run(mod, ("write_term", Var(), [("variable_names", vnterm)]))
    assert out == _IE


def test_row63_unbound_then_bad_shape_picks_domain_error(mod):
    """``[_,a]`` -- Ulrich: domain_error OR instantiation_error.  This
    engine picks domain_error (the 'a' element is conclusively not a
    Name=Var pair)."""
    out = _run(mod, ("write_term", Var(), [("variable_names", [Var(), "a"])]))
    assert out == _de("[_,a]")


def test_row64_bad_shape_then_unbound_picks_domain_error(mod):
    out = _run(mod, ("write_term", Var(), [("variable_names", ["a", Var()])]))
    assert out == _de("[a,_]")


def test_row66_bad_shape_plus_open_tail_picks_domain_error(mod):
    vnterm = (".", "a", Var())
    out = _run(mod, ("write_term", Var(), [("variable_names", vnterm)]))
    assert out == _de("[a|_]")


def test_row67_non_atom_name_culprit_is_the_whole_list(mod):
    """``[i=i,7=i]`` -- Ulrich pins the culprit as the WHOLE list, not just
    the offending ``7=i`` element."""
    out = _run(mod, ("write_term", Var(),
                      [("variable_names", [("=", "i", "i"), ("=", 7, "i")])]))
    assert out == _de("[i=i,7=i]")


def test_row68_two_unbound_elements_is_instantiation_error(mod):
    """``[_,_]`` -- Ulrich: instantiation_error ONLY (not either/or)."""
    out = _run(mod, ("write_term", Var(), [("variable_names", [Var(), Var()])]))
    assert out == _IE


# ── Scenario 6 (rows 43-44): operator-spacing is unaffected ─────────────

def test_row43_prefix_minus_operand_needs_parens_name_substituted(mod):
    X = Var()
    out = _run(mod, ("write_term", ("-", ("^", X, 2)),
                      [("variable_names", [("=", "X", X)])]))
    assert out == "- (X^2)"


def test_row44_prefix_minus_bound_arg_no_substitution(mod):
    X = Var()
    _bind((X, 1))
    out = _run(mod, ("write_term", ("-", ("^", X, 2)),
                      [("variable_names", [("=", "X", X)])]))
    assert out == "- (1^2)"


# ── Scenario 7 (rows 53-55, 58-59): name text flows through normal ──────
#    operator spacing (``_wq_glue``) with NO quoting, NO special-casing ───

def test_row53_list_bound_but_name_still_unresolved(mod):
    N, T, S = Var(), Var(), Var()
    out = _run(mod, ("write_term", S,
                      [("quoted", "true"), ("variable_names", [("=", N, T)])]))
    assert out == _IE


def test_row54_comment_text_name_no_leading_space(mod):
    """``S=1+T, N='/*r*/V'`` -- Ulrich: ``1+/*r*/V`` or ``1+ /*r*/V``, both
    conformant (whether a glue-space is inserted before a comment-looking
    name is implementation-defined).  This engine's ``_wq_glue`` inserts
    one (symbol char meets symbol char)."""
    N, T, S = Var(), Var(), Var()
    _bind((S, ("+", 1, T)), (N, "/*r*/V"))
    out = _run(mod, ("write_term", S,
                      [("quoted", "true"), ("variable_names", [("=", N, T)])]))
    assert out == "1+ /*r*/V"


def test_row55_comment_text_name_with_leading_space(mod):
    """``N=' /*r*/V'`` -- the leading space is part of the NAME's own text,
    so the result is pinned exactly (only one accepted answer)."""
    N, T, S = Var(), Var(), Var()
    _bind((S, ("+", 1, T)), (N, " /*r*/V"))
    out = _run(mod, ("write_term", S,
                      [("quoted", "true"), ("variable_names", [("=", N, T)])]))
    assert out == "1+ /*r*/V"


def test_row58_operator_atom_name_right_operand(mod):
    """``S=1+T, N=(+)`` -- Ulrich: ``1++`` or ``1+ +``, both conformant."""
    N, T, S = Var(), Var(), Var()
    _bind((S, ("+", 1, T)), (N, "+"))
    out = _run(mod, ("write_term", S,
                      [("quoted", "true"), ("variable_names", [("=", N, T)])]))
    assert out in ("1++", "1+ +")


def test_row59_operator_atom_name_left_operand(mod):
    """``S=T+1, N=(+)`` -- Ulrich: ``++1`` or ``+ +1``, both conformant."""
    N, T, S = Var(), Var(), Var()
    _bind((S, ("+", T, 1)), (N, "+"))
    out = _run(mod, ("write_term", S,
                      [("quoted", "true"), ("variable_names", [("=", N, T)])]))
    assert out in ("++1", "+ +1")


# ── Scenario 8 (row 71): repeated option, last occurrence wins ──────────

def test_row71_repeated_option_last_wins(mod):
    T = Var()
    out = _run(mod, ("write_term", T,
                      [("variable_names", [("=", "Bad", T)]),
                       ("variable_names", [("=", "Good", T)])]))
    assert out == "Good"


# ── Scenario 9 (row 73): a plain evaluable compound, for completeness ───

def test_row73_is_expression(mod):
    N, T, S = Var(), Var(), Var()
    _bind((S, ("is", 1, T)), (N, "X"))
    out = _run(mod, ("write_term", S,
                      [("quoted", "true"), ("variable_names", [("=", N, T)])]))
    assert out == "1 is X"


# ── Regression: the other write-options keep working (quoted, ───────────
#    double_quotes, ignore_ops, numbervars) alongside/without ───────────
#    variable_names, and an unrecognised option is still a domain_error ──

def test_unknown_option_still_domain_error(mod):
    out = _run(mod, ("write_term", "a", [("bogus", "true")]))
    assert out == "ERR:error(domain_error(write_option,bogus(true)),write_term/2)"


def test_variable_names_combines_with_numbervars(mod):
    # '$VAR'(0) prints as 'A' via numbervars; an UNRELATED fresh var still
    # substitutes its own name -- the two mechanisms are independent.
    N, T = Var(), Var()
    _bind((N, "Name"))
    out = _run(mod, ("write_term", ("f", ("$VAR", 0), T),
                      [("numbervars", "true"),
                       ("variable_names", [("=", N, T)])]))
    assert out == "f(A,Name)"


def test_variable_names_combines_with_ignore_ops(mod):
    N, T = Var(), Var()
    _bind((N, "Name"))
    out = _run(mod, ("write_term", ("+", T, 1),
                      [("ignore_ops", "true"),
                       ("variable_names", [("=", N, T)])]))
    assert out == "+(Name,1)"


def test_no_variable_names_option_keeps_default_var_notation(mod):
    T = Var()
    out = _run(mod, ("write_term", T, [("quoted", "true")]))
    assert out.startswith("_")


def test_write_1_is_unaffected_by_variable_names_machinery(mod):
    # write/1 takes no options at all; make sure threading var_names
    # through _format_term_iso's new keyword did not disturb its default.
    out = _run(mod, ("write", ("f", "a", "b")))
    assert out == "f(a,b)"
