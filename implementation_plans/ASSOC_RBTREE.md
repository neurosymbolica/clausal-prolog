# Assoc / Red-Black Tree — Logical Dictionaries

Implementation plan for a pure, backtrackable, logic-level dictionary in
Clausal: an AVL or red-black tree that acts as a first-class term, threads
through unification, and backtracks on search failure.

---

## Why not just DictTerm?

Clausal already has `DictTerm` (Dicts/Sets Phase 1/2) which unifies pairwise
and participates in patterns. That's great for *known-shape* dict literals.
What it doesn't give you is:

- **Logical update**: "insert K_ → V_ into Assoc_ giving NewAssoc_" as a pure
  relation that can be run in any direction.
- **Backtrackable state**: a logic variable's binding to an assoc value can
  be undone on failure without explicit trailing.
- **Ordered iteration** under unification (`AssocToList/2` backtracks over
  key-sorted pairs).
- **Partial queries** where keys or values are variables, scoped by the tree
  structure rather than a Python-level dict.

`DictTerm` uses Python dicts internally — it's an opaque hashed container.
`Assoc`/`RBTree` are built from logic-level compound terms and therefore
behave predicatively.

Host-language dictionaries in Python cover imperative cases. This feature is
explicitly the logic-programming contribution: balanced ordered maps as
persistent, unification-friendly data structures.

---

## Library surface

Two layers:

### `assoc` — balanced-tree association list (AVL)

Follows SWI `library(assoc)`. Keys compared by standard term order. Values
are arbitrary terms.

| Predicate                               | Meaning                                   |
|-----------------------------------------|-------------------------------------------|
| `EmptyAssoc(A_)`                        | `A_` = empty assoc                        |
| `GetAssoc(Key_, Assoc_, Value_)`        | lookup; fails if absent                   |
| `PutAssoc(Key_, Assoc_, Value_, New_)`  | insert/overwrite, return new tree         |
| `ListToAssoc(Pairs_, Assoc_)`           | build from `Key-Value` list               |
| `AssocToList(Assoc_, Pairs_)`           | in-order list of `Key-Value`              |
| `AssocToKeys(Assoc_, Keys_)`            | in-order keys                             |
| `AssocToValues(Assoc_, Values_)`        | in-order values                           |
| `MapAssoc(Goal_, Assoc_, New_)`         | map values                                |
| `DelAssoc(Key_, Assoc_, Value_, New_)`  | delete and report old value               |
| `MaxAssoc(Assoc_, Key_, Value_)`        | max-key entry                             |
| `MinAssoc(Assoc_, Key_, Value_)`        | min-key entry                             |
| `MergeAssoc(A_, B_, C_)`                | union; B's values win on collision        |

### `rbtree` — red-black tree (SWI `library(rbtrees)`)

Same API shape with `Rb` prefix: `RbEmpty/1`, `RbLookup/3`, `RbInsert/4`,
`RbDelete/4`, `RbVisit/2`, `RbMap/3`, `RbMin/3`, `RbMax/3`, `RbKeys/2`,
`RbValues/2`, `RbFold/4`.

Why both? Historical compatibility + performance trade-offs: AVL is stricter
balance (faster lookups), RB has cheaper inserts. SWI ships both. One
implementation strategy: ship AVL first (`assoc`), add RB later sharing the
`Tree` interface.

---

## Representation

Use a *logic term*, not a Python object. This is essential — it's what makes
the library backtrackable for free (everything on the trail already).

```
Empty tree:   t
Node:         t(Key, Value, Balance, Left, Right)
```

`Balance` ∈ `{<, =, >}` (AVL) tracks subtree height relation. Nodes are
ordinary `Compound` terms; the library is pure Clausal code, no Python
helpers except a lookup-hot-path fast version (phase 2).

Benefits of compound-term representation:
- copy_term, term_variables, numbervars all work for free
- unification with a tree pattern `t(K_, V_, _, _, _)` does what you'd
  expect — matches the root
- trail handles backtracking; no custom undo logic
- write/1 and format prints the tree legibly

Cost: every operation allocates a few `Compound` objects. For small trees
(<10^4 entries) this is fine; the hot-path optimizer (phase 2) can compile
`GetAssoc/3` to Python when the assoc is ground.

---

## Algorithm choice

### AVL (phase 1)

Adelson-Velsky–Landis trees, balance factors in `{<,=,>}` per SWI. Insert:
rebalance on the way back up (single/double rotations). Delete: same.
Well-documented, easy to get right, matches SWI exactly so tests can be
ported directly.

### Red-Black (phase 2)

