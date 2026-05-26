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


def test_F067_phrase3_rest_type_preserves_str():
    """phrase/3 Rest preserves str shape when input is str (F070 fix, Phase 2 Task 14).

    Under the Liskov "strings-as-lists" / input-type-wins contract, when
    the input to phrase/3 is a str, the remainder ``Rest`` is bound to a
    str slice rather than a list of 1-char strs. ``phrase/2,3`` no longer
    eagerly convert str → list at entry; ``_head_list_unify_input`` /
    ``_body_star_unify`` destructure str natively (str slicing yields str).
    """
    # Register a simple DCG rule: tok(_t) >> ([_t])
    source = 'tok(_t) >> ([_t])\n'
    mod = load_inline_clausal("c10_f067_phrase_rest", source).__dict__["$module"]
    cls = load_inline_clausal("c10_f067_phrase_rest", source).__dict__["tok"]

    # Case 1: str input should produce str Rest (under the input-type-wins
    # principle) or at least not silently downgrade to list.
    v, rest = Var(), Var()
    found = False
    for _ in call("phrase", cls(v), "abcd", rest, module=mod):
        rv = deref(rest)
        # F067 fix: Rest is a str slice ("bcd") of the str input, not a
        # list of 1-char strs.
        assert type(rv) is str and rv == "bcd", (
            f"phrase(tok(V), 'abcd', Rest) should preserve str type: "
            f"expected Rest='bcd', got Rest={rv!r} "
            f"(type={type(rv).__name__})"
        )
        found = True
        break
    assert found, "phrase/3 with str input should produce at least one solution"


@pytest.mark.xfail(
    strict=True,
    reason=(
        "ledger F068: phrase/3 silently splits str state-threading arg into "
        "chars (deferred in Phase 2 Task 14 — see findings.md F068 Notes for "
        "the unresolved design question)"
    ),
)
def test_F068_phrase3_str_state_threading_splits():
    """phrase/3 with str state-threading arg is silently split into chars.

    phrase/3 serves two purposes: (1) token parsing with str inputs split
    to chars, and (2) state threading with arbitrary values. When a user
    accidentally omits the brackets in state-threading form
    (phrase(rule, "bob", Rest) instead of phrase(rule, ["bob"], Rest)),
    the str "bob" is silently destructured by ``_head_list_unify_input``
    into ``_s0="b"`` and a str slice ``"ob"`` for the remainder. The rule
    head then pushes ``"alice"`` back, producing
    ``Rest=['alice', 'o', 'b']`` — same shape as the pre-fix behaviour
    (the Phase 2 Task 14 fix swapped the eager str→list conversion for
    native str destructuring, but the wrong-answer is still produced
    because the implementation cannot distinguish state-threading from
    char-parsing intent from the call shape alone).
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


def test_F069_phrase2_rejects_segstring():
    """phrase/2 accepts ground SegString input (F069 fix, Phase 2 Task 14).

    SegString is a logical str (walks to str, represents the same value).
    phrase/2 now normalizes Seg* inputs at entry via ``normalize_seg_input``,
    so a ground SegString is walked to its str form and the existing str
    arm fires.
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


def test_F069_phrase3_rejects_segstring_input():
    """phrase/3 accepts ground SegString input (F069 fix, Phase 2 Task 14).

    Like ``test_F069_phrase2_rejects_segstring``: a ground SegString in the
    list slot of phrase/3 is walked to its str form at entry.
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


def test_F069_phrase3_rejects_segstring_rest():
    """phrase/3 silently fails when Rest is unbound and Var but SegString-shaped.

    Testing the Rest arg of phrase/3 — when Rest is a SegString variable
    and should unify with the remainder, phrase/3 currently fails to handle it.

    Closed as a cascade of the F023 fix (Phase 2 Task 7, C8): non-ground
    ``SegString.__unify__(list)`` now walks-and-delegates to the equivalent
    SegList path instead of returning ``NotImplemented``, so a SegString-
    shaped Rest binds against the remainder list. The phrase2/phrase3_input
    siblings exercise a different dispatch path (SegString *as the list
    arg*, not as the Rest) and remain open.
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


