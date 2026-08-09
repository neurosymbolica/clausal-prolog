# `name 'X' is not defined` does not name the sibling module that exports X

**DONE** 2026-07-30 on `fix/nameerror-names-the-sibling-exporter`.

(Module paths and error transcripts below are paraphrased with invented,
neutral names — the error class and structure are reproduced exactly.)

## Symptom

A module in a decomposed-DAG package uses a predicate exported by a sibling module
but forgets to import it. The engine raises a bare Python `NameError`:

```
FAILURES:
  test_load.clausal:64 :: constants legitimate behaviour grounds are defined with citations — name 'cite' is not defined
    goal 1 of 6 raised:
      rulebase.compliance_screening_rule.constants.legitimate_behaviour_grounds(GROUNDS)
      NameError: name 'cite' is not defined
```

`constants.clausal` had `-import_from(...citations, [mar_art_9])` and used `cite(mar_art_9)`
in a dict value. `citations.clausal` declares `-module(citations, [cite(KEY), ...])`.
The owner of the missing name is fully decidable from the package, and the message says
nothing about it.

## Why it matters

Contrast the `strict_atoms` message for the exactly analogous mistake on an *atom*:

```
strict_atoms: undeclared atoms 'acquire', 'amend', ... in rulebase.compliance_screening_rule.constants
      bare atom references must be one of:
        - listed in -module(...)
        - listed in -private([atom, ...])
        - imported via -import_from(from_module, [atom])
        - qualified (e.g. other_module.atom)
        - obtained via global_atom("atom", Atom)
```

That one lists remedies, so a reader can act on it. The predicate case gets a raw
`NameError` with no remedy and no owner.

Measured in a local-model formalization study: `NameError: cite`
burned **16 attempts across 3 runs and never recovered** — every retry produced a
byte-identical response, because there is nothing in the message to act on. It is the
top unrecovered failure that is not attributable to the harness.

## Requested behaviour

When a `NameError` for name `X` is raised while loading or solving in module `M`, and
some other module in the same package declares `X` in its `-module(...)` export list,
name it. Fall back to today's message when no sibling declares the name (that case is
genuinely undecidable and should stay as-is).

## What shipped

```
NameError: name 'cite' is not defined
  `cite` is neither defined nor imported in constants.clausal.
  cite/1 IS exported by a sibling module in the same package:
      rulebase.compliance_screening_rule.citations
  -> add `cite` to this file's existing import:
      -import_from(rulebase.compliance_screening_rule.citations, [mar_art_9, cite])
```

The remedy distinguishes extending an existing `-import_from` for that module from
writing a new one, because the reported failure already had a directive for the very
module it needed one more name from — "add `-import_from(citations, [cite])`" would have
told the author to write a second directive beside the one they had. The list is quoted
back verbatim, aliases included (`alias(art_9, a9)` stays spelled that way); an entry
that could not be spelled makes the whole extension form decline rather than reprint a
list with a name silently dropped.

The stock first line is untouched, and `args` is CPython's own byte for byte — the hint
renders in `UndefinedNameError.__str__` only, the same discipline as the `is`/`==` note.

## Raise paths covered

* **solve time** — `clausal.logic.solve._drive_trampoline`, in an `except NameError`.
  It is the outermost driver for `call`, `solve` and the REPL, so every goal-level raise
  arrives there, and a solution never touches it.
* **load time** — `clausal.import_diagnostics.exec_with_import_diagnostics`, which
  already wrapped the module-body `exec` for `-import_from` failures and is used by both
  `_load_module` call sites. Covers `REF = cite(art_9)` at module scope.
* **the term-class shape** — `_DbDispatchAdapter.__call__` raises its own NameError
  (`Predicate 'cite/1' is not in scope as a term class`) whenever the compiler saw the
  name as a call target. It now passes `name=`, so the solve-time seam enriches it too:
  one mistake, two stock sentences, both now naming the owner.

Neither seam needs its caller to say which module failed — the module is recovered from
the innermost `.clausal`/`.pl` frame in the traceback, whose globals carry `__name__` and
`__file__`. That is also the guard against misattributing an ordinary Python `NameError`.

## Deliberately not covered

* **Predicate compilation** (`compile_module` / `_compile_all_pending`) runs *after* the
  `exec` in `_run_v2_pipeline`, so a NameError raised there is outside the load seam. No
  reproduction was found; if one turns up the seam moves out one level.
* **`import_hook._unterminated_fact_error`** raises a NameError with its own message for
  a comma-less bodyless fact and does not set `name=`, so it is never enriched. Its
  diagnosis (add the comma) is about the *head*, and is usually the right one.
* **The strict-atoms compile-time NameError** is untouched — it is the message this todo
  held up as the good one.
* **Near-miss suggestion for a typo'd name** — explicitly a bonus in the todo, not built.
* **Bare-atom exports.** `_declared_export_entry` returns the rendered entry, so a
  sibling exporting `cite` as a bare atom would be named as `cite` rather than `cite/1`.
  Untested, because an undeclared *atom* is a strict-atoms failure and never reaches
  here.

## Prior art reused

The sibling scan is the one `clausal/predicate_diagnostics.py` already ran for
`Predicate name/N not found` — `_sibling_source_files`, `_loaded_module_for`, the capped
scan, the substring pre-filter, and `_sentence`/`_arrow`/`_INDENT` from
`import_diagnostics`. One widening: `_declared_arity` was split, with its arity-parsing
kept as a thin wrapper over a new `_declared_export_entry` that returns the export as
declared. `_declared_arity`'s three-valued contract is byte-identical and its 23 tests
are untouched; the split exists because that function conflates "exported without an
arity" with "could not read the file" in a single `None`, and this diagnostic asks the
weaker question — is the bare name in that export list at all.

## Filed separately

`todo/catch3-does-not-catch-an-exception-from-a-trampolined-subgoal.md` — found while
checking that the new seam could not steal an exception `catch/3` wanted.

## Review findings, applied 2026-07-30

An independent review of the branch raised three, all Low, all applied before
merge:

1. **The sibling scan ran at least twice per failure** — once as a discarded
   gate inside `enrich_undefined_name`, then again in `__str__`, and again on
   every later render (`catch/3`'s `python_error_term` conversion reads
   `str(exc)`). The gate's result is now handed to the exception and reused;
   `__str__` still computes when handed none, so a directly-built instance is
   not silently hintless.
2. **`_import_remedy` advised a duplicate directive.** When the file already
   imported the name from the exporting module, the loop fell through to the
   "write a new `-import_from`" form. It now declines: whatever went wrong in
   that state, it is not a missing import, and the sentence naming the exporter
   still stands.
3. **The 60-file cap declines silently**, which the predicate-not-found path
   deliberately does not do (it reports `total`). Kept as-is and documented in
   `_exporting_sibling` rather than changed. Reporting the cap would mean
   attaching "no exporter found, but only 60 of N were scanned" to a *plain*
   `NameError` — i.e. to every typo'd Python name in a large package. The other
   diagnostic is already being printed so its cap note is free; this one would
   have to manufacture a message to carry it. **Known gap:** in a package with
   more than 60 sibling sources, an exporter sorting past the cap yields no
   hint and no indication that a scan was bounded.
