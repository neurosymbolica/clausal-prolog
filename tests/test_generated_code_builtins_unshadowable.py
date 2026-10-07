"""Generated code reaches Python builtins and engine helpers through ``$`` names.

A user report: a module whose DCG rule head used a functor named ``list``
made an unrelated list-pattern nonterminal raise ``TypeError: isinstance()
arg 2 must be a type, a tuple of types, or a union``.  The first-argument
list dispatch was emitted as ``isinstance(_d, (list, str, bytes))``; the
predicate's globals are layered over the module dict, which bound ``list``
to the user's atom, so ``LOAD_GLOBAL list`` returned a ``str``.

Every bare name generated code emits has the same hole: a user atom or
functor (``p(len(X)).``), or a Python binding in a seam module
(``Exception = 5``), shadows it.  The convention already used for
``$deref``/``$unify``/``$Var`` (``clausal/logic/generated_names.py``) closes
it: ``$`` is not an identifier character, so a ``$`` name cannot be spelled
by a user.  These tests bind each name the engine emits and check that the
constructs which emit it still answer.
"""

from __future__ import annotations

import ast
import builtins
import dis
import importlib
import itertools
import sys

import pytest

from clausal import to_python
from clausal.logic import solve as S
from clausal.terms import Var, deref

_COUNTER = itertools.count()


def _import(tmp_path, stem, suffix, text):
    name = f"{stem}_{next(_COUNTER)}"
    dep = f"{name}_dep"
    (tmp_path / f"{dep}.clausal").write_text(
        f":- module({dep}, [dep/1]).\ndep(2).\n:- end_module({dep}).\n")
    (tmp_path / f"{name}{suffix}").write_text(
        text.replace("@MOD@", name).replace("@DEP@", dep))
    sys.path.insert(0, str(tmp_path))
    try:
        return importlib.import_module(name)
    finally:
        sys.path.remove(str(tmp_path))


def _first(mod, goal):
    out = Var()
    for _ in S.solve((goal, out), module=mod):
        return to_python(deref(out))
    return "<no answer>"


# ── the reported shape ──────────────────────────────────────────────────────

REPORTED = """\
:- module(@MOD@, [t/1]).
t(Out) :- once(phrase(copy([a, b]), Out)).
copy([]) --> [].
copy([C|Cs]) --> [C], copy(Cs).
value(list([X|Xs])) --> value(X), commas(Xs).
:- end_module(@MOD@).
"""


def test_dcg_head_functor_list_beside_a_list_pattern_nonterminal(tmp_path):
    mod = _import(tmp_path, "gcb_reported", ".clausal", REPORTED)
    assert _first(mod, "t") == "ab"


# ── Clausal Prolog: a user functor named like an emitted builtin ────────────

#: goal -> (clauses, expected answer).  Each exercises a different emitter.
PROLOG_PROBES = {
    # first-argument list dispatch on a bound list
    "t_dispatch": ("t_dispatch(Out) :- once(phrase(copy([a, b]), Out)).\n"
                   "copy([]) --> [].\ncopy([C|Cs]) --> [C], copy(Cs).\n",
                   "ab"),
    # ... on an UNBOUND list: every class in the isinstance tuple is read,
    # then the is_var branch
    "t_dispvar": ("t_dispvar(N) :- once(phrase(copy(L), [a, b])), "
                  "length(L, N).\n", 2),
    "t_callnth": ("t_callnth(Out) :- call_nth(member(Out, [a, b, c]), 2).\n",
                  "b"),
    "t_scc": ("t_scc(Out) :- setup_call_cleanup(true, Out = a, true).\n", "a"),
    "t_freeze": ("t_freeze(Out) :- freeze(X, Out = done), X = go.\n", "done"),
    "t_catch": ("t_catch(Out) :- catch(throw(oops), E, Out = E).\n", "oops"),
    "t_multi": ("t_multi(Out) :- once(mc(Out)).\nmc(X) :- X = a.\n"
                "mc(X) :- X = b.\n", "a"),
    # an imported predicate (module-level import plumbing runs at load)
    "t_import": ("t_import(Out) :- dep(Out).\n", 2),
}