def test_F070_sequence_mode_a_preserves_str():
    """sequence//1 Mode A (S0=str, S=Var): output S should be str, not list.

    Mode A: S0 bound to str, S unbound. Under "input-type wins" (F070
    closed in Phase 2 Task 14), the remainder ``S`` is bound to a str
    slice of ``S0`` rather than a Python list of 1-char strs.
    """
    mod = load_inline_clausal("c10_f070_seq_mode_a", "").__dict__["$module"]

    s0, s = "abXY", Var()
    found = False
    for _ in call("sequence", "ab", s0, s, module=mod):
        sv = deref(s)
        # F070 fix: ``S`` is a str slice of ``S0`` ("XY"), preserving the
        # str shape of the input under the Liskov "strings-as-lists"
        # rule. The default-list / promote-to-str contract still holds:
        # the slice is naturally str because str slicing returns str.
        assert type(sv) is str and sv == "XY", (
            f"sequence('ab', 'abXY', S): expected S='XY' (str) "
            f"under input-type-wins, got S={sv!r} "
            f"(type={type(sv).__name__})"
        )
        found = True
        break
    assert found, "sequence/3 Mode A should produce at least one solution"


def test_F070_sequence_mode_b_preserves_str():
    """sequence//1 Mode B (S0=Var, S=str): output S0 should be str, not list.

    Mode B: S bound to str, S0 unbound. Under "input-type wins" (F070
    closed in Phase 2 Task 14), when both ``lst`` and ``S`` are str the
    builder concatenates as str so ``S0`` is str-typed.
    """
    mod = load_inline_clausal("c10_f070_seq_mode_b", "").__dict__["$module"]

    s0, s = Var(), "XY"
    found = False
    for _ in call("sequence", "ab", s0, s, module=mod):
        s0v = deref(s0)
        # F070 fix: ``S0`` is the str concatenation of ``lst`` and ``S``
        # ("ab" + "XY" = "abXY"). The input-type-wins rule promotes when
        # both operands are str.
        assert type(s0v) is str and s0v == "abXY", (
            f"sequence('ab', S0, 'XY'): expected S0='abXY' (str) "
            f"under input-type-wins, got S0={s0v!r} "
            f"(type={type(s0v).__name__})"
        )
        found = True
        break
    assert found, "sequence/3 Mode B should produce at least one solution"


def test_F070_sequence_mode_c_builds_segstring():
    """sequence//1 Mode C (S0=Var, S=Var, lst=str): output should be SegString.

    Mode C: both S0 and S unbound, lst is str. Under the str-preservation
    contract (F070 closed in Phase 2 Task 14), the partial output is a
    ``SegString`` so the str shape of ``lst`` carries through.
    """
    mod = load_inline_clausal("c10_f070_seq_mode_c", "").__dict__["$module"]

    s0, s = Var(), Var()
    found = False
    for _ in call("sequence", "ab", s0, s, module=mod):
        s0v = deref(s0)
        # F070 fix: ``S0`` is a SegString preserving the str type of
        # ``lst='ab'``. The trailing VarSeg holds the unbound ``S``.
        assert isinstance(s0v, SegString), (
            f"sequence('ab', S0, S) with str lst should build SegString, "
            f"got {type(s0v).__name__}: {s0v!r}"
        )
        found = True
        break
    assert found, "sequence/3 Mode C should produce at least one solution"


def test_F070_sequence_mode_d_accepts_segstring():
    """sequence//1 Mode D: lst is SegString should succeed, not fail.

    Mode D: lst is a SegString or SegList. F070 closed in Phase 2 Task 14
    via ``normalize_seg_input`` at the entry: a ground SegString is walked
    to its str form and the existing str arm fires.
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
        f"(walk to 'ab' and continue), but got {found} solutions"
    )
