"""A name exported with NO clauses: what a call, an importer, ``-dynamic``,
``clause/2``, ``listing/1`` and the load binding answer (2026-09-26).

Two export spellings reach this, and they are different declarations today:

* ``name/arity`` -- the ISO spelling (13211-1 module exports are predicate
  indicators) -- declares a PROCEDURE.  It binds the module's predicate
  handle, and a call reports the procedure as undefined in that module.
* ``name(A, B)`` -- a field-carrying entry -- declares a DATA functor
  (ruling R6/R6b, P3-2 Task 2; ``term_rewriting._predicate_export_spec``):
  it binds the atom of its spelling, and references compile to cells.

The ISO-visible answer is the same for both, and is pinned here so neither
can drift: a call raises ``existence_error(procedure, name/arity)`` (flag
``unknown`` at ``error``); ``-dynamic`` makes it fail instead; ``clause/2``
fails (ISO 8.8.1: no such procedure); ``listing/1`` fails (Scryer's
``\\+ \\+ clause(Head, _)``).  ``current_predicate/1`` is not a Clausal
builtin, so it has no answer to pin.

Operator ruling 2026-09-26: R6/R6b STANDS.  The ISO spelling ``edge/2`` is
the procedure export and already stays a procedure with no clauses; ISO
module exports are predicate indicators only, so the field-carrying spelling
is a Clausal extension ISO does not constrain, and it stays a DATA functor
(the in-repo tagged-term and constant-functor exports rely on it).  What
changed is the call's MESSAGE: it says the name is declared as DATA and names
the ISO spelling that exports a procedure, where it used to blame an
unexplained "data reference".
"""

from __future__ import annotations

import sys

import pytest

from clausal.import_hook import _load_module
from clausal.logic.atoms import mangle
from clausal.logic.exceptions import LogicException
from clausal.logic.solve import solve
from clausal.logic.variables import Var, walk
from clausal.terms import Compound


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


def _lm(mod):
    return mod.__dict__["$module"]


def _answers(mod, goal):
    return [walk(goal) for _ in solve(goal, module=_lm(mod))]


def _error(mod, goal):
    with pytest.raises(LogicException) as info:
        list(solve(goal, module=_lm(mod)))
    term = info.value.term
    assert term.functor == "error"
    return term.args[0], str(term.args[1])


FIELDED = "-module(cle_owner, [edge(A, B)])\n"
ISO_PI = "-module(cle_owner, [edge/2])\n"


def _importer(load, owner):
    return load(f"{owner}_imp",
                f"-import_from({owner}, [edge])\n"
                f"-module({owner}_imp, [q(X)])\n"
                f"q(X) <- edge(1, X)\n")


# ── the ISO-visible answers: identical for both spellings ────────────────────


@pytest.mark.parametrize("src", [FIELDED, ISO_PI], ids=["fielded", "iso-pi"])
class TestISOAnswers:
    def test_a_call_is_an_existence_error_for_the_procedure(self, load, src):
        mod = load("cle_owner", src)
        formal, _ = _error(mod, ("edge", 1, Var()))
        assert formal == Compound("existence_error",
                                  ("procedure", Compound("/", ("edge", 2))))

    def test_a_call_through_an_importer_is_the_same_error(self, load, src):
        load("cle_owner", src)
        imp = _importer(load, "cle_owner")
        formal, _ = _error(imp, ("q", Var()))
        assert formal == Compound("existence_error",
                                  ("procedure", Compound("/", ("edge", 2))))

    def test_dynamic_makes_the_call_fail_instead(self, load, src):
        mod = load("cle_owner", src + "-dynamic(edge/2)\n")
        assert _answers(mod, ("edge", 1, Var())) == []
        imp = _importer(load, "cle_owner")
        assert _answers(imp, ("q", Var())) == []

    def test_clause_2_fails(self, load, src):
        mod = load("cle_owner", src)
        assert _answers(mod, ("clause", ("edge", Var(), Var()), Var())) == []

    def test_listing_fails(self, load, src, capsys):
        mod = load("cle_owner", src)
        assert _answers(mod, ("listing", ("/", "edge", 2))) == []
        assert capsys.readouterr().out == ""


# ── the load binding: which declaration each spelling makes ─────────────────


