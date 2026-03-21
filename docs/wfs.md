# Well-Founded Semantics (WFS)

Well-Founded Semantics provides a sound three-valued treatment of negation for tabled predicates. Unlike simple negation-as-failure (which can loop or give wrong answers with recursive negation), WFS assigns each atom a truth value of **true**, **false**, or **undefined**.

The implementation extends `clausal/logic/tabling.py`.

---

## When You Need WFS

WFS is required when a program has **recursion through negation** on tabled predicates:

```clausal
-table(wins/1)

wins(X) <- (
    move(X, Y),
    not wins(Y)
),
```

Without WFS, `not wins(Y)` would loop or produce incorrect answers. With WFS:

- If `wins(Y)` is provably true → negation fails
- If `wins(Y)` is provably false → negation succeeds
- If `wins(Y)` is undefined (cyclic dependency) → the answer is marked "undefined"

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

??? abstract "Implementation Overview"

    ### Delayed Negation

    When `not Goal` is encountered for a tabled predicate and the answer is not yet determined:

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

## Requirements

WFS only applies to **tabled** predicates:

```clausal
-table(pred/arity)
```

Non-tabled predicates with negation use standard negation-as-failure (which can loop on recursive negation).

---

## Example

### Game Theory: Winning Positions

```clausal
-table(wins/1)

move(a, b),
move(b, c),
move(c, a),

wins(X) <- (move(X, Y), not wins(Y)),
```

With the cyclic graph a→b→c→a, `wins` has no definite winners — all positions are "undefined" under WFS.

---

??? info "Test coverage"

    Tests cover:

    - **Delayed negation**: basic recursive negation, cyclic dependencies
    - **Conditional answers**: resolution after fixpoint
    - **query_wfs API**: truth annotations, undefined answers
    - **Integration with tabling**: SLG resolution + WFS
