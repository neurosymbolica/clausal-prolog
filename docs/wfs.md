# Well-Founded Semantics (WFS)

Well-Founded Semantics provides a sound three-valued treatment of negation for [tabled](tabling.md) predicates. Unlike simple negation-as-failure (which can loop or give wrong answers with recursive negation), WFS assigns each atom a truth value of **true**, **false**, or **undefined** — and that third value is exactly the strong-Kleene `Undefined` literal the language already has, not a separate marker.

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
- If `wins(Y)` is undefined (cyclic dependency) → the answer is marked `Undefined`

## Spelling the truth values

Each truth value has two spellings, and they are the same value — not two values
that happen to compare equal:

| value | canonical | alias |
|---|---|---|
| true | `True` | `true` |
| false | `False` | `false` |
| third | `Undefined` | `undefined` |

The canonical spellings are Python's, because Clausal borrows Python's parser.
The aliases are Prolog's: ISO writes `true`/`false`, and XSB and SWI write
`undefined` for the well-founded third value. Aliases are resolved at parse
time, so the two spellings are indistinguishable everywhere downstream — they
unify with each other, key the same dict entry, and emit the same Prolog atom.

Two consequences worth knowing:

- `true` and `false` work in goal position, as ISO `true/0` and `fail/0` do.
  `undefined` does **not**: unlike XSB/SWI, Clausal has no `undefined/0` goal.
  A goal either succeeds or fails, and an unfounded tabled answer carries its
  `Undefined` truth value on the *answer* rather than on the call. Writing
  `undefined` as a goal is a compile-time error that says so.
- `true`, `false` and `undefined` are therefore reserved: they cannot also be
  used as ordinary atom or predicate names.

`unknown` is **not** an alias. It was this value's name before it was renamed to
match XSB/SWI; writing it gets a diagnostic pointing at `Undefined`.

---

### WFS vs Standard NAF

| Scenario | Standard NAF | WFS |
|---|---|---|
| `not member(X, [1,2,3])` | Works fine | Works fine (overkill) |
| `not wins(Y)` with cycles | Loops forever | Returns `Undefined` |
| `not even(X)` where `even`/`odd` are mutually recursive through negation | Wrong answers or loops | Correct three-valued result |

**Rule of thumb**: Use `-table` + WFS when you have negation inside a recursive predicate. For non-recursive negation, standard NAF is sufficient and faster.

---

## The `query_wfs` API

How an undefined answer reaches you depends on how you ask:

- the **goal-position seam** in a `.seam` file (`for X in --wins(X):`) is strict: a
  definite answer is exported as usual, and an undefined one raises
  `clausal.logic.seam.UndefinedAnswer` (see
  [Python integration](python_integration.md));
- the lower-level `solve()` / `call()` / `query()` functions yield every non-false
  answer **without** a truth annotation, undefined ones included;
- `query_wfs` returns every answer annotated with its truth value.

With the three-cycle `a→b→c→a` of Example 1 below:

```python
# in a .seam file, below the clauses
from clausal import Var, query_wfs
from clausal.logic.seam import UndefinedAnswer

def main(this_module):
    v = Var()
    for r in query_wfs(('wins', v), {"X": v}, module=this_module):
        print(r["X"], r["_truth"])      # a Undefined / b Undefined / c Undefined
    try:
        for X in --wins(X):
            print(X)
    except UndefinedAnswer:
        print("wins/1 has an undefined answer")
```

`query_wfs` returns a **list** (not iterator) of binding dicts, each with a `"_truth"` key:

- `True` — the answer is definitely true
- `Undefined` — the answer is neither provably true nor provably false.  This is the
  same `Undefined` singleton `.clausal` code writes, so it can be compared with
  `is Undefined` and fed straight into Kleene-aware code.  Note `bool(Undefined)`
  raises `TypeError` by design — test it explicitly rather than with `if`.

Each result also carries a `"_delays"` key: a frozenset of `DelayedNegation`
objects, non-empty exactly when `_truth` is `Undefined`. Each names the negated
tabled call the answer is still conditional on (`.functor`, `.arity`,
`.frozen_args`) — for a negation cycle, the cycle partner. A caller can
therefore report *which* atoms form the unresolved pair, not merely that
something is undefined.

The annotation is independent of how the goal is asked: the same atom reports
the same truth value whether the goal is a reified `Call` or a cell, and whether the query is ground or unbound — and answer sets
are stable across query order (see the implementation overview below). It is
also independent of the goal's SHAPE: an untabled wrapper over a tabled
predicate, a conjunction (through goal position), a call fed through `++` —
the whole solve runs under a throwaway tabling leader, so `_truth`/`_delays`
are the delays the answer's own derivation incurred. Definite answers come in
derivation order; conditional ones are delivered after global resolution; a
WFS-false answer never appears.

