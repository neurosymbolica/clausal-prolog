"""``-meta_predicate(p(1, '?'))``: Scryer's meta_predicate/1, in both eras.

Operator ruling 2026-09-25 (ruling 1, "follow Scryer").  Ruling S makes a
predicate name passed as data the plain atom, so a higher-order predicate in
another module looked it up in ITS module and silently answered nothing::

    % hutil:  -module(hutil, [apply_all(G, L)])   apply_all(G, L) <- maplist(G, L),
    % hmain:  -import_from(hutil, [apply_all])    my_pred(1),  go() <- apply_all(my_pred, [1]),

Scryer (verified on the box)::

    ?- apply_all(my_pred,[1]).    % error(existence_error(procedure,my_pred/1),my_pred/1)
    :- meta_predicate(apply_all2(1, ?)).
    ?- apply_all2(my_pred,[1]).   % yes

A ``:``/integer spec position is qualified with the CALLER's module
(``M:G`` -- the runtime cell ``(":", M, G)``) unless already qualified;
``'+'``/``'-'``/``'?'`` positions are untouched; the qualified goal resolves
in the caller through call/N, maplist, phrase and time_goal inside the
callee.  Without the declaration the name resolves in the callee and --
ruling 2 (2026-09-25) -- an unknown procedure RAISES.
"""
from __future__ import annotations

import sys
import textwrap

import pytest

from clausal.logic.atoms import mangle, mint
from clausal.logic.exceptions import LogicException
from clausal.logic.predicate import PredicateMeta
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref, walk
from clausal.terms import Compound


def _load(tmp_path, monkeypatch, name, body):
    from clausal.import_hook import _load_module
    monkeypatch.syspath_prepend(str(tmp_path))
    p = tmp_path / f"{name}.clausal"
    p.write_text(textwrap.dedent(body).lstrip())
    mod = _load_module(name, str(p))
    assert sys.modules[name] is mod
    return mod


def _bind_imports_as_owner_handles(monkeypatch, owner):
    """The handle era for ``-import_from`` (D1: an import binds the OWNER's
    handle) -- the emulation test_arity_mismatch_is_iso_existence_error_both_eras
    uses."""
    import clausal.logic.compiler_v2 as cv
    orig = cv._process_imports
    seen = []

    def flipped(items, module_dict, db=None):
        orig(items, module_dict, db)
        for k, v in list(module_dict.items()):
            if (isinstance(v, PredicateMeta) and v._row is not None
                    and v._row._db is owner.db):
                module_dict[k] = mangle(owner.name, v._row._key[0])
                seen.append(k)

    monkeypatch.setattr(cv, "_process_imports", flipped)
    return seen


_OWNER = """
    -module(mpu_ERA, [apply_all(G, L), apply_all_raw(G, L), call_it(G, X),
                      parse_with(NT, L), time_it(G), collect(G, L),
                      qual_probe(G, Q), colon_probe(M, Q), data_probe(A, B, C, Q),
                      my_map(G, L), last_goal(G, L, Q)])
    -meta_predicate(apply_all(1, '?'), call_it(1, '?'), parse_with(2, '?'),
                    time_it(0), collect(1, '?'), qual_probe(0, '?'),
                    colon_probe(':', '?'), data_probe('+', '-', '?', '?'),
                    my_map(1, '?'), last_goal(1, '?', '?'))
    apply_all(G, L) <- maplist(G, L),
    apply_all_raw(G, L) <- maplist(G, L),
    call_it(G, X) <- call(G, X),
    parse_with(NT, L) <- phrase(NT, L),
    time_it(G) <- time_goal(G),
    collect(G, L) <- findall(X, call(G, X), L),
    qual_probe(G, Q) <- (Q is G),
    colon_probe(M, Q) <- (Q is M),
    data_probe(A, B, C, Q) <- (Q is [A, B, C]),
    my_map(_G, []),
    my_map(G, [H, *T]) <- (call(G, H), my_map(G, T)),
    last_goal(G, [], Q) <- (Q is G),
    last_goal(G, [_H, *T], Q) <- last_goal(G, T, Q),
"""

_IMPORTER = """
    -module(mpm_ERA, [])
    -import_from(mpu_ERA, [apply_all, apply_all_raw, call_it, parse_with,
                           time_it, collect, qual_probe, colon_probe, data_probe,
                           my_map, last_goal])
    my_pred(1),
    my_pred(2),
    greet >> (["h", "i"])
    go_decl() <- apply_all(my_pred, [1, 2]),
    go_decl_miss() <- apply_all(my_pred, [3]),
    go_raw() <- apply_all_raw(my_pred, [1]),
    go_call(X) <- call_it(my_pred, X),
    go_phrase() <- parse_with(greet, ["h", "i"]),
    go_time() <- time_it(my_pred(1)),
    go_collect(L) <- collect(my_pred, L),
    go_meta_call() <- call(apply_all, my_pred, [1]),
    go_qual(Q) <- qual_probe(my_pred, Q),
    go_colon(Q) <- colon_probe(my_pred, Q),
    go_data(Q) <- data_probe(my_pred, my_pred, my_pred, Q),
    pass_through(G, Q) <- qual_probe(G, Q),
    go_map() <- my_map(my_pred, [1, 2, 1]),
    go_last(Q) <- last_goal(my_pred, [1, 2, 3], Q),
"""


