"""A name both IMPORTED and declared LOCALLY as a procedure is refused at
load (operator ruling 2026-09-26, in the spirit of ISO 13211-2: a local
definition that clashes with an import is an error).

The clash is by PREDICATE INDICATOR: the local name at the arity the
import brings.  A local ``edge/3`` beside an imported ``edge/2`` is a
different predicate and loads.  That follows Scryer, measured 2026-09-26
(``use_module(own, [edge/2])`` plus local ``edge(5, 6, 7)``: both answer).
For the SAME indicator Scryer is lax: it warns and overwrites for clauses,
and silently ignores a local ``:- dynamic(edge/2)``.  The ruling refuses
both.

Before this, a local ``-dynamic(edge/2)`` beside an imported ``edge`` was
never reached: the import rebinds the name after the module body runs, so a
call got ``existence_error`` (DATA import) or the imported clauses
(procedure import) where the local dynamic procedure should have failed.

Local declarations that clash: clauses, ``-dynamic``, ``-discontiguous``,
``-table``.  A PROCEDURE import met by local CLAUSES at the same indicator
was already refused by the load gate (``describe_imported_predicate_
redefinition``), and keeps that message; the new check covers the rest.  (``-multifile`` is not a Clausal directive.)  Import kinds: a
DATA functor (a field-carrying export entry, R6/R6b) and a procedure (with
clauses, or a clause-less ``name/arity`` export).  An ALIASED import clashes
on its LOCAL name.
"""

from __future__ import annotations

import sys

import pytest

from clausal.import_hook import _load_module
from clausal.logic.solve import solve
from clausal.logic.variables import Var, walk

OWNERS = {
    "data": ("own_data", "-module(own_data, [edge(A, B)])\n"),
    "proc": ("own_proc", "-module(own_proc, [edge(A, B)])\nedge(1, 2),\n"),
    "proc_pi": ("own_pi", "-module(own_pi, [edge/2])\n-dynamic(edge/2)\n"),
}

LOCALS = {
    "dynamic": lambda n, a: f"-dynamic({n}/{a})\n",
    "clauses": lambda n, a: f"{n}({', '.join(str(i + 5) for i in range(a))}),\n",
    "discontiguous": lambda n, a: (
        f"-discontiguous({n}/{a})\n"
        f"{n}({', '.join(str(i + 5) for i in range(a))}),\n"),
    "table": lambda n, a: (
        f"-table({n}/{a})\n"
        f"{n}({', '.join(str(i + 5) for i in range(a))}),\n"),
}


@pytest.fixture
def load(tmp_path):
    names = []

    def _load(name, src):
        path = tmp_path / f"{name}.clausal"
        path.write_text(src)
        sys.modules.pop(name, None)
        names.append(name)
        return _load_module(name, str(path))

    yield _load
    for name in names:
        sys.modules.pop(name, None)


def _importer_src(name, owner_mod, local_decl, alias, arity):
    local = "e" if alias else "edge"
    imported = "alias(edge, e)" if alias else "edge"
    return (f"-import_from({owner_mod}, [{imported}])\n"
            f"-module({name}, [z(X)])\n"
            + LOCALS[local_decl](local, arity)
            + "z(1),\n")


# (kind, local declaration) pairs refused at the SAME indicator.  The
# narrowed ruling: every local declaration against a DATA import; a local
# -dynamic against a STATIC procedure import; clauses against a procedure
# import (the load gate's existing refusal -- -discontiguous and -table
# reach it here because LOCALS gives them clauses).  NOT refused: a local
# -dynamic of an imported DYNAMIC procedure (``proc_pi``), the
# assert-through idiom -- see test_a_local_dynamic_of_an_imported_dynamic_...
REFUSED = [(k, d) for k in ("data",) for d in LOCALS] + [
    ("proc", "dynamic"), ("proc", "clauses"), ("proc", "discontiguous"),
    ("proc", "table"), ("proc_pi", "clauses"), ("proc_pi", "discontiguous"),
    ("proc_pi", "table"),
]


