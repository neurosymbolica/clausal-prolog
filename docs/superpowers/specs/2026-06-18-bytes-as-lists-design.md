# bytes-as-lists — Design Spec

**Date:** 2026-06-18
**Author:** Michael Amy (with Claude)
**Status:** Implemented (2026-06-18)
**Origin:** Surfaced while writing the F046 follow-up spec; tracked in
`todo/bytes-as-lists.md`, which this spec supersedes for design decisions.
**Related:** strings-as-lists audit (`../audits/2026-05-25-string-implementation/`),
F046 (`2026-06-13-f046-head-literal-mismatch-design.md`) — its `head_match.py`
str-branch is the documented extension point this feature plugs `bytes` into.

---

## Goal

Make Python `bytes` a first-class sequence in Clausal under the **same
contract** that governs `str`, so that byte sequences participate in
unification, decomposition, partial-term matching, DCGs, and indexing exactly
as character strings do. Concretely:

```
b"abc"  unifies-with  [97, 98, 99]
```

The motivating use case is **DCGs over binary protocols** (parse/build byte
streams with `phrase//`), which need byte sequences to behave like the lists
they logically are. The principle is **symmetry**: strings-as-lists made a
`str` a list of characters; bytes-as-lists makes a `bytes` a list of byte
values, with the same type-preservation discipline.

---

## Background and the core decision

### bytes is genuinely not str

`str` and `bytes` look alike but are different domains, and conflating them
would be wrong:

- A 1-char `str` is a fixed point: `"a"[0] is "a"`. Iterating/indexing a `str`
  yields 1-char `str`s.
- A `bytes` has **no** fixed point: `b"a"[0] == 97` (an `int`), not `b"a"`.
  `bytes` is, in Python's own model, a **sequence of ints in `[0, 255]`**.

So the element domains differ, and the contract must respect that:

| | `str` (chars model) | `bytes` (codes model) |
|---|---|---|
| literal | `"abc"` | `b"abc"` |
| decomposes to | `['a', 'b', 'c']` (1-char `str`s) | `[97, 98, 99]` (`int`s) |
| element fixed point? | yes (`"a"` → `"a"`) | no (`97` is an `int`) |
| object type preserved? | yes | yes |
| partial-term term | `SegString` | `SegBytes` (new) |

### It is unification-equivalence, not conversion

The crucial framing — and the reason "compile-time conversion to a list of
ints" felt wrong — is that strings-as-lists does **not** convert `"abc"` into a
list. The `str` object stays a `str` (the entire C1 audit class is about this
type preservation); it merely *unifies with* `['a', 'b', 'c']` at the unify
layer and is otherwise preserved with all its Python methods.

bytes-as-lists applies the identical discipline: a `bytes` object stays
`bytes` — retaining `.decode()`, `.hex()`, `b'a'[0] == 97`, every method — and
only **decomposes into ints when unified against a list pattern** (a DCG
terminal, an `[X|Xs]` split). There is no compile-time conversion and no lost
methods. The int list is a *logical view*, exactly as the char list is for
`str`.

### This is the classical Prolog `codes` model

Prolog has always had two string representations: `chars` (list of one-char
atoms) and `codes` (list of integer character codes). Clausal's strings-as-lists
is the `chars` model. **bytes-as-list-of-ints is the `codes` model** — which is
exactly what the Triska/DCG tradition uses for byte and binary work (SWI's
`get_byte/2`, code-list `phrase/2`). So integer terminals are what binary-
protocol DCGs actually want, and a `bytes` literal used as a DCG terminal
sequence decomposes to its int codes, just as a `str` literal terminal
decomposes to its chars:

```
get_request --> b"GET", b" ", path.   # b"GET" decomposes to [71, 69, 84]
```

Raw int terminals (`[71, 69, 84]`) are the same list under the contract.

### Promiscuity decision: full symmetry, no constraint

The equivalence is *promiscuous* — just as any list of 1-char `str`s unifies
with the matching `str`, any list of ints in `[0, 255]` unifies with the
matching `bytes`. Because int-lists are common "real" data, `[1, 2, 3]` would
unify with `b"\x01\x02\x03"`.

