"""Probe F068 — ``phrase/3`` silently splits str state-threading arg
into chars.

The ``docs/dcg.md`` "State Threading" section (lines 175-234) documents
DCGs as a general state-passing mechanism — ``phrase/3`` is invoked as
``phrase(rule, [State0], [State])`` to carry an arbitrary value through
a Triska-style state-threading rule.  The wrapping list ``[State]``
holds *one* element that is the state.

But ``phrase/3`` unconditionally splits a ``str`` input into characters
at ``dcg.py:49-50``.  If a user accidentally drops the brackets and
calls ``phrase(set_name("alice"), "bob", Rest)`` instead of
``phrase(set_name("alice"), ["bob"], Rest)``, ``"bob"`` is silently
treated as the 3-element list ``["b", "o", "b"]`` — the rule head
unifies the *first character* "b" with what was meant to be the
whole state "bob", and the remaining state-threading machinery
operates on the partial char-list residue.

The result silently *succeeds* with a wrong answer like
``Rest = ['alice', 'o', 'b']`` instead of the intended
``Rest = ['alice']``.  No type error, no warning — just a wrong answer
because phrase's two distinct uses (token parsing vs. state threading)
share a single input slot and the str-as-char-list conversion is
applied to *both* uses.

Logged as bug under C10 — this is a "wrong answer" outcome: a real
program will get incorrect output, not a runtime error.
"""
from __future__ import annotations

import os
import tempfile

from clausal.import_hook import _load_module
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref


SOURCE = """
-module(s2, [state2(_s0, _s, S0_2, S_2), set_name(_n, _s0, _s)])
(state2(_s0, _s), [_s]) >> ([_s0])
set_name(_n) >> (state2(_, _n))
"""


def _load_inline_clausal(name: str, source: str):
    with tempfile.NamedTemporaryFile(
        suffix=".clausal", mode="w", delete=False
    ) as f:
        f.write(source)
        f.flush()
        path = f.name
    try:
        return _load_module(name, path)
    finally:
        os.unlink(path)


def main() -> None:
    print("Probe F068 — phrase/3 with str state arg splits to chars.")

    mod_obj = _load_inline_clausal("probe_f068", SOURCE)
    mod = mod_obj.__dict__["$module"]

    # Correct usage: phrase(set_name("alice"), ["bob"], Rest)
    # -> Rest = ["alice"]  (state is replaced)
    rest = Var()
    for _ in call(
        "phrase",
        mod_obj.__dict__["set_name"]("alice"),
        ["bob"],
        rest,
        module=mod,
    ):
        rv = deref(rest)
        print(f"  Correct: phrase(set_name('alice'), ['bob'], Rest) -> "
              f"Rest={rv!r}")
        assert rv == ["alice"]
        break

    # User-error: forgot the brackets — passes 'bob' (str) as state list.
    # phrase converts to ['b', 'o', 'b'] and silently succeeds with junk.
    rest = Var()
    for _ in call(
        "phrase",
        mod_obj.__dict__["set_name"]("alice"),
        "bob",
        rest,
        module=mod,
    ):
        rv = deref(rest)
        print(f"  Bug:     phrase(set_name('alice'), 'bob', Rest) -> "
              f"Rest={rv!r}")
        assert rv == ["alice", "o", "b"], (
            f"unexpected: {rv!r}"
        )
        break

    print()
    print("  Verdict: 'bob' is split to ['b','o','b']; state-threading machinery")
    print("  unifies 'b' with what was meant to be the whole state.  Rest comes")
    print("  back as ['alice', 'o', 'b'] — silently wrong, no type error.")
    print("  Phrase/3's two uses (token parsing vs state threading) conflict on")
    print("  the str-input slot.  Bug.")


if __name__ == "__main__":
    main()