@pytest.fixture(params=["class", "handle"])
def pair(request, tmp_path, monkeypatch):
    era = request.param
    ow = _load(tmp_path, monkeypatch, f"mpu_{era}", _OWNER.replace("ERA", era))
    O = ow.__dict__["$module"]
    seen = (_bind_imports_as_owner_handles(monkeypatch, O)
            if era == "handle" else None)
    im = _load(tmp_path, monkeypatch, f"mpm_{era}", _IMPORTER.replace("ERA", era))
    I = im.__dict__["$module"]
    if era == "handle":
        assert "apply_all" in seen, "the handle era must really be exercised"
        assert I.module_dict["apply_all"] == mangle(f"mpu_{era}", "apply_all")
    return era, O, I


def _n(module, goal, *args):
    return len(list(call(goal, *args, module=module)))


def _one(module, goal):
    q = Var()
    out = [walk(q) for _ in call(goal, q, module=module)]
    assert len(out) == 1, out
    return out[0]


def test_the_declaration_is_recorded_on_the_owner_and_read_through_the_import(pair):
    _era, O, I = pair
    assert O.db.meta_predicate_specs("apply_all", 2) == (1, "?")
    assert I.db.meta_predicate_specs("apply_all", 2) == (1, "?")
    assert I.db.meta_predicate_specs("apply_all_raw", 2) is None


def test_undeclared_the_name_resolves_in_the_callee_and_raises(pair):
    """The HIGH as the controller measured it, now loud (ruling 2): the
    callee's maplist looks ``my_pred`` up in the CALLEE's module."""
    _era, _O, I = pair
    with pytest.raises(LogicException) as exc:
        _n(I, "go_raw")
    formal = exc.value.term.args[0]
    assert formal.functor == "existence_error"
    assert formal.args == (mint("procedure"), Compound("/", (mint("my_pred"), 1)))


def test_declared_the_meta_argument_resolves_in_the_caller(pair):
    _era, _O, I = pair
    assert _n(I, "go_decl") == 1
    assert _n(I, "go_decl_miss") == 0          # resolved, and simply fails


def test_meta_arguments_reach_call_n_phrase_time_goal_and_findall(pair, capsys):
    _era, _O, I = pair
    x = Var()
    assert sorted(deref(x) for _ in call("go_call", x, module=I)) == [1, 2]
    assert _n(I, "go_phrase") == 1
    assert _n(I, "go_time") == 1
    assert _one(I, "go_collect") == [1, 2]


def test_a_meta_call_of_a_declared_predicate_qualifies_too(pair):
    """``call(apply_all, my_pred, L)`` -- Scryer's expand_call_goal."""
    _era, _O, I = pair
    assert _n(I, "go_meta_call") == 1


def test_a_python_query_qualifies_with_the_query_module(pair):
    _era, _O, I = pair
    assert _n(I, "apply_all", "my_pred", [1]) == 1


@pytest.mark.parametrize("goal, spec", [("go_qual", "0"), ("go_colon", ":")])
def test_each_qualifying_spec_kind_qualifies_with_the_caller(pair, goal, spec):
    era, _O, I = pair
    assert _one(I, goal) == (":", f"mpm_{era}", "my_pred"), spec


def test_plus_minus_and_question_positions_are_untouched(pair):
    _era, _O, I = pair
    assert _one(I, "go_data") == ["my_pred", "my_pred", "my_pred"]


def test_an_already_qualified_argument_is_left_alone(pair):
    era, _O, I = pair
    q = Var()
    already = (":", "somewhere_else", "p")
    assert [walk(q) for _ in call("pass_through", already, q, module=I)] == [already]
    # ... and a plain one bound at run time is qualified.
    q = Var()
    assert [walk(q) for _ in call("pass_through", "p", q, module=I)] == [
        (":", f"mpm_{era}", "p")]


def test_a_malformed_declaration_is_a_load_error(tmp_path, monkeypatch):
    """Scryer's setup_meta_predicate accepts only + - ? : and integers;
    ``^`` and ``//`` are an InvalidMetaPredicateDecl there."""
    for bad in ("p('^')", "p('//')", "p(-1)", "p(x)"):
        with pytest.raises(SyntaxError, match="meta"):
            _load(tmp_path, monkeypatch, "mp_bad",
                  f"-module(mp_bad, [p(A)])\n-meta_predicate({bad})\np(_A),\n")
        sys.modules.pop("mp_bad", None)


def test_a_recursive_meta_predicate_runs_and_never_nests_the_qualification(pair):
    """The owner's own recursive tail call re-qualifies G with the OWNER's
    module at each step -- which leaves an already-qualified G alone, so the
    caller's qualification survives unnested (Scryer: HeadVars)."""
    era, _O, I = pair
    assert _n(I, "go_map") == 1
    assert _one(I, "go_last") == (":", f"mpm_{era}", "my_pred")