**Decision: accept full symmetry, no special constraint.** Rationale: the
bytes↔list contract only *fires when a `bytes` object is actually present on one
side of a unification* — identical to how strings-as-lists only fires when a
`str` is present. Two plain int-lists unify as int-lists; **nothing ever
spuriously becomes `bytes`.** The only new behaviour is "a `bytes` value unifies
with its int-code list," which is the entire point of the feature. Constraining
it would require a runtime marker distinguishing "ints that are bytes" from
"ints that are ints" — which has no clean representation and breaks the symmetry
the design rests on.

---

## Architecture

The feature mirrors the strings-as-lists implementation surface-for-surface,
substituting the `int ∈ [0,255]` element domain for the 1-char-`str` domain and
`SegBytes` for `SegString`. Each surface below is an independently testable
unit.

### 1. Core unify — `clausal/logic/variables/_variables.c`

The strings-as-lists contract lives in the symmetric branches at ~L1139-1256
(`PyUnicode_Check(t1) && PyList_Check(t2)` and the reverse), which decompose a
`str` against a list element-wise, preserving the `str`. Add parallel
`PyBytes_Check` branches that decompose a `bytes` against a list, where each
byte unifies with an `int` element equal to its value (`b"abc"[i] == list[i]`).

The walk / inspect / copy / functor-arg decomposition helpers (L2017, L2167,
L2253, L2573 and similar) currently treat `bytes` as a non-decomposable scalar
alongside `int`/`float`. They must treat `bytes` as a sequence under the codes
contract, parallel to how `str` (L2159, L2248, L2393, L2483) is decomposed —
**but always reconstructing/preserving the `bytes` type** on the way out (the
C1 type-preservation rule applied to bytes).

### 2. Partial-term term — `SegBytes` in `clausal/terms.py`

A new term mirroring `SegString` (`terms.py:734`):

- **Segments:** concrete `bytes` literals alternating with `VarSeg` holes.
  `VarSeg`s bind to `bytes` substrings (never int-lists, never `str`).
- **Construction validation:** reject non-`bytes`/`VarSeg` segments with a
  `PartialTermError`, exactly as `SegString.__init__` does for non-`str`.
- **`__walk__`:** collapse bound `VarSeg`s, merge adjacent `bytes`; return a
  plain `bytes` when fully ground.
- **`__unify__`:**
  - against `bytes`: ground → `==`; non-ground → generator enumerating splits
    (a `_segbytes_unify_gen` analogous to `_segstring_unify_gen`).
  - against `list`: decompose to int-codes and unify element-wise (each concrete
    byte → its int value), enumerating splits when non-ground.
  - against `SegBytes`/`SegList`: follow the `SegString` precedent (return
    `NotImplemented`; see the F023 soft-spot note — symmetric handling is a
    known limitation carried over, not introduced here).
- **`__eq__` / `__hash__`:** symmetric with `SegString` — `bytes`/int-list aware
  `__eq__`; **unconditionally unhashable** (`SegString` precedent, F017).
- **sequence protocol** (`__len__`/`__iter__`/`__contains__`): ground iterates
  the walked `bytes` as **ints** (honouring `list(b"abc") == [97,98,99]`);
  non-ground exposes the concrete int prefix.

### 3. Seg-unify runtime — `clausal/logic/runtime/`

`_list_unify.c` / `list_unify.py` / `_seg_helpers.py` are `str`/`list` aware
(`PyUnicode_Check` at `_list_unify.c:90,125,344,445`). Add the parallel
`bytes`/int-list handling so `_head_list_unify_input`/`_output` and the
seg-helpers decompose `bytes` into int elements and reconstruct `bytes` on
output. The element check that currently validates "1-char `str`" gains a
"`int` in `[0,255]`" counterpart for the bytes path.

### 4. Compiler head-match — `clausal/logic/compiler/head_match.py`

**This is the F046 extension point.** F046 split `str` out of the `MatchValue`
scalar tuple into a wildcard-capture + `unify`-guard branch and *deliberately
left `bytes` on `MatchValue`* pending this contract. Now that a runtime bytes
contract exists, move `bytes` out of the `(int, float, bytes, complex)` tuple
and into the same wildcard-capture + `unify`-guard branch as `str` (a head
literal `Quux(b"abc")` must match a caller `Quux([97,98,99])`). The same-type
short-circuit guard generalises: `_cap == b"abc" or unify(_cap, b"abc", trail)`.

