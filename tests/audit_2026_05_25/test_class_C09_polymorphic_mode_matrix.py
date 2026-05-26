"""C9 — Polymorphic builtin mode matrix.

12 findings (5 bug + 6 design-gap + 1 smell). The polymorphic list/higher-order
builtins handle str and list inputs separately, but the matrix of
input-type x mode reveals silent-failure modes (Seg* rejection),
silent-wrong-answers (split_with join), error-swallowing (sum_list),
and pervasive output-type asymmetry.

Findings tested here:
- F050 (bug) split_with join mode drops str parts
- F051 (bug) _as_items rejects ground SegList/SegString
- F052 (bug) sum_list/max_list/min_list swallow TypeError
- F053 (design-gap) length/replicate output always list
- F054 (design-gap) _seq_result asymmetry across 8 input shapes
- F055 (design-gap) transpose silently fails on str matrix
- F056 (design-gap) flatten str-as-atom equivalence break
- F061 (bug) Seg* silent failure across all higher_order predicates
- F062 (design-gap) list-of-1-char-str input != str output asymmetry
- F063 (design-gap) maplist/3, filter_map, group_by, sort_by always build list
- F072 (bug) Char-bound vs Type-bound mode mismatch in char_type
- F077 (smell) error-class confusion in char predicates
"""

import pytest


def test_F050_split_with_join_preserves_str_parts():
    """`split_with(Sep, J, Parts)` (join mode) with str elements in
    Parts must include those str elements in J. Currently the join
    branch at lists.py:630-642 gates ``joined.extend(p)`` on
    ``isinstance(p, list)`` only, so any str part is silently skipped.

    Concretely:
      - ``split_with(',', 'a,b,c', P)`` yields ``P = ['a','b','c']``
        (3 one-char strs).
      - Round-trip: ``split_with(',', J, ['a','b','c'])`` should give
        back a representation equivalent to ``'a,b,c'``. Instead it
        gives ``J = [',', ',']`` — every str part is dropped.

    Expected: the join direction round-trips (so the inverse of the
    split direction matches), e.g. ``J = 'a,b,c'`` or
    ``['a',',','b',',','c']`` — at minimum it must include the
    str parts, not silently drop them.
    Actual: ``J = [',', ',']`` — only the separators survive.
    """
    from clausal.logic.solve import call
    from clausal.logic.variables import Var, deref
    from tests.audit_2026_05_25._helpers import load_inline_clausal

    mod = load_inline_clausal(
        "c09_f050_split_with", "-module(t, [])\n"
    ).__dict__["$module"]

    # First confirm the split direction yields ['a','b','c'] (precondition).
    parts = Var()
    split_results = []
    for _ in call("split_with", ",", "a,b,c", parts, module=mod):
        split_results.append(deref(parts))
    assert split_results == [["a", "b", "c"]], (
        f"precondition: split_with(',', 'a,b,c', P) should yield "
        f"P = ['a','b','c']; got {split_results!r}"
    )

    # Now run the inverse direction (join mode) with the same parts.
    J = Var()
    join_results = []
    for _ in call("split_with", ",", J, ["a", "b", "c"], module=mod):
        join_results.append(deref(J))

    assert len(join_results) > 0, (
        f"split_with(',', J, ['a','b','c']) yielded 0 solutions; "
        f"the join direction should be deterministic with one answer."
    )
    j = join_results[0]
    # The bug: the join only contains the separators. Under any
    # reasonable round-trip / inverse-of-split contract the join
    # must include the 'a', 'b', 'c' parts.
    assert j != [",", ","], (
        f"split_with(',', J, ['a','b','c']) returned J = {j!r}; this is "
        f"the bug signature (only separators, all str parts dropped). "
        f"Expected J to include 'a', 'b', 'c' (e.g. ``'a,b,c'`` or "
        f"``['a',',','b',',','c']``)."
    )
    # Stronger: every str part should appear somewhere in J.
    flat = list(j) if not isinstance(j, str) else j
    for p in ("a", "b", "c"):
        assert p in flat, (
            f"split_with(',', J, ['a','b','c']) returned J = {j!r}; "
            f"expected part {p!r} to appear in J (round-trip with the "
            f"split direction's output)."
        )