def test_the_iso_spelling_binds_the_module_handle(load):
    mod = load("cle_owner", ISO_PI)
    assert mod.__dict__["edge"] == mangle("cle_owner", "edge")
    imp = _importer(load, "cle_owner")
    assert imp.__dict__["edge"] == mangle("cle_owner", "edge")


def test_a_clauseless_fielded_export_is_declared_data(load):
    """R6/R6b (reaffirmed 2026-09-26): the binding is the atom, the Database
    says DATA -- it does not become a procedure for lack of clauses."""
    mod = load("cle_owner", FIELDED)
    assert mod.__dict__["edge"] == "edge"
    assert mod.__dict__["edge"] != mangle("cle_owner", "edge")
    assert _lm(mod).db.declared_kind("edge", 2) == "data"


def test_an_importer_of_a_clauseless_fielded_export_gets_the_atom(load):
    """The importer sees the same DATA declaration, not a predicate handle:
    its binding is the atom, and its OWN Database declares ``edge/2`` as
    data (the -import_from carrier registers the owner's field names under
    the local name)."""
    load("cle_owner", FIELDED)
    imp = _importer(load, "cle_owner")
    assert imp.__dict__["edge"] == "edge"
    assert imp.__dict__["edge"] != mangle("cle_owner", "edge")
    assert _lm(imp).db.declared_kind("edge", 2) == "data"


def test_an_exported_bare_atom_stays_an_atom(load):
    """``-module(m, [foo, ...])``: a bare name in an export list is an ATOM,
    and stays one whatever happens to the field-carrying entries."""
    mod = load("cle_atom", "-module(cle_atom, [foo, bar(X)])\nbar(foo)\n")
    assert mod.__dict__["foo"] == "foo"
    assert _answers(mod, ("bar", Var())) == [("bar", "foo")]
    formal, _ = _error(mod, "foo")
    assert formal == Compound("existence_error",
                              ("procedure", Compound("/", ("foo", 0))))


# ── the message: names the DATA declaration by its source ───────────────────


def test_a_module_export_entry_is_named_as_this_files_export(load):
    mod = load("cle_owner", FIELDED)
    _, message = _error(mod, ("edge", 1, Var()))
    assert "data reference" not in message
    assert message.startswith("edge/2 is declared as DATA")
    assert "the -module export entry edge(A, B) in cle_owner" in message
    assert "write edge/2 in that export list instead" in message


def test_a_private_entry_is_named_as_a_private_entry_not_an_export(load):
    mod = load("cle_priv", "-module(cle_priv, [q(X)])\n"
               "-private([hid(A, B)])\nq(X) <- hid(1, X)\n")
    formal, message = _error(mod, ("q", Var()))
    assert formal == Compound("existence_error",
                              ("procedure", Compound("/", ("hid", 2))))
    assert "the -private entry hid(A, B) in cle_priv" in message
    assert "write hid/2 in that -private list instead" in message
    assert "export" not in message


def test_an_import_names_the_owner_module_and_its_export_entry(load):
    load("cle_owner", FIELDED)
    imp = _importer(load, "cle_owner")
    _, message = _error(imp, ("q", Var()))
    assert "data reference" not in message
    assert message.startswith("edge/2 is declared as DATA")
    assert "imported from cle_owner, whose export entry edge(A, B)" in message
    assert "its export list writes edge/2 instead" in message


def test_an_aliased_import_names_the_owners_spelling_not_the_alias(load):
    """``alias(edge, e)`` declares ``e/2`` in the importer, but ``e`` is bound
    to the owner's atom ``edge``, so the call reaches ``edge/2`` -- and the
    message must name ``edge`` and ``cle_owner``, never tell the user to
    write ``e/2`` in an export list (the owner exports ``edge``)."""
    load("cle_owner", FIELDED)
    imp = load("cle_alias", "-import_from(cle_owner, [alias(edge, e)])\n"
               "-module(cle_alias, [q(X)])\nq(X) <- e(1, X)\n")
    assert imp.__dict__["e"] == "edge"
    assert _lm(imp).db.declared_kind("e", 2) == "data"
    formal, message = _error(imp, ("q", Var()))
    assert formal == Compound("existence_error",
                              ("procedure", Compound("/", ("edge", 2))))
    assert "imported from cle_owner, whose export entry edge(A, B)" in message
    assert "e/2" not in message.replace("edge/2", "")
    assert "data reference" not in message


