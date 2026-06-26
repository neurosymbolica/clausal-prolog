# INVESTIGATE: a lazy "reversed view" of a list (zero-copy reversal)

**Filed 2026-06-26** as a follow-up to the `reverse/2` bidirectionality fix and
the list-representation review (plain `list` vs `SegList`).

## Idea

Represent the reversal of a list as a **view** over the original — a term that
points at the same underlying sequence but knows it is oriented end-to-start and
iterates backwards — instead of allocating a fresh reversed copy.

Benefits:
- **O(1) reversal**, instant even for very long lists; no allocation.
- **Re-reversal is free**: reverse(reverse(L)) returns the *original* L (the view
  is an involution — unwrap instead of re-copy).
- **Partial lists reverse correctly** (see below), which the current
  copy-based path cannot do at all.

## Why the current path can't reverse partial lists

`reverse/2` (`clausal/logic/builtins/lists.py::_reverse__2`) reverses via
`_as_items`, which returns `None` for a **non-ground** `SegList`. So today:

```clausal
reverse([1, *BS, 9], R)   % BS unbound  -> NO solution (verified 2026-06-26)
```

A naive concrete reversal of `[a, *BS, c]` would also be *wrong*: it must reverse
both the **segment order** and the orientation *within* the variable segment —
the answer is `[c | reverse(BS) ++ [a]]`, i.e. roughly `SegList([ConcreteSeg([c]),
ReversedView(BS), ConcreteSeg([a])])`. The element order inside `BS` must itself
be reversed once `BS` is bound; a forward copy of `BS` would be incorrect.

## Sketch (grounded in the current representation)

- Plain ground lists are Python `list`s; partial/star lists are
  `SegList`/`SegString`/`SegBytes` (see `clausal/terms.py`). `_as_items` walks a
  *ground* Seg\* to a concrete list.
- Introduce a reversed-view term (e.g. `RevView`, or a `reversed: bool` flag /
  orientation on `SegList`) that:
  - iterates/`__walk__`s its target backwards;
  - unifies element-wise against another sequence in reversed order;
  - composes: reversing a `RevView` yields the wrapped target (involution);
  - reverses a `SegList` by reversing the **segment list** and wrapping each
    segment as a reversed view (so `ConcreteSeg([c])` stays `[c]` but the order
    of segments flips and `VarSeg(BS)` becomes a reversed view of `BS`).
- `reverse/2` returns the view instead of a copy; `_as_items` / unification /
  printing learn to honour the orientation (materialize lazily only when a
  concrete `list`/`str`/`bytes` is actually demanded).

## Open questions to resolve in the investigation

1. **Surface vs internal**: is the view a first-class term users can hold and
   unify, or an internal optimization that always materializes at API
   boundaries? (Affects `==`, `copy_term`, `print_term`, C-extension consumers
   that assume a concrete `list`.)
2. **Strings/bytes**: `str`/`bytes` are immutable; a reversed view over them is
   pure win (no copy) but every str/bytes-consuming builtin must accept the view
   or it materializes — measure the churn.
3. **Trailing / backtracking**: binding a `VarSeg` inside a reversed view must
   interact correctly with the trail; the view must not cache a stale walk.
4. **Interaction with destructive reuse**
   (`todo/reverse-in-place-destructive-reuse.md`): a view supersedes the in-place
   variant for the shared case (no mutation needed), but the in-place option may
   still win when a concrete list is required immediately downstream.
5. **Cost of laziness**: pervasive views can make every list consumer pay an
   orientation check. Quantify against the allocation saved.

## Done when (for the investigation)

- A design note deciding surface-vs-internal, the partial-list reversal
  semantics (`[a,*BS,c]` → correct reversed shape), and the materialization
  boundary; with a prototype + benchmark showing the O(1) / re-reversal-free
  win and no behavioural change on the existing suite. Then file the
  implementation as its own todo.
