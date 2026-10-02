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

Handle era (W4b-2d flip): the module-dict binding is a mangled handle
(``mint_predicate_handle``) and the row it resolves to at the clause arity
must be the clause arity's row.  The class arm and the stand-in ``_flip``
helper are gone: the load itself flips now, and a stand-in that flips
nothing would have made the second arm a silent copy of the first.
"""
from __future__ import annotations

import pytest

from clausal.import_hook import _load_module
from clausal.logic.predicate import (
    mint_predicate_handle, resolve_predicate_row)
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref
from tests._suffix import SEAM


def _load(tmp_path, name, src):
    p = tmp_path / f"{name}{SEAM}"
    p.write_text(src)
    return _load_module(name, str(p))


def _assert_handle_on_row(mod, name, arity):
    """The load bound *name* to its handle, and that handle resolves to the
    clause arity's row -- the handle-era form of "the class stayed on its
    own row"."""
    md = mod.__dict__
    lm = md["$module"]
    assert md[name] == mint_predicate_handle(lm.db, name), (
        "the load did not bind the handle")
    row = resolve_predicate_row(md[name], arity=arity, db=lm.db)
    assert row is not None and row.key == (name, arity)
    assert row is lm.db.row(name, arity)


def _count(lm, name, arity):
    return sum(1 for _ in call(name, *[Var() for _ in range(arity)], module=lm))


def test_zero_arity_clause_beside_a_dynamic_declaration_at_arity_two(
        tmp_path):
    mod = _load(tmp_path, "dyn_ping_1",
                "-dynamic(ping/2)\n\nping <- True\n")
    lm = mod.__dict__["$module"]
    _assert_handle_on_row(mod, "ping", 0)
    assert _count(lm, "ping", 0) == 1
    # The call AT the declared arity answers it (no rows).
    assert lm.db.is_dynamic("ping", 2)
    assert lm.db.row("ping", 2).clauses == []
    assert _count(lm, "ping", 2) == 0


def test_one_arity_fact_beside_a_dynamic_declaration_at_arity_two(tmp_path):
    mod = _load(tmp_path, "dyn_d_1", "-dynamic(d/2)\nd(1),\n")
    lm = mod.__dict__["$module"]
    _assert_handle_on_row(mod, "d", 1)
    x = Var()
    assert [deref(x) for _ in call("d", x, module=lm)] == [1]
    assert lm.db.row("d", 2).clauses == []
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
    _assert_handle_on_row(mod, "ping", 0)
