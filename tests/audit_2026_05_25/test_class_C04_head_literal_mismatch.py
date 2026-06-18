"""C4 — Head-pattern literal mismatch (rule heads with str literals).

1 bug finding (F046), now FIXED by the narrow head_match.py change: str is
split out of the MatchValue tuple at head_match.py and emitted as a wildcard
capture + a same-type-short-circuit unify guard (`_scap == "abc" or
unify(_scap, "abc", trail)`), mirroring the list-literal path. This routes the
comparison through unify() so a char-list caller honours the strings-as-lists
contract, while keeping the fast `==` path for same-type str callers.

Background on the original bug: Quux("abc") <- (real_body) used to compile to
MatchValue(Constant("abc")). Python's match uses == for MatchValue, so a caller
Quux(['a','b','c']) silently failed despite the strings-as-lists contract.
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

from clausal.logic.solve import call
from tests.audit_2026_05_25._helpers import load_inline_clausal

def test_F046_rule_str_head_matches_charlist_caller():
    """All 8 cross-call combinations (fact/rule × str-head/list-head ×
    str-caller/list-caller) return exactly 1 solution each.

    Registers four clauses via inline .clausal source:
    - Fact `Foo("abc")` — handled by the elaborator dodge
    - Fact `Bar(['a', 'b', 'c'])` — handled by elaboration + list path
    - Rule `Quux("abc") <- (Helper(1))` — the F046 surface (now fixed)
    - Rule `Zorp(['a','b','c']) <- (Helper(1))` — list-literal head
    - Plus `Helper(1)` so the rule bodies succeed

    Under the strings-as-lists contract, all 8 calls work:
    1. Foo("abc") — control (fact, str-head, str-caller)
    2. Foo(['a','b','c']) — strings-as-lists test (fact, str-head, list-caller)
    3. Bar("abc") — strings-as-lists test (fact, list-head, str-caller)
    4. Bar(['a','b','c']) — control (fact, list-head, list-caller)
    5. Quux("abc") — control (rule, str-head, str-caller)
    6. Quux(['a','b','c']) — strings-as-lists test (rule, str-head, list-caller)
    7. Zorp("abc") — strings-as-lists test (rule, list-head, str-caller)
    8. Zorp(['a','b','c']) — control (rule, list-head, list-caller)

    Call #6 — Quux(['a','b','c']) — was the F046 bug surface (0 solutions
    before the fix); it now returns 1.
    """
    # Register fixtures inline.
    source = """\
Foo("abc"),
Bar(['a', 'b', 'c']),

Helper(1),

Quux("abc") <- (Helper(1))
Zorp(['a', 'b', 'c']) <- (Helper(1))
"""
    mod = load_inline_clausal("c04_f046_heads", source).__dict__["$module"]

    # Collect all 8 solution counts.
    n_foo_str = sum(1 for _ in call("Foo", "abc", module=mod))
    n_foo_list = sum(1 for _ in call("Foo", ["a", "b", "c"], module=mod))
    n_bar_str = sum(1 for _ in call("Bar", "abc", module=mod))
    n_bar_list = sum(1 for _ in call("Bar", ["a", "b", "c"], module=mod))
    n_quux_str = sum(1 for _ in call("Quux", "abc", module=mod))
    n_quux_list = sum(1 for _ in call("Quux", ["a", "b", "c"], module=mod))
    n_zorp_str = sum(1 for _ in call("Zorp", "abc", module=mod))
    n_zorp_list = sum(1 for _ in call("Zorp", ["a", "b", "c"], module=mod))

    # Assert all 8 return exactly 1 solution.
    assert n_foo_str == 1, (
        f"Fact Foo(\"abc\") called with \"abc\" returned {n_foo_str} "
        f"solutions; expected 1 (control)"
    )
    assert n_foo_list == 1, (
        f"Fact Foo(\"abc\") called with ['a','b','c'] returned "
        f"{n_foo_list} solutions; expected 1 (strings-as-lists test, "
        f"handled by elaborator dodge)"
    )
    assert n_bar_str == 1, (
        f"Fact Bar(['a','b','c']) called with \"abc\" returned {n_bar_str} "
        f"solutions; expected 1 (strings-as-lists test)"
    )
    assert n_bar_list == 1, (
        f"Fact Bar(['a','b','c']) called with ['a','b','c'] returned "
        f"{n_bar_list} solutions; expected 1 (control)"
    )
    assert n_quux_str == 1, (
        f"Rule Quux(\"abc\") <- Helper(1) called with \"abc\" returned "
        f"{n_quux_str} solutions; expected 1 (control)"
    )
    assert n_quux_list == 1, (
        f"Rule Quux(\"abc\") <- Helper(1) called with ['a','b','c'] "
        f"returned {n_quux_list} solutions; expected 1 (strings-as-lists "
        f"test — the F046 surface: str-literal head now emits a wildcard "
        f"capture + unify guard instead of MatchValue, so the char-list "
        f"caller matches)"
    )
    assert n_zorp_str == 1, (
        f"Rule Zorp(['a','b','c']) <- Helper(1) called with \"abc\" "
        f"returned {n_zorp_str} solutions; expected 1 (strings-as-lists "
        f"test, list-literal heads work via wildcard+runtime-unify)"
    )
    assert n_zorp_list == 1, (
        f"Rule Zorp(['a','b','c']) <- Helper(1) called with "
        f"['a','b','c'] returned {n_zorp_list} solutions; expected 1 "
        f"(control)"
    )


def test_F046_str_literal_dispatch_table_via_charlist():
    """A multi-clause str-literal dispatch table reached by a char-list caller.

    Exercises the first-arg indexing layer (F095 canonicalisation buckets the
    char-list caller with the str-literal head) together with the converted
    head guard. Each char-list caller must match exactly its corresponding
    clause and no other; a non-matching char-list must match nothing (the
    wildcard capture must NOT degrade into match-anything).
    """
    source = """\
