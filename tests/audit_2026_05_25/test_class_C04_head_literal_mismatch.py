"""C4 — Head-pattern literal mismatch (rule heads with str literals).

1 bug finding (F046), now FIXED by the narrow head_match.py change: str is
split out of the match_value tuple at head_match.py and emitted as a wildcard
capture + a same-type-short-circuit unify guard (`_scap == "abc" or
unify(_scap, "abc", trail)`), mirroring the list-literal path. This routes the
comparison through unify() so a char-list caller honours the strings-as-lists
contract, while keeping the fast `==` path for same-type str callers.

Background on the original bug: quux("abc") <- (real_body) used to compile to
match_value(constant("abc")). Python's match uses == for match_value, so a caller
quux(['a','b','c']) silently failed despite the strings-as-lists contract.
Only str-literal heads in rules with non-True bodies hit this — facts
(including <- (True) rules) dodge it via the _normalize_dataclass_fact
elaborator at database.py:332-361, and list-literal heads already went through
the wildcard-capture + runtime-unify path.

This test guards the highest-blast-radius fix in the audit. It composes with
F095 (first-arg indexing canonicalisation, already landed), which buckets
str-literal heads and char-list callers together.

Findings tested here:
- F046 (bug, fixed) — Rules with str-literal heads now match char-list callers.
- F048 (inherited) — Compound str-literal heads inherit the same fix.

bytes is deliberately excluded (no strings-as-lists contract); the bytes
regression test below locks in that a bytes-literal head still matches a bytes
caller and is unaffected by this change.
"""

from clausal.logic.atoms import mint
from clausal.logic.solve import call
from tests.audit_2026_05_25._helpers import load_inline_clausal

