"""W4b-3 slice 5: the rewriter emits no ``class <functor>(metaclass=
$PredicateMeta)`` block.

A predicate name a ``.clausal`` file defines or declares is bound, while the
module body runs, straight to its HANDLE (``$declare_head``,
``clausal.logic.predicate.declare_head``), and the field names a head is
built against live in the namespace's ``$predicate_heads`` record until
step 4 stamps them on the row.  These tests pin:

* the POSITIVE CONTROL: loading a module creates zero ``PredicateMeta``
  classes, and the rewriter's output names no ``PredicateMeta``;
* the pooled-atom override: a head whose spelling another, earlier module
  declared as an ATOM still becomes this module's predicate (the old class
  block's ``type(x) is str and x == 'x'`` arm), for the defining module and
  for a module importing it, while the declaring module keeps its atom;
* the construction diagnostic still names the declaration site.
"""
from __future__ import annotations

import ast
import sys
import textwrap

import pytest

import clausal.import_hook  # noqa: F401 -- installs the meta-path finder
from clausal.import_hook import _load_module
from clausal.logic import predicate as predicate_mod
from clausal.logic.atoms import mangle
from clausal.logic.predicate import ClausalTermConstructionError
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref


def _write(tmp_path, name, src):
    path = tmp_path / name
    path.write_text(textwrap.dedent(src).lstrip())
    return str(path)


def _load(tmp_path, name, src):
    sys.modules.pop(name, None)
    return _load_module(name, _write(tmp_path, f"{name}.clausal", src))


def _metaclass_instances():
    """Every live CLASS whose metaclass is a predicate metaclass -- one
    named ``PredicateMeta`` (a class statement against a stale copy), or
    the placeholder the C slot holds (``_NoPredicateClasses``).  Since W4b-3
    slice 7 deleted the class this must stay empty: the census counts by
    walking the live objects, because there is no ``__new__`` left to hook."""
    import gc
    placeholder = predicate_mod._NoPredicateClasses
    return [o.__name__ for o in gc.get_objects()
            if isinstance(o, type) and (isinstance(o, placeholder)
                                        or type(o).__name__ == "PredicateMeta")]


@pytest.fixture
def class_census():
    """The predicate-metaclass instances created while the fixture is live
    (a gc census before and after; see ``_metaclass_instances``)."""
    before = set(_metaclass_instances())
    created: list = []
    yield created
    created.extend(sorted(set(_metaclass_instances()) - before))


def _answers(module, name, arity):
    out = []
    args = [Var() for _ in range(arity)]
    for _ in call(name, *args, module=module):
        out.append(tuple(deref(a) for a in args))
    return out


# ── The positive control ─────────────────────────────────────────────────

_EVERY_SHAPE = """
    -module(s5_shapes, [fib/2, pt(X, Y), exported(A), count3(_counter0, _counter)])
    -private([red])
    -dynamic(ghost/1)
    -edcg_acc(counter, _x, _in, _out, {_out == _in + _x})
    -edcg_pred(inc, 0, [counter])
    -edcg_pred(count3, 0, [counter])

    fib(0, 0),
    fib(N, F) <- (N > 0, eval_(N - 1, M), fib(M, G), eval_(G + 1, F))
    exported(red),
    flag,
    sorted(X) <- exported(X)
    inc >> ([1] // counter)
    count3 >> (inc, inc, inc)
"""


def test_loading_a_module_creates_no_predicate_class(tmp_path, monkeypatch,
                                                      class_census):
    monkeypatch.syspath_prepend(str(tmp_path))
    mod = _load(tmp_path, "s5_shapes", _EVERY_SHAPE)
    # POSITIVE CONTROL first: the load really ran and the predicates answer,
    # so a zero below is a census of a real load, not of nothing.
    f = Var()
    assert [deref(f) for _ in call("fib", 5, f, module=mod)] == [5]
    assert _answers(mod, "exported", 1) == [("red",)]
    assert _answers(mod, "flag", 0) == [()]
    assert _answers(mod, "sorted", 1) == [("red",)]
    assert _answers(mod, "ghost", 1) == []
    n = Var()
    assert [deref(n) for _ in call("count3", 0, n, module=mod)] == [3]
    assert mod.fib == mangle("s5_shapes", "fib")
    assert _metaclass_instances() == [], (
        f"predicate metaclass instances are alive: {_metaclass_instances()}")


def test_the_metaclass_census_sees_an_instance_when_there_is_one():
    """POSITIVE CONTROL for ``_metaclass_instances``: a class made with the
    placeholder metaclass (the only predicate metaclass left) is counted,
    so the zero above is a census of something that can be non-zero."""
    placeholder = predicate_mod._NoPredicateClasses
    probe = placeholder("s7_census_probe", (), {})
    try:
        assert "s7_census_probe" in _metaclass_instances()
    finally:
        del probe


