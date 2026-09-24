"""F1 row 4: the ``.clausal`` test runner's descent resolves a failing goal's
predicate to its ROW, at the goal's own arity, and reads the defining module
off the row's database.

It used to read a ``PredicateMeta`` class out of the module dict -- ``_row``
for the clauses, ``__module__`` to find the defining module through
``sys.modules``.  After the retirement flip a binding is a mangled atom, so
that resolved nothing and the descent section would silently vanish from
every failing test.  Measured before the change over the house suite: the
row-based resolver agrees with the class-based one on 47 of 47 resolutions
(same row, same defining module, same source path).
"""

from __future__ import annotations

import sys
import textwrap
from types import SimpleNamespace

import clausal.import_hook  # noqa: F401 — installs the meta-path finder
from clausal.import_hook import _load_module
from clausal.logic.atoms import mangle
from clausal.logic.predicate import PredicateMeta
from clausal.pythonic_ast.nodes import Call
from clausal.terms import LoadName
from clausal.testing import _resolve_predicate, main


def _write(tmp_path, name, src):
    p = tmp_path / name
    p.write_text(textwrap.dedent(src).lstrip())
    return p


def _goal(name, *args):
    return Call(func=LoadName(name=name), args=list(args), kwargs=[])


def test_resolution_does_not_read_the_module_dict_bindings(tmp_path):
    """The post-flip shape: every predicate binding replaced by a mangled
    atom.  The resolver answers the same row either way."""
    _write(tmp_path, "r4flip.clausal", """
        r4_check(N) <- (N > 100, N < 0),
    """)
    sys.modules.pop("r4flip", None)
    lm = _load_module("r4flip", str(tmp_path / "r4flip.clausal")).__dict__["$module"]
    goal = _goal("r4_check", 5)

    before = _resolve_predicate(goal, lm, "caller.clausal")
    assert before is not None, "nothing resolved: nothing compared"
    assert before[0] is lm.db.row("r4_check", 1)

    flipped_md = {k: (mangle("r4flip", k) if isinstance(v, PredicateMeta)
                      else v) for k, v in lm.module_dict.items()}
    assert not isinstance(flipped_md["r4_check"], PredicateMeta)
    flipped = SimpleNamespace(db=lm.db, module_dict=flipped_md, name=lm.name)
    after = _resolve_predicate(goal, flipped, "caller.clausal")
    assert after is not None
    assert after[0] is before[0]


def test_the_goal_s_arity_picks_the_row(tmp_path):
    """Resolved at the goal's own arity: a call at another arity names no
    row, rather than borrowing the one row the name has."""
    _write(tmp_path, "r4arity.clausal", """
        r4_two(1, 2),
    """)
    sys.modules.pop("r4arity", None)
    lm = _load_module("r4arity", str(tmp_path / "r4arity.clausal")).__dict__["$module"]
    assert _resolve_predicate(_goal("r4_two", 1, 2), lm, "c")[0].key == ("r4_two", 2)
    assert _resolve_predicate(_goal("r4_two", 1), lm, "c") is None
    assert _resolve_predicate(_goal("r4_two", 1, 2, 3), lm, "c") is None


def test_a_cross_module_leaf_names_its_defining_file_after_the_owner_is_popped(
        capsys, tmp_path, monkeypatch):
    """The owner module is gone from ``sys.modules`` when the descent runs
    (the runner pops modules it loads).  The class route looked the defining
    module up there, missed, and fell back to the CALLER; the row knows its
    own database."""
    monkeypatch.syspath_prepend(str(tmp_path))
    sys.modules.pop("r4_popped_lib", None)
    _write(tmp_path, "r4_popped_lib.clausal", """
        -module(r4_popped_lib, [r4_lib_check(N)])

        r4_lib_check(N) <- (N > 100, N < 0)
    """)
    p = _write(tmp_path, "r4_use.clausal", """
        -import_from(r4_popped_lib, [r4_lib_check])

        test("cross-module, owner popped") <- (
            r4_lib_check(5)
        ),
    """)
    import clausal.testing as _t
    real_descend = _t._descend

    def descend_after_popping(*a, **k):
        sys.modules.pop("r4_popped_lib", None)
        return real_descend(*a, **k)

    monkeypatch.setattr(_t, "_descend", descend_after_popping)
    try:
        assert main([str(p)]) == 1
        out = capsys.readouterr().out
        assert "N > 100" in out
        assert "r4_popped_lib.clausal:" in out
    finally:
        sys.modules.pop("r4_popped_lib", None)