The judgement is per ANSWER, not per solve, in three ways worth naming. A
branch that delayed and then FAILED does not leave its conditions behind for
the next answer: conditions are trailed, so the backtracking that undoes the
branch's bindings retracts them too (`p(X) <- (wins(X), ok(X))` with `ok(d)`
the only fact reports `d` as plain true, however many branches delayed before
it). A condition consumed FROM a table is remembered as the row it came from,
so a later delay-free re-derivation of that row — which nothing re-streams,
because the answer tuple is already known — still makes the answer true.  And
a definite derivation of bindings already deferred as conditional collapses
them to unconditional, because WFS truth is a disjunction over derivations:
`r(a) <- wins(a)` alongside the fact `r(a)` gives one true answer, not a true
one and an undefined one.

A bag carries its conditions. `findall`/`bagof`/`setof` and `count_all`
collect over their own trail mark and unwind it, but the bag (or the count)
outlives the unwind, so the conditions its rows were derived under are charged
to the derivation that receives it: a goal reading a list built entirely out of
undefined answers is itself undefined, not true.

---

## Example 1: Game Theory — Winning Positions

A position wins if there is a move to a position that does NOT win:

```clausal
-table(wins/1)

move('a', 'b'),
move('b', 'c'),
move('c', 'a'),

wins(X) <- (move(X, Y), not wins(Y))
```

With the cyclic graph a→b→c→a, every position depends on its successor not winning, which depends on *its* successor not winning, and so on in a circle. WFS correctly assigns all positions as **`Undefined`** — there are no definite winners.

### Asymmetric Moves

Add a non-cyclic escape and the picture changes:

```clausal
-table(wins/1)

move('a', 'b'),
move('b', 'a'),
move('a', 'c'),

wins(X) <- (move(X, Y), not wins(Y))

test("a wins") <- wins('a')
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

In a cycle of length 4 (1→2→3→4→1), `even_node` and `odd_node` are mutually recursive through negation. WFS resolves this: nodes whose parity is determinable get **true**/**false**, while nodes in an unfounded cycle get **undefined**.

---

## Understanding "Undefined"

An answer is **undefined** when it is neither provably true nor provably false. This happens when:

1. **Self-supporting cycles**: A depends on not-B, B depends on not-A. Neither can be resolved without the other.
2. **Unfounded loops**: A depends on not-A (directly or through a chain).

Undefined does NOT mean "error" — it is a legitimate third truth value. In game theory, undefined positions represent draws or positions where neither player has a winning strategy.

### What to Do with Undefined Answers

- **Know which API you are using**: `solve()`/`call()`/`query()` yield undefined answers alongside true ones, unmarked; the goal-position seam raises `UndefinedAnswer` instead of exporting one.
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

    An answer's condition is a **disjunction of delay sets** — one set per
    derivation (A04-F003). WFS truth is an OR over derivations: an answer
    derived both through a cycle (conditionally) and via a fact or resolved
    negation (unconditionally) is *true*, and only keeping the first
    derivation's delays would lose that.

    ### `_naf_tabled` Runtime

    For tabled predicates, negation-as-failure uses `_naf_tabled` instead of the standard `_found`-flag pattern. This integrates with the tabling engine to correctly handle:

    - Incomplete tables (computation still in progress)
    - Conditional answers (answers with delayed conditions) — negating a
      *complete* table whose only matching answers are themselves conditional
      delays too (`not Undefined` is `Undefined`), rather than failing
    - Cyclic dependencies
    - Never-evaluated subgoals: a ground `not p(...)` with no table and no
      complete subsuming table **spawns** the positive subgoal (the compiled
      seam passes the database as `$naf_db`) and decides against the
      completed result, instead of conservatively succeeding — this is what
      makes answer sets independent of query mode and order

    ### Conditional Answer Resolution

    After all tables reach a fixpoint, `_resolve_conditions` iterates over conditional answers and attempts to resolve them:

    - If all conditions of some derivation are satisfied → answer becomes true
    - If every derivation has a violated condition → answer is removed
    - If conditions are cyclic → answer remains undefined

    Resolution runs per-leader at completion and again **globally** over all
    completed tables when the root leader exits, so a table that completed
    early still sees the final truth of targets that completed after it.

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
    - **Query-surface consistency**: the symmetric cycle reports `Undefined`
      for every goal shape (reified `Call`, cell) and every query order
      (unbound/ground, either atom first), with `_delays` naming the partner
    - **Disjunctive derivations**: a fact inside a negation cycle wins
      (true), and its cycle partner correctly fails; asymmetric win reports
      exactly `{a: true}` at the surface

---

*See also: [Tabling](tabling.md) — SLG tabling, which WFS builds on.*
*See also: [Directives](directives.md) — the `-table` directive.*
*See also: [Constraints](constraints.md) — `dif/2` for disequality constraints (a different approach to negation).*