def test_F046_str_head_no_longer_matches_charlist_caller():
    """RETIRED by P3-1 Task 5 (\u00a71b). All 8 cross-call combinations
    (fact/rule x str-head/list-head x str-caller/list-caller): the 4
    SAME-TYPE combinations still return exactly 1 solution; the 4
    CROSS-TYPE combinations (the ones this test used to call
    "strings-as-lists test") now return 0 -- the str-literal head's
    unify guard (`_scap0 == 'abc' or unify(_scap0, 'abc', trail)`) still
    runs, but `unify()` itself no longer accepts a list on the other
    side of a str.

    Registers four clauses via inline .clausal source:
    - Fact `foo("abc")` — handled by the elaborator dodge
    - Fact `bar(['a', 'b', 'c'])` — handled by elaboration + list path
    - Rule `quux("abc") <- (helper(1))` — the (retired) F046 surface
    - Rule `zorp(['a','b','c']) <- (helper(1))` — list-literal head
    - Plus `helper(1)` so the rule bodies succeed

    1. foo("abc") — control (fact, str-head, str-caller) -> 1
    2. foo(['a','b','c']) — cross-type, RETIRED (fact, str-head, list-caller) -> 0
    3. bar("abc") — cross-type, RETIRED (fact, list-head, str-caller) -> 0
    4. bar(['a','b','c']) — control (fact, list-head, list-caller) -> 1
    5. quux("abc") — control (rule, str-head, str-caller) -> 1
    6. quux(['a','b','c']) — cross-type, RETIRED (rule, str-head, list-caller) -> 0
    7. zorp("abc") — cross-type, still 1 (rule, list-head, str-caller) -> 1
    8. zorp(['a','b','c']) — control (rule, list-head, list-caller) -> 1

    Call #6 — quux(['a','b','c']) — was the F046 bug surface (0 solutions
    before the historical fix, 1 after it, back to 0 post-retirement): a
    str-literal RULE HEAD compiles to a wildcard-capture + `unify()` guard
    (head_match.py), and `unify()` itself no longer accepts a list where
    it holds a str, so this specific combination is retired.

    Call #7 — zorp("abc") — is DIFFERENT and NOT retired: a list-literal
    RULE HEAD compiles through a SEPARATE mechanism
    (`_head_list_unify_input` in `clausal/logic/runtime/list_unify.py`),
    which destructures a str target NATIVELY (via Python str indexing/
    slicing, matching one char per list-pattern element) rather than by
    calling the generic `unify()` with the whole str against the whole
    list. That native str-as-a-sequence destructuring is the OLDER,
    separate "strings-as-lists" contract §1b does not touch (it is not
    built on the retired do_unify cross-type branch) — see
    ``tests/test_dcg.py``'s cons-rule-retirement-vs-DCG audit note for the
    fuller rationale. Empirically re-verified against the rebuilt
    extension (2026-09-04): foo/bar/quux's cross-type calls all go to 0,
    zorp("abc") alone stays at 1.
    """
    # Register fixtures inline.
    source = """\
foo("abc"),
bar(['a', 'b', 'c']),

helper(1),

quux("abc") <- (helper(1))
zorp(['a', 'b', 'c']) <- (helper(1))
"""
    mod = load_inline_clausal("c04_f046_heads", source).__dict__["$module"]

    # Collect all 8 solution counts.
    n_foo_str = sum(1 for _ in call("foo", mint("abc"), module=mod))
    n_foo_list = sum(1 for _ in call("foo", [mint("a"), mint("b"), mint("c")], module=mod))
    n_bar_str = sum(1 for _ in call("bar", mint("abc"), module=mod))
    n_bar_list = sum(1 for _ in call("bar", [mint("a"), mint("b"), mint("c")], module=mod))
    n_quux_str = sum(1 for _ in call("quux", mint("abc"), module=mod))
    n_quux_list = sum(1 for _ in call("quux", [mint("a"), mint("b"), mint("c")], module=mod))
    n_zorp_str = sum(1 for _ in call("zorp", "abc", module=mod))
    n_zorp_list = sum(1 for _ in call("zorp", [mint("a"), mint("b"), mint("c")], module=mod))

    # P3-1 \u00a71b: same-type combinations still return 1; cross-type
    # (str-head/list-caller or list-head/str-caller) now return 0.
    assert n_foo_str == 1, (
        f"Fact foo(\"abc\") called with \"abc\" returned {n_foo_str} "
        f"solutions; expected 1 (control, same-type)"
    )
    assert n_foo_list == 0, (
        f"Fact foo(\"abc\") called with ['a','b','c'] returned "
        f"{n_foo_list} solutions; expected 0 (cross-type, RETIRED by \u00a71b)"
    )
    assert n_bar_str == 0, (
        f"Fact bar(['a','b','c']) called with \"abc\" returned {n_bar_str} "
        f"solutions; expected 0 (cross-type, RETIRED by \u00a71b)"
    )
    assert n_bar_list == 1, (
        f"Fact bar(['a','b','c']) called with ['a','b','c'] returned "
        f"{n_bar_list} solutions; expected 1 (control, same-type)"
    )
    assert n_quux_str == 1, (
        f"Rule quux(\"abc\") <- helper(1) called with \"abc\" returned "
        f"{n_quux_str} solutions; expected 1 (control, same-type)"
    )
    assert n_quux_list == 0, (
        f"Rule quux(\"abc\") <- helper(1) called with ['a','b','c'] "
        f"returned {n_quux_list} solutions; expected 0 (cross-type, "
        f"RETIRED by \u00a71b — the str-literal head's unify guard still "
        f"runs unify(_scap0, 'abc', trail), which now declines a list)"
    )
    assert n_zorp_str == 1, (
        f"Rule zorp(['a','b','c']) <- helper(1) called with the STRING "
        f"\"abc\" returned {n_zorp_str} solutions; expected 1 -- THE FLIP "
        f"(spec §6.2) makes a string and its char-atom list one term, and "
        f"the head list holds char atoms"
    )
    assert n_zorp_list == 1, (
        f"Rule zorp(['a','b','c']) <- helper(1) called with "
        f"['a','b','c'] returned {n_zorp_list} solutions; expected 1 "
        f"(control, same-type)"
    )


