# `catch(fail, _, R)` in a `.pl` body does not compile: `ValueError: empty body on Try`

**Status: FIXED 2026-10-22 (commit 03c535c7).** The inline catch's try body is `pass` when the Goal lowers to no statements (`control_constructs.py`), so `catch(fail, C, R)` loads and fails on the native `.pl` front end, the translator and the seam. Pinned in tests/test_pl_translator_data_terms_followups.py::test_member_and_phrase_bodies_in_meta_and_data_positions (rows c01-c03, both front ends, Scryer's answers).

Found while probing the final review's I-1 (2026-10-16). It reproduces on the branch base a643125b, so it predates this round.

```prolog
k(X) :- catch(fail, _, true), X = 1.
```

Importing this `.pl` (native front end) raises `ValueError: empty body on Try` from `codegen.functiondef_to_function`. The Goal `fail` lowers to `[]` (`Fail()` drops its continuation), and the inline trampoline catch puts that empty list straight into an `ast.Try` body. Scryer: `k(X)` fails.

Fix: when the Goal lowers to no statements, emit `pass` in the try body. Or drop the try altogether: a goal that cannot run cannot throw.
