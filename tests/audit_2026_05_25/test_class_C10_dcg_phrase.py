"""C10 — DCG / phrase interaction.

4 findings (2 bug + 2 design-gap). The DCG layer threads a difference-list
through goals; with strings, the type can change at each step in
inconsistent ways. F067 has a lock-in test in tests/test_dcg.py that
Phase 2 must update when the fix lands.

Findings tested here:
- F067 (design-gap) phrase/3 Rest type doesn't preserve str input
- F068 (bug) phrase/3 silently splits str state-threading arg into chars
- F069 (bug) phrase/2,3 silently fail on SegString input
- F070 (design-gap) sequence//1 drops str type across every binding mode
"""

import pytest

from clausal.logic.solve import call
from clausal.logic.variables import Var, deref, Trail, unify
from clausal.terms import SegString, VarSeg, SegList, ConcreteSeg
from tests.audit_2026_05_25._helpers import load_inline_clausal


@pytest.mark.xfail(
    strict=True,
    reason="ledger F067: phrase/3 Rest type does not preserve str input shape",
)
def test_F067_phrase3_rest_type_preserves_str():
    """phrase/3 Rest should preserve str shape when input is str.

    Under the strings-as-lists "input-type wins" contract, if the input
    to phrase/3 is a str, the remainder Rest should also be a str (or at
    least offer an opt-in to get str-shaped Rest). Currently Rest is always
    a list-of-1-char-strs regardless of the input type.

    The documented contract in docs/dcg.md:148 asserts Rest == ['a', 'b']
    (list), so this is *currently correct*. The design-gap is the
    inconsistency with other builtins (F018/F033/F042/F043/F053/F062/F063)
    that preserve str shape on output.
    """
    # Register a simple DCG rule: tok(_t) >> ([_t])
    source = 'tok(_t) >> ([_t])\n'
    mod = load_inline_clausal("c10_f067_phrase_rest", source).__dict__["$module"]
    cls = load_inline_clausal("c10_f067_phrase_rest", source).__dict__["tok"]

    # Case 1: str input should produce str Rest (under the input-type-wins
    # principle) or at least not silently downgrade to list.
    v, rest = Var(), Var()
    for _ in call("phrase", cls(v), "abcd", rest, module=mod):
        rv = deref(rest)
        # Current (buggy) behaviour: Rest is always a list of 1-char strs.
        # Under input-type-wins, Rest should be "bcd" (str) to match input type.
        assert type(rv) is str and rv == "bcd", (
            f"phrase(tok(V), 'abcd', Rest) should preserve str type: "
            f"expected Rest='bcd', got Rest={rv!r} "
            f"(type={type(rv).__name__})"
        )
        break


@pytest.mark.xfail(
    strict=True,
    reason="ledger F068: phrase/3 silently splits str state-threading arg into chars",
)
def test_F068_phrase3_str_state_threading_splits():
    """phrase/3 with str state-threading arg is silently split into chars.

    phrase/3 serves two purposes: (1) token parsing with str inputs split
    to chars, and (2) state threading with arbitrary values. When a user
    accidentally omits the brackets in state-threading form
    (phrase(rule, "bob", Rest) instead of phrase(rule, ["bob"], Rest)),
    the str "bob" is silently converted to ['b', 'o', 'b'], the rule unifies
    the first char with what was meant to be the whole state, and the
    remainder is a junk wrong answer like Rest=['alice', 'o', 'b'] instead
    of Rest=['alice']. No error, no warning — silent wrong answer.
    """
    # Register DCG rules for state threading.
    source = """-module(s2, [state2(_s0, _s, S0_2, S_2), set_name(_n, _s0, _s)])
(state2(_s0, _s), [_s]) >> ([_s0])
set_name(_n) >> (state2(_, _n))
"""
    mod_obj = load_inline_clausal("c10_f068_phrase_state", source)
    mod = mod_obj.__dict__["$module"]
    set_name = mod_obj.__dict__["set_name"]

    # Correct usage: brackets around the state value.
    rest = Var()
    for _ in call("phrase", set_name("alice"), ["bob"], rest, module=mod):
        rv = deref(rest)
        assert rv == ["alice"], (
            f"phrase(set_name('alice'), ['bob'], Rest) correct form "
            f"should give Rest=['alice'], got {rv!r}"
        )
        break

    # Bug: user forgot brackets — str "bob" is silently split to chars.
    # The desired behaviour is that this either raises an error or at least
    # doesn't produce a silent wrong answer. Under phrase/3's state-threading
    # semantics, Rest=['alice'] is expected, not Rest=['alice', 'o', 'b'].
    rest = Var()
    for _ in call("phrase", set_name("alice"), "bob", rest, module=mod):
        rv = deref(rest)
        # This should not happen: phrase/3 should reject str inputs in
        # state-threading position or at minimum not silently produce
        # Rest = ['alice', 'o', 'b'].
        assert rv == ["alice"], (
            f"phrase(set_name('alice'), 'bob', Rest) should give "
            f"Rest=['alice'] (state-threading semantics), "
            f"got Rest={rv!r}"
        )
        break