@pytest.mark.parametrize("alias", [False, True], ids=["plain", "alias"])
@pytest.mark.parametrize("kind, local_decl", REFUSED)
def test_the_same_indicator_is_refused_at_load(load, kind, local_decl, alias):
    owner_mod, owner_src = OWNERS[kind]
    load(owner_mod, owner_src)
    with pytest.raises(SyntaxError) as info:
        load("clash_imp", _importer_src("clash_imp", owner_mod, local_decl,
                                        alias, 2))
    message = str(info.value)
    local = "e" if alias else "edge"
    # It names the local predicate and the module the import comes from.
    assert f"{local}/2" in message or "edge/2" in message
    assert owner_mod in message


@pytest.mark.parametrize("kind, local_decl", [
    ("data", "dynamic"), ("data", "discontiguous"), ("data", "table"),
    ("data", "clauses"), ("proc", "dynamic"),
])
def test_the_refusal_names_the_import_the_declaration_and_both_remedies(
        load, kind, local_decl):
    owner_mod, owner_src = OWNERS[kind]
    load(owner_mod, owner_src)
    with pytest.raises(SyntaxError) as info:
        load("clash_imp", _importer_src("clash_imp", owner_mod, local_decl,
                                        False, 2))
    message = str(info.value)
    assert "clash_imp declares edge/2 locally" in message
    assert f"-import_from({owner_mod}, [edge])" in message
    if local_decl == "clauses":
        assert "(clauses for edge/2)" in message
    else:
        assert f"-{local_decl}(edge/2)" in message
    assert "remove edge from the -import_from list" in message
    assert "alias(edge, " in message


@pytest.mark.parametrize("alias", [False, True], ids=["plain", "alias"])
def test_a_local_dynamic_of_an_imported_dynamic_procedure_loads(load, alias):
    """The assert-through idiom stays allowed (operator ruling 2026-09-26):
    the local ``-dynamic`` names the owner's dynamic procedure, and an
    ``assertz`` through it lands on the owner."""
    owner = load("own_pi", OWNERS["proc_pi"][1])
    local = "e" if alias else "edge"
    imported = "alias(edge, e)" if alias else "edge"
    imp = load("assert_through",
               f"-import_from(own_pi, [{imported}])\n"
               f"-module(assert_through, [add(X), q(X)])\n"
               f"-dynamic({local}/2)\n"
               f"add(X) <- assertz({local}(X, 9))\n"
               f"q(X) <- {local}(X, 9)\n")
    lm = imp.__dict__["$module"]
    assert [None for _ in solve(("q", Var()), module=lm)] == []
    assert list(solve(("add", 4), module=lm)) != []
    assert [walk(g)[1] for g in [("q", Var())] for _ in solve(g, module=lm)] == [4]
    assert len(owner.__dict__["$module"].db.row("edge", 2).clauses) == 1


def test_the_existing_table_refusal_runs_first_with_its_own_message(load):
    """``-table`` on an imported procedure with no local clauses keeps the
    refusal ``_validate_directive_targets`` gives it."""
    load("own_proc", OWNERS["proc"][1])
    with pytest.raises(SyntaxError) as info:
        load("table_imp", "-import_from(own_proc, [edge])\n"
             "-module(table_imp, [z(X)])\n-table(edge/2)\nz(1),\n")
    assert "declares edge/2 locally" not in str(info.value)
    assert "-table(edge/2)" in str(info.value)


def test_discontiguous_on_an_imported_procedure_target_is_accepted(load):
    load("own_proc", OWNERS["proc"][1])
    load("discontig_imp", "-import_from(own_proc, [edge])\n"
         "-module(discontig_imp, [z(X)])\n-discontiguous(edge/2)\nz(1),\n")