def test_F046_str_literal_dispatch_table_charlist_caller_retired():
    """RETIRED by P3-1 Task 5 (\u00a71b): a multi-clause str-literal
    dispatch table is no longer reachable by a char-list caller — every
    char-list call now returns 0, str callers (same-type) still match.

    (Formerly ``test_F046_str_literal_dispatch_table_via_charlist``,
    which asserted the char-list caller matched its corresponding
    clause; that was the retired cross-type behaviour.)
    """
    source = """\
helper(1),

color("red") <- (helper(1))
color("green") <- (helper(1))
color("blue") <- (helper(1))
"""
    mod = load_inline_clausal("c04_f046_dispatch", source).__dict__["$module"]

    # P3-1 \u00a71b: char-list callers no longer match a str-literal head.
    assert sum(1 for _ in call("color", list("red"), module=mod)) == 0
    assert sum(1 for _ in call("color", list("green"), module=mod)) == 0
    assert sum(1 for _ in call("color", list("blue"), module=mod)) == 0
    # str callers (control, same-type) still match.
    assert sum(1 for _ in call("color", mint("red"), module=mod)) == 1
    assert sum(1 for _ in call("color", mint("green"), module=mod)) == 1
    # A char-list still matches nothing for a non-matching clause either.
    assert sum(1 for _ in call("color", list("purple"), module=mod)) == 0
    assert sum(1 for _ in call("color", [mint("x")], module=mod)) == 0


def test_F046_segstring_caller_against_str_head():
    """A SegString caller (ground and partial) unifies with a str-literal head.

    The unify guard dispatches to the caller's own SegString.__unify__:
    - a ground SegString matches via the `==` short-circuit disjunct;
    - a partial SegString (with a VarSeg hole) matches via the unify disjunct,
      which enumerates the split and binds the hole.
    """
    from clausal.logic.variables import Var, walk
    from clausal.terms import SegString, VarSeg

    # THE FLIP (spec §7): ``"abc"`` means a STRING only under
    # ``-double_quotes(chars)``; that is what this test is about.
    source = """\
-double_quotes(chars)
helper(1),

quux("abc") <- (helper(1))
"""
    mod = load_inline_clausal("c04_f046_segstring", source).__dict__["$module"]

    # Ground SegString caller — matches via the `==` disjunct.
    ground = SegString(["abc"])
    assert sum(1 for _ in call("quux", ground, module=mod)) == 1

    # Partial SegString caller `a<X>c` — the unify disjunct enumerates the
    # split against "abc", binding X to "b". The binding lives on the trail
    # only inside the solution scope, so read it during iteration.
    x = Var()
    partial = SegString(["a", VarSeg(x), "c"])
    bindings = [walk(x) for _ in call("quux", partial, module=mod)]
    assert bindings == ["b"], (
        f"partial SegString caller a<X>c vs head \"abc\": expected exactly "
        f"one solution binding X='b', got bindings={bindings!r}"
    )


def test_F046_str_head_compiles_to_unify_guard_not_matchvalue():
    """Compiler-level lock-in: a str-literal head emits a wildcard capture +
    `== or unify` guard, NOT a bare MatchValue.

    This pins the exact fix surface so a regression that re-introduces
    MatchValue(Constant("abc")) for a str head is caught directly, independent
    of runtime behaviour. Mirrors the structure verified by hand:

        case [_scap0]:
            ...
            if _scap0 == 'abc' or unify(_scap0, 'abc', trail):
                ...
    """
    import ast as _ast

    from clausal.logic.compiler.head_match import compile_head_to_match_case

    # THE FLIP (spec §7): under ``-double_quotes(chars)`` the head literal is
    # a STRING, which is what the ``_scap0`` guard below is about; the atom
    # spelling of the same text takes the ``_acap0`` guard instead.
    source = """\
-double_quotes(chars)
helper(1),

quux("abc") <- (helper(1))
"""
    mod = load_inline_clausal("c04_f046_compile", source).__dict__["$module"]
    clause = mod.db._clauses[("quux", 1)][0]

    case = compile_head_to_match_case(
        head=clause.head,
        body_stmts=[_ast.Pass()],
        var_context={},
        arity=1,
    )
    rendered = _ast.unparse(
        _ast.fix_missing_locations(
            _ast.Match(subject=_ast.Name("subj", _ast.Load()), cases=[case])
        )
    )

    # No bare MatchValue for the str literal: the arg pattern is a wildcard
    # capture, and "abc" appears inside a unify() call in the guard.
    assert "case ['abc']" not in rendered, (
        f"str head still compiled to a MatchValue pattern:\n{rendered}"
    )
    assert "unify(_scap0, 'abc', trail)" in rendered, (
        f"str head did not emit the expected unify guard:\n{rendered}"
    )
    assert "_scap0 == 'abc'" in rendered, (
        f"str head did not emit the same-type `==` short-circuit:\n{rendered}"
    )


