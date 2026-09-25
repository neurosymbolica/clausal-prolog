"""A ``-dynamic`` declaration at an arity the name's clauses do not have.

``todo/done/zero-field-class-bound-to-another-aritys-row-crashes-call-2026-09-24.md``
and ``todo/done/dynamic-at-another-arity-moves-the-class-2026-09-17.md``:

    -dynamic(ping/2)          -dynamic(d/2)
    ping <- True              d(1),

used to leave the NAME's class bound to the declared arity's row, because
step 5 compiles the clause-less ``ping/2`` with no class and
``compile_predicate_*`` then resolved one by NAME (arity-blind) and
``_install`` re-bound it.  Every call to the clause arity then ran the other
arity's compiled function -- a raw Python ``TypeError``.

Both eras: the module-dict binding is the CLASS today, and a mangled handle
(``mint_predicate_handle``) after the flip.
"""
from __future__ import annotations

import pytest

from clausal.import_hook import _load_module
from clausal.logic.predicate import PredicateMeta, mint_predicate_handle
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref


def _load(tmp_path, name, src):
    p = tmp_path / f"{name}.clausal"
    p.write_text(src)
    return _load_module(name, str(p))


def _flip(mod, name):
    md = mod.__dict__
    assert isinstance(md[name], PredicateMeta), "fixture no longer binds a class"
    md[name] = mint_predicate_handle(md["$module"].db, name)


def _count(lm, name, arity):
    return sum(1 for _ in call(name, *[Var() for _ in range(arity)], module=lm))


@pytest.mark.parametrize("flipped", [False, True], ids=["class", "flipped"])
def test_zero_arity_clause_beside_a_dynamic_declaration_at_arity_two(
        tmp_path, flipped):
    mod = _load(tmp_path, f"dyn_ping_{int(flipped)}",
                "-dynamic(ping/2)\n\nping <- True\n")
    lm = mod.__dict__["$module"]
    cls = mod.__dict__["ping"]
    assert cls._row.key == ("ping", 0), "the class moved onto another row"
    if flipped:
        _flip(mod, "ping")
    assert _count(lm, "ping", 0) == 1
    # The call AT the declared arity: the flipped era answers it (no rows);
    # the class era still refuses it with PredicateArityMismatchError -- the
    # open todo/wrong-arity-call-still-refuses-in-two-places-2026-09-24.md
    # (solve.call Phase 5), not this defect.  The row is asserted directly.
    assert lm.db.is_dynamic("ping", 2)
    assert lm.db.row("ping", 2).clauses == []
    if flipped:
        assert _count(lm, "ping", 2) == 0


@pytest.mark.parametrize("flipped", [False, True], ids=["class", "flipped"])
def test_one_arity_fact_beside_a_dynamic_declaration_at_arity_two(
        tmp_path, flipped):
    mod = _load(tmp_path, f"dyn_d_{int(flipped)}", "-dynamic(d/2)\nd(1),\n")
    lm = mod.__dict__["$module"]
    assert mod.__dict__["d"]._row.key == ("d", 1)
    if flipped:
        _flip(mod, "d")
    x = Var()
    assert [deref(x) for _ in call("d", x, module=lm)] == [1]
    assert lm.db.row("d", 2).clauses == []
    if flipped:  # see the note above
        assert _count(lm, "d", 2) == 0


def test_a_runtime_assert_at_the_declared_arity_leaves_the_clause_arity_alone(
        tmp_path):
    """The RECOMPILE after an assertz resolves the class by name too."""
    mod = _load(tmp_path, "dyn_ping_assert",
                "-dynamic(ping/2)\n\nping <- True\n")
    lm = mod.__dict__["$module"]
    assert next(call("assertz", ("ping", 1, 2), module=lm), None) is not None
    assert len(lm.db.row("ping", 2).clauses) == 1
    # Force the lazy recompile the assert left behind: it installs through
    # ``_install`` with a class resolved BY NAME.
    assert lm.db.get_dispatch("ping", 2) is not None
    assert _count(lm, "ping", 0) == 1
    assert mod.__dict__["ping"]._row.key == ("ping", 0)