def test_an_aliased_import_clashes_on_its_local_name(load):
    load("own_data", OWNERS["data"][1])
    with pytest.raises(SyntaxError) as info:
        load("clash_alias", _importer_src("clash_alias", "own_data",
                                          "dynamic", True, 2))
    message = str(info.value)
    assert "clash_alias declares e/2 locally" in message
    assert "-import_from(own_data, [alias(edge, e)])" in message


def test_an_aliased_import_does_not_clash_on_the_owners_spelling(load):
    """``alias(edge, e)`` imports the name ``e``; a local ``edge/2`` is a
    different name here and loads, and ``e`` still reaches the owner."""
    load("own_proc", OWNERS["proc"][1])
    mod = load("alias_free", "-import_from(own_proc, [alias(edge, e)])\n"
               "-module(alias_free, [q(X), r(X)])\n-dynamic(edge/2)\n"
               "q(X) <- e(1, X)\nr(X) <- edge(1, X)\n")
    lm = mod.__dict__["$module"]
    assert [walk(g)[1] for g in [("q", Var())] for _ in solve(g, module=lm)] == [2]


@pytest.mark.xfail(strict=True, reason=(
    "Separate, pre-existing: under alias(edge, e) the importer's own name "
    "`edge` is bound to the OWNER's handle, so a local -dynamic(edge/2) is "
    "unreachable and edge(1, X) answers the owner's fact.  Parked as an open "
    "question"))
def test_under_an_alias_the_owners_spelling_is_the_local_predicate(load):
    load("own_proc", OWNERS["proc"][1])
    mod = load("alias_local", "-import_from(own_proc, [alias(edge, e)])\n"
               "-module(alias_local, [r(X)])\n-dynamic(edge/2)\n"
               "r(X) <- edge(1, X)\n")
    lm = mod.__dict__["$module"]
    assert [None for _ in solve(("r", Var()), module=lm)] == []


@pytest.mark.parametrize("local_decl", list(LOCALS))
@pytest.mark.parametrize("kind", list(OWNERS))
def test_another_arity_is_a_different_predicate_and_loads(
        load, kind, local_decl):
    owner_mod, owner_src = OWNERS[kind]
    load(owner_mod, owner_src)
    load("arity_imp", _importer_src("arity_imp", owner_mod, local_decl,
                                    False, 3))


def test_a_procedure_import_and_a_local_other_arity_both_answer(load):
    load("own_proc", OWNERS["proc"][1])
    mod = load("both_arities", "-import_from(own_proc, [edge])\n"
               "-module(both_arities, [q(X), r(X)])\n"
               "edge(5, 6, 7),\nq(X) <- edge(1, X)\nr(Y) <- edge(5, 6, Y)\n")
    lm = mod.__dict__["$module"]
    assert [walk(g)[1] for g in [("q", Var())] for _ in solve(g, module=lm)] == [2]
    assert [walk(g)[1] for g in [("r", Var())] for _ in solve(g, module=lm)] == [7]


@pytest.mark.xfail(strict=True, reason=(
    "Separate, pre-existing: beside a DATA import of edge, a LOCAL edge/3 is "
    "unreachable -- the import rebinds `edge` to the atom after the body "
    "runs, and a call edge(5, 6, Y) raises existence_error(procedure, "
    "edge/3).  Not a clash (another arity); parked as an open question"))
def test_a_data_import_and_a_local_other_arity_procedure_answers(load):
    load("own_data", OWNERS["data"][1])
    mod = load("data_arity", "-import_from(own_data, [edge])\n"
               "-module(data_arity, [r(X)])\n"
               "edge(5, 6, 7),\nr(Y) <- edge(5, 6, Y)\n")
    lm = mod.__dict__["$module"]
    assert [walk(g)[1] for g in [("r", Var())] for _ in solve(g, module=lm)] == [7]


def test_a_python_import_is_not_checked(load):
    """``-import_from(py.json, [...])`` binds Python values, not predicates of
    a Clausal module; there is no indicator to clash with."""
    load("py_imp", "-import_from(py.json, [parse])\n"
         "-module(py_imp, [z(X)])\n-dynamic(parse/2)\nz(1),\n")
