"""``assertz``/``retract`` through an ALIASED ``-import_from`` land on the
owner's row, in both eras, owner loaded or popped.

``todo/done/assertz-through-an-aliased-import-raises-existence-error-2026-09-24.md``:
``row60_alias_user`` imports ``alias(gd_p, gd_loc)``; its body's
``gd_loc(X)`` is a CELL spelled with the OWNER's name (``("gd_p", X)`` --
``terms_to_ast._functor_spelling``, so the owner's clauses can match it), and
the assert looked ``gd_p/1`` up in the importer, where only ``gd_loc`` is
bound and adopted: ``existence_error(procedure, gd_p/1)``.

Handle era (W4b-2d flip): the load binds ``gd_loc`` to the OWNER's handle
itself (ruling D1), so the class arm and the stand-in re-binding in
``_setup`` are gone; ``_setup`` asserts the binding instead, so the arm can
never run on a binding nothing set.
"""
from __future__ import annotations

import os
import sys

import pytest

import clausal.import_hook  # noqa: F401 -- installs the meta-path finder
from clausal import cell_args, cell_functor
from clausal.import_hook import _load_module
from clausal.logic.exceptions import LogicException
from clausal.logic.predicate import mint_predicate_handle
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref
from tests._suffix import SEAM

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
_OWNER = "tests.fixtures.gate_dyn_owner"
_ALIAS = "_alias_assert_user"

_SRC = """\
-dynamic(gd_loc/1)
-module(_alias_assert_user, [gd_loc_add(X), gd_loc_del(X), gd_loc_call(X)])
-import_from(tests.fixtures.gate_dyn_owner, [alias(gd_p, gd_loc)])

gd_loc_add(X) <- assertz(gd_loc(X))
gd_loc_del(X) <- retract(gd_loc(X))
gd_loc_call(X) <- call(gd_loc(X))
"""


@pytest.fixture
def aliased(tmp_path):
    saved = sys.modules.pop(_OWNER, None)
    sys.modules.pop(_ALIAS, None)
    owner = _load_module(_OWNER, os.path.join(FIXTURES, "gate_dyn_owner.clausal"))
    src = tmp_path / f"{_ALIAS}{SEAM}"
    src.write_text(_SRC)
    user = _load_module(_ALIAS, str(src))
    yield owner, user
    sys.modules.pop(_ALIAS, None)
    if saved is not None:
        sys.modules[_OWNER] = saved
    else:
        sys.modules.pop(_OWNER, None)


_ERAS = [pytest.param(p, id=f"{'popped' if p else 'loaded'}")
         for p in (False, True)]


def _owner_answers(owner):
    x = Var()
    return sorted(deref(x) for _ in call("gd_p", x,
                                         module=owner.__dict__["$module"]))


def _setup(owner, user, owner_popped):
    lm = user.__dict__["$module"]
    assert lm.db.adopted_row("gd_loc", 1) is not None
    assert lm.db.adopted_row("gd_p", 1) is None, "keyed by the importer's name"
    # Ruling D1, done by the load: an imported name binds the OWNER's handle.
    assert user.__dict__["gd_loc"] == mint_predicate_handle(
        owner.__dict__["$module"].db, "gd_p"), "the load did not flip gd_loc"
    if owner_popped:
        sys.modules.pop(_OWNER, None)
    return lm


@pytest.mark.parametrize("owner_popped", _ERAS)
def test_assertz_through_the_alias_lands_on_the_owner(
        aliased, owner_popped):
    owner, user = aliased
    lm = _setup(owner, user, owner_popped)
    assert next(call("gd_loc_add", 42, module=lm), None) is not None
    assert _owner_answers(owner) == [1, 42]
    assert lm.db.row("gd_loc", 1).clauses == [], "wrote the importer's twin"


@pytest.mark.parametrize("owner_popped", _ERAS)
def test_retract_through_the_alias_removes_from_the_owner(
        aliased, owner_popped):
    owner, user = aliased
    lm = _setup(owner, user, owner_popped)
    assert next(call("gd_loc_add", 42, module=lm), None) is not None
    assert next(call("gd_loc_del", 1, module=lm), None) is not None
    assert _owner_answers(owner) == [42]


