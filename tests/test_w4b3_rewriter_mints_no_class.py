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
from clausal.logic.predicate import ClausalTermConstructionError, PredicateMeta
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref


def _write(tmp_path, name, src):
    path = tmp_path / name
    path.write_text(textwrap.dedent(src).lstrip())
    return str(path)


def _load(tmp_path, name, src):
    sys.modules.pop(name, None)
    return _load_module(name, _write(tmp_path, f"{name}.clausal", src))


@pytest.fixture
def class_census(monkeypatch):
    """Every ``PredicateMeta`` class created while the fixture is live."""
    created = []
    original = PredicateMeta.__new__

    def counting_new(mcs, name, bases, namespace, **kwargs):
        created.append(name)
        return original(mcs, name, bases, namespace, **kwargs)

    monkeypatch.setattr(PredicateMeta, "__new__", counting_new)
    return created


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
    assert class_census == [], (
        f"the load created PredicateMeta classes: {class_census}")


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