### 5. First-arg indexing — `clausal/logic/compiler/arg_index.py`

F095 added `_charlist_to_str_or_none` so a str-literal head and a char-list
caller share a dispatch bucket. Add the bytes analog
(`_bytelist_to_bytes_or_none`: a list/tuple of ints in `[0,255]` canonicalises
to its joined `bytes`) so a bytes-literal head and an int-list caller bucket
together. `_INDEXABLE_TYPES` already lists `bytes`.

### 6. DCG / `phrase` integration

Byte sequences must thread through `phrase//2,3` and DCG terminals the same way
char strings do: a `bytes` literal terminal decomposes to its int codes, and a
`bytes` value as the phrase subject decomposes for terminal matching while the
remainder is preserved as `bytes` (or `SegBytes` when partial). This rides the
existing DCG machinery once the core-unify and seg-runtime branches exist.

> **Interaction with F068 (deferred):** F068 is the unresolved phrase/3
> ambiguity between state-threading mode and char-splitting mode. bytes-as-lists
> introduces the *same* ambiguity for `bytes` subjects (split into codes vs.
> thread as opaque state). This spec does **not** resolve F068; bytes DCG
> support adopts whatever phrase/3 contract is in force and must not regress the
> str behaviour. If F068 is later resolved, the resolution applies uniformly to
> `str` and `bytes`.

---

## Error handling

- **`SegBytes` malformed segments** → `PartialTermError` at construction (mirror
  `SegString`).
- **Out-of-range int in a list unified against `bytes`** → unification **fails**
  (no solution); it is not an error. `unify(b"...", [256, ...])` simply does not
  match, because no byte equals 256. (A list containing a non-int where a byte
  is expected likewise fails to unify, not raises.)
- **`VarSeg` in a `SegBytes` bound to a non-`bytes`** → typed `PartialTermError`
  on walk, mirroring `SegString`'s non-char-list guard (F024 precedent).

---

## Generalization and future work

`bytes` is, conceptually, "a list of ints constrained to `[0, 255]`," which
invites a generalization to typed homogeneous numeric sequences (fixed-width
ints, floats, numpy-style arrays). This section records the deliberate decision
**not** to build that generalization now, and why, so the door stays open
without paying for it.

- **`SegBytes` is bytes-specific and `[0, 255]`-bounded — enforced at the
  boundary, never tracked.** `SegBytes` stores `bytes` segments / `bytes`-bound
  `VarSeg` holes; it never stores raw ints. The `[0, 255]` domain is Python's
  own `bytes` invariant, checked *where a `bytes` object meets a list* (unify
  against an out-of-range int simply **fails**). There is no homogeneity flag,
  no dtype state, and no per-operation invariant to maintain.

- **"List of ints" is the *view*, not the *representation*.** The ground form
  walks to a `bytes` **object** (preserving `.decode()`/`.hex()`/identity); the
  int list is only what it *unifies-with*. Modelling this as a `SegInts` whose
  ground walk yields an int list would destroy type preservation — so the term
  is `SegBytes`, and the `b"..."` literal produces a genuine `bytes` object, not
  sugar over a list.

- **Homogeneity is not worth tracking as list state.** A tracked "list of one
  type" property is alien to the Triska/Prolog model (lists are heterogeneous by
  nature), would multiply the term zoo and burden every dispatch site, and buys
  nothing the boundary check does not already provide. Constraints belong at the
  typed-object boundary, not as an invariant on every list-producing operation.

- **The reusable thing is the *pattern*, not a typed-list abstraction.** The
  template is "an opaque object type with a list view, where the object carries
  the domain constraint, with type preservation." `bytes` is its first instance
  (after `str`). If fixed-width int/float vectors or numpy/array interop ever
  arrive, each would be *its own* object-type-with-a-view (e.g. an
  `NDArrayTerm`) following this same template — **not** a generic
  `SegInts<range>`. numpy in particular is a different domain (packed efficient
  numeric computation), orthogonal to unification; it would be a "wrap an
  external array as a term" feature sharing the pattern but not this machinery.

- **Floats are moot now.** There is no literal representation for a sequence of
  floats, so float-sequences carry no pressure; they fall under the same
  recognized-but-unbuilt future-work umbrella.

---