@pytest.mark.parametrize("owner_popped", _ERAS)
def test_call_of_the_alias_cell_answers_from_the_owner(
        aliased, owner_popped):
    """``call(gd_loc(X))`` hands call/1 the same owner-spelled cell; it used
    to answer NOTHING, silently (higher_order resolves through the same
    ``_find_pred_cls``)."""
    owner, user = aliased
    lm = _setup(owner, user, owner_popped)
    x = Var()
    assert [deref(x) for _ in call("gd_loc_call", x, module=lm)] == [1]


def test_an_unrelated_cell_is_still_refused(aliased):
    """The reverse lookup is by the adopted row's OWN key, so a cell naming
    something nobody imported is still refused -- as the write to a static
    procedure it is (ruling R7, 2026-09-28)."""
    _owner, user = aliased
    lm = user.__dict__["$module"]
    with pytest.raises(LogicException) as exc:
        next(call("assertz", ("gd_nothing", 1), module=lm), None)
    assert cell_functor(cell_args(exc.value.term)[0]) == "permission_error"


def test_the_reverse_spelling_refuses_to_guess_between_two_owners():
    from clausal.logic.database import Database

    a, b, imp = Database(), Database(), Database()
    row_a, row_b = a.row("p", 1, create=True), b.row("p", 1, create=True)
    assert imp.adopt_row("pa", 1, row_a)
    assert imp.adopted_spelling("p", 1) == "pa"
    assert imp.adopt_row("pa2", 1, row_a)          # same row twice: still one
    assert imp.adopted_spelling("p", 1) in ("pa", "pa2")
    assert imp.adopt_row("pb", 1, row_b)            # a second owner's p/1
    assert imp.adopted_spelling("p", 1) is None
    assert imp.adopted_spelling("p", 2) is None


def test_two_aliased_imports_that_swap_names_do_not_recurse_forever():
    """``alias(a, b)`` from one owner and ``alias(b, a)`` from another, with
    neither local name bound in the importer: ``_find_pred_cls``'s
    reverse-spelling fallback maps a -> b -> a -> ...  It used to recurse
    until RecursionError; a spelling already tried now answers nothing."""
    from types import SimpleNamespace
    from clausal.logic.builtins.database_ops import _find_pred_cls
    from clausal.logic.database import Database

    own_a, own_b, imp = Database(), Database(), Database()
    assert imp.adopt_row("b", 1, own_a.row("a", 1, create=True))  # alias(a, b)
    assert imp.adopt_row("a", 1, own_b.row("b", 1, create=True))  # alias(b, a)
    assert imp.adopted_spelling("a", 1) == "b"
    assert imp.adopted_spelling("b", 1) == "a"
    md = {"$module": SimpleNamespace(db=imp)}
    assert _find_pred_cls("a", 1, md) is None
    assert _find_pred_cls("b", 1, md) is None


def test_the_alias_redirect_leaves_a_row_this_database_owns_alone():
    """roborev LOW (2026-09-25): the owner-spelling -> alias redirect in
    ``_find_pred_cls`` and ``_adopted_row_named_by`` checked only the module
    dict.  A database that OWNS a row under the owner's spelling (``p/1``,
    say one assertz created, with no binding) while importing another
    module's ``p`` as ``alias(p, q)`` must keep its own ``p``: no redirect to
    the import."""
    from types import SimpleNamespace
    from clausal.logic.atoms import mangle
    from clausal.logic.builtins.database_ops import (
        _adopted_row_named_by, _find_pred_cls,
    )
    from clausal.logic.database import Database

    owner = Database({"__name__": "redir_owner"})
    imp = Database({"__name__": "redir_imp"})
    assert imp.adopt_row("q", 1, owner.row("p", 1, create=True))   # alias(p, q)
    imp.row("p", 1, create=True)                                      # its OWN p/1
    assert imp.owns("p", 1) and imp.adopted_spelling("p", 1) == "q"
    handle = mangle("redir_owner", "p")
    md = {"$module": SimpleNamespace(db=imp), "q": handle}
    imp.module_dict.update(md)
    assert _adopted_row_named_by(imp, handle, "p", 1) is None
    assert _find_pred_cls("p", 1, md) is None
    # ... and with no row of its own the redirect still answers the import.
    imp2 = Database({"__name__": "redir_imp2"})
    assert imp2.adopt_row("q", 1, owner.row("p", 1))
    assert _adopted_row_named_by(imp2, handle, "p", 1) is owner.row("p", 1)
