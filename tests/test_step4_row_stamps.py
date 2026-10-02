"""Load step 4 -- what the clause install writes onto the ROW, whatever the
predicate's name is bound to.

Step 4 used to stamp ``row.source`` (the owner the mutation gate reads) only
when the module dict bound the functor to a ``PredicateMeta`` class.  After the
PredicateMeta retirement flip every binding is a mangled atom, so nothing
would be stamped, every row would read as unowned, and the gate's
clause-clobber refusal would pass every load.  These tests pin the stamp to
the row, with the non-class shape exercised TODAY: ``t5b_local_pred`` binds
``t5b_slot`` to an imported ATOM while defining a local ``t5b_slot/2``.

The signature tests pin where ``row.signature`` comes from.  It used to be
read off the class (``pred_cls._fields``), which nothing supplies once there
is no class.  It now comes from the rewriter's own record of each head's
field names -- the ``HeadFieldNames`` module item, a snapshot of
``EmbedTransformer._seen_functors`` -- stamped on the row the clause landed
on, whatever the name is bound to (operator ruling 2026-09-24;
implementation_plans/step4-signature-source-design-2026-09-24.md,
todo/done/step4-signature-comes-from-the-class-2026-09-24.md).  These tests
must stay GREEN through the PredicateMeta flip.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap

import pytest

import clausal.import_hook  # noqa: F401 — installs the meta-path finder
from clausal.import_hook import _load_module
from clausal.logic.atoms import mint, mangle
from clausal.logic.predicate import module_source_path
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref
from tests._suffix import SEAM


FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


@pytest.fixture(autouse=True)
def _forget_s4rs_modules():
    """Every ``s4rs_*`` module a test here loads from its ``tmp_path`` is
    removed from ``sys.modules`` afterwards, so no later test can resolve an
    import against a module whose file is gone."""
    before = set(sys.modules)
    yield
    for name in [n for n in sys.modules
                 if n.startswith("s4rs_") and n not in before]:
        sys.modules.pop(name, None)


def _write_module(tmp_path, name: str, source: str):
    path = tmp_path / f"{name}{SEAM}"
    path.write_text(textwrap.dedent(source).lstrip())
    return _load_module(name, str(path))


def test_a_predicate_whose_name_is_bound_to_an_atom_is_owned_by_its_load():
    """The post-flip shape, available today: the name is not a class."""
    module = _load_module("tests.fixtures.t5b_local_pred",
                          os.path.join(FIXTURES, "t5b_local_pred.clausal"))
    lm = module.__dict__["$module"]
    assert not isinstance(module.__dict__.get("t5b_slot"), type), (
        "the fixture no longer exercises a non-class binding")
    row = lm.db.row("t5b_slot", 2)
    assert row.clauses, "the local definition wrote no clauses"
    assert row.source == ("tests.fixtures.t5b_local_pred",
                          module_source_path(module.__dict__))


def test_every_clause_bearing_row_a_module_owns_has_an_owner(
        tmp_path, monkeypatch):
    """The population check: non-empty, covering BOTH binding shapes, and no
    clause-bearing owned row left unstamped.  ``s4rs_slot`` is imported as an
    atom, so the local ``s4rs_slot/2`` arrives with a non-class binding."""
    monkeypatch.syspath_prepend(str(tmp_path))
    _write_module(tmp_path, "s4rs_vocab", """
        -module(s4rs_vocab, [s4rs_slot])
    """)
    module = _write_module(tmp_path, "s4rs_owned", """
        -import_from(s4rs_vocab, [s4rs_slot])

        s4rs_a(1),
        s4rs_a(2),
        s4rs_b(X, Y) <- (s4rs_a(X), s4rs_a(Y)),
        s4rs_slot(7, 1),
    """)
    # The two binding shapes post-W4b-2d: a predicate HANDLE (``s4rs_a``; it
    # was a class) and a plain imported ATOM (``s4rs_slot``).
    from clausal.logic.atoms import is_mangled
    slot = module.__dict__.get("s4rs_slot")
    assert isinstance(slot, str) and not is_mangled(slot), (
        "s4rs_slot is bound to a predicate: the atom path is not exercised")
    assert module.__dict__.get("s4rs_a") == mangle("s4rs_owned", "s4rs_a")
    db = module.__dict__["$module"].db
    bearing = {k for k in db.owned_keys() if db.row(*k).clauses}
    assert {("s4rs_a", 1), ("s4rs_b", 2), ("s4rs_slot", 2)} <= bearing
    assert {k for k in bearing if db.row(*k).source is None} == set()
    assert {db.row(*k).source[0] for k in bearing} == {"s4rs_owned"}


def test_an_undeclared_predicate_carries_the_field_names_of_its_head(tmp_path):
    """Permanent, and must stay GREEN at the flip.  ``define_predicate``
    registers no signature here (a cell head has anonymous variables), and
    the ``(r, s)`` does NOT come from the class any more: step 4 reads it off
    the rewriter's ``HeadFieldNames`` module item."""
    module = _write_module(tmp_path, "s4rs_sig", """
        s4rs_pair(1, 2),
        s4rs_swap(R, S) <- s4rs_pair(S, R),
    """)
    db = module.__dict__["$module"].db
    assert db.row("s4rs_swap", 2).signature == ("r", "s"), (
        "the head's field names did not reach the row: step 4 stamps them "
        "from the HeadFieldNames module item, not from the class")