def test_F051_as_items_accepts_ground_seg_inputs():
    """Every polymorphic list builtin that gates on ``_as_items`` must
    accept ground SegList / SegString as if they were the list / str
    they walk to.

    ``_as_items`` (lists.py:48-57) accepts only ``list`` / ``str`` and
    returns ``None`` for anything else. Ground ``SegList`` and
    ``SegString`` walk to a concrete list / str via ``__walk__`` and
    are semantically equivalent under the SegList / strings-as-lists
    contracts, but ``_as_items`` never tries the walk. Every gated
    builtin (~20 predicates) therefore silently yields zero solutions
    on a Seg* input.

    This test exercises a representative subset (append, in_, length,
    reverse, take) for both SegList and SegString.
    """
    from clausal.logic.solve import call
    from clausal.logic.variables import Var
    from clausal.terms import SegList, SegString, ConcreteSeg
    from tests.audit_2026_05_25._helpers import load_inline_clausal

    mod = load_inline_clausal(
        "c09_f051_seg_builtins", "-module(t, [])\n"
    ).__dict__["$module"]

    sl = SegList([ConcreteSeg(["a", "b", "c"])])
    ss = SegString(["abc"])
    # Preconditions: both ground. Under the Phase 2 Task 13 Liskov rule
    # (default output is list; promote to str when all elements are
    # 1-char strs), a SegList whose elements are all 1-char strs walks
    # to the equivalent str (``"abc"``) rather than the char list.
    assert sl.is_ground() and sl.__walk__() == "abc", (
        f"precondition: SegList([ConcreteSeg(['a','b','c'])]) should be "
        f"ground and walk to 'abc' (Liskov promote-to-str); got "
        f"is_ground={sl.is_ground()}, walk={sl.__walk__()!r}"
    )
    assert ss.is_ground() and ss.__walk__() == "abc", (
        f"precondition: SegString(['abc']) should be ground and walk to "
        f"'abc'; got is_ground={ss.is_ground()}, walk={ss.__walk__()!r}"
    )

    # Controls: list/str inputs succeed.
    R = Var()
    n_list_append = sum(
        1 for _ in call("append", ["a", "b", "c"], "d", R, module=mod)
    )
    R = Var()
    n_str_append = sum(1 for _ in call("append", "abc", "d", R, module=mod))
    assert n_list_append > 0 and n_str_append > 0, (
        f"controls: append(list/str, ...) should both succeed; got "
        f"list={n_list_append}, str={n_str_append}. If this fails the "
        f"fixture is broken."
    )

    # The bug: Seg* inputs silently fail across every gated builtin.
    R = Var()
    n_sl_append = sum(1 for _ in call("append", sl, "d", R, module=mod))
    R = Var()
    n_ss_append = sum(1 for _ in call("append", ss, "d", R, module=mod))
    assert n_sl_append > 0, (
        f"append(SegList(ground), 'd', R) yielded {n_sl_append} solutions; "
        f"expected >0 (matches the list/str control of {n_list_append}). "
        f"_as_items rejects SegList -> silent (_fail, DONE)."
    )
    assert n_ss_append > 0, (
        f"append(SegString(ground), 'd', R) yielded {n_ss_append} solutions; "
        f"expected >0 (matches the str control of {n_str_append}). "
        f"_as_items rejects SegString -> silent (_fail, DONE)."
    )

    # Cross-check: length, reverse, in_, take.
    N = Var()
    n_sl_len = sum(1 for _ in call("length", sl, N, module=mod))
    assert n_sl_len > 0, (
        f"length(SegList(ground), N) yielded {n_sl_len} solutions; "
        f"expected >0 (the ground SegList walks to a 3-element list)."
    )
    N = Var()
    n_ss_len = sum(1 for _ in call("length", ss, N, module=mod))
    assert n_ss_len > 0, (
        f"length(SegString(ground), N) yielded {n_ss_len} solutions; "
        f"expected >0 (the ground SegString walks to 'abc')."
    )

    V = Var()
    n_sl_in = sum(1 for _ in call("in_", V, sl, module=mod))
    assert n_sl_in > 0, (
        f"in_(V, SegList(ground)) yielded {n_sl_in} solutions; "
        f"expected >0 (member of the walked list)."
    )

    R = Var()
    n_sl_rev = sum(1 for _ in call("reverse", sl, R, module=mod))
    assert n_sl_rev > 0, (
        f"reverse(SegList(ground), R) yielded {n_sl_rev} solutions; "
        f"expected >0 (reverse of the walked list)."
    )

    T = Var()
    n_sl_take = sum(1 for _ in call("take", 2, sl, T, module=mod))
    assert n_sl_take > 0, (
        f"take(2, SegList(ground), T) yielded {n_sl_take} solutions; "
        f"expected >0 (prefix of the walked list)."
    )


