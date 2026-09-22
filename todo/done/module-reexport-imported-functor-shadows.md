# Re-exporting an imported functor "shadows" it with a fresh empty class — NON-BUG (resolved 2026-07-22)

**Status:** RESOLVED — investigation showed the engine already does the right
thing. Closed with regression tests, no code change. Kept as a note because
both `tests/test_functor_reexport.py` and
`todo/done/statement-context-tuple-goals-silently-discarded.md` reference it.

## Original report
A module that BOTH `-import_from`'s a functor and lists it in its own `-module`
export list appeared to get a fresh, distinct predicate class — silently
shadowing the import — so a downstream `-import_from` of the "re-exported"
functor found nothing (a query returned **0 solutions**).

## Investigation (2026-07-22) — not a shadowing bug
The engine already preserves identity. `compiler_v2._process_declarations`
only mints a fresh module-local class when no class exists *or* the existing
binding is the process-global default (`existing is global_cls`). An imported
functor is module-local — never the global default — so it is preserved, and
listing it in `-module` re-exports it with **shared class identity**.

The pre-existing `test_atom_shadowing.py` suite exercises the narrowed
shadowing *warning* by running `_process_declarations` in isolation, so it never
binds a real imported class and cannot observe the identity outcome. The new
`tests/test_functor_reexport.py` closes that gap: it loads real modules through
the import hook and asserts identity is shared and solutions flow across a
`library → queries → downstream` re-export chain.

## What the "0 solutions" symptom actually was
The re-export chain was a red herring. The real cause of the observed
"re-exported functor finds 0 solutions" was an **unparenthesised multi-goal
clause body written at statement level** — `fact(R), other(R)` parses as a bare
Python tuple that is evaluated and silently discarded, so the intended goals
never became a clause. That footgun is filed and fixed separately:

→ **See `todo/done/statement-context-tuple-goals-silently-discarded.md`** for the
root cause and the fix (statement-level arrow-less multi-goal tuples now raise a
`SyntaxError` instead of silently no-op'ing).

## Guard against regression
If someone ever changes the narrowed shadowing trigger to re-mint predicate
functors (believing it should match the atom-shadowing behaviour),
`tests/test_functor_reexport.py` fails loudly.

---

## SUPERSEDED — the reconciliation below was WRONG (corrected 2026-07-29, same day)

> **Do not act on the section that follows.** It is kept only so the reasoning
> trail is visible.
>
> It hypothesised that the field-name mismatch was explained by a *bare-name
> re-export* versus an *args-bearing declaration*. A subsequent investigation
> ran the preserved reproduction and found the real cause is neither: it is a
> **declaration/clause ARITY disagreement**, reproducible in a **single module
> with no imports at all**:
>
> ```clausal
> -module(m, [f(A)])
> f(1, 2),
> ```
>
> The axis is arity, not field names, and re-export is not involved. Both
> explanations previously on record were refuted, with regression tests:
> the anonymous-`_` → `arg_N` fallback is **unreachable** (`_is_logic_var_name`
> rejects all-underscore spellings before it, and body goals are emitted
> positionally so their spellings cannot mismatch), and the import-ordering
> defect is real but is a **different bug** that the reproduction does not hit.
>
> **This file's NON-BUG verdict stands and was never in question** — the tension
> was an artefact of my wrong hypothesis, not of the 2026-07-22 investigation.
> `tests/test_functor_reexport.py` still passes.
>
> Current state of the arity bug: fixed as a compile-time load error naming both
> the declaration and the conflicting clause. See
> `todo/done/functor-field-name-mismatch-diagnostic.md`.
>
> The import-ordering defect (a) is now **fixed** (third pass, same day): no
> winner is imposed between the local declaration and the import — instead a
> clause head for a functor the same file imports is emitted **positionally**,
> which removes the field-name axis from the head entirely. Both textual
> orderings keep working; `tests/test_functor_reexport.py` still passes
> untouched. Details in that same todo.

<details>
<summary>Original (wrong) reconciliation, 2026-07-29 — retained for the trail</summary>

## READ THIS IF YOU ARE FIXING THE FUNCTOR FIELD-NAME MISMATCH (added 2026-07-29)

`todo/done/functor-field-name-mismatch-diagnostic.md` records a root cause traced on
2026-07-29 that **sounds like** it contradicts this file's NON-BUG verdict. It
probably does not, but the distinction is subtle and easy to get wrong, so it is
written out here rather than left to be rediscovered.

### The apparent contradiction

- **This file (2026-07-22)** concluded: a module that imports a functor and
  lists it in its own `-module` exports keeps **shared class identity**. Not a
  bug.
- **The 2026-07-29 trace** concluded: a module that declares a functor locally
  *and* imports the same name gets the local class block emitted at the
  declaration position, then `-import_from` rebinds the global to the **foreign**
  class at *its* source position — while `EmbedTransformer._seen_functors` still
  holds the **local** field names. Later construction sites are emitted with
  local keyword names against the foreign class, producing the bare `TypeError`.

### Why they are most likely both right — the declaration shape differs

The two reports are about **different `-module` entries**:

| | this file (2026-07-22) | field-mismatch (2026-07-29) |
|---|---|---|
| `-module` entry | **bare name** — `-module(m, [verdict])` | **with field names** — `-module(m, [verdict(STATUS, CITATIONS)])` |
| meaning | *re-export* an existing functor | *declare* a functor, minting a class with those fields |
| layer | `compiler_v2._process_declarations` (identity preservation) | `EmbedTransformer` in `templating/term_rewriting.py` (codegen emission order) |
| outcome | identity preserved — correct | local fields vs foreign class — the bug |

A bare re-export mints nothing, so there are no local field names to disagree
with the import. An args-bearing declaration mints a class *and* records field
names, which is what the import can then contradict.

### Evidence, verified on `main` @ `4377eed1`

- `tests/test_functor_reexport.py` — **4 passed** on the current tree, so this
  file's conclusion still holds after the 2026-07-29 diagnostic work.
- The field-mismatch fixture `tests/fixtures/fnmismatch_use.clausal:9` uses the
  args-bearing shape:
  `-module(fnmismatch_use, [fnm_verdict(STATUS, CITATIONS), fnm_chk(RESULT)])`.

### What this means for the fix — and the trap

This reconciliation is a **hypothesis supported by two observations, not a
proof.** Confirm it before relying on it. Specifically:

1. Establish whether the bug reproduces with a **bare-name** re-export. If it
   does, this file's NON-BUG verdict is too broad and its Status line must be
   corrected — do not leave a stale RESOLVED banner in place.
2. `tests/test_functor_reexport.py` is a deliberate tripwire (see *Guard against
   regression* above). If your fix makes it fail, that is the guard doing its
   job: it means you have changed re-export identity semantics, which is a
   different and larger decision than fixing field-name disagreement. Do not
   "fix" the test to make it pass without arguing the semantics change.
3. The two findings live in different layers (`compiler_v2` vs
   `templating/term_rewriting.py`). A fix in one should not silently alter the
   other; if it does, say so explicitly.

</details>
