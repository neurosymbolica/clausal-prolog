"""C2 — Non-deterministic SegList/SegString unification collapsed to first split.

2 bug findings: every split of ``[*A, *B]`` against a list or a text is an
answer.

Findings tested here:
- F015 SegList: every split of a two-hole partial list
- F016 SegString: the same against text

Where the compiler sees the pattern (a clause head, an ``is`` goal) it
enumerates the splits itself.  Where the pattern reaches ``unify`` as a
value, unify is deterministic and binds the first split.  The fix of
2026-05-25 exposed the other splits by calling unify again on the same
trail, keyed by the target's content; that lost answers (``member/2`` over
equal lists) and was removed on 2026-10-08.  The value case waits on a
nondeterministic pending-goal channel.
"""

import pytest

from clausal.logic.cells import chars
from clausal.logic.solve import solve
from clausal.logic.variables import Var, deref
from clausal.testing import load_clausal_module

_SRC = """\
split_is(T, A, B) <- ([*A, *B] is T)
split_head([*A, *B], A, B),
via_head(T, A, B) <- split_head(T, A, B)
via_value(T, A, B) <- (P is [*A, *B], P is T)
"""

_LIST = [1, 2, 3]
_LIST_SPLITS = [([], [1, 2, 3]), ([1], [2, 3]), ([1, 2], [3]), ([1, 2, 3], [])]
_TEXT_SPLITS = [(chars(""), chars("abc")), (chars("a"), chars("bc")),
                (chars("ab"), chars("c")), (chars("abc"), chars(""))]


@pytest.fixture(scope="module")
def mod(tmp_path_factory):
    p = tmp_path_factory.mktemp("c02") / "c02.seam"
    p.write_text(_SRC)
    return load_clausal_module(p)


def _splits(mod, goal, target):
    a, b = Var(), Var()
    return [(deref(a), deref(b)) for _ in solve((goal, target, a, b), mod)]


def _walked(pairs):
    w = lambda x: x.__walk__() if hasattr(x, "__walk__") else x
    return [(w(a), w(b)) for a, b in pairs]


@pytest.mark.parametrize("goal", ["split_is", "via_head"])
def test_F015_seglist_compiled_pattern_enumerates_all_splits(mod, goal):
    assert _walked(_splits(mod, goal, list(_LIST))) == _LIST_SPLITS


@pytest.mark.parametrize("goal", ["split_is", "via_head"])
def test_F016_segstring_compiled_pattern_enumerates_all_splits(mod, goal):
    assert _walked(_splits(mod, goal, chars("abc"))) == _TEXT_SPLITS


@pytest.mark.xfail(strict=True, reason="ledger F015: a pattern unified as a "
                   "value binds its first split; needs a pending-goal channel")
def test_F015_seglist_value_pattern_enumerates_all_splits(mod):
    assert _walked(_splits(mod, "via_value", list(_LIST))) == _LIST_SPLITS


@pytest.mark.xfail(strict=True, reason="ledger F016: a pattern unified as a "
                   "value binds its first split; needs a pending-goal channel")
def test_F016_segstring_value_pattern_enumerates_all_splits(mod):
    assert _walked(_splits(mod, "via_value", chars("abc"))) == _TEXT_SPLITS