def test_F052_reduction_predicates_dont_swallow_typeerror():
    """`sum_list/max_list/min_list` must not silently turn a TypeError
    from ``sum/max/min`` into ``(_fail, DONE)``. Either they should
    succeed on str input (concatenation / orderable chars) or raise a
    typed clausal error, but a silent zero-solution result is the
    indistinguishable-from-"no answer" worst case.

    Specifically:
      - ``sum_list("abc", S)`` currently yields 0 solutions because
        ``sum(("a","b","c"), 0)`` raises TypeError.
      - ``max_list([1, "a"], M)`` currently yields 0 solutions because
        ``max(1, "a")`` raises TypeError on mixed types.

    Both should be distinguishable from the legitimate "the list is
    empty / no candidate" failure (e.g. by raising a typed error).
    """
    from clausal.logic.solve import call
    from clausal.logic.variables import Var
    from clausal.logic.exceptions import LogicException
    from tests.audit_2026_05_25._helpers import load_inline_clausal

    mod = load_inline_clausal(
        "c09_f052_sum_list", "-module(t, [])\n"
    ).__dict__["$module"]

    # Control: sum_list on a numeric list works (precondition).
    S = Var()
    sums = []
    for _ in call("sum_list", [1, 2, 3], S, module=mod):
        from clausal.logic.variables import deref
        sums.append(deref(S))
    assert sums == [6], (
        f"control: sum_list([1,2,3], S) should yield [6]; got {sums!r}. "
        f"If this fails the fixture is broken."
    )

    # The bug: sum_list("abc", S) silently fails (TypeError swallowed).
    S = Var()
    try:
        n_str = sum(1 for _ in call("sum_list", "abc", S, module=mod))
    except LogicException:
        # Acceptable post-fix behaviour: a typed clausal exception is fine.
        return
    assert n_str > 0, (
        f"sum_list('abc', S) yielded {n_str} solutions silently; expected "
        f"either a defined sum (e.g. string concatenation = 'abc') or a "
        f"typed clausal exception, not indistinguishable-from-empty "
        f"failure (a TypeError swallowed into _fail)."
    )


def test_F053_output_mode_builders_respect_str_type_hint():
    """`length(L, 5)`, ``replicate(5, 'a', R)``, and
    ``same_length("abc", X)`` allocate Python lists unconditionally,
    even when adjacent arguments carry str typing.

    The output-mode builders at lists.py:210-215 (length),
    :589-598 (replicate), and :683-697 (same_length) have no
    input-type hint to switch on, so they hard-code list output.
    Under the string-preserving contract, callers with str-adjacent
    arguments should receive a str-typed hole / value.

    Concrete asserts:
      - ``replicate(5, 'a', R)``: every element is a 1-char str; the
        natural / lossless representation is ``'aaaaa'`` (str),
        not ``['a','a','a','a','a']``.
      - ``same_length("abc", X)``: the sibling arg is str, so the
        result shape should be str.
    """
    from clausal.logic.solve import call
    from clausal.logic.variables import Var, deref
    from tests.audit_2026_05_25._helpers import load_inline_clausal

    mod = load_inline_clausal(
        "c09_f053_output_mode", "-module(t, [])\n"
    ).__dict__["$module"]

    # replicate(5, 'a', R) — all 1-char strs, so str output is lossless.
    R = Var()
    rep_results = []
    for _ in call("replicate", 5, "a", R, module=mod):
        rep_results.append(deref(R))
        break
    assert len(rep_results) == 1, (
        f"precondition: replicate(5, 'a', R) should produce one solution; "
        f"got {len(rep_results)}."
    )
    rep = rep_results[0]
    assert isinstance(rep, str), (
        f"replicate(5, 'a', R) returned R = {rep!r} of type "
        f"{type(rep).__name__}; expected a str (every element is a "
        f"1-char str, so 'aaaaa' is the natural / lossless str shape). "
        f"The output-mode builder at lists.py:589-598 has no type hint "
        f"and unconditionally allocates a list."
    )

    # same_length("abc", X) — sibling arg is str, X should be str-shaped.
    # Under option A (input-type wins) the str-shaped fresh placeholder
    # is either a concrete ``str`` (if all elements are already bound)
    # or a ``SegString`` of fresh ``VarSeg`` holes (the natural
    # variable-bearing str shape — walks to a ``str`` once bound).
    from clausal.terms import SegString
    X = Var()
    same_results = []
    for _ in call("same_length", "abc", X, module=mod):
        same_results.append(deref(X))
        break
    assert len(same_results) == 1, (
        f"precondition: same_length('abc', X) should produce one "
        f"solution; got {len(same_results)}."
    )
    same = same_results[0]
    assert isinstance(same, (str, SegString)), (
        f"same_length('abc', X) returned X = {same!r} of type "
        f"{type(same).__name__}; expected a str-shaped value (a str "
        f"or a SegString of fresh VarSeg holes) since the sibling "
        f"argument is str. The output-mode builder at "
        f"lists.py:756-783 should pick the str shape per option A "
        f"(input-type wins)."
    )
    if isinstance(same, SegString):
        assert len(same.segments) == 3, (
            f"same_length('abc', X) returned a SegString with "
            f"{len(same.segments)} segments; expected 3 (one VarSeg per "
            f"sibling-str character)."
        )