Helper(1),

Color("red") <- (Helper(1))
Color("green") <- (Helper(1))
Color("blue") <- (Helper(1))
"""
    mod = load_inline_clausal("c04_f046_dispatch", source).__dict__["$module"]

    # char-list callers land in the right bucket and match their clause.
    assert sum(1 for _ in call("Color", list("red"), module=mod)) == 1
    assert sum(1 for _ in call("Color", list("green"), module=mod)) == 1
    assert sum(1 for _ in call("Color", list("blue"), module=mod)) == 1
    # str callers (control) still match.
    assert sum(1 for _ in call("Color", "red", module=mod)) == 1
    assert sum(1 for _ in call("Color", "green", module=mod)) == 1
    # A char-list with no matching clause matches nothing — the guard
    # discriminates; it does not match every caller.
    assert sum(1 for _ in call("Color", list("purple"), module=mod)) == 0
    assert sum(1 for _ in call("Color", ["x"], module=mod)) == 0


def test_F046_segstring_caller_against_str_head():
    """A SegString caller (ground and partial) unifies with a str-literal head.

    The unify guard dispatches to the caller's own SegString.__unify__:
    - a ground SegString matches via the `==` short-circuit disjunct;
    - a partial SegString (with a VarSeg hole) matches via the unify disjunct,
      which enumerates the split and binds the hole.
    """
    from clausal.logic.variables import Var, walk
    from clausal.terms import SegString, VarSeg

    source = """\
Helper(1),

Quux("abc") <- (Helper(1))
"""
    mod = load_inline_clausal("c04_f046_segstring", source).__dict__["$module"]

    # Ground SegString caller — matches via the `==` disjunct.
    ground = SegString(["abc"])
    assert sum(1 for _ in call("Quux", ground, module=mod)) == 1

    # Partial SegString caller `a<X>c` — the unify disjunct enumerates the
    # split against "abc", binding X to "b". The binding lives on the trail
    # only inside the solution scope, so read it during iteration.
    x = Var()
    partial = SegString(["a", VarSeg(x), "c"])
    bindings = [walk(x) for _ in call("Quux", partial, module=mod)]
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

    source = """\
Helper(1),

Quux("abc") <- (Helper(1))
"""
    mod = load_inline_clausal("c04_f046_compile", source).__dict__["$module"]
    clause = mod.db._clauses[("Quux", 1)][0]

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


def test_F048_compound_str_head_inner_arg_via_list_unify():
    """F048: a compound head `Quux(foo("abc"))` keeps its inner str literal on
    the runtime list-unify path (NOT a bare MatchValue), so a char-list inner
    arg unifies under strings-as-lists.

    Unlike a bare str head, the inner "abc" sits inside the Call's args list and
    is handled by `_head_list_unify_input` (the args go through the list path) —
    this was already correct, independent of the F046 str-head fix. This test
    documents that and guards against a regression that would specialise the
    inner str into a MatchValue.
    """
    import ast as _ast

    from clausal.logic.compiler.head_match import compile_head_to_match_case

    source = """\
Helper(1),

Quux(foo("abc")) <- (Helper(1))
"""
    mod = load_inline_clausal("c04_f048_compound", source).__dict__["$module"]
    clause = mod.db._clauses[("Quux", 1)][0]

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

    # The inner str literal is a list-unify element, not a MatchValue pattern.
    assert "['abc']" in rendered and "head_list_unify_input" in rendered, (
        f"compound head inner str not on the list-unify path:\n{rendered}"
    )


def test_F046_bytes_literal_head_matches_int_list():
    """bytes-as-lists extension (supersedes F046's deliberate exclusion): a
    bytes-literal head now compiles to a wildcard-capture + unify guard, so
    an int-list caller matches it under the codes-model contract. A same-type
    bytes caller still hits the == fast path; a str caller still does not
    cross into the bytes domain.
    """
    source = """\
Helper(1),

Quux(b"abc") <- (Helper(1))
"""
    mod = load_inline_clausal("c04_f046_bytes", source).__dict__["$module"]

    # Same-type bytes caller matches (fast == path).
    assert sum(1 for _ in call("Quux", b"abc", module=mod)) == 1
    # bytes-as-lists: the int-code list form now matches (was 0 pre-feature).
    assert sum(1 for _ in call("Quux", [97, 98, 99], module=mod)) == 1
    # No str/bytes cross-unification: a str caller must NOT match.
    assert sum(1 for _ in call("Quux", "abc", module=mod)) == 0


def test_F046_same_type_str_fast_path():
    """The same-type str caller path (the `==` short-circuit disjunct) works.

    A plain str caller against a str-literal head returns one solution without
    relying on the unify() fallback.
    """
    source = """\
Helper(1),

Quux("hello") <- (Helper(1))
"""
    mod = load_inline_clausal("c04_f046_fastpath", source).__dict__["$module"]

    assert sum(1 for _ in call("Quux", "hello", module=mod)) == 1
    # A different str does not match.
    assert sum(1 for _ in call("Quux", "world", module=mod)) == 0