def test_the_rewriter_output_names_no_predicate_class(tmp_path):
    from clausal.tools.dump_transformed import dump_source
    source = dump_source(_write(tmp_path, "s5_dump.clausal", _EVERY_SHAPE))
    tree = ast.parse(source.replace("$", "_D_"))
    classes = [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
    assert "$declare_head(" in source          # positive control: the new statement
    assert classes == []
    assert "PredicateMeta" not in source


# ── The pooled-atom override (a head spelled like another module's atom) ─

def test_a_head_spelled_like_an_earlier_module_s_atom_is_this_module_s_predicate(
        tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(tmp_path))
    atom_side = _load(tmp_path, "s5_atom_side", """
        -module(s5_atom_side, [s5_shared, tag(X)])
        tag(s5_shared),
    """)
    # The atom is pooled process-wide now: a LATER module's namespace starts
    # with ``s5_shared`` bound to the atom -- the shape the override is for.
    from clausal.import_hook import predicate_builtins
    assert predicate_builtins.get("s5_shared") == "s5_shared"

    definer = _load(tmp_path, "s5_definer", """
        -module(s5_definer, [s5_shared/1, use_it/1])
        s5_shared(X) <- eval_(41 + 1, X)
        use_it(Y) <- s5_shared(Y)
    """)
    importer = _load(tmp_path, "s5_importer", """
        -import_from(s5_definer, [s5_shared])
        again(Y) <- s5_shared(Y)
    """)

    assert definer.s5_shared == mangle("s5_definer", "s5_shared")
    assert _answers(definer, "s5_shared", 1) == [(42,)]
    assert _answers(definer, "use_it", 1) == [(42,)]
    assert importer.s5_shared == mangle("s5_definer", "s5_shared")
    assert _answers(importer, "again", 1) == [(42,)]
    # The declaring module's atom is untouched: still the atom, still data.
    assert atom_side.s5_shared == "s5_shared"
    assert _answers(atom_side, "tag", 1) == [("s5_shared",)]


def test_a_head_spelled_like_an_atom_the_same_file_declares_is_the_predicate(
        tmp_path, monkeypatch):
    """Phenomenon A in one file: the -private atom line runs first, the
    clause's declaration wins the binding."""
    monkeypatch.syspath_prepend(str(tmp_path))
    mod = _load(tmp_path, "s5_same_file", """
        -private([s5_both])
        s5_both(1),
        s5_both(2),
    """)
    assert mod.s5_both == mangle("s5_same_file", "s5_both")
    assert _answers(mod, "s5_both", 1) == [(1,), (2,)]


# ── The declaration site ─────────────────────────────────────────────────

def test_the_declaration_site_reaches_the_row(tmp_path, monkeypatch):
    """The class's ``_registered_at`` used to travel to ``row.declared_at``
    at step 4 (``_bind_row``); the ``$predicate_heads`` record carries it
    now, and the row is stamped from there."""
    monkeypatch.syspath_prepend(str(tmp_path))
    mod = _load(tmp_path, "s5_site", """
        -module(s5_site, [pair(Left, Right)])

        pair(1, 2),
    """)
    row = mod.__dict__["$module"].db.row("pair", 2)
    assert row is not None and row.declared_at is not None
    assert row.declared_at[0].endswith("s5_site.clausal")
    assert row.declared_at[1] == 1


# ── Follow-ups (operator answers + review, 2026-09-25) ───────────────────

def test_the_arity_conflict_message_names_the_declaration_not_a_class(
        tmp_path, monkeypatch):
    """There is no class to be "minted with N fields" any more: the message
    says what is true -- the name is DECLARED with N field(s)."""
    monkeypatch.syspath_prepend(str(tmp_path))
    with pytest.raises(SyntaxError) as info:
        _load(tmp_path, "s5_conflict", """
            s5c_p(1),
            s5c_p(1, 2),
        """)
    text = str(info.value)
    assert "conflicts with the declaration of s5c_p/1" in text
    assert "s5c_p is declared with 1 field(s) (arg_0)" in text
    assert "class is minted" not in text


def test_a_circular_import_still_lists_what_the_partial_module_defines(
        tmp_path, monkeypatch):
    """The one reachable case of ``import_diagnostics._defined_names`` on a
    module whose load has not reached the flip: a CIRCULAR import reads the
    partially initialised module mid-exec.  Its names are handles by then,
    answered from the loading record (the class era listed the classes)."""
    monkeypatch.syspath_prepend(str(tmp_path))
    _write(tmp_path, "s5_circ_a.clausal", """
        s5ca_one(1),
        s5ca_two(1, 2),
        -import_from(s5_circ_b, [s5cb_pred])
        s5ca_other(X) <- s5cb_pred(X)
    """)
    _write(tmp_path, "s5_circ_b.clausal", """
        -import_from(s5_circ_a, [s5ca_missing])
        s5cb_pred(1),
    """)
    for name in ("s5_circ_a", "s5_circ_b"):
        monkeypatch.delitem(sys.modules, name, raising=False)
    try:
        with pytest.raises(ImportError) as info:
            __import__("s5_circ_a")
        text = str(info.value)
        assert "partially initialized module 's5_circ_a'" in text   # the case
        assert "s5_circ_a does define: s5ca_one/1, s5ca_two/2" in text
    finally:
        for name in ("s5_circ_a", "s5_circ_b"):
            sys.modules.pop(name, None)


def test_importlib_reload_rereads_the_body_without_duplicating_clauses(
        tmp_path, monkeypatch):
    """``importlib.reload`` re-runs a module body in the SAME namespace.  On
    main (0c645200) it raised ``TypeError: cannot build a clause head for p:
    the predicate handle ... names nothing its owner module knows``; the
    body's declarations are fresh per run now, so it reloads -- the same
    answers, no duplicated clauses, and an edited file's change is seen."""
    import importlib
    import os
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.delitem(sys.modules, "s5_rl_mod", raising=False)
    path = _write(tmp_path, "s5_rl_mod.clausal", """
        -module(s5_rl_mod, [s5rl_p(X)])
        s5rl_p(1),
        s5rl_p(2),
    """)
    try:
        mod = importlib.import_module("s5_rl_mod")
        assert _answers(mod, "s5rl_p", 1) == [(1,), (2,)]
        mod = importlib.reload(mod)
        assert _answers(mod, "s5rl_p", 1) == [(1,), (2,)]
        assert len(mod.__dict__["$module"].db.clauses_for("s5rl_p", 1)) == 2
        # An edited source (mtime bumped so the bytecode cache cannot serve the
        # old code) is what the reload reads.
        _write(tmp_path, "s5_rl_mod.clausal", """
            -module(s5_rl_mod, [s5rl_p(X)])
            s5rl_p(1),
            s5rl_p(2),
            s5rl_p(3),
        """)
        st = os.stat(path)
        os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 10**9))
        mod = importlib.reload(mod)
        assert _answers(mod, "s5rl_p", 1) == [(1,), (2,), (3,)]
    finally:
        sys.modules.pop("s5_rl_mod", None)