def _signature_3(lm, name, arity):
    """What ``signature/3`` answers, as a tuple of names, or None."""
    names = Var()
    for _ in call("signature", mint(name), arity, names, module=lm):
        return tuple(str(n) for n in deref(names))
    return None


def test_the_first_registration_wins_and_signature_3_reports_it(tmp_path):
    """Precedence, as the rewriter settles it: a declaration beats a clause,
    the first clause beats a later one, a ``-dynamic`` placeholder loses to
    the first real head, a repeated variable is numbered, a non-variable
    argument is ``arg_<i>``, and a DCG head carries its two list slots."""
    module = _write_module(tmp_path, "s4rs_multi", """
        -double_quotes(atom)
        -private([s4rs_decl(Q, W)])
        -dynamic(s4rs_dyn/2)

        s4rs_first(A, B) <- (A == B),
        s4rs_first(X, Y) <- (X == Y),
        s4rs_decl(E, F) <- (E == F),
        s4rs_dyn(P, Q2) <- (P == Q2),
        s4rs_dup(Z, Z),
        s4rs_const(1, V) <- (V == 1),
        s4rs_greet(W) >> ["hi", W]
    """)
    lm = module.__dict__["$module"]
    expected = {
        ("s4rs_first", 2): ("a", "b"),
        ("s4rs_decl", 2): ("Q", "W"),
        ("s4rs_dyn", 2): ("p", "q2"),
        ("s4rs_dup", 2): ("z", "z_1"),
        ("s4rs_const", 2): ("arg_0", "v"),
        ("s4rs_greet", 3): ("w", "dcg0", "dcg1"),
    }
    got = {k: lm.db.row(*k).signature for k in expected}
    assert got == expected
    assert {k: _signature_3(lm, *k) for k in expected} == expected


def test_an_edcg_predicate_carries_its_hidden_argument_names(tmp_path):
    """EDCG hidden arguments are the one surviving source keyword-goal form,
    and ``-edcg_pred`` never calls ``declare_functor`` -- so their names come
    ONLY from this stamp.  The keyword call below needs them."""
    module = _write_module(tmp_path, "s4rs_edcg", """
        -edcg_acc(counter, _x, _in, _out, {_out == _in + _x})
        -edcg_pred(s4rs_bump, 0, [counter])

        s4rs_bump >> ([1] // counter)

        s4rs_run(COUNT) <- s4rs_bump(_edcg_counter_in=0, _edcg_counter_out=COUNT)
    """)
    lm = module.__dict__["$module"]
    assert lm.db.row("s4rs_bump", 2).signature == (
        "_edcg_counter_in", "_edcg_counter_out")
    n = Var()
    assert [deref(n) for _ in call("s4rs_run", n, module=lm)] == [1]


@pytest.mark.parametrize("binding", ["mangled_handle", "absent"])
def test_the_stamp_does_not_depend_on_what_the_name_is_bound_to(
        tmp_path, monkeypatch, binding):
    """BOTH ERAS.  Rebind every clause-bearing name to something that is not
    a class -- the post-flip mangled handle, or nothing at all -- just before
    ``compile_module`` runs, and the rows still get their head names."""
    import clausal.logic.compiler_v2 as cv2
    original = cv2.compile_module
    seen = []

    def compile_module(predicate_nodes, module_items, module_dict,
                       module_name="<module>"):
        if module_name == "s4rs_eras":
            for name in ("s4rs_pair", "s4rs_swap"):
                # Since W4b-3 slice 5 the module body binds its own handle
                # (``$declare_head``), not a class: "mangled_handle" below
                # rebinds the same value, "absent" removes it.
                assert module_dict.get(name) == mangle(module_name, name)
                if binding == "mangled_handle":
                    module_dict[name] = mangle(module_name, name)
                else:
                    del module_dict[name]
                seen.append(name)
        return original(predicate_nodes, module_items, module_dict,
                        module_name)

    monkeypatch.setattr(cv2, "compile_module", compile_module)
    module = _write_module(tmp_path, "s4rs_eras", """
        s4rs_pair(1, 2),
        s4rs_swap(R, S) <- s4rs_pair(S, R),
    """)
    assert seen == ["s4rs_pair", "s4rs_swap"], "the rebinding never ran"
    db = module.__dict__["$module"].db
    assert db.row("s4rs_pair", 2).signature == ("arg_0", "arg_1")
    assert db.row("s4rs_swap", 2).signature == ("r", "s")


