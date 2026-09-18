"""Under ``-double_quotes(chars)`` a string IS its char list — everywhere.

ISO chars mode makes ``"ab"`` and ``[a, b]`` the SAME term, so every term
operation has to agree on it.  Ground unification and ``length/2`` already did
(the ``SegString`` / ``maybe_promote_to_str`` discipline in
``clausal/logic/runtime/_seg_helpers.py``); ``==`` did not, because its ground
fallback was Python's own ``==`` and ``str.__eq__`` answers ``False`` to a
list.  The seven rows below are the table from
``todo/string-is-its-char-list-in-eq-and-partial-list-unification-2026-09-08.md``,
plus the two negatives that keep the rule from over-firing: a string is its
CHAR list, not any list, and not a list of a different length.

``[H, *T]`` is Clausal's spelling of Prolog's ``[H|T]`` — a bare ``|`` in a
list display is a bitwise-or term on this branch, and the head linter says so.
"""
import os
import tempfile

from clausal.import_hook import _load_module
from clausal.logic.cells import chars
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref


def _load_inline(name: str, source: str):
    d = tempfile.mkdtemp()
    path = os.path.join(d, f"{name}.clausal")
    with open(path, "w") as fh:
        fh.write(source)
    return _load_module(name, path)


_SRC = (
    "-module(_chars_is_list, [\n"
    "    ground_unify, eq_self, length_two,\n"
    "    str_eq_list, list_eq_str, str_eq_quoted_chars,\n"
    "    partial_left(H, T), partial_right(H, T),\n"
    "    partial_left_pinned, partial_right_pinned,\n"
    "    eq_non_char_list, unify_wrong_length,\n"
    "    empty_eq_nil, char_atom_not_one_char_str,\n"
    "    eq_same_list, neq_str_list, neq_non_char_list,\n"
    "])\n"
    "-double_quotes(chars)\n"
    "-implicit_atoms\n"
    # ── rows 1-2: already true before the fix ──
    "ground_unify <- (\"ab\" is [a, b])\n"
    "eq_self <- (\"ab\" == \"ab\")\n"
    "length_two <- (length(\"ab\", 2))\n"
    # ── rows 3-5: structural equality across the two spellings ──
    "str_eq_list <- (\"ab\" == [a, b])\n"
    "list_eq_str <- ([a, b] == \"ab\")\n"
    "str_eq_quoted_chars <- (\"ab\" == ['a', 'b'])\n"
    # ── rows 6-7: a string against a PARTIAL list, both directions ──
    "partial_left(H, T) <- ([H, *T] is \"ab\")\n"
    "partial_right(H, T) <- (\"ab\" is [H, *T])\n"
    "partial_left_pinned <- ([H, *T] is \"ab\", H == a, T == [b])\n"
    "partial_right_pinned <- (\"ab\" is [H, *T], H == a, T == [b])\n"
    # ── negatives ──
    "eq_non_char_list <- (\"ab\" == [1, 2])\n"
    "unify_wrong_length <- (\"ab\" is [a, b, c])\n"
    "char_atom_not_one_char_str <- (a == \"a\")\n"
    # ── coherence ──
    "empty_eq_nil <- (\"\" == [])\n"
    "eq_same_list <- ([a, b] == [a, b])\n"
    "neq_str_list <- (\"ab\" != [a, b])\n"
    "neq_non_char_list <- (\"ab\" != [1, 2])\n"
)

_MOD = _load_inline("_chars_is_list", _SRC)
_M = _MOD.__dict__["$module"]


def _holds(name, *args):
    for _ in call(name, *args, module=_M):
        return True
    return False


def _first(name, n):
    args = [Var() for _ in range(n)]
    for _ in call(name, *args, module=_M):
        return [deref(a) for a in args]
    return None


class TestAlreadyAgreeing:
    """Rows 1-2 — the behaviour the rest of the table has to match."""

    def test_a_string_ground_unifies_with_its_char_list(self):
        assert _holds("ground_unify")

    def test_a_string_equals_itself(self):
        assert _holds("eq_self")

    def test_a_two_char_string_has_length_two(self):
        assert _holds("length_two")


class TestStructuralEquality:
    """Rows 3-5 — ``==`` across the two spellings of one term."""

    def test_a_string_equals_its_char_list(self):
        assert _holds("str_eq_list")

    def test_a_char_list_equals_the_string(self):
        assert _holds("list_eq_str")

    def test_a_string_equals_a_list_of_quoted_char_atoms(self):
        assert _holds("str_eq_quoted_chars")


