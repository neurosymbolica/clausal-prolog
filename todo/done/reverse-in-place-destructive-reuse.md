# perf: reverse/2 could reuse its input list in place (destructive reuse)

**Filed 2026-06-26** while fixing `reverse-not-bidirectional` and reviewing list
representation (question: "can we use Python's list.reverse in some cases?").

## Context

`reverse/2` (`clausal/logic/builtins/lists.py::_reverse__2`) always **allocates a
new list** via `list(reversed(items))`. That is correct and already uses native
Python reversal — but for the common forward, deterministic mode `reverse(+List,
-Rev)` where the input list is not shared, it could reverse in place
(`items.reverse()`), avoiding the allocation.

The codebase already has this pattern: `_append_dr__3` is a destructive-reuse
variant gated on `_sys.getrefcount(l1_val) <= 3`, selected by the compiler via
the `destructive_reuse` IR hint and `_DR_NAME_MAP` in
`clausal/logic/compiler/_lower_goalop_shared.py` (currently only `append`,
`dict_put`, `set_union`).

## Representation note (why this is safe to consider)

Complete/ground lists are plain Python `list`s; only **partial** lists (star /
tail-var patterns), DCG difference-lists, and concatenations-with-partials use
`SegList`/`SegString`/`SegBytes`. `_as_items` walks a *ground* Seg\* to a concrete
list. So in the deterministic `+List` mode the value is typically a plain
`list` — a candidate for in-place mutation when provably unshared.

## Sketch

- Add `_reverse_dr__2`: when the first arg is a plain `list` with a low refcount
  (mirroring `_append_dr__3`), do `items.reverse()` in place and unify; else fall
  back to the copying `_reverse__2`.
- Register it and add `"reverse": "$dr_reverse__2"` to `_DR_NAME_MAP`, and ensure
  the compiler marks eligible `reverse/2` call sites with the `destructive_reuse`
  hint (check how append's hint is decided — see the destructive-reuse analysis
  pass).
- **Care:** must NOT mutate in backward mode, when the list is shared, when it is
  a str/bytes (immutable — already a copy via `_seq_result`), or when it is a
  Seg\*. Only the plain-list, unshared, forward case is eligible.

## Priority

Low — pure allocation-avoidance optimization; correctness is unaffected. Worth it
only if reverse shows up in an allocation-heavy hot path.

## Done when

- A refcount-gated in-place reverse variant exists, the copying path remains the
  default/fallback, and a benchmark or test confirms no behavioural change.

---

## CLOSED 2026-09-02 — shipped exactly per the sketch

- `_reverse_dr__2` (`clausal/logic/builtins/lists.py`): forward mode over an
  unshared plain list (`getrefcount <= 3`, mirroring `_append_dr__3`) does
  `list.reverse()` in place and unifies; str/bytes/Seg*/shared/backward all
  fall back to the copying `_reverse__2`. NOT registered as the `reverse`
  builtin — only reachable through the compiler's rewrite, because the
  refcount gate alone is insufficient (backtracking could re-read the
  reversed list through the still-live source var; the liveness analysis is
  what rules that out).
- `("reverse", 2): 0` added to `_DR_CANDIDATES`
  (compiler/destructive_reuse.py) — the analyse→apply pass and its
  eligibility conditions (source dead after, unaliased with head vars,
  deterministic prefix) are table-driven, so nothing else changed.
- `"reverse": "$dr_reverse__2"` in `_DR_NAME_MAP`
  (_lower_goalop_shared.py) + dispatch registration in
  compiler/predicate.py.

Tests: `TestReverseDR` (in-place identity pinned, shared-list protection,
str fallback, backward-mode fallback) and `TestReverseEligibility`
(analysis + end-to-end) in tests/test_destructive_reuse.py; all 97
reverse-touching tests in the tree green.