def test_the_iso_spelling_does_not_get_the_data_message(load):
    mod = load("cle_owner", ISO_PI)
    _, message = _error(mod, ("edge", 1, Var()))
    assert "DATA" not in message
    assert "edge/2 is not defined in module 'cle_owner'" in message


def test_an_undeclared_atom_keeps_the_general_message(load):
    """A plain atom called as a goal -- no DATA declaration at that arity --
    is not told about export lists."""
    mod = load("cle_atom", "-module(cle_atom, [foo, bar(X)])\nbar(foo)\n")
    _, message = _error(mod, "foo")
    assert "is declared as DATA" not in message
    assert "is not callable at arity 0" in message


# ── import diagnostics ───────────────────────────────────────────────────────


@pytest.mark.parametrize("src", [FIELDED, ISO_PI], ids=["fielded", "iso-pi"])
def test_a_bad_import_lists_the_export_whichever_spelling_declared_it(
        load, src):
    """A failed ``-import_from`` names what the module exports.  For the ISO
    ``edge/2`` spelling it used to say the module had "an EMPTY -module(...)
    export list": the ``name/arity`` entries are recorded as
    ``predicate_export`` directive items, which the diagnostic did not read."""
    load("cle_owner", src)
    with pytest.raises(ImportError) as info:
        load("cle_imp_bad", "-import_from(cle_owner, [edge, nope])\n"
             "-module(cle_imp_bad, [z(X)])\nz(1),\n")
    message = str(info.value)
    assert "cannot import name 'nope'" in message
    assert "EMPTY" not in message
    assert "cle_owner exports: edge/2" in message


def test_a_private_name_arity_entry_is_not_listed_as_an_export(load):
    """``-private([helper/1])`` is not public API: the diagnostic must not
    list it under "exports"."""
    load("cle_priv", "-module(cle_priv, [edge/2])\n-private([helper/1])\n")
    with pytest.raises(ImportError) as info:
        load("cle_priv_imp", "-import_from(cle_priv, [nope])\n"
             "-module(cle_priv_imp, [z(X)])\nz(1),\n")
    message = str(info.value)
    assert "cle_priv exports: edge/2" in message
    exports_line = next(l for l in message.splitlines() if "exports:" in l)
    assert "helper" not in exports_line


def _module_items(src, name):
    from clausal.import_hook import _parse_clausal_source
    _code, transformer = _parse_clausal_source(src, f"/nonexistent/{name}.clausal")
    return transformer._module_items


def test_the_rewriter_records_name_arity_entries_just_before_their_declaration():
    """``import_diagnostics._declared_exports`` attributes a
    ``predicate_export`` item to the -module or -private declaration that
    FOLLOWS it.  That relies on the rewriter appending each list's
    ``name/arity`` items while it walks the list, before the declaration
    item itself.  Pinned directly, so a rewriter change that moves them
    fails here instead of silently misattributing an export."""
    from clausal.pythonic_ast.nodes import (
        Directive, ModuleDeclaration, PrivateDeclaration,
    )
    src = ("-module(cle_ord, [edge/2, pt(X, Y), foo, walk/1])\n"
           "-private([helper/1, rec(A)])\n")
    shapes = []
    for item in _module_items(src, "cle_ord"):
        if isinstance(item, Directive) and item.name == "predicate_export":
            shapes.append(("pi", tuple(item.specs)))
        elif isinstance(item, ModuleDeclaration):
            shapes.append(("module", tuple(
                e if isinstance(e, str) else e[0] for e in item.exports)))
        elif isinstance(item, PrivateDeclaration):
            shapes.append(("private", tuple(
                e if isinstance(e, str) else e[0] for e in item.items)))
    assert shapes == [
        ("pi", (("edge", 2),)), ("pi", (("walk", 1),)),
        ("module", ("pt", "foo")),
        ("pi", (("helper", 1),)),
        ("private", ("rec",)),
    ]


def _exports_line(load, owner_name, owner_src):
    load(owner_name, owner_src)
    with pytest.raises(ImportError) as info:
        load(f"{owner_name}_bad", f"-import_from({owner_name}, [nope])\n"
             f"-module({owner_name}_bad, [z(X)])\nz(1),\n")
    return next(l.strip() for l in str(info.value).splitlines()
                if "exports:" in l)