## Explicitly out of scope

- **`str` ↔ `bytes` cross-unification.** `"abc"` does **not** unify with
  `b"abc"`, and `['a','b','c']` does not unify with `b"abc"`. They are distinct
  domains ("it would be wrong to conflate them"). Crossing between them stays an
  explicit user operation (`.encode()` / `.decode()` via the `py` module).
- **Resolving F068.** See the interaction note above.
- **A `bytearray` contract.** Only immutable `bytes` is in scope; `bytearray`
  (mutable) is not a logic term and is not addressed here.
- **Changing the `str` contract.** strings-as-lists is unchanged; this is purely
  additive.

---

## Testing

Mirror the strings-as-lists adversarial suite for bytes. New tests (a dedicated
`tests/` module, structured like the existing string-unification tests):

1. **Core unify, both directions:** `b"abc"` ↔ `[97,98,99]`; element-wise
   binding (`unify(b"abc", [X, 98, 99])` binds `X = 97`); length mismatch fails.
2. **No fixed point (regression):** `b"a"` decomposes to `[97]`, **not** to
   itself; `b"a"` does not unify with `[b"a"]`.
3. **Type preservation:** a `bytes` threaded through head/body unify and
   recursion stays `bytes` (the C1 rule for bytes); `.hex()`/`.decode()` still
   callable on a bound result.
4. **`SegBytes` partial term:** prefix peel
   (`SegBytes([b"GET", VarSeg(Rest)])` vs `b"GET /"` binds `Rest = b" /"`);
   ground walk returns plain `bytes`; unhashable; iterates as ints.
5. **Head-literal (F046 extension):** `Quux(b"abc") <- body` matched by
   `Quux([97,98,99])`; same-type `bytes` caller fast path; and the **former
   F046 bytes-regression test flips** — it currently asserts a bytes head stays
   on `MatchValue`; update it to assert the new unify-guard behaviour (noted in
   the F046 spec/test as the trigger point).
6. **Indexing:** a multi-clause bytes-literal dispatch table reached by an
   int-list caller buckets and matches correctly; a non-matching int-list
   matches nothing.
7. **DCG over bytes:** a small binary-protocol grammar (e.g. parse `b"GET "`)
   driven by `phrase//`; remainder preserved as `bytes`.
8. **Promiscuity:** `b"\x01\x02\x03"` unifies with `[1,2,3]` (documented,
   intended); two plain int-lists do not become `bytes`.
9. **Out-of-scope guards:** `"abc"` does not unify with `b"abc"`; `b"abc"` does
   not unify with `['a','b','c']`.

A `benchmarks/bench_bytes_dispatch.py` micro-benchmark mirrors
`bench_f046_head_dispatch.py` for the bytes head-dispatch path.

---

## Success criteria

1. `b"abc"` unifies with `[97,98,99]` (both directions, element binding,
   length-mismatch failure) with the `bytes` object type-preserved.
2. `SegBytes` provides partial-byte-string matching symmetric to `SegString`.
3. A `bytes`-literal head matches an int-list caller (F046 extension landed;
   `bytes` moved off `MatchValue`).
4. Bytes DCGs parse/build via `phrase//` with int/`bytes`-literal terminals.
5. First-arg indexing buckets bytes-literal heads with int-list callers.
6. No `str`/`bytes` cross-unification; strings-as-lists behaviour unchanged.
7. Full test suite green; new bytes suite + benchmark added.

---

## Notes for planning

This is a **large, cross-cutting** feature (core C unify + a new term type +
seg-runtime + compiler + indexing + DCG) — substantially bigger than F046's
single compiler site. The implementation plan should sequence the surfaces
bottom-up so each layer is testable before the next depends on it:

1. `SegBytes` term in `terms.py` (pure-Python, unit-testable in isolation).
2. Core C unify `bytes`↔list branches + type-preserving walk/inspect/copy.
3. Seg-unify runtime (`_list_unify.c` / Python fallbacks / `_seg_helpers`).
4. Compiler head-match (`bytes` off `MatchValue`) + first-arg indexing.
5. DCG/`phrase` integration.
6. Full bytes adversarial suite + benchmark.

Each layer mirrors an already-audited strings-as-lists surface, so the
strings-as-lists tests double as the reference contract for the bytes analog.
