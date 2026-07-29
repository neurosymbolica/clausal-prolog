# Bug: functor field-name mismatch surfaces as a bare, unattributable `TypeError`

**Reported:** 2026-07-29, from the clausify formalizer-training harness
**Severity:** high — *for machine authors*. The error carries no location, so an
LLM repair loop cannot act on it and burns its entire attempt budget.

---

## STATUS (2026-07-29, third pass — the import-ordering defect is FIXED)

**All three parts now closed: the reported diagnostic, the arity-conflict bug,
and the import-ordering hazard (a).**

### The fix

`EmbedTransformer` emits a clause head **positionally** when the functor is
`-import_from`'d earlier in the same file *and* the head does not itself emit a
guarded class block (`_emit_head_positionally`). Field names are a module-local
labelling of slots; arity is the cross-module contract, so a positional head
binds against whatever class the import supplied and a local labelling can no
longer contradict a foreign class. Explicitly-written keyword arguments in a
head still bind by name — they name a field on purpose.

The second condition is what keeps **Phenomenon A** working: when a head *does*
emit a class block (a functor's first clause), that block re-mints the class to
exactly the derived fields unless they already match, so the bound class is
known at that point and keyword emission is precise. `au/firb/computation.clausal`
and `us/sara_irc_tax/computation.clausal` import a 0-arity vocabulary atom and
then define a same-named predicate, relying on exactly that re-mint.

`_check_head_signature` is deliberately left running for imported functors: the
local declaration's arity is still an in-file contract, and no corpus file
disagrees with it.

### What it costs

* `tests/fixtures/fnmismatch_use.clausal` now **loads**, so
  `TestDirectiveMintedPlaceholderMismatch` asserts that (identity shared with
  the exporter) instead of the raise.
* `tests/fixtures/atomshadow_use.clausal` still raises, but through the
  positional-overflow check rather than the keyword path: "constructed with 2
  positional argument(s) / registered with 0 field(s) ()". Attribution and the
  Phenomenon-A hint are unchanged; the only loss is that
  `_construction_hint` can no longer see logic-variable-shaped supplied names,
  so it says "likely" where it used to say "almost certainly".
* `CLAUSAL_BYTECODE_TAG` 5 → 6.

### Evidence

* Suite: `1 failed, 10406 passed, 136 skipped, 44 xfailed` before →
  `1 failed, 10419 passed, 136 skipped, 44 xfailed` after (+13 in
  `tests/test_functor_import_ordering.py`; 7 of those 13 fail on the parent
  commit). The one failure is the pre-existing `test_doc_snippet_coverage.py`.
* `tests/test_functor_reexport.py` (the re-export identity tripwire) and
  `tests/test_functor_arity_conflict.py` pass untouched.
* Corpus codegen differential over all 767 `.clausal` files in
  `/workspace/clausify-domains` (sha256 of `ast.unparse`): **exactly 2 files
  change**, `au/firb/computation.clausal` and
  `us/sara_irc_tax/computation.clausal`, **one line each** — the *second*
  clause of the predicate that shadows an imported 0-arity atom
  (`query_date(p=…, query_date=…)` → `query_date(…, …)`,
  `dependents_count(case=…, n=…)` → `dependents_count(…, …)`). The first clause,
  which mints the class, is unchanged. No re-export module changes, because a
  re-exported functor has no local clause head.
* Load sweep of all 767 files: identical OK/ERR outcome on both trees (704 OK,
  63 pre-existing environmental failures), including both changed files.
* All 210 domain test files under `/workspace/clausify-domains/*/tests/` run
  through `python -m clausal.testing`: byte-identical results on both trees
  (189 PASSED; the 21 failures are pre-existing and environmental).

### Adjacent hazard found, NOT introduced here and NOT fixed

A module that defines a clause for a functor it imported **replaces** that
functor's clause list rather than extending it: after loading such a module the
exporter's own facts are gone from the shared class. Verified identical on the
parent commit (it was simply unreachable before whenever the field spellings
differed, because the keyword head raised first). Worth its own todo — now filed as
`todo/imported-functor-clause-list-replaced-not-extended.md`, with a verified
reproduction and the extend-vs-refuse design question.

---

## STATUS (2026-07-29, second pass — the actual defect)

**Reported bug: FIXED. Positional-overflow sibling bug: FIXED.
Import-ordering hazard (explanation (a)): open by decision, argued below.**

> **Superseded by the third pass above — (a) is now fixed.** The reasoning in
> this section is still correct about *why no winner can be imposed*; the fix
> imposes no winner, it removes the field-name axis from the head instead.

### The two competing explanations, reconciled

Neither was the cause of the reported failure.

* **(b) — the anonymous-`_` placeholder — is WRONG, twice over.**
  `_derive_field_names`' `base = arg.id.lstrip("_").lower() or f"arg_{i}"`
  fallback is unreachable: `_is_logic_var_name` rejects `_`, `__*` and every
  all-underscore spelling *before* that branch, so `lstrip("_")` can never be
  empty there. And the shape from the report,
  `decide_amlr_bo_chain(PROFILE, amlr_bo_chain_verdict(STATUS, _))`, is a
  **body goal**: body goals are emitted positionally
  (`Call(func=LoadName('f'), args=[…])`), never as keywords, so their argument
  spellings cannot mismatch anything. A `_` in a *head* does derive `arg_i`,
  but the declared signature overlays it by position. Regression-tested.
* **(a) — the declaration-vs-`-import_from` ordering — is REAL but is not this
  bug.** It reproduces exactly as traced (the two fixtures still demonstrate
  it), and it is genuinely order-dependent. It is not what the reproduction
  package hits. See *Decision on (a)* below.
* **The actual cause is a third thing, present in a SINGLE module:** a functor
  whose declaration and whose clause disagree on **arity**.

### Minimal repro (one file — the earlier "needs cross-module" note was wrong)

```
-module(m, [
    f(A)
])

f(1, 2),

Test("x") <- ( f(A, B), A == 1 )
```
→ `__init__() got an unexpected keyword argument 'arg_1'`

Mechanism: `-module` mints `f` with `_fields=('A',)`. The clause head derives
`['arg_0','arg_1']`, and the overlay loop

```python
for i in range(len(arg_field_names)):
    if i < len(prev_fields):
        arg_field_names[i] = prev_fields[i]
```

only renames the positions that *fit*; position 1 keeps `arg_1`, and the head
is emitted as `f(A=1, arg_1=2)` against a one-field class. Two clauses of the
same functor with different arity (no directive at all) do the same thing.

In `repro-arg1-scratch/` the offender is `constants.clausal`: the `-module`
export list declares `amlr_bo_chain_threshold_bps(THRESHOLD_BPS)` (arity 1)
while the fact — and every use in the package — is arity 2.

### What was fixed

1. **`clausal/templating/term_rewriting.py` — compile-time signature check.**
   `EmbedTransformer._check_head_signature` rejects a clause head that names a
   field the bound class does not have. In practice that is an arity overflow;
   a functor name has exactly one arity in Clausal, so it is a source error,
   not something to resolve. Supplying *fewer* arguments than declared is still
   allowed (it builds a partial head whose trailing fields become fresh
   `Var()`s — a documented `PredicateMeta.__call__` behaviour). The error names
   the functor, both arities, both source lines *in its own file* and both
   source texts. `EmbedTransformer` now takes a `filename` so the message does
   not read as an error in whichever file imported it.
2. **`clausal/logic/predicate.py` — positional overflow raises.**
   `PredicateMeta.__call__` used to *drop* positional arguments past
   `len(_fields)`, so `some_atom(A, B)` on a zero-arity class returned a bogus
   term with no error at all — worse than the keyword path, which at least
   raised. It now raises the same `ClausalTermConstructionError`, with the same
   attribution, plus a new arity-specific hint. The former per-argument
   `if i < len(fields)` test is replaced by one length check, so the hot path
   is if anything marginally cheaper (measured: no regression; 4-ary
   construction ~1.00 µs → ~0.95 µs, within noise).
3. `CLAUSAL_BYTECODE_TAG` 4 → 5, so a stale `.pyc` for an already-broken module
   cannot skip the new compile-time check.

### Decision on (a): the import-ordering hazard is NOT changed

The brief asked which should win when a module both declares a functor locally
and imports the same name. Corpus evidence says **neither winner can be imposed
and neither ordering can be made an error**:

* 7 corpus modules declare a functor in `-module`/`-private` *and* import the
  same name. That is the blessed re-export idiom
  (`tests/test_functor_reexport.py`,
  `todo/module-reexport-imported-functor-shadows.md`). Both textual orderings
  occur in working domains: `eu/gdpr/lawfulness.clausal` and
  `eu/labour/posted_workers_long_term_trigger/__init__.clausal` declare first
  and import later; `us/irc_s121/eligibility.clausal` imports first.
* 2 corpus modules (`au/firb/computation.clausal`,
  `us/sara_irc_tax/computation.clausal`) import a 0-arity vocabulary atom and
  then define a same-named *predicate*, relying on the clause-head class block
  re-minting over the import. That is Phenomenon A
  (`implementation_plans/dict-atom-keys-vs-predicates.md`), tracked separately.

So: forcing "import wins" breaks the second group; forcing "declaration wins"
splits class identity silently — the worst failure mode in this engine, since a
same-named-but-distinct class simply yields 0 solutions. Making either ordering
a load-time error breaks the first group.

The one change that *would* fix (a) cleanly is to **emit clause heads
positionally rather than by keyword** whenever the functor is imported in the
same file. Field names are a module-local labelling of slots; arity is the
cross-module contract. Positional heads bind against whatever class the import
supplied, and any real disagreement (arity) is then caught by fix 2 above with
full attribution. That is the recommended next step — but it makes
`tests/fixtures/fnmismatch_use.clausal` load successfully, which retires
`tests/test_functor_field_name_diagnostic.py::TestDirectiveMintedPlaceholderMismatch`.
Not done here because that pass required those 11 tests to keep passing.

### Evidence

* Suite: `1 failed, 10366 passed, 136 skipped, 44 xfailed` before →
  `1 failed, 10385 passed, 136 skipped, 44 xfailed` after (+19 new tests in
  `tests/test_functor_arity_conflict.py`); the one failure is
  the pre-existing, unrelated `test_doc_snippet_coverage.py`.
* All 11 tests of `tests/test_functor_field_name_diagnostic.py` still pass and
  their messages are unchanged.
* Corpus: the generated Python for all 757 loadable `.clausal` files in
  `/workspace/clausify-domains` is **byte-identical** before and after
  (sha256 of `ast.unparse` per file), so the compile-time fix has provably zero
  corpus effect. No corpus file contains a declaration/clause arity conflict.
* The runtime fix's only internal caller at risk is
  `clausal/logic/builtins/_registry.py::_MultiArityBuiltin.__call__`, which
  falls back to the max-arity class when an unregistered arity is requested.
  For `arity > max` that fallback silently dropped arguments; it now raises.
  Nothing in the suite relied on it.
* Not done: the 62 differential harnesses in `/workspace/clausify-domains`
  could not be run here — they need `formalize_lib`, which ships with the
  clausify harness and is not present in this environment.

### New message

```
functor amlr_bo_chain_threshold_bps/2 conflicts with the declaration of
amlr_bo_chain_threshold_bps/1 in the same file
  declared: …/constants.clausal:8 (-module export list) — amlr_bo_chain_threshold_bps(THRESHOLD_BPS)
  clause:   …/constants.clausal:22 — amlr_bo_chain_threshold_bps(2500, cite(eu_reg_2024_1624_art_52_1)),
amlr_bo_chain_threshold_bps's class is minted with 1 field(s) (THRESHOLD_BPS),
so a 2-argument head cannot be built against it. A functor name has exactly one
arity in Clausal: give the declaration and every clause head of
amlr_bo_chain_threshold_bps the same number of arguments, or rename one of them.
```

---

## STATUS (2026-07-29, first pass — diagnostics)

**Diagnostic: DONE. Underlying codegen defect: OPEN (deliberately).**

### What reproduced

The bug **does** reproduce on the current tree (`dot-attribute-access`), contrary
to the original note that it did not. Both flavours of the identical bare
`TypeError` were reproduced from scratch with two-module fixtures:

1. **Placeholder vs derived field names** (the reported `arg_N` message).
   `tests/fixtures/fnmismatch_schema.clausal` + `fnmismatch_use.clausal`.
2. **Phenomenon A** — an imported 0-arity atom shadowing a same-named exported
   predicate (`implementation_plans/dict-atom-keys-vs-predicates.md`).
   `tests/fixtures/atomshadow_schema.clausal` + `atomshadow_use.clausal`.

### Root cause (traced, NOT fixed)

The rewriter emits the guarded functor-class block at the position of the
declaration that first registers the functor (`-module` / `-private` /
`-dynamic` export list), and emits the `-import_from` as a plain Python
`from <mod> import <name>` at *its* source position. When a module both
declares a functor locally and imports the same name, the import runs **after**
the class block and rebinds the module global to the *foreign* class — but
`EmbedTransformer._seen_functors` still holds the **local** field names, so
every later construction site in that file is emitted with local keyword names
against the foreign class:

```
-module(use, [verdict(STATUS, CITATIONS)])       # mints class _fields=('STATUS','CITATIONS')
-import_from(schema, [verdict])                  # rebinds `verdict` -> schema's class
verdict("ok", [])                                # verdict(STATUS=…, CITATIONS=…) -> TypeError
```

The `arg_N` flavour is the same mechanism with a `-dynamic(f/N)`-minted class on
one side: `-dynamic` mints `('arg_0', …, 'arg_{N-1}')` and only a *real clause in
the same file* unseats it (`_unseat_directive_minted`), so an exporter whose
`-dynamic` has no clause exports a class named `(arg_0, arg_1)` no matter what
its `-module` export list spells.

The guard inside `_make_functor_class_ast` (re-`class` when `_fields` differ)
protects only sites where a class block is *re-emitted*; it cannot protect a
construction site whose class block already ran before the import.

**Not fixed here**, because "which declaration should win — the local one or the
import?" is a semantics decision, and the brief asked for diagnostics. Filed as
the open half of this todo (see *Remaining* below).

### What changed

Diagnostics only. Behaviour of field naming is unchanged.

* `clausal/logic/predicate.py`
  * new `ClausalTermConstructionError(TypeError)` carrying `functor`, `arity`,
    `supplied_fields`, `registered_fields`, `registered_at`, `constructed_at`;
  * `PredicateMeta.__call__` wraps `cls.__init__(instance, **kwargs)` and, when
    the kwargs are not all fields of the class, re-raises with the full context.
    Any other `TypeError` from `__init__` passes through untouched;
  * `PredicateMeta.__new__` records `cls._registered_at = (file, lineno)` by
    walking to the nearest `.clausal` (or first non-engine) frame;
  * the hint names *which of the two causes* it is — placeholder `arg_N` names
    on either side → directive-minted mismatch; a 0-arity target class →
    Phenomenon A, with "un-export the predicate / import under an alias /
    keep the key a string" as the remedies.
* `clausal/templating/term_rewriting.py` — `_make_functor_class_ast` now
  positions the **whole** generated block, not just the outer `try`. The inner
  `class` statement was keeping the snippet's own line 7, so "registered by:"
  (and any traceback through a functor class block) pointed at a line unrelated
  to the declaration — sometimes past the end of the file.
* `clausal/import_hook.py` — `CLAUSAL_BYTECODE_TAG` 3 → 4 (codegen line numbers
  changed; stale `.pyc` would otherwise keep the old positions).
* `conftest.py` — a `.clausal` file whose first 30 lines contain
  `# clausal: no-collect` is skipped by automatic test collection, so a fixture
  that is *meant* to fail at load can live in `tests/fixtures/`.
* `tests/test_functor_field_name_diagnostic.py` (11 tests) + four fixtures.

Suite: `1 failed, 10314 passed` before → `1 failed, 10325 passed` after; the one
failure is the pre-existing, unrelated
`tests/test_doc_snippet_coverage.py::test_no_raw_untested_blocks`.

### Message produced

Cause 1 — directive-minted placeholders:

```
functor fnm_verdict/2 was constructed with field names (STATUS, CITATIONS)
but its class was registered with (arg_0, arg_1)
  registered by: tests/fixtures/fnmismatch_schema.clausal:8
  constructed at: tests/fixtures/fnmismatch_use.clausal:12
  (a functor minted by a directive keeps placeholder arg_N names until a real
   clause unseats it — -dynamic(f/N) with no clause in that file leaves the
   class named (arg_0, ..). Check whether both modules declare the same
   functor, and whether an -import_from rebinds this name after the local
   declaration: the import wins, so later constructions use the local field
   names against the foreign class. Fix: declare the functor in exactly one
   module and import it.)
```

Cause 2 — Phenomenon A:

```
functor ash_query_key/0 was constructed with field names (PROFILE, VALUE)
but its class was registered with ()
  registered by: tests/fixtures/atomshadow_schema.clausal:4
  constructed at: tests/fixtures/atomshadow_use.clausal:9
  (ash_query_key resolved to a 0-arity atom, but it was called with 2
   argument(s) — almost certainly an imported atom is shadowing a same-named
   predicate. A module that both exports the predicate ash_query_key/2 and
   imports the atom ash_query_key binds the atom last, so every call constructs
   the atom. Fix: un-export ash_query_key/2, or import the atom under an alias
   — -import_from(vocab, [alias(ash_query_key, AshQueryKey)]) — or keep the key
   a string.)
```

### Remaining

1. **The codegen ordering defect itself** (above). Candidate fixes: (a) make a
   local declaration and an `-import_from` of the same name a load-time error
   (or extend `ClausalAtomShadowingWarning`, which today is narrowed to atoms,
   to predicate functors); (b) have `_handle_import_from_directive` drop the
   local `_seen_functors` entry so later construction sites re-derive against
   the imported class; (c) emit imports before all class blocks. (a) is the
   safest and is pure diagnostics; (b)/(c) change resolution semantics.
2. **Phenomenon A proper** — option 3 in
   `implementation_plans/dict-atom-keys-vs-predicates.md` (arity-aware call
   resolution) still stands; the diagnostic only makes the collision legible.
3. **Silent sibling bug found while tracing:** `PredicateMeta.__call__` drops
   *positional* arguments beyond `len(_fields)` without complaint —
   `some_atom(A, B)` on a 0-arity class returns a bogus instance with no error.
   Only the keyword path is diagnosed here. Worth a separate arity check.
   *(Fixed in the second pass — see the STATUS block above.)*

---

## Symptom (original report)

Loading a generated domain fails with:

```
tests/test_load.clausal::<load> — __init__() got an unexpected keyword argument 'arg_1'
```

That is the whole message. It names:

- no source file
- no line
- no functor
- neither the expected nor the supplied field names

## Why it matters here

This harness measures whether a model can author Clausal from a spec, repairing
against gate output. The repair prompt contains the failure text verbatim, so an
unattributable error is unrepairable *by construction*: the model has nothing to
locate. Observed live — a 27B model spent **5 consecutive attempts** on this error,
producing byte-identical output each time, because there was no signal to act on.
A frontier model would fare no better; nothing in the string identifies a target.

Compare the recently-improved `-module` arity error, which now prints the offending
directive text. That change turned a 3-attempt dead end into a 1-attempt fix. The
same treatment applied here should have the same effect.

## Mechanism (as far as traced)

`clausal/templating/term_rewriting.py` mints a term class per functor. Field names
come from one of two places:

- placeholder names `arg_0 .. arg_{N-1}` when a functor is minted from a
  directive (e.g. `-dynamic`) before any real clause exists — see
  `_make_functor_class_ast` around the `field_names = [f"arg_{i}" ...]` sites;
- names derived from the head variables once a real clause registers the functor
  (`_unseat_directive_minted`).

When the same functor ends up constructed against a class minted under the *other*
naming regime — e.g. the same functor name registered in two modules, or a
directive-minted class not unseated before a sibling module constructs it — the
constructor is called with `arg_1=...` against a class whose fields are named after
head variables (or vice versa). Python raises the bare `TypeError`, which propagates
with no Clausal-level context attached.

Not yet isolated to a minimal repro; the trigger involved a multi-module package
where `schema.clausal` exported a constructor `amlr_bo_chain_verdict(STATUS, CITATIONS)`
and sibling modules referenced the same functor.

> **Confirmed 2026-07-29.** The mechanism above is exactly right; see STATUS.

## Note on reproduction

The failure was observed against an older interpreter (`/workspace/clausal` on the
GPU box). It did **not** reproduce on the newer tree, so it may already be fixed or
merely masked. Worth confirming before investing in a fix — but the *diagnostic*
weakness below is worth addressing regardless, because any future field-name
mismatch will surface just as opaquely.

> **Superseded 2026-07-29.** It does reproduce on the newer tree — see STATUS.
> The original non-repro was presumably a different module ordering, not a fix.

### Original reproduction package and command (preserved from the source report)

The **underlying codegen defect is still open** (only the diagnostic was fixed),
so the original reproduction is kept here verbatim — it is the starting point
for whoever fixes the real bug.

A reproducing package is preserved at `repro-arg1-scratch/` in the repo root.
**It is untracked** — 29 files, a copy of the `eu/aml/amlr_bo_chain` domain. Do
not clean it up without first confirming a minimal repro exists, or the
reproduction is lost.

```
CLAUSAL_ROOT=/workspace/clausal python3 -c "
from pathlib import Path
from auto import runclausal          # from /workspace/clausify-executor-train
p = Path('/workspace/clausal-bug-fix/repro-arg1-scratch/eu/aml/amlr_bo_chain/tests/test_load.clausal')
print(runclausal.run_clausal(p)[1])"
```

→ `test_load.clausal::<load> — __init__() got an unexpected keyword argument 'arg_1'`

### Original narrowing (hypothesis, NOT confirmed by the diagnostic work)

- **Not an arity mismatch.** `schema.clausal` declares
  `amlr_bo_chain_verdict(STATUS, CITATIONS)` and every use across the package is
  arity 2. The conflict is in FIELD NAMES.
- **Suspected source** — `term_rewriting.py` around line 1671:
  ```python
  base = arg.id.lstrip("_").lower() or f"arg_{i}"
  ```
  An anonymous `_` argument strips to the empty string and falls back to
  `arg_{i}`. The failing package contains exactly that shape:
  `decide_amlr_bo_chain(PROFILE, amlr_bo_chain_verdict(STATUS, _))` — which
  would derive `(status, arg_1)` where the declaration derives
  `(status, citations)`.
  **Note:** the 2026-07-29 tracing attributed the failure to the
  declaration-vs-`-import_from` binding order instead (see *Root cause* above).
  These two explanations have NOT been reconciled; both may contribute.
- **A single-module minimal case does NOT trigger it.** Declaring
  `verdict(STATUS, CITATIONS)` and using `verdict(V, _)` in the same file loads
  fine, so the unseating logic handles the simple case. Cross-module use is
  therefore likely required; a minimal cross-module repro was not isolated.

## Requested fix

Attach Clausal-level context wherever a term class is constructed, so the message
answers "what, where, and what did you expect":

```
functor amlr_bo_chain_verdict/2 was constructed with field names (arg_0, arg_1)
but its class was registered with (status, citations)
  registered by: eu/aml/amlr_bo_chain/schema.clausal:11
  constructed at: eu/aml/amlr_bo_chain/tests/test_load.clausal:17
  (a functor minted by a directive keeps placeholder arg_N names until a real
   clause unseats it — check whether both modules declare the same functor)
```

Wrapping the constructor call site to catch `TypeError` and re-raise with the
functor name, both field-name tuples, and the two source locations would be enough.
The tail of the hint matters as much as the locations: it names the *class* of
mistake, which is what lets an author choose a different fix instead of re-rolling
the same one.

> **Done 2026-07-29** — implemented at `PredicateMeta.__call__`, which is the
> single choke point for every term construction. See STATUS.

## Related

- `-strict_atoms` is now deprecated (strict resolution is the default). The
  clausify harness stopped emitting it in scaffold templates and stopped teaching
  it in the authoring prompt as of this date.
- `implementation_plans/dict-atom-keys-vs-predicates.md` — Phenomenon A, the
  second cause of the identical bare `TypeError`.
- `todo/module-reexport-imported-functor-shadows.md` — class *identity* across a
  re-export chain is preserved; this bug is about *field names*, which are not.
- `todo/done/atom-identity-cross-module-mismatch-diagnosability.md` — same family
  of "make a cross-module name collision legible" work.
