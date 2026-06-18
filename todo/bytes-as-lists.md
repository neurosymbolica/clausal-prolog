# TODO: bytes-as-lists — make `bytes` a first-class sequence like `str`

**Status:** Designed — spec written 2026-06-18, pending implementation plan.
See **`docs/superpowers/specs/2026-06-18-bytes-as-lists-design.md`**, which
supersedes this file for all design decisions. This file is retained as the
surface inventory; the open questions below are now **resolved in the spec**.
**Origin:** Surfaced while writing the F046 follow-up spec
(`docs/superpowers/specs/2026-06-13-f046-head-literal-mismatch-design.md`,
2026-06-13). F046 deliberately left `bytes` on the `MatchValue` fast path and
documented it as out of scope; this todo tracks the actual feature.

## Decisions made (see spec)

- **Canonical form:** `bytes` unifies-with its **list of ints** decomposition
  (`b"abc" ↔ [97, 98, 99]`) — the Prolog *codes* model. Element domain is
  `int ∈ [0, 255]`, **not** length-1 `bytes` (bytes has no fixed point:
  `b"a"[0] == 97`). Resolves the "blocking design decision" below.
- **Not conversion:** unification-equivalence + C1 type preservation; the
  `bytes` object stays `bytes`, decomposing only on unify against a list.
- **Promiscuity:** full symmetry, no constraint (fires only when a `bytes`
  operand is present).
- **No `str`↔`bytes` cross-unification** (distinct domains).

## Goal

Make `bytes` behave under the same sequence/unification contract that `str`
enjoys ("a string is a list of single-character strings") so that a `bytes`
literal and its list form unify, decompose, and dispatch like `str` does.
Motivated by Python interop: `bytes` flows in from sockets and HTTP
(`clausal/modules/py/tcp.py` `Receive/2`, `clausal/modules/py/http.py`) and is
currently a dead-end scalar everywhere downstream.

## Blocking design decision (resolve FIRST)

**What is the canonical "char list" form of `bytes`?** This is genuinely
ambiguous and must be decided before any code:

- `list(b"abc") == [97, 98, 99]` — Python's native iteration yields **ints**.
- `[b'a', b'b', b'c']` — single-byte `bytes` objects, the closest analog to
  `str`'s `['a','b','c']` (1-char strs).

`str`'s contract is unambiguous because iterating a `str` yields 1-char `str`s.
`bytes` has no such fixed-point: iterating yields `int`, but indexing a slice
yields `bytes`. The whole feature hinges on this choice — pick one and make it
the contract everywhere. (Consider: does `[97,98,99]` collide with a genuine
list-of-ints term? That ambiguity may argue for the `[b'a',...]` form, or for a
dedicated `SegBytes`-only representation with no bare-list equivalence.)

Open sub-question: is bare-`bytes`↔bare-`list` equivalence even wanted, or
should bytes only get a partial-term (`SegBytes`) representation without the
list-coercion contract? `str` has both; bytes may not need the list half.

## Surfaces to change (grounded in current code)

1. **Core unify — `clausal/logic/variables/_variables.c`**
   - The strings-as-lists symmetric branches at ~L1139-1256
     (`PyUnicode_Check(t1) && PyList_Check(t2)` and the reverse) — add
     `PyBytes_Check` analogs honouring the chosen element type.
   - Walk / inspect / copy / functor-arg decomposition treat `bytes` as a
     non-decomposable scalar alongside int/float at L2017, L2167, L2253, L2573
     (and similar). These would need bytes-as-sequence handling to match how
     `str` (L2159, L2248, L2393, L2483) is decomposed.

2. **Partial-term machinery — `clausal/terms.py`**
   - Decide whether to add a `SegBytes` term mirroring `SegString`
     (`terms.py:734`), or whether ground bytes can reuse a decode→str path.
     `SegString` is `str`-only by construction (`__init__` rejects non-`str`/
     `VarSeg` segments); a `SegBytes` would parallel it for variable-length
     `bytes` holes.

3. **Seg unify runtime — `clausal/logic/runtime/_list_unify.c` /
   `list_unify.py` / `_seg_helpers.py`**
   - The seg-split machinery is `str`/`list` aware (`PyUnicode_Check` at
     `_list_unify.c:90,125,344,445`). A bytes contract needs the parallel
     bytes handling (or a decode bridge).

4. **Compiler head match — `clausal/logic/compiler/head_match.py:253`**
   - **This is the F046 extension point.** Once a runtime bytes contract
     exists, move `bytes` out of the `MatchValue` tuple
     `(int, float, bytes, complex)` and into the `str` wildcard-capture +
     `unify`-guard branch added by the F046 fix. ~one line at this site.

5. **First-arg indexing — `clausal/logic/compiler/arg_index.py`**
   - `_charlist_to_str_or_none` (L45) canonicalises char-lists to `str` so
     str-literal heads and char-list callers share a dispatch bucket (F095). A
     bytes analog is needed so bytes-literal heads and bytes-list callers
     bucket together. `_INDEXABLE_TYPES` (L37) already lists `bytes`.

6. **List dispatch lift — `clausal/logic/compiler/list_dispatch.py:122`**
   - Already groups `str`/`bytes` for the lift decision (L64-69, L122). Revisit
     once bytes gains the list contract — the current grouping assumes bytes is
     an opaque scalar.

## Test / verification

- Mirror the `str` coverage: bytes-literal head matched by a bytes-list caller
  and vice versa; `SegBytes` (if added) partial unification; indexing bucket
  sharing; interop round-trip (`tcp.Receive` bytes used in a list-shaped goal).
- Update the F046 spec's bytes regression test: it currently asserts a
  bytes-literal head stays on the `MatchValue` fast path. When this feature
  lands, that test's intent changes — bytes will instead route through the
  unify guard. Revisit
  `tests/audit_2026_05_25/test_class_C04_head_literal_mismatch.py` (the bytes
  regression case described in the F046 spec).

## Scope notes

- Pure feature work, not a correctness bug — no current behaviour is wrong,
  bytes is simply inert as a sequence.
- Larger blast radius than F046 (core C unify + term machinery, not one
  compiler site). Warrants its own brainstorm → spec → plan cycle.
- Decide the canonical list form (above) before estimating effort.