Okasaki's functional RB insertion (ML-style pattern match on tree shape) is
beautiful as Clausal clauses because our head-patterns handle nested
`Compound` matching natively. Literally transcribable:

```clausal
# Okasaki balance, as four patterns
Balance(t(z, t(y, t(x, a, b), c), d), t(y, t(x, a, b), t(z, c, d))) <- ...
# ... (three more rotational rearrangements)
# default
Balance(T, T)
```

The first-argument indexing we already have (V2-1) makes these patterns
efficient.

RB deletion is notoriously finicky; use Germane & Might (2014) "Deletion:
the curse of the red-black tree" formulation, which has only three cases.

---

## Standard term ordering

Comparisons rely on Clausal's existing `Compare/3` (or equivalent). If
Compare isn't present yet, add it first — it's a prerequisite. ISO standard
order of terms: `Var < Number < Atom < String < Compound`, within each
class the natural order, compounds by arity then functor then args.

Verify: `clausal/logic/builtins/` — search for `compare`. If absent, add a
small `StandardCompare(Order_, X_, Y_)` in `builtins/comparison.py` before
the assoc library.

---

## File layout

```
clausal/modules/assoc.clausal        # pure-Clausal AVL implementation
clausal/modules/rbtree.clausal       # phase 2
clausal/logic/builtins/comparison.py # StandardCompare, @</2, @=</2 if missing
tests/test_assoc.py                  # Python-side tests
tests/test_rbtree.py
tests/fixtures/assoc_ops.clausal     # in-language test fixture
docs/assoc.md
docs/rbtree.md
```

The assoc and rbtree libraries are written in `.clausal`, not Python. They
become the first substantial library in Clausal written in Clausal itself —
a useful forcing function for the language.

---

## Testing

About 60 tests across Python + fixture files:

- empty + single + multi-entry construction
- lookup hits and misses
- overwrite semantics on `PutAssoc`
- `ListToAssoc` ↔ `AssocToList` roundtrip on random pair lists
- `AssocToList` is key-sorted even when input list isn't
- delete removes exactly one entry and preserves others
- `MinAssoc`/`MaxAssoc` on trees of various shapes
- `MergeAssoc` precedence rule
- `MapAssoc` preserves structure
- invariant check: AVL balance factors in `{-1,0,1}` after every op (via
  `check_avl/1` helper used in tests only)
- backtracking: after a failed branch, tree state restored byte-for-byte
- large random stress test: 10^4 random inserts + deletes, final assoc
  matches a Python `dict` oracle

Port a representative subset of SWI's `library(assoc)` test suite (it's
public domain / BSD-compatible — check license).

---

## Phases

### Phase 1 — AVL assoc library (1 week)
- [ ] `StandardCompare/3` builtin (if missing)
- [ ] `clausal/modules/assoc.clausal` — full API, all 12 predicates
- [ ] 60 tests passing
- [ ] Docs page with three worked examples (word count, scope tracker,
      memoization table)
- [ ] `@</2`, `@=</2`, `@>/2` term-order comparison operators if missing

### Phase 2 — red-black tree (0.5 week)
- [ ] `clausal/modules/rbtree.clausal` using Okasaki insert + Germane-Might
      delete
- [ ] Test parity with phase 1 assoc (same oracle)

### Phase 3 — hot-path optimization (optional, 0.5 week)
- [ ] When `Assoc_` is ground at a `GetAssoc` call site, compile to a
      Python iterative lookup. Reuse groundness-keyed dispatch (V2-2) —
      the infrastructure is already there, just need an additional plan
      for the "ground assoc" case.
- [ ] Benchmark: ground-lookup should be within 2× of a Python dict get
      for trees ≤10^4 entries.

---

## Open questions

- **DictTerm vs Assoc choice guidance.** Both will exist; docs need a clear
  "when to use which" page. Rough rule: DictTerm for pattern-matching
  literals with known keys; assoc for accumulators, scopes, maps updated
  during search.
- **Iteration order.** SWI's `assoc_to_list/2` is in-order by key.
  `rbtree`'s `rb_visit/2` same. Document this; users *will* rely on it.
- **Key equality under unification.** If a key is a non-ground term, insert
  semantics get weird — unification vs term-equality collision. SWI treats
  keys by standard order, not unification. Match that behavior and reject
  with `instantiation_error` if a key cannot be compared.
- **Should this live in `clausal/modules/` or be a builtin?** Pure-Clausal
  implementation in `modules/` is preferred — it's the more honest and more
  hackable path, and it exercises our own compiler. Builtin route reserved
  for phase 3 hot-path only.