# F054 — _seq_result symmetry across 8 input shapes. Parametrised.
# Under option A (input-type wins): str input → str output, list input →
# list output. The two halves must be symmetric in **shape** — the
# element values match, but list inputs never promote to str even when
# every element is a 1-char str.

@pytest.mark.parametrize(
    "label, args_list, args_str, expected_str_result, expected_list_result",
    [
        (
            "reverse",
            ("reverse", ["a", "b", "c"]),
            ("reverse", "abc"),
            "cba",
            ["c", "b", "a"],
        ),
        (
            "msort",
            ("msort", ["c", "b", "a"]),
            ("msort", "cba"),
            "abc",
            ["a", "b", "c"],
        ),
        (
            "sort",
            ("sort", ["a", "b", "c"]),
            ("sort", "abc"),
            "abc",
            ["a", "b", "c"],
        ),
        (
            "take",
            ("take", 2, ["a", "b", "c"]),
            ("take", 2, "abc"),
            "ab",
            ["a", "b"],
        ),
        (
            "drop",
            ("drop", 1, ["a", "b", "c"]),
            ("drop", 1, "abc"),
            "bc",
            ["b", "c"],
        ),
        (
            "list_to_set",
            ("list_to_set", ["a", "b", "c"]),
            ("list_to_set", "abc"),
            "abc",
            ["a", "b", "c"],
        ),
        (
            "subtract",
            ("subtract", ["a", "b", "c"], ["b"]),
            ("subtract", "abc", "b"),
            "ac",
            ["a", "c"],
        ),
        (
            "union",
            ("union", ["a", "b", "c"], ["d"]),
            ("union", "abc", "d"),
            "abcd",
            ["a", "b", "c", "d"],
        ),
    ],
    ids=[
        "reverse", "msort", "sort", "take", "drop",
        "list_to_set", "subtract", "union",
    ],
)
def test_F054_seq_result_input_type_wins(
    label, args_list, args_str, expected_str_result, expected_list_result
):
    """For every ``_seq_result``-gated predicate, the result shape
    tracks the *input shape*: str input → str output, list input →
    list output. The element values match across the two halves, but
    list-of-1-char-strs inputs are *not* silently promoted to str —
    that asymmetry was the F054 bug.

    Per the user's decision (option A — input-type wins), the two
    halves are symmetric in shape: each preserves its input's
    container type. This is parametrised over the 8 representative
    predicates from the ledger's matrix.
    """
    from clausal.logic.solve import call
    from clausal.logic.variables import Var, deref
    from tests.audit_2026_05_25._helpers import load_inline_clausal

    mod = load_inline_clausal(
        f"c09_f054_{label}", "-module(t, [])\n"
    ).__dict__["$module"]

    def _first(functor_and_args):
        out = Var()
        for _ in call(*functor_and_args, out, module=mod):
            return deref(out)
        return None

    list_result = _first(args_list)
    str_result = _first(args_str)

    assert list_result is not None and str_result is not None, (
        f"precondition: both {label}(list-input) and {label}(str-input) "
        f"should yield at least one solution; got list={list_result!r}, "
        f"str={str_result!r}."
    )

    # Str input → str output (control + the string-preserving half).
    assert str_result == expected_str_result, (
        f"{label}(str-input) should return {expected_str_result!r}; "
        f"got {str_result!r}."
    )
    assert isinstance(str_result, str), (
        f"{label}(str-input) returned {str_result!r} of type "
        f"{type(str_result).__name__}; expected str (str input → str "
        f"output under option A)."
    )

    # List input → list output. Same element values as the str half,
    # but kept in a Python list (no silent promotion).
    assert list_result == expected_list_result, (
        f"{label}(list-input) should return {expected_list_result!r}; "
        f"got {list_result!r}."
    )
    assert isinstance(list_result, list), (
        f"{label}(list-of-1-char-strs) returned {list_result!r} of type "
        f"{type(list_result).__name__}; expected a list (list input → "
        f"list output under option A — input-type wins, list-of-1-char- "
        f"strs is *not* silently promoted to str)."
    )