#: Lowercase names a Clausal Prolog module can bind as a functor.
PROLOG_NAMES = ["list", "str", "bytes", "isinstance", "int", "len", "range",
                "tuple", "type", "globals", "is_var"]


def _prolog_module(name, shape):
    bind = (f"value({name}([X|Xs])) --> value(X), commas(Xs).\n"
            if shape == "dcg" else f"p({name}(x)).\n")
    exports = ", ".join(f"{g}/1" for g in PROLOG_PROBES)
    body = "".join(src for src, _ in PROLOG_PROBES.values())
    return (f":- module(@MOD@, [{exports}]).\n"
            ":- use_module(@DEP@, [dep/1]).\n"
            f"{bind}{body}:- end_module(@MOD@).\n")


@pytest.mark.parametrize("shape", ["dcg", "fact"])
@pytest.mark.parametrize("name", PROLOG_NAMES)
def test_prolog_functor_named_like_an_emitted_name(tmp_path, name, shape):
    mod = _import(tmp_path, f"gcb_pl_{shape}", ".clausal",
                  _prolog_module(name, shape))
    got = {g: _first(mod, g) for g in PROLOG_PROBES}
    assert got == {g: want for g, (_, want) in PROLOG_PROBES.items()}


# ── seam: a Python binding of the same name in the module ───────────────────

SEAM_PROBES = {
    "t_dispatch": ("t_dispatch(N) <- (once(copy(L, [a, b])), length(L, N))\n"
                   "copy([], []),\ncopy([C, *Cs], [C, *Ds]) <- copy(Cs, Ds)\n",
                   2),
    # a multi-star head: len/range/isinstance and the SegList tests
    "t_multistar": ("t_multistar(A) <- once(split([a, x, b], A, _))\n"
                    "split([*A, x, *B], A, B),\n", ["a"]),
    "t_callnth": ("t_callnth(Out) <- call_nth(member(Out, [a, b, c]), 2)\n",
                  "b"),
    "t_scc": ("t_scc(Out) <- setup_call_cleanup(true, Out is a, true)\n", "a"),
    "t_freeze": ("t_freeze(Out) <- (freeze(X, Out is done), X is go)\n",
                 "done"),
    # a second freeze/2 on the same variable extends its goal list
    "t_freeze2": ("t_freeze2(Out) <- (freeze(X, Out is done), freeze(X, true), "
                  "X is go)\n", "done"),
    "t_catch": ("t_catch(Out) <- catch(throw(oops), E, Out is E)\n", "oops"),
    # once/1 abandons mc/1's choicepoint: closing it runs the GeneratorExit
    # handler of the head's trail guard
    "t_multi": ("t_multi(Out) <- once(mc(Out))\nmc(X) <- (X is a)\n"
                "mc(X) <- (X is b)\n", "a"),
    # a tail call whose argument comes from a head decomposition: the TRO
    # path checks it is bound at run time
    "t_tro": ("t_tro(R) <- wk([1, 2, 3], 0, R)\nwk([], A, A),\n"
              "wk([H, *T], A, R) <- (eval_(A + H, A1), wk(T, A1, R))\n", 6),
}

#: Every name generated CLAUSE code reached bare before the fix.
CLAUSE_NAMES = ["isinstance", "list", "str", "bytes", "tuple", "int", "len",
                "range", "Exception", "GeneratorExit", "SystemExit",
                "is_var", "SegList", "SegString", "SegBytes", "StepGenerator"]


def _seam_module(binding):
    exports = ", ".join(f"{g}(X)" for g in SEAM_PROBES)
    body = "".join(src for src, _ in SEAM_PROBES.values())
    return (f"-module(@MOD@, [{exports}, t_halt(X)])\n"
            "-private([a, b, c, x, oops, done, go])\n"
            f"{binding}{body}t_halt(_) <- halt\n")