def test_a_mixed_export_list_lists_every_entry(load):
    """Fielded, ISO and atom entries in one list: all listed, the
    ``name/arity`` group first (the documented order), -private ones not."""
    line = _exports_line(
        load, "cle_mix",
        "-module(cle_mix, [edge/2, pt(X, Y), foo, walk/1])\n"
        "-private([helper/1, rec(A)])\n")
    assert line == "cle_mix exports: edge/2, walk/1, pt/2, foo"


def test_a_second_module_directive_after_a_private_list_is_attributed_to_it(
        load):
    line = _exports_line(
        load, "cle_two",
        "-module(cle_two, [edge/2])\n"
        "-private([helper/1])\n"
        "-module(cle_two, [late/3, pt(X)])\n")
    assert line == "cle_two exports: edge/2, late/3, pt/1"


# ── an origin speaks only for a key that is STILL data (roborev 200) ─────────


def test_an_origin_is_ignored_once_the_key_has_a_row(load):
    """REPRODUCED 2026-09-26: an importer that imports the DATA ``edge`` and
    ALSO declares ``-dynamic(edge/2)`` has a ROW for ``edge/2``
    (``declared_kind`` answers ``"predicate"``), but its binding is still the
    owner's atom, so a call reaches the atom arm -- and the message said
    "declared as DATA ... imported from cle_owner".  The recorded origin must
    only speak while the key is still DATA."""
    load("cle_owner", FIELDED)
    imp = load("cle_dynimp", "-import_from(cle_owner, [edge])\n"
               "-module(cle_dynimp, [q(X)])\n-dynamic(edge/2)\n"
               "q(X) <- edge(1, X)\n")
    db = _lm(imp).db
    assert db.row("edge", 2) is not None
    assert db.declared_kind("edge", 2) == "predicate"
    formal, message = _error(imp, ("q", Var()))
    assert formal == Compound("existence_error",
                              ("procedure", Compound("/", ("edge", 2))))
    assert "declared as DATA" not in message


def test_an_aliased_origin_is_ignored_once_the_local_key_has_a_row(load):
    load("cle_owner", FIELDED)
    imp = load("cle_dynalias", "-import_from(cle_owner, [alias(edge, e)])\n"
               "-module(cle_dynalias, [q(X)])\n-dynamic(e/2)\n"
               "q(X) <- e(1, X)\n")
    assert _lm(imp).db.declared_kind("e", 2) == "predicate"
    _, message = _error(imp, ("q", Var()))
    assert "declared as DATA" not in message


def test_two_aliased_imports_of_the_same_spelling_name_both_owners(load):
    """``alias(edge, e1)`` from one module and ``alias(edge, e2)`` from
    another both bind the atom ``edge``: a call through either reaches
    ``edge/2``, and nothing tells the two apart, so the message names both
    owners rather than guessing one."""
    load("cle_own1", "-module(cle_own1, [edge(A, B)])\n")
    load("cle_own2", "-module(cle_own2, [edge(X, Y)])\n")
    imp = load("cle_twoalias",
               "-import_from(cle_own1, [alias(edge, e1)])\n"
               "-import_from(cle_own2, [alias(edge, e2)])\n"
               "-module(cle_twoalias, [q(X)])\nq(X) <- e1(1, X)\n")
    _, message = _error(imp, ("q", Var()))
    assert "cle_own1" in message and "cle_own2" in message
    assert "edge(A, B)" in message and "edge(X, Y)" in message


def test_a_placeholder_module_name_is_not_put_in_the_message():
    """A Database with no real module name answers ``<detached>`` /
    ``<anonymous>``; that placeholder must not appear in user text."""
    from clausal.logic.compiler_v2 import _process_directives
    from clausal.logic.database import Database
    from clausal.logic.predicate import _atom_goal_message
    from clausal.pythonic_ast.nodes import ModuleDeclaration
    for db in (Database(), Database(module_dict={})):
        assert db.module_name() in ("<detached>", "<anonymous>")
        _process_directives(
            [ModuleDeclaration(module_name="x", exports=[("edge", ["A", "B"])])],
            db)
        message = _atom_goal_message("edge", 2, db)
        assert message.startswith("edge/2 is declared as DATA")
        assert "<" not in message
        assert "the -module export entry edge(A, B) declares" in message
