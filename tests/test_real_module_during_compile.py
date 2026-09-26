"""The REAL LogicModule is ``$module`` for the whole of ``compile_module``.

Pre-flip task 4 (W4b-2d dry run, root cause R1): ``import_hook`` execs a
module body with a PLACEHOLDER ``LogicModule`` bound as ``$module``.  Its
Database shares the module dict, so it reports the real module's name and
claims every local handle -- but answers from an EMPTY store.  Before this
fix the real module replaced it only after ``compile_module`` returned, so
any handle to the module being compiled that was resolved MID-compile
(``_db_for_module_name`` / ``resolve_module`` -> ``sys.modules``) found the
placeholder: after the flip, ``-specialize`` over a local source program
raised ``existence_error(natnum_program/1)``.

These tests were written to build the post-flip shape by hand
(``mint_predicate_handle(db, name)``) while every binding was still a class;
after the W4b-2d flip the load produces that shape itself, and they check it.
"""
from __future__ import annotations

import os
import sys

import pytest

import clausal.import_hook  # noqa: F401 -- installs the meta-path finder
from clausal.import_hook import _load_module
from clausal.logic import compiler_v2
from clausal.logic.predicate import (
    _db_for_module_name, mint_predicate_handle, resolve_predicate_row,
)
from clausal.logic.solve import call, resolve_module
from clausal.logic.variables import Var, deref, walk

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
_NAME = "_realmod_specialize_natnum"


@pytest.fixture
def load_natnum():
    sys.modules.pop(_NAME, None)

    def load():
        return _load_module(_NAME, os.path.join(FIXTURES,
                                                "specialize_natnum.clausal"))
    yield load
    sys.modules.pop(_NAME, None)


def _program_through(handle):
    out = []
    v = Var()
    for _ in call(handle, v):
        out.append(walk(deref(v)))
    return out


def test_a_handle_to_the_module_being_compiled_resolves_to_the_real_db(
        monkeypatch, load_natnum):
    """Mid-compile (step 6b), after step 5 filled the real db: the name
    resolves to THAT db, and a handle to a local predicate answers."""
    seen = {}
    original = compiler_v2._run_specialization

    def spy(module_items, predicate_nodes, module_dict, db):
        name = db.module_name()
        seen["name"] = name
        seen["by_name"] = _db_for_module_name(name) is db
        seen["resolved"] = resolve_module(name).db is db
        seen["dollar_module"] = module_dict["$module"].db is db
        handle = mint_predicate_handle(db, "natnum_program")
        seen["answers"] = _program_through(handle)
        return original(module_items, predicate_nodes, module_dict, db)

    monkeypatch.setattr(compiler_v2, "_run_specialization", spy)
    module = load_natnum()
    assert seen["name"] == _NAME            # the spy ran, on this module
    assert seen["dollar_module"]
    assert seen["by_name"]
    assert seen["resolved"]
    assert len(seen["answers"]) == 1        # the one program list
    assert module.__dict__["$module"] is module.__clausal_module__


def test_specialize_over_a_local_source_program_bound_to_a_handle(
        monkeypatch, load_natnum):
    """End to end: the post-flip binding shape for the SOURCE program.
    ``-specialize`` calls it at step 6b through ``call()`` /
    ``resolve_module``; before the fix that found the placeholder's empty
    store and the load raised existence_error(natnum_program/1)."""
    # After the W4b-2d flip the load itself binds the source program to its
    # handle; this spy used to REBIND it by hand (a stand-in flip).  It now
    # only confirms, at step 6b, that the binding already IS the handle --
    # so the end-to-end check below is over a handle-bound source program.
    original = compiler_v2._run_specialization
    observed = []

    def see_source(module_items, predicate_nodes, module_dict, db):
        binding = module_dict["natnum_program"]
        assert binding == mint_predicate_handle(db, "natnum_program"), binding
        observed.append(binding)
        return original(module_items, predicate_nodes, module_dict, db)

    monkeypatch.setattr(compiler_v2, "_run_specialization", see_source)
    module = load_natnum()
    assert observed, "step 6b never ran over the source program: nothing tested"
    spec = module.__dict__["solve_count_natnum"]
    n = Var()
    counts = [walk(deref(n)) for _ in call(
        spec, [["natnum", ["s", ["s", 0]]]], n)]
    assert counts == [3]