@pytest.mark.parametrize("name", CLAUSE_NAMES)
def test_seam_binding_named_like_an_emitted_clause_name(tmp_path, name,
                                                        monkeypatch):
    unraisable = []
    monkeypatch.setattr(sys, "unraisablehook", unraisable.append)
    mod = _import(tmp_path, "gcb_seam", ".seam",
                  _seam_module(f"{name} = 5\n"))
    assert vars(mod)[name] == 5
    got = {g: _first(mod, g) for g in SEAM_PROBES}
    assert got == {g: want for g, (_, want) in SEAM_PROBES.items()}
    with pytest.raises(SystemExit):
        _first(mod, "t_halt")
    import gc
    gc.collect()
    assert [repr(u.exc_value) for u in unraisable] == []


def test_bare_query_with_a_nested_frozenset_beside_a_module_binding(tmp_path):
    """A query term is compiled against the module's namespace (the
    bare-query path); a nested ``frozenset`` value is rebuilt by an emitted
    constructor call."""
    mod = _import(tmp_path, "gcb_fs", ".seam",
                  "-module(@MOD@, [t(L, X)])\nfrozenset = 5\nt([X], X),\n")
    out = Var()
    got = [deref(out) for _ in S.solve(("t", [frozenset({1, 2})], out),
                                       module=mod)]
    assert got == [frozenset({1, 2})]


# ── module-level code (directives, import plumbing, templates) ──────────────


def test_atom_globals_before_a_functor_declaration(tmp_path):
    mod = _import(tmp_path, "gcb_glob", ".seam",
                  "-module(@MOD@, [t(X)])\n-private([globals])\n"
                  "-private([pt(a, b)])\nt(X) <- (X is 1)\n")
    assert _first(mod, "t") == 1


def test_atom_globals_beside_seam_escapes_and_a_constant(tmp_path):
    """``--goal``/``--term`` in Python-hosted code and a structured constant
    each hand the engine their module's namespace through an emitted
    ``globals()``."""
    mod = _import(tmp_path, "gcb_glob_seam", ".seam",
                  "-module(@MOD@, [p(A), t(X)])\n"
                  "-private([globals, pt(a, b)])\n"
                  "-constant_value(k, pt(1, 2))\n"
                  "t(X) <- (X is constant(k))\np(1),\n"
                  "def goal():\n    if --p(X): return X\n"
                  "def term(): return --p(1)\n")
    assert mod.goal() == 1
    assert mod.term() == ("p", 1)
    assert _first(mod, "t") == ("pt", 1, 2)


def test_functor_globals_after_a_use_module(tmp_path):
    mod = _import(tmp_path, "gcb_glob_pl", ".clausal",
                  ":- module(@MOD@, [t/1]).\n:- use_module(@DEP@, [dep/1]).\n"
                  "p(globals(x)).\nt(X) :- dep(X).\n:- end_module(@MOD@).\n")
    assert _first(mod, "t") == 2


def test_seam_binding_of___import___before_an_import(tmp_path):
    mod = _import(tmp_path, "gcb_imp", ".seam",
                  "-module(@MOD@, [t(X)])\n__import__ = 5\n"
                  "-import_from(@DEP@, [dep])\nt(X) <- dep(X)\n")
    assert _first(mod, "t") == 2


def test_seam_binding_of_ImportError_keeps_the_import_error(tmp_path):
    with pytest.raises(ImportError):
        _import(tmp_path, "gcb_ie", ".seam",
                "-module(@MOD@, [t(X)])\nImportError = 5\n"
                "-import_from(gcb_no_such_module, [foo])\nt(X) <- (X is 1)\n")


def test_seam_binding_of_NameError_keeps_the_missing_comma_hint(tmp_path):
    with pytest.raises(NameError, match="missing its trailing ','"):
        _import(tmp_path, "gcb_ne", ".seam",
                "-module(@MOD@, [t(X)])\nNameError = 5\ncopy([], [])\n")