def test_F055_transpose_accepts_str_outer_matrix():
    """`transpose(M, T)` must not silently yield zero solutions on a
    str outer matrix. The outer guard at lists.py:704 demands
    ``isinstance(mat, list)`` — but inner rows go through
    ``_as_items``, so a list-of-str matrix works. The asymmetry is the
    silent failure on a str outer matrix.

    Either ``transpose("ab", T)`` should succeed (str-as-list-of-1-char
    interpretation gives ``[['a'], ['b']]`` — a 2x1 matrix) or it
    should raise a typed clausal exception calling out the contract.
    Silent zero-solutions on a logically-shaped input is the gap.
    """
    from clausal.logic.solve import call
    from clausal.logic.variables import Var
    from clausal.logic.exceptions import LogicException
    from tests.audit_2026_05_25._helpers import load_inline_clausal

    mod = load_inline_clausal(
        "c09_f055_transpose", "-module(t, [])\n"
    ).__dict__["$module"]

    # Control: list-of-list and list-of-str both work.
    T = Var()
    n_list = sum(1 for _ in call("transpose", [[1, 2], [3, 4]], T, module=mod))
    assert n_list > 0, (
        f"control: transpose([[1,2],[3,4]], T) should succeed; got "
        f"{n_list}. If this fails the fixture is broken."
    )
    T = Var()
    n_los = sum(1 for _ in call("transpose", ["ab", "cd"], T, module=mod))
    assert n_los > 0, (
        f"control: transpose(['ab','cd'], T) should succeed via "
        f"per-row _as_items; got {n_los}."
    )

    # The gap: str outer matrix silently yields zero solutions.
    T = Var()
    try:
        n_str = sum(1 for _ in call("transpose", "ab", T, module=mod))
    except LogicException:
        # Acceptable post-fix: a typed clausal exception is fine.
        return
    assert n_str > 0, (
        f"transpose('ab', T) yielded {n_str} solutions silently; expected "
        f"either a defined transpose (e.g. [['a'], ['b']] under the "
        f"str-as-list-of-1-char interpretation) or a typed clausal "
        f"exception identifying the contract. The current outer "
        f"``isinstance(mat, list)`` gate at lists.py:704 silently rejects "
        f"the str matrix while inner-row _as_items would accept it."
    )


def test_F056_flatten_str_list_equivalence():
    """Under the strings-as-lists contract, ``['ab']`` and
    ``[['a','b']]`` are equivalent values. ``flatten`` should preserve
    that equivalence — but at lists.py:277-301 it treats str as an
    atom (only recurses through ``isinstance(x, list)``), so
    ``flatten(['ab'], R)`` returns ``['ab']`` (1 element) while
    ``flatten([['a','b']], R)`` returns ``['a','b']`` (2 elements).

    Expected (string-preserving): both produce ``['a','b']`` (or both
    a 1-char-str list-like form). Actual: the str-wrapped form keeps
    str-as-atom semantics and the equivalence breaks at the most
    user-visible spot in lists.py.
    """
    from clausal.logic.solve import call
    from clausal.logic.variables import Var, deref
    from tests.audit_2026_05_25._helpers import load_inline_clausal

    mod = load_inline_clausal(
        "c09_f056_flatten", "-module(t, [])\n"
    ).__dict__["$module"]

    def _first(arg):
        R = Var()
        for _ in call("flatten", arg, R, module=mod):
            return deref(R)
        return None

    r_str_wrapped = _first(["ab"])
    r_list_wrapped = _first([["a", "b"]])

    assert r_str_wrapped is not None and r_list_wrapped is not None, (
        f"precondition: both flatten calls should yield a solution; "
        f"got str-wrapped={r_str_wrapped!r}, "
        f"list-wrapped={r_list_wrapped!r}."
    )
    # Under the strings-as-lists equivalence, these inputs are
    # equivalent so the outputs should be equivalent too.
    assert r_str_wrapped == r_list_wrapped, (
        f"flatten(['ab'], R) returned {r_str_wrapped!r} but "
        f"flatten([['a','b']], R) returned {r_list_wrapped!r}; under "
        f"the strings-as-lists equivalence these two inputs are the "
        f"same value, so the outputs must agree. The current "
        f"str-as-atom rule (lists.py:277-301) breaks the equivalence."
    )


