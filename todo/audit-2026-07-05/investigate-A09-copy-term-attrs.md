# investigate(A09-F010/D004): copy_term/2 drops attribute constraints — for Opus

**Finding:** docs/superpowers/audits/2026-07-05-fable-partition/09-builtins/findings.md A09-F010
**Tests:** tests/audit_2026_07_05/test_09_builtins.py::test_F010_copy_term_copies_dif (xfail)

## Problem

`_copy_term_py` (inspection.py:28-32) maps an unbound (possibly attributed)
Var to a bare fresh `Var()` — dif/FD/CLP(B)/… constraints vanish from the
copy: `dif(X,1), copy_term(X,Y), Y is 1` succeeds. SWI copies constraints
(copy_term/2 reinstates attribute goals). The C twin `_copy_term_impl` in
_variables.c has the same behaviour.

## Investigation

1. Decide semantics per A09-D004 (recommendation: copy attrs).
2. Mechanics: deep-copy the attr dict onto the fresh Var — but attr VALUES
   contain Vars that must go through var_map (a dif attr references peer
   vars!) and solver state that may be identity-keyed (A05/A06 hooks —
   coordinate; naive copy could corrupt solver stores).
3. C twin parity (_variables.c) + findall/bagof template copies (A03-D002
   uses the same walker?) — check blast radius.
4. Fallback: document "copies are constraint-free" + lint.
