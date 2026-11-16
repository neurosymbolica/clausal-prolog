"""Probe F070 — ``sequence//1`` (sequence/3 builtin) drops str type
across all four binding modes.

``sequence//1`` is the DCG-builtin from SWI compat that asserts
``S0 = List ++ S``.  Its implementation in ``dcg.py:73-116`` has four
binding modes (S0 bound / S bound / both unbound / list-only) and
*every* one of them produces a list-typed output even when the inputs
are str:

  Mode A (S0 bound to str):  output S is always a list (line 96 — the
    str S0 is converted via ``list(s0_val)`` and ``s0_val[n:]`` is a
    list slice).
  Mode B (S bound to str):   output S0 is always a list (line 103 —
    ``lst_val + s_val`` where ``lst_val`` was eagerly converted to list
    at line 86).
  Mode C (both unbound):     output S0 is a ``SegList`` (with
    ``ConcreteSeg(list)``) regardless of whether ``lst`` was a str —
    line 111 always builds ``SegList`` not ``SegString``.
  Mode D (lst is SegList/SegString):  unsupported — line 81 falls into
    ``_fail`` for any input that isn't plain list/str.

Modes A and B silently strip the str shape ([[F067]]-class output loss);
mode C is the str-promotion gap parallel to [[F042]]/[[F043]]/[[F053]];
mode D is the SegString blind spot parallel to [[F069]].

Logged as design-gap under C10 (the contract for sequence//1's output
shape isn't documented; the implementation just always makes a list).
"""
from __future__ import annotations

import os
import tempfile

from clausal.import_hook import _load_module
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref, Trail, unify
from clausal.terms import SegString, SegList, ConcreteSeg, VarSeg


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
    print("Probe F070 — sequence//1 mode matrix on str/list/Seg* inputs.")

    mod_obj = _load_inline_clausal("probe_f070", "")
    mod = mod_obj.__dict__["$module"]

    # Mode A: S0 bound to str, S unbound — S should be a str if "input-type
    # wins", but is unconditionally a list.
    print()
    print("Mode A (S0=str, S=Var, lst=str):")
    s0, s = "abXY", Var()
    for _ in call("sequence", "ab", s0, s, module=mod):
        sv = deref(s)
        print(f"  S = {sv!r} (type {type(sv).__name__})  "
              f"<-- expected 'XY' under input-type-wins")
        assert type(sv) is list and sv == ["X", "Y"]
        break

    # Mode B: S bound to str, S0 unbound — S0 should be a str when both
    # lst and s are str; is unconditionally a list.
    print()
    print("Mode B (S0=Var, S=str, lst=str):")
    s0, s = Var(), "XY"
    for _ in call("sequence", "ab", s0, s, module=mod):
        s0v = deref(s0)
        print(f"  S0 = {s0v!r} (type {type(s0v).__name__})  "
              f"<-- expected 'abXY' under input-type-wins")
        assert type(s0v) is list and s0v == ["a", "b", "X", "Y"]
        break

    # Mode C: both unbound, lst is str — S0 should be SegString,
    # but is SegList(ConcreteSeg(['a','b']), VarSeg(...)).
    print()
    print("Mode C (S0=Var, S=Var, lst=str):")
    s0, s = Var(), Var()
    for _ in call("sequence", "ab", s0, s, module=mod):
        s0v = deref(s0)
        print(f"  S0 = {s0v!r} (type {type(s0v).__name__})  "
              f"<-- expected SegString-shaped result for str lst")
        assert isinstance(s0v, SegList)
        break

    # Mode D: lst is a SegString — unsupported.
    print()
    print("Mode D (lst=SegString, S0=Var, S=Var):")
    X = Var()
    t = Trail()
    unify(X, "b", t)
    seg = SegString(["a", VarSeg(X)])
    s0, s = Var(), Var()
    found = False
    for _ in call("sequence", seg, s0, s, module=mod):
        found = True
        break
    print(f"  found={found}  <-- BUG, SegString rejected at line 81 guard")
    assert not found

    # And lst is a SegList — same hole.
    sl = SegList([ConcreteSeg(["a", "b"])])
    s0, s = Var(), Var()
    found = False
    for _ in call("sequence", sl, s0, s, module=mod):
        found = True
        break
    print(f"  lst=SegList variant: found={found}  <-- also rejected")
    assert not found

    print()
    print("  Verdict: every output of sequence//1 is hard-coded to list/SegList")
    print("  regardless of input shape.  Mirrors the C9 _seq_result gap in")
    print("  lists.py (F053/F063).  Design-gap.")


if __name__ == "__main__":
    main()