def test_seam_bindings_do_not_reach_a_template_function(tmp_path):
    mod = _import(tmp_path, "gcb_tpl", ".seam",
                  "-module(@MOD@, [t(X)])\n"
                  "list = 5\ntuple = 5\nisinstance = 5\ntype = 5\n"
                  "TypeError = 5\nglobals = 5\n"
                  "@{}\ndef tpl(X):\n    {X}\n"
                  "@{}\ndef bad(X):\n    {X}\n"
                  "t(X) <- (X is 1)\n")
    out = mod.tpl(ast.Pass())
    assert [type(s) for s in out] == [ast.Pass]
    with pytest.raises(TypeError, match="expected AST node"):
        mod.bad(5)


# ── the emitted code itself names nothing a user can bind ───────────────────

#: Bare engine names generated code reached before the fix.
_ENGINE_BARE = {"is_var", "SegList", "SegString", "SegBytes", "StepGenerator",
                "ConcreteSeg", "VarSeg"}


def _global_loads(code, out):
    for ins in dis.get_instructions(code):
        if ins.opname in ("LOAD_GLOBAL", "LOAD_NAME"):
            out.add(ins.argval)
    for c in code.co_consts:
        if hasattr(c, "co_code"):
            _global_loads(c, out)


def test_compiled_clause_code_loads_no_bare_builtin(tmp_path, monkeypatch):
    import clausal.logic.cells as cells
    loads: set = set()
    real = cells.register_compiled_constants

    def spy(code):
        _global_loads(code, loads)
        return real(code)

    monkeypatch.setattr(cells, "register_compiled_constants", spy)
    pl = _import(tmp_path, "gcb_scan_pl", ".clausal",
                 _prolog_module("zz_unused", "dcg"))
    sm = _import(tmp_path, "gcb_scan_seam", ".seam", _seam_module(""))
    for g in PROLOG_PROBES:
        _first(pl, g)
    for g in SEAM_PROBES:
        _first(sm, g)
    assert loads, "the spy saw no generated code"
    bare = sorted(n for n in loads
                  if n in vars(builtins) or n in _ENGINE_BARE)
    assert not bare, f"bare names in generated code: {bare}"


def test_every_twin_is_bound_in_every_generated_code_namespace():
    from clausal import import_hook
    from clausal.logic.compiler.predicate import INJECTED_RUNTIME_BUILTINS
    from clausal.logic.generated_names import (
        GENERATED_CODE_BUILTINS, MODULE_CODE_BUILTINS)

    for twin, value in GENERATED_CODE_BUILTINS.items():
        assert twin.startswith("$")
        assert INJECTED_RUNTIME_BUILTINS[twin] is value
        assert import_hook.runtime_builtins[twin] is value
        assert import_hook._simple_ast_builtins[twin] is value
    for twin, value in MODULE_CODE_BUILTINS.items():
        assert twin.startswith("$")
        assert import_hook.runtime_builtins[twin] is value
        assert import_hook._simple_ast_builtins[twin] is value
        # module-level only: never in a clause's own table
        assert twin not in INJECTED_RUNTIME_BUILTINS
    # no bare alias rides along
    for twin in (*GENERATED_CODE_BUILTINS, *MODULE_CODE_BUILTINS):
        assert twin[1:] not in INJECTED_RUNTIME_BUILTINS
        assert twin[1:] not in import_hook.runtime_builtins


def test_the_seam_audit_does_not_treat_a_builtin_twin_as_an_engine_name():
    """The audit allows a ``$`` name as compiler-emitted engine plumbing; a
    Python builtin is not engine plumbing, so it stays a route there."""
    from clausal import seam_audit
    from clausal.logic.generated_names import (
        GENERATED_CODE_BUILTINS, MODULE_CODE_BUILTINS)
    engine = seam_audit._engine_names()
    assert not (set(GENERATED_CODE_BUILTINS) | set(MODULE_CODE_BUILTINS)) & engine


