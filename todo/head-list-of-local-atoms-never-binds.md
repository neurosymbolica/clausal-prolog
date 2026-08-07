# A bare LIST in a clause head, built from atoms declared in the SAME module, succeeds but never binds

**Filed:** 2026-08-07, found while re-slicing `eu/customs/customs_valuation_hierarchy` in the
clausify corpus (determination-slices refactor). The refactor did not fail — it **hung the
domain**. Bisected to the case below and reproduced independently before filing.

Same family as `todo/done/numeric-head-literal-unification-bug.md` (RESOLVED 2026-06-23),
`todo/done/head-list-compound-bodybound-var.md` and
`todo/quantity-head-literal-compiles-to-a-pythunk-that-never-matches.md` — but distinct from
all three, see **Relation to the family** below.

## Symptom

A clause whose **head** carries a **top-level bare list** built from atoms declared in the
**same module** does not bind that list into a caller's variable — whenever the proof succeeds
through `get/3` with a **ground** third argument (directly, or through a helper).

**The query SUCCEEDS.** It returns one solution and hands back a fresh unbound variable. This
is the part that makes it dangerous: it is not "no solutions" (the numeric-head-literal
signature), so nothing looks wrong at the call site.

```clausal
-module(m, [q(A0, A1), a, b, rr])
q(P, [a, b]) <- ( get(P, rr, True) )
```

```
solve(m.q(DictTerm({m.rr: True}), B))   ->  1 solution, B = _1     # UNBOUND
```

The identical clause with `a`/`b` **imported from a sibling** binds correctly:

```
solve(m.q(DictTerm({m.rr: True}), B))   ->  1 solution, B = [a, b]
```

## Repro

`todo/head_list_local_atoms_repro.clausal`

```
cd /workspace/clausal-bug-fix
python -m clausal.testing todo/head_list_local_atoms_repro.clausal
  ->  10 tests: 6 passed, 4 failed [FAILED]
```

The four failures are the bug; the six controls pass. Note the repro asserts `ground(B)`
rather than comparing the value: `==` raises `type_error(evaluable)` on a list, and `is`
would **bind** the unbound variable and mask the defect entirely.

## Narrowing — all four conditions are required

| head arg | body | atoms | result |
|---|---|---|---|
| bare list `[a,b]` | `get(P,rr,True)` | **local** | **UNBOUND** |
| bare list `[a]` (one element) | `get(P,rr,True)` | **local** | **UNBOUND** |
| bare list `[a,b]` | helper that calls `get(P,rr,True)` | **local** | **UNBOUND** |
| bare list `[a,b]` | `get(P,kk,1)` (int-valued key) | **local** | **UNBOUND** |
| bare list `[a,b]` | `get(P,rr,True)` | imported | ok |
| **bare atom** `a` (no list) | `get(P,rr,True)` | local | ok |
| list nested in a compound `unk([a,b])` | `get(P,rr,True)` | local | ok |
| bare list `[a,b]` | `get(P,rr,V), V is True` | local | ok |
| bare list `[a,b]` | `P == P` (no `get/3`) | local | ok |
| bare list `[a,b]` | plain FACT, no neck | local | ok |

So: **top-level bare list**, in the **head**, from **locally-declared** atoms, proved through
**`get/3` with a ground third argument**. Remove any one and it binds correctly.

The one-element case and the bare-atom control together locate it precisely: the list wrapper
is the trigger, not the number of atoms, and not the atoms themselves.

## Why it hangs rather than merely returning the wrong thing

Downstream, `formalize_lib`'s `eval_requirements/4` recurses on the returned open list
**forever**. In `customs_valuation_hierarchy` the affected predicate is `valuation_sequence/3`,
and the symptom at the corpus level was a test battery that never terminated — no error, no
diagnostic, no timeout.

## Where to look (hypothesis, not a diagnosis)

`clausal/logic/compiler/head_match.py` already carries this exact bug *class* in its comments,
and its own fix for the numeric case:

- `:256-261` — "a bare `MatchValue` ... never *binds* the literal. Every atomic head literal
  must therefore capture the arg and route through `unify()`".
- `:620-632` — the `PredicateMeta` atom path inside the **list-literal** handling, which
  appends `("atom", cap_name, term)` to `list_guards`.

Since an imported atom binds and a locally-declared one does not, the likely seam is whether a
same-module atom reaches that capture+`unify()` path at all, or is instead resolved at compile
time to something the list-literal pattern treats as a plain literal. I did not confirm this —
it is where I would start.

## Relation to the family, and why none of them covers it

- **`numeric-head-literal-unification-bug.md`** (RESOLVED) — same root shape (literal in a
  ruled head not unified against a caller var) but the failure was **no solutions**. Here the
  query succeeds and returns an unbound var, so the existing regression test for that fix
  would not catch this.
- **`head-list-compound-bodybound-var.md`** (done) — head **list elements** not normalized,
  specifically a **compound** nested in a head list whose inner var the body binds. Here the
  elements are atoms and are fully ground in the source; the list itself is what fails to bind,
  and the control shows a compound nested in the list works.
- **`quantity-head-literal-compiles-to-a-pythunk-that-never-matches.md`** (open) — a
  `value(unit)` head literal matching nothing. Again the "no solutions" signature.

None is conditioned on **where the atom is declared**, which is the discriminator here.

## Why it matters beyond one domain

The clausify determination-slices refactor moves each domain's value atoms out of a shared
`schema.clausal` into the slice that spells them — i.e. from the working IMPORTED column to
the broken LOCAL one. It is a corpus-wide refactor, so any domain with a head list of value
atoms is exposed. `customs_valuation_hierarchy` had to keep six atoms in its kernel as a
**compiler-forced placement** to work around this, documented in that file's header.

## Fixes, in order of value

1. **Bind it.** A ground head list of locally-declared atoms should unify with the caller's
   variable exactly as the imported case does. The local/imported asymmetry localises the
   cause.
2. **Fail loudly meanwhile.** A head list that compiles to something which cannot bind should
   be a load error. Every other member of this family errors or returns no solutions; this one
   silently succeeds.
3. **Guard the recursion in `formalize_lib`.** `eval_requirements/4` recursing on an open list
   forever converts a wrong answer into an unbounded hang. A ground check at that entry point
   would make this and any future instance diagnosable.