def test_F061_higher_order_accepts_seg_inputs():
    """Every higher_order predicate must accept ground SegList /
    SegString inputs just like list / str. They all consume the
    shared ``_as_items`` helper from lists.py which rejects Seg*
    (root cause [[F051]]); each higher_order predicate then gates on
    ``items is None`` and silently yields zero solutions.

    This test exercises a representative subset (maplist/2,
    include/3, foldl/4, partition/4, group_by/3) for both SegList
    and SegString.
    """
    from clausal.logic.solve import call
    from clausal.logic.variables import Var
    from clausal.terms import SegList, SegString, ConcreteSeg
    from tests.audit_2026_05_25._helpers import load_inline_clausal

    src = """
-module(t, [is_vowel(_c), concat(_c, _a, _o), key_of(_c, _k)])
is_vowel(_c) <- in_(_c, ['a', 'e', 'i', 'o', 'u'])
concat(_c, _a, _o) <- atom_concat(_a, _c, _o)
key_of(_c, _k) <- If(in_(_c, ['a', 'e', 'i', 'o', 'u']), _k == 1, _k == 0)
"""
    mod = load_inline_clausal("c09_f061_higher_order_seg", src).__dict__[
        "$module"
    ]

    sl = SegList([ConcreteSeg(["a", "e", "i"])])
    ss = SegString(["aei"])
    # Phase 2 Task 13 Liskov rule: all-1-char-str SegList walks to str.
    assert sl.is_ground() and sl.__walk__() == "aei", (
        f"precondition: SegList ground/walks (Liskov promote-to-str); "
        f"got is_ground={sl.is_ground()}, walk={sl.__walk__()!r}"
    )
    assert ss.is_ground() and ss.__walk__() == "aei", (
        f"precondition: SegString ground/walks; got is_ground={ss.is_ground()}, "
        f"walk={ss.__walk__()!r}"
    )

    is_vowel = mod.module_dict["is_vowel"]
    concat = mod.module_dict["concat"]
    key_of = mod.module_dict["key_of"]

    # Control: list/str inputs succeed for maplist/2.
    ok_list = any(
        True for _ in call("maplist", is_vowel, ["a", "e", "i"], module=mod)
    )
    ok_str = any(True for _ in call("maplist", is_vowel, "aei", module=mod))
    assert ok_list and ok_str, (
        f"control: maplist(is_vowel, list/str) should succeed; got "
        f"list={ok_list}, str={ok_str}."
    )

    # The bug: Seg* inputs silently fail.
    ok_sl = any(True for _ in call("maplist", is_vowel, sl, module=mod))
    assert ok_sl, (
        f"maplist(is_vowel, SegList) returned {ok_sl}; expected True "
        f"(matches the list control). Silent failure via _as_items "
        f"None-rejection."
    )
    ok_ss = any(True for _ in call("maplist", is_vowel, ss, module=mod))
    assert ok_ss, (
        f"maplist(is_vowel, SegString) returned {ok_ss}; expected True "
        f"(matches the str control). Silent failure via _as_items "
        f"None-rejection."
    )

    # include, foldl, partition, group_by — all silent on Seg*.
    R = Var()
    n_sl_inc = sum(1 for _ in call("include", is_vowel, sl, R, module=mod))
    assert n_sl_inc > 0, (
        f"include(is_vowel, SegList, R) yielded {n_sl_inc} solutions; "
        f"expected >0."
    )
    R = Var()
    n_ss_fold = sum(
        1 for _ in call("foldl", concat, ss, "", R, module=mod)
    )
    assert n_ss_fold > 0, (
        f"foldl(concat, SegString, '', R) yielded {n_ss_fold} solutions; "
        f"expected >0."
    )
    Y, N = Var(), Var()
    n_sl_par = sum(
        1 for _ in call("partition", is_vowel, sl, Y, N, module=mod)
    )
    assert n_sl_par > 0, (
        f"partition(is_vowel, SegList, Y, N) yielded {n_sl_par} solutions; "
        f"expected >0."
    )
    R = Var()
    n_ss_grp = sum(
        1 for _ in call("group_by", key_of, ss, R, module=mod)
    )
    assert n_ss_grp > 0, (
        f"group_by(key_of, SegString, R) yielded {n_ss_grp} solutions; "
        f"expected >0."
    )


