# Well-Founded Semantics (WFS)

Well-Founded Semantics provides a sound three-valued treatment of negation for [tabled](tabling.md) predicates. Unlike simple negation-as-failure (which can loop or give wrong answers with recursive negation), WFS assigns each atom a truth value of **true**, **false**, or **undefined**.

---

## when You Need WFS

Standard negation-as-failure (`not Goal`) works fine when negation is not recursive — e.g., `not member(X, List)`. But when a program has **recursion through negation** on tabled predicates, NAF can loop infinitely or produce wrong answers.

WFS handles this by delaying negation until enough information is available:

```clausal
--8<-- "tests/fixtures/docs/misc_phase7_sigs.txt:wfs_example"
```

Without WFS, `not wins(Y)` would loop or produce incorrect answers. With WFS:

- If `wins(Y)` is provably true → negation fails
- If `wins(Y)` is provably false → negation succeeds
- If `wins(Y)` is undefined (cyclic dependency) → the answer is marked "undefined"

### WFS vs Standard NAF

| Scenario | Standard NAF | WFS |
|---|---|---|
| `not member(X, [1,2,3])` | Works fine | Works fine (overkill) |
| `not wins(Y)` with cycles | Loops forever | Returns "undefined" |
| `not even(X)` where `even`/`odd` are mutually recursive through negation | Wrong answers or loops | Correct three-valued result |

**Rule of thumb**: Use `-table` + WFS when you have negation inside a recursive predicate. For non-recursive negation, standard NAF is sufficient and faster.

---

## The `query_wfs` API

The standard `query()` / `call()` / `solve()` functions yield all non-failed answers without truth annotation. To see WFS truth values, use `query_wfs`:

```python
from clausal.logic.solve import query_wfs

results = query_wfs(goal, {"X": X}, module=mod)
for r in results:
    print(r["X"], r["_truth"])  # True or "undefined"
```

`query_wfs` returns a **list** (not iterator) of binding dicts, each with a `"_truth"` key:

- `True` — the answer is definitely true
- `"undefined"` — the answer is neither provably true nor provably false

---

## Example 1: Game Theory — Winning Positions

A position wins if there is a move to a position that does NOT win:

```clausal
-table(wins/1)

move("a", "b"),
move("b", "c"),
move("c", "a"),

wins(X) <- (move(X, Y), not wins(Y))
```

With the cyclic graph a→b→c→a, every position depends on its successor not winning, which depends on *its* successor not winning, and so on in a circle. WFS correctly assigns all positions as **undefined** — there are no definite winners.

### Asymmetric Moves

Add a non-cyclic escape and the picture changes:

```clausal
-table(wins/1)

move("a", "b"),
move("b", "a"),
move("a", "c"),

wins(X) <- (move(X, Y), not wins(Y))

Test("a wins") <- wins("a")
```

Now:

- `wins(c)` = **false** (no moves from c)
- `wins(a)` = **true** (via `move(a, c)`, and `not wins(c)` succeeds since wins(c) is false)
- `wins(b)` = **false** (only move is to a, but wins(a) is true, so `not wins(a)` fails)

---

## Example 2: Mutual Recursion Through Negation

WFS handles mutual recursion where two predicates depend on each other's negation:

```clausal
-table(even_node/1)
-table(odd_node/1)

edge(1, 2),
edge(2, 3),
edge(3, 4),
edge(4, 1),

even_node(X) <- (edge(X, Y), not odd_node(Y))
odd_node(X) <- (edge(X, Y), not even_node(Y))
```

in_ a cycle of length 4 (1→2→3→4→1), `even_node` and `odd_node` are mutually recursive through negation. WFS resolves this: nodes whose parity is determinable get **true**/**false**, while nodes in an unfounded cycle get **undefined**.

---

## Understanding "Undefined"

An answer is **undefined** when it is neither provably true nor provably false. This happens when:

1. **Self-supporting cycles**: A depends on not-B, B depends on not-A. Neither can be resolved without the other.
2. **Unfounded loops**: A depends on not-A (directly or through a chain).

Undefined does NOT mean "error" — it is a legitimate third truth value. in_ game theory, undefined positions represent draws or positions where neither player has a winning strategy.

### What to Do with Undefined Answers

- **Treat as false**: in_ many practical programs, undefined answers can be safely treated as false (this is what `query()`/`call()` do — they yield undefined answers alongside true ones).
- **Inspect explicitly**: Use `query_wfs` when you need to distinguish true from undefined — e.g., for debugging, verification, or reporting.
- **Restructure the program**: If you don't expect undefined answers, the cyclic dependency may indicate a modeling error.

---

## Requirements

WFS only applies to **tabled** predicates. Mark them with the [`-table` directive](directives.md):

```clausal
--8<-- "tests/fixtures/docs/misc_phase7_sigs.txt:wfs_directive"
```

Non-tabled predicates with negation use standard negation-as-failure (which can loop on recursive negation).

---

??? abstract "Implementation Overview"

    ### Delayed Negation

    when `not Goal` is encountered for a tabled predicate and the answer is not yet determined:

    1. The negation is **delayed** rather than immediately evaluated
    2. A conditional answer is recorded: "this answer holds if the delayed condition resolves"
    3. After the top-level computation completes, `_resolve_conditions` processes all conditional answers

    ### `_naf_tabled` Runtime

    For tabled predicates, negation-as-failure uses `_naf_tabled` instead of the standard `_found`-flag pattern. This integrates with the tabling engine to correctly handle:

    - Incomplete tables (computation still in progress)
    - Conditional answers (answers with delayed conditions)
    - Cyclic dependencies

    ### Conditional Answer Resolution

    After all tables reach a fixpoint, `_resolve_conditions` iterates over conditional answers and attempts to resolve them:

    - If all conditions are satisfied → answer becomes true
    - If any condition is violated → answer is removed
    - If conditions are cyclic → answer remains undefined

---

??? info "Test coverage"

    Tests are in `tests/test_wfs.py`.

    - **DelayedNegation**: equality, hashability, repr
    - **TableEntry conditions**: unconditional, conditional, truth values
    - **Leader context**: push/pop/nested
    - **_naf_tabled**: complete table, evaluating table, var args, no entry
    - **_resolve_conditions**: unconditional passthrough, resolve to true/false, unfounded stays conditional
    - **WFS integration**: symmetric win (all undefined), asymmetric win (true/false/undefined)
    - **query_wfs API**: truth annotations, list return type

---

*See also: [Tabling](tabling.md) — SLG tabling, which WFS builds on.*
*See also: [Directives](directives.md) — the `-table` directive.*
*See also: [Constraints](constraints.md) — `dif/2` for disequality constraints (a different approach to negation).*