def test_a_clause_at_the_console_is_not_an_internal_error():
    """``ClausalConsole``'s namespace carries ``__name__`` again (the default
    ``code.InteractiveConsole`` gives it), so a clause typed there fails as
    it did on main -- no clause store at the console -- and not with an
    ``internal:`` error from ``$declare_head``."""
    import contextlib
    import io
    from clausal.python_repl import ClausalConsole
    console = ClausalConsole()
    assert console.locals["__name__"] == "__console__"
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        console.runsource("s5con_f(a),")
    assert "internal" not in err.getvalue()
    assert "$define_predicate" in err.getvalue()     # main's error, unchanged
    assert console.locals["s5con_f"] == mangle("__console__", "s5con_f")


def test_a_loading_handle_answers_its_arity_even_before_its_owner_resolves():
    """``predicate_arities_for`` reads the loading record FIRST, as
    ``is_declared_predicate[_name]`` do, so the three agree while the owner
    module cannot be resolved (review, 2026-09-25)."""
    from clausal.logic.predicate import (
        begin_loading_declarations, end_loading_declarations,
        is_declared_predicate, is_declared_predicate_name,
        predicate_arities_for, PREDICATE_HEADS_KEY,
    )
    ns = {"__name__": "s5_unresolved_owner"}
    begin_loading_declarations(ns)
    handle = mangle("s5_unresolved_owner", "s5u_p")
    ns[PREDICATE_HEADS_KEY]["s5u_p"] = (("a", "b"), None)
    ns["s5u_p"] = handle
    try:
        assert "s5_unresolved_owner" not in sys.modules
        assert is_declared_predicate_name(handle)
        assert is_declared_predicate(handle, arity=2)
        assert predicate_arities_for(handle) == {2}
    finally:
        end_loading_declarations(ns)
    assert predicate_arities_for(handle) == set()


@pytest.mark.parametrize("name", [None, ""])
def test_a_namespace_with_no_usable_name_is_refused_at_run_time(name):
    """``$declare_head`` in a namespace whose ``__name__`` is missing or
    falsy raises a RUNTIME error (it fires while a body runs, where a
    ``SyntaxError`` would have no file or line), with the user wording."""
    from clausal.logic.predicate import declare_head
    ns = {"__d": declare_head}
    if name is not None:
        ns["__name__"] = name
    with pytest.raises(RuntimeError, match="no usable __name__") as info:
        exec("__d('s5nn_p', ('a',))", ns)
    assert info.type is RuntimeError
    assert "non-empty module-level __name__" in str(info.value)