def test_F062_higher_order_input_type_wins():
    """For every higher_order predicate that derives ``was_str`` from
    ``isinstance(lst_val, str)`` (include, exclude, take_while,
    drop_while, span, partition, tfilter, tpartition), the result
    shape tracks the *input shape*: str input → str output, list
    input → list output.

    Per the user's decision (option A — input-type wins), the two
    halves are symmetric: each preserves its input's container type.
    List-of-1-char-strs inputs are *not* silently promoted to str —
    that asymmetry was the F062 bug.

    This test asserts on a representative subset: include/3 and
    partition/4 (two output args).
    """
    from clausal.logic.solve import call
    from clausal.logic.variables import Var, deref
    from tests.audit_2026_05_25._helpers import load_inline_clausal

    src = """
-module(t, [is_vowel(_c)])
is_vowel(_c) <- in_(_c, ['a', 'e', 'i', 'o', 'u'])
"""
    mod = load_inline_clausal(
        "c09_f062_higher_order_asym", src
    ).__dict__["$module"]
    is_vowel = mod.module_dict["is_vowel"]

    list_input = ["h", "e", "l", "l", "o"]
    str_input = "hello"

    # include — list keeps list, str preserves str (input-type wins).
    R = Var()
    list_inc = None
    for _ in call("include", is_vowel, list_input, R, module=mod):
        list_inc = deref(R)
        break
    R = Var()
    str_inc = None
    for _ in call("include", is_vowel, str_input, R, module=mod):
        str_inc = deref(R)
        break

    assert list_inc is not None and str_inc is not None, (
        f"precondition: include should succeed on both inputs; got "
        f"list_inc={list_inc!r}, str_inc={str_inc!r}."
    )
    assert str_inc == "eo", (
        f"include(is_vowel, 'hello', R) should return 'eo' (str); "
        f"got {str_inc!r}."
    )
    assert isinstance(str_inc, str), (
        f"include(is_vowel, 'hello', R) returned {str_inc!r} of type "
        f"{type(str_inc).__name__}; expected str (str input → str "
        f"output under option A)."
    )
    assert list_inc == ["e", "o"], (
        f"include(is_vowel, ['h','e','l','l','o'], R) should return "
        f"['e', 'o'] (list); got {list_inc!r}."
    )
    assert isinstance(list_inc, list), (
        f"include(is_vowel, ['h','e','l','l','o'], R) returned "
        f"{list_inc!r} of type {type(list_inc).__name__}; expected a "
        f"list (list input → list output under option A — input-type "
        f"wins, no silent promotion to str)."
    )

    # partition — same symmetry with two output args.
    Y, N = Var(), Var()
    list_par = None
    for _ in call("partition", is_vowel, list_input, Y, N, module=mod):
        list_par = (deref(Y), deref(N))
        break
    Y, N = Var(), Var()
    str_par = None
    for _ in call("partition", is_vowel, str_input, Y, N, module=mod):
        str_par = (deref(Y), deref(N))
        break

    assert list_par is not None and str_par is not None, (
        f"precondition: partition should succeed on both inputs; got "
        f"list_par={list_par!r}, str_par={str_par!r}."
    )
    assert str_par == ("eo", "hll"), (
        f"partition(is_vowel, 'hello', Y, N) should bind Y='eo', "
        f"N='hll'; got {str_par!r}."
    )
    assert isinstance(str_par[0], str) and isinstance(str_par[1], str), (
        f"partition(is_vowel, 'hello', Y, N) bound ({str_par[0]!r}, "
        f"{str_par[1]!r}); expected both str under option A."
    )
    assert list_par == (["e", "o"], ["h", "l", "l"]), (
        f"partition(is_vowel, ['h','e','l','l','o'], Y, N) bound "
        f"{list_par!r}; expected (['e','o'], ['h','l','l'])."
    )
    assert isinstance(list_par[0], list) and isinstance(list_par[1], list), (
        f"partition(is_vowel, ['h','e','l','l','o'], Y, N) bound "
        f"({list_par[0]!r}, {list_par[1]!r}); expected both list under "
        f"option A (list input → list output)."
    )


def test_F063_output_building_higher_order_preserves_str():
    """`maplist/3`, ``filter_map/3``, ``group_by/3``, ``sort_by/3``
    have no ``was_str``/``_seq_result`` thread — their result is
    hard-coded to a Python ``list`` even when the input is a str and
    every result element is a 1-char str (i.e. the case where str
    promotion would be unambiguous and lossless).

    Sibling of [[F053]] (output-mode builders always list). This test
    exercises maplist/3 and sort_by/3 on str input with 1-char-str
    outputs.
    """
    from clausal.logic.solve import call
    from clausal.logic.variables import Var, deref
    from tests.audit_2026_05_25._helpers import load_inline_clausal

    src = """
-module(t, [upcase(_c, _u), code_key(_c, _k)])
upcase(_c, _u) <- upcase_atom(_c, _u)
code_key(_c, _k) <- char_code(_c, _k)
"""
    mod = load_inline_clausal(
        "c09_f063_output_building", src
    ).__dict__["$module"]
    upcase = mod.module_dict["upcase"]
    code_key = mod.module_dict["code_key"]

    # maplist/3 on str — every result element is a 1-char str.
    R = Var()
    mp = None
    for _ in call("maplist", upcase, "abc", R, module=mod):
        mp = deref(R)
        break
    assert mp is not None, (
        f"precondition: maplist(upcase, 'abc', R) should succeed; got None."
    )
    # All elements are 1-char strs; "ABC" is the lossless str shape.
    assert isinstance(mp, str), (
        f"maplist(upcase, 'abc', R) returned {mp!r} of type "
        f"{type(mp).__name__}; expected a str (e.g. 'ABC') under the "
        f"string-preserving contract — every element of the result is "
        f"a 1-char str, so the str shape is lossless. These four "
        f"output-building predicates have no _seq_result thread."
    )

    # sort_by on str — same: result elements are 1-char strs.
    R = Var()
    sb = None
    for _ in call("sort_by", code_key, "cba", R, module=mod):
        sb = deref(R)
        break
    assert sb is not None, (
        f"precondition: sort_by(code_key, 'cba', R) should succeed; got None."
    )
    assert isinstance(sb, str), (
        f"sort_by(code_key, 'cba', R) returned {sb!r} of type "
        f"{type(sb).__name__}; expected a str (e.g. 'abc'). Hard-coded "
        f"list output: no _seq_result/was_str path."
    )