@pytest.mark.xfail(
    strict=True,
    reason="ledger F069: phrase/2,3 silently fail on SegString input",
)
def test_F069_phrase2_rejects_segstring():
    """phrase/2 silently fails on ground SegString input.

    SegString is a logical str (walks to str, represents the same value)
    but phrase/2 only recognises isinstance(_, str). When a ground SegString
    is passed (all VarSegs bound), phrase should succeed with the same
    outcome as passing the walked str, but currently fails silently.
    """
    # Register a simple DCG rule.
    source = 'hi >> (["h", "i"])\n'
    mod = load_inline_clausal("c10_f069_phrase2", source).__dict__["$module"]
    hi = load_inline_clausal("c10_f069_phrase2", source).__dict__["hi"]

    # Baseline: phrase/2 with plain str succeeds.
    found_str = sum(1 for _ in call("phrase", hi, "hi", module=mod))
    assert found_str == 1, (
        f"phrase/2 with str should succeed; got {found_str} solutions"
    )

    # Bug: phrase/2 with ground SegString fails despite walking to the str.
    X = Var()
    t = Trail()
    unify(X, "i", t)
    seg = SegString(["h", VarSeg(X)])
    # Verify the SegString walks to "hi".
    assert seg.__walk__() == "hi", (
        f"SegString should walk to 'hi', got {seg.__walk__()!r}"
    )

    found_seg = sum(1 for _ in call("phrase", hi, seg, module=mod))
    assert found_seg == 1, (
        f"phrase/2 with ground SegString should succeed (walks to 'hi'), "
        f"but got {found_seg} solutions — BUG"
    )


@pytest.mark.xfail(
    strict=True,
    reason="ledger F069: phrase/2,3 silently fail on SegString input",
)
def test_F069_phrase3_rejects_segstring_input():
    """phrase/3 silently fails on ground SegString input (first arg).

    Like F069_phrase2, but testing phrase/3 with SegString as the list arg.
    """
    # Register a simple DCG rule.
    source = 'tok(_t) >> ([_t])\n'
    mod = load_inline_clausal("c10_f069_phrase3_input", source).__dict__["$module"]
    tok = load_inline_clausal("c10_f069_phrase3_input", source).__dict__["tok"]

    # Build a ground SegString equal to "abc".
    X = Var()
    t = Trail()
    unify(X, "b", t)
    seg = SegString(["a", VarSeg(X), "c"])
    assert seg.__walk__() == "abc", (
        f"SegString should walk to 'abc', got {seg.__walk__()!r}"
    )

    # Bug: phrase/3 with ground SegString input fails.
    v, rest = Var(), Var()
    found = sum(
        1 for _ in call("phrase", tok(v), seg, rest, module=mod)
    )
    assert found == 1, (
        f"phrase/3 with ground SegString input should succeed "
        f"(walks to 'abc'), but got {found} solutions — BUG"
    )


@pytest.mark.xfail(
    strict=True,
    reason="ledger F069: phrase/2,3 silently fail on SegString input",
)
def test_F069_phrase3_rejects_segstring_rest():
    """phrase/3 silently fails when Rest is unbound and Var but SegString-shaped.

    Testing the Rest arg of phrase/3 — when Rest is a SegString variable
    and should unify with the remainder, phrase/3 currently fails to handle it.
    """
    # Register a simple DCG rule.
    source = 'tok(_t) >> ([_t])\n'
    mod = load_inline_clausal("c10_f069_phrase3_rest", source).__dict__["$module"]
    tok = load_inline_clausal("c10_f069_phrase3_rest", source).__dict__["tok"]

    # phrase/3 where Rest is meant to be unbound and SegString-shaped.
    # This is a more advanced case — the system should allow SegString
    # to unify as the remainder.
    Y = Var()
    seg_rest = SegString([VarSeg(Y)])
    v = Var()

    found = sum(
        1 for _ in call("phrase", tok(v), "abcd", seg_rest, module=mod)
    )
    assert found == 1, (
        f"phrase/3 with SegString-shaped Rest should unify; "
        f"got {found} solutions — BUG"
    )