def test_F048_compound_str_head_inner_arg_hoisted_to_body_unify():
    """F048: a compound head `quux(foo("abc"))` does not specialise its inner str
    literal into a head MatchValue.

    Nested structural literals in a head are now *hoisted* into a body
    ``Unify`` goal (so inner vars couple correctly — the structural-head fix):
    the head arg becomes a fresh var and the body unifies it with the full
    ``foo("abc")`` term, keeping the inner "abc" on the ordinary unify path
    (where strings-as-lists applies) rather than a bare ``MatchValue``. This
    guards against a regression that would specialise the inner str into a match
    pattern.
    """
    import ast as _ast

    from clausal.logic.compiler.head_match import compile_head_to_match_case
    from clausal.terms import Unify

    source = """\
helper(1),

quux(foo("abc")) <- (helper(1))
"""
    mod = load_inline_clausal("c04_f048_compound", source).__dict__["$module"]
    clause = mod.db._clauses[("quux", 1)][0]

    # The inner foo("abc") is hoisted out of the head into a body Unify goal.
    unifies = [g for g in clause.body if isinstance(g, Unify)]
    assert unifies, f"expected a hoisted head-literal Unify in body: {clause.body!r}"
    hoisted = unifies[0]
    rhs = _ast.dump(_ast.parse(repr(hoisted.right))) if False else repr(hoisted.right)
    assert "foo" in rhs and "abc" in rhs, (
        f"hoisted Unify does not carry foo(\"abc\"): {hoisted!r}"
    )

    # The head match itself must NOT specialise the inner str into a MatchValue:
    # the head arg is now a plain captured var, so 'abc' never appears as a match
    # pattern in the rendered case.
    case = compile_head_to_match_case(
        head=clause.head,
        body_stmts=[_ast.Pass()],
        var_context={},
        arity=1,
    )
    rendered = _ast.unparse(
        _ast.fix_missing_locations(
            _ast.Match(subject=_ast.Name("subj", _ast.Load()), cases=[case])
        )
    )
    assert "'abc'" not in rendered, (
        f"inner str leaked into the head match as a literal pattern:\n{rendered}"
    )


def test_F046_bytes_literal_head_matches_int_list():
    """bytes-as-lists extension (supersedes F046's deliberate exclusion): a
    bytes-literal head now compiles to a wildcard-capture + unify guard, so
    an int-list caller matches it under the codes-model contract. A same-type
    bytes caller still hits the == fast path; a str caller still does not
    cross into the bytes domain.
    """
    source = """\
helper(1),

quux(b"abc") <- (helper(1))
"""
    mod = load_inline_clausal("c04_f046_bytes", source).__dict__["$module"]

    # Same-type bytes caller matches (fast == path).
    assert sum(1 for _ in call("quux", b"abc", module=mod)) == 1
    # bytes-as-lists: the int-code list form now matches (was 0 pre-feature).
    assert sum(1 for _ in call("quux", [97, 98, 99], module=mod)) == 1
    # No str/bytes cross-unification: a str caller must NOT match.
    assert sum(1 for _ in call("quux", mint("abc"), module=mod)) == 0


def test_F046_same_type_str_fast_path():
    """The same-type str caller path (the `==` short-circuit disjunct) works.

    A plain str caller against a str-literal head returns one solution without
    relying on the unify() fallback.
    """
    source = """\
helper(1),

quux("hello") <- (helper(1))
"""
    mod = load_inline_clausal("c04_f046_fastpath", source).__dict__["$module"]

    assert sum(1 for _ in call("quux", mint("hello"), module=mod)) == 1
    # A different str does not match.
    assert sum(1 for _ in call("quux", mint("world"), module=mod)) == 0
