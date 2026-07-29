# Bug: functor field-name mismatch surfaces as a bare, unattributable `TypeError`

**Reported:** 2026-07-29, from the clausify formalizer-training harness
**Severity:** high — *for machine authors*. The error carries no location, so an
LLM repair loop cannot act on it and burns its entire attempt budget.

---

## STATUS (updated 2026-07-29)

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