def test_a_name_bound_to_an_imported_atom_still_gets_its_signature(
        tmp_path, monkeypatch):
    """Operator ruling 2026-09-24: stamp EVERY row this load writes clauses
    to, like ``record_clause_source``.  Both names are imported ATOMS (not
    classes) with a same-named local predicate; before the ruling they got no
    signature at all."""
    module = _load_module("tests.fixtures.t5b_local_pred",
                          os.path.join(FIXTURES, "t5b_local_pred.clausal"))
    assert not isinstance(module.__dict__.get("t5b_slot"), type)
    lm = module.__dict__["$module"]
    assert lm.db.row("t5b_slot", 2).signature == ("arg_0", "arg_1")
    assert _signature_3(lm, "t5b_slot", 2) == ("arg_0", "arg_1")

    monkeypatch.syspath_prepend(str(tmp_path))
    _write_module(tmp_path, "s4rs_avocab", """
        -module(s4rs_avocab, [s4rs_aslot])
    """)
    owned = _write_module(tmp_path, "s4rs_aowned", """
        -import_from(s4rs_avocab, [s4rs_aslot])

        s4rs_aslot(7, 1),
    """)
    assert not isinstance(owned.__dict__.get("s4rs_aslot"), type)
    assert owned.__dict__["$module"].db.row("s4rs_aslot", 2).signature == (
        "arg_0", "arg_1")


@pytest.mark.parametrize("schema, use, functor", [
    ("fnmismatch_schema", "fnmismatch_use", "fnm_verdict"),
    ("impord_fact_vocab", "impord_declare_then_import_fact",
     "impord_fverdict"),
])
def test_declare_then_import_then_define_is_refused_so_it_stamps_nothing(
        schema, use, functor):
    """The only disagreements the class source had (design §3): the module
    declares ``f(STATUS, CITATIONS)``, imports ``f`` from a module that only
    DECLARES it (the class carries unseated ``arg_i`` placeholders), then
    defines it.  That shape is the dropped "vocabulary-implements" idiom
    (operator ruling 2026-09-24,
    todo/done/vocabulary-implements-steal-has-no-row-form-2026-09-24.md), so
    it is now refused at step 3d, before step 4 stamps anything.

    This used to pin that the row is labelled by the declaration, not the
    class.  No legal shape remains where a step-4 row is bound to a FOREIGN
    placeholder class: every clause write through an ``-import_from`` is now
    refused (the clobber refusal or this one).  What stays pinned: the load
    is refused with THAT refusal, and the exporter's row is not stamped with
    the importer's names -- the declaration never leaks onto the owner."""
    owner = _load_module(f"tests.fixtures.{schema}",
                         os.path.join(FIXTURES, f"{schema}.clausal"))
    with pytest.raises(SyntaxError) as exc_info:
        _load_module(f"tests.fixtures.{use}",
                     os.path.join(FIXTURES, f"{use}.clausal"))
    assert f"only declares {functor}/2" in " ".join(str(exc_info.value).split())
    owner_row = owner.__dict__["$module"].db.row(functor, 2)
    if owner_row is not None:
        assert not owner_row.clauses
        assert owner_row.signature != ("STATUS", "CITATIONS")


_CACHE_PROBE = """
import sys
import clausal.import_hook as ih
ran = []
_orig = ih.PredicateLoader.source_to_code
def _spy(self, *a, **k):
    ran.append(1)
    return _orig(self, *a, **k)
ih.PredicateLoader.source_to_code = _spy
sys.path.insert(0, sys.argv[1])
import s4rs_cached
db = s4rs_cached.__dict__["$module"].db
print(repr((bool(ran), db.row("s4rs_cswap", 2).signature)))
"""


def test_the_signature_survives_a_bytecode_cache_hit(tmp_path):
    """On a cache hit ``source_to_code`` never runs; the module items are
    re-derived by re-parsing the source.  The second process must not have
    rewritten anything (the positive control that the cache WAS hit) and must
    still stamp the same names."""
    (tmp_path / f"s4rs_cached{SEAM}").write_text(textwrap.dedent("""
        s4rs_cpair(1, 2),
        s4rs_cswap(R, S) <- s4rs_cpair(S, R),
    """).lstrip())
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # A cache that is never written can never be hit: clear the switch
    # that stops CPython writing it, whatever the calling environment says.
    env = {k: v for k, v in os.environ.items()
           if k != "PYTHONDONTWRITEBYTECODE"}

    def run():
        out = subprocess.run(
            [sys.executable, "-c", _CACHE_PROBE, str(tmp_path)],
            cwd=repo, env=env, capture_output=True, text=True, timeout=300)
        assert out.returncode == 0, out.stderr
        return out.stdout.strip().splitlines()[-1]

    assert run() == "(True, ('r', 's'))"
    cached = list((tmp_path / "__pycache__").glob("s4rs_cached.*.pyc"))
    assert cached, "the first load wrote no bytecode cache file"
    assert run() == "(False, ('r', 's'))"


def test_reify_source_does_not_render_the_head_field_names_item():
    """A compile-time worklist, not something the author wrote."""
    from clausal.reflection import reify_source
    terms = reify_source(textwrap.dedent("""
        -module(s4rs_reify, [s4rs_r(A)])
        s4rs_r(1),
        s4rs_q(X) <- s4rs_r(X),
    """).lstrip())
    assert "HeadFieldNames" not in repr(terms)
    assert "arg_0" not in repr(terms)