def test_module_level_code_names_no_bare_builtin(tmp_path, monkeypatch):
    """The module code the loaders compile -- import/registry plumbing, the
    ISO front end's import drops and constant lookups -- reaches builtins
    only through their ``$`` names.  None of these sources holds Python of
    its own, so any builtin name in the trees is the compiler's."""
    from clausal import import_hook
    trees = []

    def spy(source, filename, *args, **kwargs):
        # only this test's own files: a library module compiled on the way
        # (clpz) names its own predicates, ``sum`` among them
        if isinstance(source, ast.AST) and str(filename).startswith(
                str(tmp_path)):
            trees.append(source)
        return compile(source, filename, *args, **kwargs)

    monkeypatch.setattr(import_hook, "compile", spy, raising=False)
    (tmp_path / "gcb_cdep.clausal").write_text(
        ":- module(gcb_cdep, [fee/0, dep/1, other/1]).\n"
        ":- constant_number_units(fee, 5000, euro).\n"
        "dep(2).\nother(3).\n:- end_module(gcb_cdep).\n")
    sources = {
        # a constant imported from its owner: looked up in the owner module
        "gcb_mc_const.clausal": ":- module(gcb_mc_const, [t/2]).\n"
            ":- use_module(gcb_cdep, [fee/0]).\n"
            "t(N, U) :- constant_number_units(fee, N, U).\n"
            ":- end_module(gcb_mc_const).\n",
        # use_module(M, []) undoes the earlier import of M
        "gcb_mc_drop.clausal": ":- module(gcb_mc_drop, [t/1]).\n"
            ":- use_module(gcb_cdep, [dep/1]).\n:- use_module(gcb_cdep, []).\n"
            "t(1).\n:- end_module(gcb_mc_drop).\n",
        # a local definition of a library override drops that import
        "gcb_mc_over.clausal": ":- module(gcb_mc_over, [t/1, label/1]).\n"
            ":- use_module(library(clpz)).\nlabel(_).\nt(1).\n"
            ":- end_module(gcb_mc_over).\n",
        # the seam's constant lookup in the owner of an imported constant
        "gcb_ms_cown.seam": "-module(gcb_ms_cown, [fee_s])\n"
            "-import_from(united_states, [usd])\n"
            "-constant_number_units(fee_s, 11.00, usd)\n",
        "gcb_ms_cuse.seam": "-module(gcb_ms_cuse, [look/2])\n"
            "-import_from(gcb_ms_cown, [fee_s])\n"
            "look(N, U) <- constant_number_units(fee_s, N, U)\n",
        "gcb_ms_imp.seam": "-module(gcb_ms_imp, [t(X)])\n"
            "-import_from(gcb_cdep, [dep, other/1])\n"
            "-private([pt(a, b)])\nt(X) <- dep(X)\n",
    }
    sys.path.insert(0, str(tmp_path))
    try:
        for fname, text in sources.items():
            (tmp_path / fname).write_text(text)
            try:
                importlib.import_module(fname.split(".")[0])
            except Exception:   # noqa: BLE001 -- the TREE is what is checked
                pass
    finally:
        sys.path.remove(str(tmp_path))
    assert len(trees) >= len(sources), "the spy saw too few module trees"
    names = {n.id for t in trees for n in ast.walk(t)
             if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
    # positive control: the plumbing these sources exist for was emitted
    assert {"$globals", "$__import__", "$ImportError"} <= names
    bare = sorted(n for n in names if n in vars(builtins))
    assert not bare, f"bare builtin names in module code: {bare}"


def test_interactive_star_query_beside_a_session_binding_of_globals():
    """The interactive ``*(goal)`` wrapper hands the session namespace to
    the query through an emitted ``globals()``."""
    from clausal.import_hook import (
        _simple_ast_builtins, _star_query_input_transformer,
        _StarQueryTransformer)
    src = "".join(_star_query_input_transformer(["*(member(X, [1, 2]))\n"]))
    tree = _StarQueryTransformer().visit(ast.parse(src))
    ast.fix_missing_locations(tree)
    ns = dict(_simple_ast_builtins)
    ns["globals"] = "globals"
    exec(compile(tree, "<cell>", "exec"), ns)