def test_class_bindings_see_the_same_module_objects(load_natnum):
    """The load's end state is the one module object under both names, and
    its predicate bindings (handles, after the W4b-2d flip) resolve to that
    module's own Database."""
    module = load_natnum()
    lm = module.__clausal_module__
    assert module.__dict__["$module"] is lm
    binding = module.__dict__["natnum_program"]
    assert binding == mint_predicate_handle(lm.db, "natnum_program")
    row = resolve_predicate_row(binding, arity=1, db=lm.db)
    assert row is not None and row.db is lm.db


def test_a_bare_dict_compile_is_not_given_module_names():
    """compile_module called on a namespace with NO placeholder (the
    direct API) installs nothing into it."""
    from clausal.logic.compiler_v2 import compile_module
    ns: dict = {}
    lm = compile_module([], [], ns, "_realmod_bare")
    assert "$module" not in ns
    assert "__clausal_module__" not in ns
    assert lm is not None


def test_import_module_still_brings_no_term_expansion_rules(tmp_path,
                                                            monkeypatch):
    """The one observable change the swap would otherwise make: the TE pass
    stashed a module's expansion clauses on ``$module``, which used to be the
    placeholder (discarded), so ``-import_module(provider)`` never carried
    them.  With the real module installed first that stash would reach
    importers; it is gone, and a qualified-access import still brings none.
    A by-name import (the documented route) still does -- positive control.
    """
    from clausal.logic.atoms import mint
    monkeypatch.syspath_prepend(FIXTURES)
    (tmp_path / "te_imod.clausal").write_text(
        "-double_quotes(atom)\n-import_module(expansion_provider)\n\n"
        'color("red"),\ncolor("green"),\n')
    (tmp_path / "te_ifrom.clausal").write_text(
        "-double_quotes(atom)\n-import_from(expansion_provider, [term_expansion])\n\n"
        'color("red"),\ncolor("green"),\n')
    names = ("expansion_provider", "_realmod_te_imod", "_realmod_te_ifrom")
    try:
        answers = {}
        for stem, name in (("te_imod", names[1]), ("te_ifrom", names[2])):
            mod = _load_module(name, str(tmp_path / f"{stem}.clausal"))
            x = Var()
            answers[stem] = sorted(
                deref(x) for _ in call("color", x,
                                       module=mod.__dict__["$module"]))
        assert answers["te_imod"] == [mint("green"), mint("red")]
        assert answers["te_ifrom"] == [mint("green"), mint("green"),
                                       mint("red"), mint("red")]
    finally:
        for n in names:
            sys.modules.pop(n, None)


def test_a_second_compile_into_a_loaded_namespace_keeps_the_live_module(
        load_natnum):
    """Review MEDIUM: only the import hook's PLACEHOLDER is replaced, and it
    is identified positively (the hook hands it over), never "whatever
    ``$module`` holds".  A second ``compile_module`` into a namespace that
    already finished loading must leave the live module under both names --
    today's behaviour, since compile_module never wrote either name."""
    from clausal.logic.compiler_v2 import compile_module
    module = load_natnum()
    ns = module.__dict__
    live = ns["$module"]
    assert live.db.row("natnum_program", 1).clauses   # a live, non-empty db
    other = compile_module([], [], ns, _NAME)
    assert other is not live
    assert ns["$module"] is live
    assert module.__clausal_module__ is live
    assert live.db.row("natnum_program", 1).clauses