@pytest.mark.xfail(
    strict=True,
    reason="ledger F070: sequence//1 drops str type across every binding mode",
)
def test_F070_sequence_mode_a_preserves_str():
    """sequence//1 Mode A (S0=str, S=Var): output S should be str, not list.

    Mode A: S0 bound to str, S unbound. Under "input-type wins", the output
    S should also be str, but sequence//1 always produces a list.
    """
    mod = load_inline_clausal("c10_f070_seq_mode_a", "").__dict__["$module"]

    s0, s = "abXY", Var()
    found = False
    for _ in call("sequence", "ab", s0, s, module=mod):
        sv = deref(s)
        # Current behaviour (buggy): s is always a list.
        assert type(sv) is list and sv == ["X", "Y"], (
            f"sequence('ab', 'abXY', S): current (buggy) behaviour "
            f"gives S=['X','Y'] (list), got S={sv!r} "
            f"(type={type(sv).__name__})"
        )
        # Desired behaviour (under input-type-wins):
        # S should be "XY" (str).
        assert type(sv) is str and sv == "XY", (
            f"sequence('ab', 'abXY', S): expected S='XY' (str) "
            f"under input-type-wins, got S={sv!r} "
            f"(type={type(sv).__name__})"
        )
        found = True
        break
    assert found, "sequence/3 Mode A should produce at least one solution"


@pytest.mark.xfail(
    strict=True,
    reason="ledger F070: sequence//1 drops str type across every binding mode",
)
def test_F070_sequence_mode_b_preserves_str():
    """sequence//1 Mode B (S0=Var, S=str): output S0 should be str, not list.

    Mode B: S bound to str, S0 unbound. Under "input-type wins", the output
    S0 should be str, but sequence//1 always produces a list.
    """
    mod = load_inline_clausal("c10_f070_seq_mode_b", "").__dict__["$module"]

    s0, s = Var(), "XY"
    found = False
    for _ in call("sequence", "ab", s0, s, module=mod):
        s0v = deref(s0)
        # Current behaviour (buggy): s0 is always a list.
        assert type(s0v) is list and s0v == ["a", "b", "X", "Y"], (
            f"sequence('ab', S0, 'XY'): current (buggy) behaviour "
            f"gives S0=['a','b','X','Y'] (list), got S0={s0v!r} "
            f"(type={type(s0v).__name__})"
        )
        # Desired behaviour (under input-type-wins):
        # S0 should be "abXY" (str).
        assert type(s0v) is str and s0v == "abXY", (
            f"sequence('ab', S0, 'XY'): expected S0='abXY' (str) "
            f"under input-type-wins, got S0={s0v!r} "
            f"(type={type(s0v).__name__})"
        )
        found = True
        break
    assert found, "sequence/3 Mode B should produce at least one solution"


@pytest.mark.xfail(
    strict=True,
    reason="ledger F070: sequence//1 drops str type across every binding mode",
)
def test_F070_sequence_mode_c_builds_segstring():
    """sequence//1 Mode C (S0=Var, S=Var, lst=str): output should be SegString.

    Mode C: both S0 and S unbound, lst is str. Under the str-preservation
    contract, the output should be a SegString (not a SegList), matching
    the str input type.
    """
    mod = load_inline_clausal("c10_f070_seq_mode_c", "").__dict__["$module"]

    s0, s = Var(), Var()
    found = False
    for _ in call("sequence", "ab", s0, s, module=mod):
        s0v = deref(s0)
        # Current behaviour (buggy): s0 is a SegList.
        assert isinstance(s0v, SegList), (
            f"sequence('ab', S0, S): current (buggy) behaviour "
            f"builds SegList, got S0={s0v!r} "
            f"(type={type(s0v).__name__})"
        )
        # Desired behaviour: S0 should be a SegString to preserve the
        # str type of lst='ab'.
        assert isinstance(s0v, SegString), (
            f"sequence('ab', S0, S) with str lst should build SegString, "
            f"got {type(s0v).__name__}"
        )
        found = True
        break
    assert found, "sequence/3 Mode C should produce at least one solution"


@pytest.mark.xfail(
    strict=True,
    reason="ledger F070: sequence//1 drops str type across every binding mode",
)
def test_F070_sequence_mode_d_accepts_segstring():
    """sequence//1 Mode D: lst is SegString should succeed, not fail.

    Mode D: lst is a SegString or SegList. Currently sequence//1 silently
    fails (guard at dcg.py:81 rejects non-list/non-str). The fix should
    walk ground SegString/SegList to str/list and succeed.
    """
    mod = load_inline_clausal("c10_f070_seq_mode_d", "").__dict__["$module"]

    # Build a ground SegString.
    X = Var()
    t = Trail()
    unify(X, "b", t)
    seg = SegString(["a", VarSeg(X)])
    assert seg.__walk__() == "ab", (
        f"SegString should walk to 'ab', got {seg.__walk__()!r}"
    )

    s0, s = Var(), Var()
    found = sum(1 for _ in call("sequence", seg, s0, s, module=mod))
    assert found == 1, (
        f"sequence(SegString('ab'), S0, S) should succeed "
        f"(walk to 'ab' and continue), but got {found} solutions — BUG"
    )