class TestPartialListUnification:
    """Rows 6-7 — ``[H, *T]`` against a string, both directions.

    The tail comes back as the string ``"b"``, which IS ``[b]`` — the point of
    the ``==`` rows above is that the two spellings now compare equal, so the
    ``T == [b]`` the reporter wrote holds without the caller having to know
    which spelling the engine chose.
    """

    def test_a_partial_list_on_the_left_destructures_a_string(self):
        assert _first("partial_left", 2) == [("a",), chars("b")]

    def test_a_partial_list_on_the_right_destructures_a_string(self):
        assert _first("partial_right", 2) == [("a",), chars("b")]

    def test_the_head_and_tail_pin_as_the_char_list_spelling(self):
        assert _holds("partial_left_pinned")

    def test_the_head_and_tail_pin_in_the_other_direction_too(self):
        assert _holds("partial_right_pinned")


class TestTheRuleDoesNotOverFire:
    """A string is its CHAR list — not any list, and not a longer one."""

    def test_a_string_does_not_equal_a_list_of_ints(self):
        assert not _holds("eq_non_char_list")

    def test_a_string_does_not_unify_with_a_longer_char_list(self):
        assert not _holds("unify_wrong_length")

    def test_a_char_atom_is_not_the_one_char_string(self):
        # ``"a"`` is the one-element LIST [a]; the CELL ``a`` is not that list.
        assert not _holds("char_atom_not_one_char_str")

    def test_a_plain_list_still_equals_itself(self):
        assert _holds("eq_same_list")


class TestDisequalityAgrees:
    """``!=`` is the complement of ``==`` — it must not disagree with it."""

    def test_a_string_is_not_unequal_to_its_char_list(self):
        assert not _holds("neq_str_list")

    def test_a_string_is_unequal_to_a_non_char_list(self):
        assert _holds("neq_non_char_list")

    def test_the_empty_string_equals_the_empty_list(self):
        assert _holds("empty_eq_nil")


class TestPartialListUnificationAtTheTermLevel:
    """Rows 6-7 stated on the terms themselves, not through the surface.

    ``[H, *T]`` in a goal reaches the unifier as a ``SegList`` with a ``VarSeg``
    tail; the head binds to the first char atom and the tail to the REMAINDER
    AS A STRING, so repeated destructuring keeps working.  Both twins of
    ``_head_list_unify_input`` already agree on this (pinned in
    ``test_python_fallbacks.py::TestListUnifyCharTwinParity``) — these pins
    state the same contract for the core unifier, in both argument orders,
    which is the half of the todo the ``==`` fix does not touch.
    """

    def test_a_var_tailed_seglist_destructures_a_string(self):
        from clausal.logic.variables import Trail, unify
        from clausal.terms import ConcreteSeg, SegList, VarSeg
        h, t = Var(), Var()
        trail = Trail()
        assert unify(SegList([ConcreteSeg([h]), VarSeg(t)]), chars("ab"), trail)
        assert deref(h) == ("a",)
        assert deref(t) == chars("b")

    def test_a_string_destructures_a_var_tailed_seglist(self):
        from clausal.logic.variables import Trail, unify
        from clausal.terms import ConcreteSeg, SegList, VarSeg
        h, t = Var(), Var()
        trail = Trail()
        assert unify(chars("ab"), SegList([ConcreteSeg([h]), VarSeg(t)]), trail)
        assert deref(h) == ("a",)
        assert deref(t) == chars("b")

    def test_the_tail_of_a_one_char_string_is_the_empty_remainder(self):
        from clausal.logic.variables import Trail, unify
        from clausal.terms import ConcreteSeg, SegList, VarSeg
        h, t = Var(), Var()
        trail = Trail()
        assert unify(chars("a"), SegList([ConcreteSeg([h]), VarSeg(t)]), trail)
        assert deref(h) == ("a",)
        # The empty remainder is the empty string, which IS ``[]``.
        assert deref(t) == chars("")
        assert _holds("empty_eq_nil")

    def test_repeated_destructuring_walks_the_whole_string(self):
        from clausal.logic.variables import Trail, unify
        from clausal.terms import ConcreteSeg, SegList, VarSeg
        trail = Trail()
        rest, seen = chars("abc"), []
        for _ in range(3):
            h, t = Var(), Var()
            assert unify(SegList([ConcreteSeg([h]), VarSeg(t)]), rest, trail)
            seen.append(deref(h))
            rest = deref(t)
        assert seen == [("a",), ("b",), ("c",)]
        assert rest == chars("")