def test_F072_char_type_modes_agree_on_non_ascii():
    """`char_type/2` must be a well-defined relation across modes:
    if ``char_type('α', alpha)`` succeeds in test mode (Char bound),
    then the enumeration ``findall(C, char_type(C, alpha), L)`` (Type
    bound) must include ``'α'`` in L. Currently the Char-bound modes
    use full-Unicode classifiers (Py_UNICODE_ISALPHA / str.isalpha)
    while the Type-bound enumeration iterates ASCII-only pre-computed
    tables — so ``'α'`` is in the relation under one mode and not
    enumerated under the other.
    """
    from clausal.logic.builtins import get_builtin_dispatch
    from clausal.logic.variables import Var, Trail, deref
    from clausal.logic.trampoline import StepGenerator, solutions

    disp = get_builtin_dispatch("char_type", 2, None)

    # Test mode: char_type('α', alpha) — Char bound, Type bound.
    n_test = len(
        solutions(StepGenerator(disp, None, None, None, "α", "alpha", Trail()))
    )
    assert n_test == 1, (
        f"precondition: char_type('α', alpha) should succeed (Char-bound "
        f"mode supports full Unicode via Py_UNICODE_ISALPHA / "
        f"str.isalpha); got {n_test} solutions."
    )

    # Enumeration mode: findall(C, char_type(C, alpha), L) — Type bound.
    v = Var()
    chars_for_alpha = solutions(
        StepGenerator(disp, None, None, None, v, "alpha", Trail()),
        snapshot=lambda: deref(v),
    )
    assert "α" in chars_for_alpha, (
        f"findall(C, char_type(C, alpha), L) returned a list of "
        f"{len(chars_for_alpha)} entries; expected 'α' to appear since "
        f"char_type('α', alpha) succeeds in the Char-bound test mode. "
        f"The Type-bound enumeration iterates ASCII-only "
        f"_TYPE_TO_CHARS / type_to_chars tables, so the relation is "
        f"not consistent across modes."
    )


def test_F077_atom_concat_type_error_for_non_atom_bound_args():
    """`atom_concat/3` with fully-bound but non-atom-shaped args
    (e.g. a list ``[h,e,l]``, an int ``1``, a float ``3.14``) must
    raise ``type_error(atom, NonAtom)`` per ISO, not
    ``instantiation_error``. The current implementation infers
    boundness from ``_atom_to_str(...) is not None``, so a bound
    non-atom appears as "unbound" and falls through to the
    ``instantiation_error`` branch — masking real type errors from
    any ``catch(_, instantiation_error, _)`` handler.
    """
    from clausal.logic.builtins import get_builtin_dispatch
    from clausal.logic.variables import Var, Trail
    from clausal.logic.trampoline import StepGenerator, solutions
    from clausal.logic.exceptions import LogicException

    disp = get_builtin_dispatch("atom_concat", 3, None)

    # Each of these is fully-bound with a non-atom arg, so the correct
    # ISO error is type_error(atom, NonAtom).
    cases = [
        ("list-arg", (["h", "e", "l"], "lo", Var())),
        ("int-args", (1, 2, Var())),
        ("float-arg", (3.14, "x", Var())),
    ]
    for label, args in cases:
        try:
            solutions(
                StepGenerator(disp, None, None, None, *args, Trail())
            )
            pytest.fail(
                f"atom_concat({label}) returned without raising; "
                f"expected type_error(atom, NonAtom)."
            )
        except LogicException as e:
            msg = str(e)
            assert "type_error" in msg, (
                f"atom_concat({label}) raised {msg!r}; expected the "
                f"message to mention 'type_error' (ISO type_error(atom, "
                f"NonAtom)). Current implementation infers boundness "
                f"via _atom_to_str(...) is not None and falls through "
                f"to instantiation_error, masking real type errors."
            )
