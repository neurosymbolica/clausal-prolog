"""Probe F069 — ``phrase/2`` and ``phrase/3`` silently fail on
``SegString`` input (parallel to F031/F032 for ``_head_list_unify_input``).

``dcg.py:18,49`` only recognises ``isinstance(list_val, str)`` for the
str-to-list normalisation.  ``SegString`` instances — which walk to a
``str`` and represent the same logical value — are not handled.

The dispatched rule body then receives the raw ``SegString`` as
``s_in`` and tries to unify it against ``[t1, ..., tn, *s_out]``.  Even
for a *ground* SegString (every VarSeg bound, walks to a str) the
unification fails because the list-vs-SegString path doesn't exist
(``__unify__`` for SegString accepts ``str`` and ``list`` but a head
``s_in is [...]`` does an identity-shaped match that doesn't traverse
the SegString into chars).

This mirrors the C3 issues already logged at the lists.py /
list_unify.py layer ([[F031]], [[F032]], [[F034]], [[F040]], [[F041]],
[[F047]]).  The DCG layer silently inherits the same SegString blind
spot: phrase produces zero solutions where a ground SegString
equivalent to a passing str input should succeed.

Logged as bug under C10 (root cause is the DCG layer's missing
SegString conversion, not the deeper unify path; cross-link to the
C3 cluster).
"""
from __future__ import annotations

import os
import tempfile

from clausal.import_hook import _load_module
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref, Trail, unify
from clausal.terms import SegString, VarSeg


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
    print("Probe F069 — phrase/2,3 reject SegString input.")

    src = 'hi >> (["h", "i"])\n'
    mod_obj = _load_inline_clausal("probe_f069", src)
    mod = mod_obj.__dict__["$module"]
    cls = mod_obj.__dict__["hi"]

    # Build ground SegString equal to 'hi'.
    X = Var()
    t = Trail()
    unify(X, "i", t)
    seg = SegString(["h", VarSeg(X)])
    print(f"  seg = {seg!r}; walks to {seg.__walk__()!r}")

    # Baseline: phrase/2 with str succeeds.
    found_str = False
    for _ in call("phrase", cls, "hi", module=mod):
        found_str = True
        break
    print(f"  phrase(hi, 'hi'): found={found_str}")
    assert found_str

    # Bug: phrase/2 with SegString fails despite walking to the same str.
    found_seg = False
    for _ in call("phrase", cls, seg, module=mod):
        found_seg = True
        break
    print(f"  phrase(hi, SegString-of-'hi'): found={found_seg}  "
          f"<-- BUG, expected True")
    assert not found_seg, "if this assertion fires, the bug has been fixed"

    # Same hole for phrase/3.
    src3 = 'tok(_t) >> ([_t])\n'
    mod_obj3 = _load_inline_clausal("probe_f069_3", src3)
    mod3 = mod_obj3.__dict__["$module"]
    cls3 = mod_obj3.__dict__["tok"]

    X2 = Var()
    t2 = Trail()
    unify(X2, "b", t2)
    seg2 = SegString(["a", VarSeg(X2), "c"])

    v, rest = Var(), Var()
    found_seg3 = False
    for _ in call("phrase", cls3(v), seg2, rest, module=mod3):
        found_seg3 = True
        break
    print(f"  phrase(tok(V), SegString-of-'abc', Rest): found={found_seg3}  "
          f"<-- BUG, expected True with V='a' Rest=['b','c'] or 'bc'")
    assert not found_seg3

    # And for the Rest arg of phrase/3.
    Y = Var()
    seg_rest = SegString([VarSeg(Y)])
    v = Var()
    found_seg_rest = False
    for _ in call("phrase", cls3(v), "abcd", seg_rest, module=mod3):
        found_seg_rest = True
        break
    print(f"  phrase(tok(V), 'abcd', SegString([VarSeg(Y)])): "
          f"found={found_seg_rest}  <-- BUG, expected True")
    assert not found_seg_rest

    print()
    print("  Verdict: phrase/2 and phrase/3 ignore SegString in all three slots")
    print("  (input list, partial Rest, even when ground).  Mirrors the C3")
    print("  cluster (F031/F032/F034/F040/F041/F047) one layer up.  Bug.")


if __name__ == "__main__":
    main()
