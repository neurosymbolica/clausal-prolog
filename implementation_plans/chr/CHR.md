# CHR — Constraint Handling Rules

Implementation plan for CHR in Clausal: a forward-chaining, committed-choice rule
layer that lives alongside the existing logic engine and CLP(*) solvers.

---

## Background

**CHR (Thom Frühwirth, 1991)** is a declarative, committed-choice language for
writing constraint solvers. Rules rewrite a multiset (the *constraint store*)
until a fixpoint. Unlike Prolog clauses, CHR rules:

- never backtrack over rule selection (committed choice),
- may consume (*simplify*), keep (*propagate*), or partly consume (*simpagate*)
  the constraints they match,
- fire as soon as their head and guard are satisfied, on assertion or on
  variable wake-up.

Reference implementations: SICStus `library(chr)`, SWI `library(chr)` (both
based on Holzbaur/Frühwirth's K.U. Leuven CHR compiler), and Christian Duck's
CHR^∨ (disjunctive CHR).

### The three rule forms

```
simplification   :   H1, …, Hn <=> G | B1, …, Bm.
propagation      :   H1, …, Hn  => G | B1, …, Bm.
simpagation      :   H1, …, Hk \ Hk+1, …, Hn <=> G | B1, …, Bm.
```

- `Hi` — constraint heads (must all be present in the store).
- `G` — optional guard (must succeed without binding head variables).
- `Bi` — body goals (new constraints, or ordinary Clausal goals).

Simplification deletes all matched heads; propagation keeps them; simpagation
keeps those left of `\` and removes those right of it.

### Why CHR in Clausal

- Fills a real gap: CLP(FD/Q/R/B) solve *specific* theories; CHR lets users
  write *new* ones (union-find, Gauss elim, interval arithmetic, type
  inference, agent coordination).
- Composes with existing attributed-variable machinery — CHR constraints are
  attached to variables they share and wake up on unification.
- Pure Python implementation is feasible; no heroic compilation needed for
  first release.

---

## Clausal surface syntax

CHR rules are module-level items declared with a new AST form. Two candidate
surface syntaxes:

### Option A — directive-style (preferred)

```clausal
-chr_constraint(Leq/2)
-chr_constraint(Gcd/1)

# simpagation: Leq is antisymmetric
Leq(X_, Y_) // Leq(Y_, X_) <=> X_ = Y_
# propagation: transitive closure
Leq(X_, Y_), Leq(Y_, Z_) ==> Leq(X_, Z_)
# simplification
Leq(X_, X_) <=> True
```

`//` separates kept from removed heads (ASCII stand-in for `\`).
`<=>` and `==>` are new operators registered only inside CHR blocks.

### Option B — decorator-style

```python
@chr_constraint
class Leq(Predicate):
    _fields = ('x', 'y')

@chr_rule
def leq_antisym(X_, Y_):
    # kept // removed <=> guard | body
    return Leq(X_, Y_) // Leq(Y_, X_) <= (X_ == Y_)
```

**Recommendation:** ship Option A first (matches existing `-directive` style,
keeps `.clausal` files declarative) and add Option B later as a Python-native
sugar.

---

## Architecture

```
┌────────────────────────────────────────────────────────┐
│  Clausal goal engine  (compiler.py, solve.py)          │
│    ──────────── posts constraint ────────────▶         │
├────────────────────────────────────────────────────────┤
│  CHR runtime  (clausal/logic/chr/runtime.py)           │
│    • ConstraintStore (multiset, indexed by functor)    │
│    • History set (propagation: no re-fires)            │
│    • Scheduler (activation queue)                      │
│    • Attribute hook (wake on var binding)              │
├────────────────────────────────────────────────────────┤
│  Compiled rule table  (generated per module)           │
│    • per-occurrence match code                         │
│    • refined operational semantics order               │
└────────────────────────────────────────────────────────┘
```

### ConstraintStore

- Multiset keyed by `(functor_name, arity)` → list of `ConstraintOccurrence`.
- Each occurrence carries: `args`, `id` (monotonic int), `alive` flag,
  per-functor index position.
- On unification of variables in head args, attributed-variable hook
  re-activates the owning constraint (push onto scheduler).

### Propagation history

Propagation rules must not fire twice on the same tuple of constraints.
Maintain a `set[tuple[RuleId, tuple[int,...]]]` of fired head-id tuples.
Clear entries when any participating constraint is removed.

### Refined operational semantics (Duck et al., 2004)

The standard semantics used by SWI/SICStus:

1. Newly posted constraint C becomes *active*; occurrences matched in textual
   rule order, left-to-right in head.
2. For each occurrence, search the store for a matching partner tuple; apply
   guard; if it fires, run the body.
3. When C's own occurrences are exhausted without deletion, C goes *passive*
   (sits in store, may be activated as partner later, or re-activated on var
   binding).

This is deterministic enough to reason about termination and fits the
trampoline/continuation model we already use.

---

## Compilation

CHR is usually *compiled* per occurrence (Holzbaur/Frühwirth 1999; Schrijvers
2005). For phase 1 we keep a simpler interpreter; phase 2 ports to compiled
form.

### Phase 1 — interpreter

Each rule stored as:

```python
@dataclass
class ChrRule:
    kind: Literal["simp", "prop", "simpa"]
    removed: list[HeadPattern]      # consumed heads
    kept:    list[HeadPattern]      # kept heads
    guard:   GoalTree | None
    body:    GoalTree
    rule_id: int
```

`HeadPattern` is a tuple `(functor, arg_patterns)` where each arg is an AST
expression possibly containing logic vars.

Activation of a constraint C:
1. For each rule where C's functor appears in heads, for each matching
   occurrence position:
   - unify C with that head pattern,
   - search store for partner occurrences of the remaining heads (nested
     loops, indexed by functor),
   - check guard in a *copy* of the trail (guard failure must not bind head
     vars; use `copy_term` or a trail barrier),
   - on success: for propagation, record in history; delete removed heads;
     call body as ordinary Clausal goal.
2. If body posts new constraints, they enter the scheduler.

Complexity is poor in the worst case (O(n^k) for k-head rules) but fine for
the small stores typical of CHR applications.

### Phase 2 — compiled

Generate per-occurrence Python functions mirroring what K.U. Leuven CHR emits:
indexed lookup on shared arguments, early guard checks, tail-merged body.
Defer until phase 1 has real users.

---

## Integration points

### Attributed variables

A CHR constraint mentioning variables `V1…Vn` adds itself to each `Vi`'s
attribute list under key `'chr'`. On unification, the attribute hook
pushes the constraint onto the scheduler. Reuses the existing
`put_attr`/`get_attr` API from V2-5 and CLP(FD).

### Backtracking

The store must be trail-aware:
- inserting a constraint trails an "erase id" entry,
- deleting a constraint trails a "resurrect id" entry,
- history insertions are trailed as removals.

Implement via a small `ChrTrail` that piggybacks on the main trail's choice
points. Model after `clpfd.py`'s trailing.

### Interaction with tabling and WFS

CHR rules that post into a tabled predicate are delicate (answer tables must
freeze the constraint store with the answer). Phase 1 documents this as
unsupported; phase 3 explores constraint-aware tabling (see Schrijvers &
Warren, "Answer Set Programming in CHR-enabled Prolog").

---

## API

```python
from clausal.chr import chr_constraint, post, store_snapshot

# module-level, usually from parsed -chr_constraint directive
@chr_constraint(name='leq', arity=2)
class Leq: ...

# runtime
post(Leq(X_, Y_))               # inject constraint
store_snapshot()                # list[ConstraintOccurrence]
```

Query integration: a top-level `query()` returns bindings *plus* the residual
constraint store, analogous to how CLP(FD) returns residual `in/2` goals.

New builtins:
- `chr_store/1` — unify with list of current constraints
- `chr_show/0` — debug print (goes through existing `Writeln`)
- `find_chr_constraint/2` — `find_chr_constraint(leq/2, List)`

---

## File layout

```
clausal/logic/chr/
  __init__.py
  runtime.py        # ConstraintStore, scheduler, activation loop
  trail.py          # ChrTrail
  rules.py          # ChrRule, HeadPattern dataclasses
  compile.py        # rule compiler (phase 2; phase 1 = interpreter)
  builtins.py       # chr_store/1 etc.
  history.py        # propagation history, GC on deletion
  hook.py           # attribute-var wakeup hook
clausal/templating/
  chr_syntax.py     # parse <=> / ==> / // inside AST
tests/
  test_chr_runtime.py
  test_chr_rules.py
  test_chr_examples.py     # leq, gcd, union-find, min, fib-memo
  fixtures/
    chr_leq.clausal
    chr_gcd.clausal
    chr_union_find.clausal
docs/
  chr.md
```

---

## Phases

### Phase 1 — core interpreter (2-3 weeks)
- [ ] `ConstraintStore`, `ChrRule`, `HeadPattern`, `ChrTrail`
- [ ] `-chr_constraint` directive parsing + registration
- [ ] `<=>`, `==>`, `//` operator parsing inside CHR rule blocks
- [ ] Interpreter activation loop with refined operational semantics
- [ ] Propagation history with GC on head deletion
- [ ] Attribute-var wakeup on unification
- [ ] Guard evaluation in isolated trail scope (no head-var binding)
- [ ] Backtracking: trail entries for store insert/delete + history
- [ ] Residual-store reporting in `query()` results
- [ ] Five canonical examples: leq, gcd, min, union-find, primes sieve
- [ ] ≥50 tests

### Phase 2 — compilation (2 weeks)
- [ ] Per-occurrence compiler emitting indexed Python
- [ ] Shared-argument index (functor+arg_pos → occurrence list)
- [ ] Early-guard specialization
- [ ] Benchmark vs interpreter on leq/union-find; require ≥5× on typical stores

### Phase 3 — integration (1 week)
- [ ] CHR ↔ CLP(FD) interplay tests (post `Leq` among FD vars)
- [ ] Decorator-style `@chr_rule` Python API
- [ ] Docs + tutorial page
- [ ] Decide on CHR-tabling interaction (document unsupported, or implement)

---

## Open questions

- **Syntax for `\` (kept/removed split).** `//` is my preferred ASCII form;
  `\\` clashes with escape; `|` clashes with guard separator. Confirm with
  user before phase 1 starts.
- **Guard language.** SWI allows any goal; SICStus restricts to "ask
  constraints" (no binding). Start strict (must not bind head vars, must not
  post constraints), relax later.
- **Disjunctive CHR (CHR^∨).** Out of scope for phase 1.
- **Priorities / `pragma passive`.** SWI feature; defer.
