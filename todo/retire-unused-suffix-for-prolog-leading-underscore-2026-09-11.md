# Retire the `_UNUSED` suffix; a leading underscore means unused, as in Prolog

**Raised by the operator, 2026-09-11.** Adopt the Prolog de-facto standard — a leading
underscore marks a variable the clause does not use — and delete the `_UNUSED` suffix
system. With the carve-out for uncased scripts described below.

## The proposal, as stated

> Remove that `_UNUSED` suffix system and go to the Prolog de-facto standard: leading
> underscore is unused. The only issue is that if foreign-language non-cased identifiers are
> needed (e.g. Japanese), they would be forced to use a leading underscore for variable names.
> So then there is no distinction, all names look unused. The analyser could look at the letter
> behind the `_`: if it is e.g. Japanese, it is not understood to be unused, and instead it
> looks for a trailing underscore to indicate unusedness.

## Why it fits, and why it could not have been proposed before today

The variable rule after 2026-09-10 is: underscore-led (not `__`-led, not bare `_`) **or**
capital-initial. An uncased script has no capital form, so `円周率` is not a variable and
`_円周率` is the ONLY spelling available — the leading underscore is forced, and can carry no
meaning. That is exactly the operator's objection, and it is real: measured on this tree,
`_is_logic_var_name('円周率')` is False and `_is_logic_var_name('_円周率')` is True.

The proposed fallback marker is a trailing underscore on an underscore-led name — `_円周率_`.
**That spelling is not free today: it is the module-constant class.** Measured:

    _x_       is_var=False   is_constant=True
    _X_       is_var=False   is_constant=True
    _円周率_   is_var=False   is_constant=True

`feat/lowercase-constants-2026-09-11` retires that class (its Task 6 deletes
`_is_constant_name` from all five `_is_logic_var_name` copies), at which point all three
become ordinary variables and the spelling becomes available. **So this work is strictly
downstream of that branch** — starting it first would put two agents in
`_is_logic_var_name` and its five copies at once, which is the "two moving inputs" failure
this project has paid for repeatedly.

## The test is "is the character after the leading underscore cased?" — not the alternatives

The operator's own formulation is the right one, and the two plausible-sounding alternatives
are both wrong. Worth writing down so neither gets "simplified" in later:

- **Not "does the name contain any cased letter".** `_円周率X` contains one, but dropping the
  underscore gives `円周率X`, which is not capital-initial and so is an atom. The underscore is
  still forced.
- **Not "would it still be a variable without the leading underscore".** That test puts `_x`
  in the forced bucket (since `x` is an atom), so `_x` would stop meaning unused — which
  breaks the very Prolog convention being adopted. A Latin-lowercase name has a capital form
  available (`X`); an uncased one does not. The difference is the SCRIPT, so the script is
  what to test.

Python has no `str.iscased`, so the predicate is `c.isupper() or c.islower()`.

**Decide the non-letter edge:** `_1` and `_1_` are both legal identifiers and a digit is
uncased, so `_1` lands in the forced bucket and would need `_1_` to be marked unused. That is
probably fine (there is no uppercase `1` either), but it is an accident of the predicate rather
than a decision, so pin whichever answer is chosen in a test.

Unaffected: bare `_` (anonymous, always fine), `__`-led names (not variables at all), and the
per-file `-allow_singletons` opt-out.

## The one real semantic question: assert, or merely suppress?

Today `_UNUSED` **asserts**: `_warn_singletons` warns when a `*_UNUSED` name occurs *more than
once* ("marked _UNUSED but occurs more than once in its clause"), as well as warning about an
unmarked singleton. ISO/SWI's leading underscore only **suppresses** — `_Foo` used three times
is silent.

The proposal's phrasing ("all names look unused") implies the asserting reading, and that is
the stronger lint. But it changes existing code in the noisy direction: every `_foo` used twice
on purpose starts warning, where today it is silent. The suppressing reading changes code in
the quiet direction instead: every underscore-led singleton stops being reported, which loses
real typo-catching.

**This cannot be settled by reading the source.** The measurement is: implement the predicate,
run the engine suite and downstream code with each reading, and count the warnings each produces.
Do that before choosing.

## Migration cost, measured 2026-09-11

Counted by walking the filesystem for `.clausal`/`.seam` files, matching identifiers ending
`_UNUSED` (excluding CPython's `Py_UNUSED` macro, which is why the C files must not be counted):

| tree | seam files | occurrences | distinct names |
| --- | --- | --- | --- |
| engine (`/workspace/clausal`, `/workspace/clausal-bug-fix`) | 100 | 423 | 163 |
| the live sibling corpus | **0** | 0 | 0 |
| frozen study snapshots under that tree | 58 | 322 | 35 |

Top engine names: `X_UNUSED` ×55, `_x_UNUSED` ×39, `Y_UNUSED` ×25, `_X_UNUSED` ×11,
`_OUT_UNUSED` ×10. Note that `_x_UNUSED` and `_X_UNUSED` are already belt-and-braces — they
become simply `_x` and `_X`, which is a deletion rather than a rename.

**A correction worth keeping, because the first instrument failed open.** `git grep` over the
sibling repos reported **0** occurrences downstream; the filesystem walk reported **322**. Both
were right about different things — the files are untracked — and the git-grep number would
have gone into a commit message as "0 downstream" if the slower instrument had not also been
run. The reconciliation is that all 322 are under `_reruns/`, which are frozen records of past
runs and must NOT be migrated: they are evidence of what was executed, and rewriting them
falsifies the record. They would emit singleton *warnings* if ever re-loaded, which is
acceptable; say so rather than discovering it.

## Sketch of the change

Small and contained — the whole system is 6 references:

- `clausal/templating/term_rewriting.py:5170-5182` (`_warn_singletons`) — the only behavioural
  site. Replace the `ident.endswith("_UNUSED")` test with the new predicate, and rewrite the
  remedy text in the singleton warning (it currently offers `` `{ident}_UNUSED` (or `_`) ``).
- `clausal/templating/term_rewriting.py:7544` — the `-constants` warning that exists solely to
  stop a constant name colliding with the marker. When the marker goes, this goes. It sits in
  code `feat/lowercase-constants-2026-09-11` is already editing, which is a second reason to
  sequence after it.
- `clausal/lint_warnings.py:19` — the `ClausalSingletonWarning` docstring, which documents the
  suffix as the suppression mechanism.
- The 100 engine seam files.
- `docs/directives.md`, `docs/exceptions.md`, `docs/currency.md`, `docs/examples.md`,
  `docs/metainterpreters.md`, `docs/csv.md`, `docs/for_prolog_programmers.md` all name the
  suffix; `tests/test_doc_snippet_coverage.py` compiles the ```clausal blocks, so a bad
  migration shows up there.

## Definition of done

- A predicate (name it for what it decides, e.g. `_is_unused_marked_name`) implementing the
  cased/uncased split, with tests covering `_x`, `_X`, `X`, `_円周率`, `_円周率_`, `_1`, `_1_`,
  `__x` and `_`.
- `_warn_singletons` keyed on it; the assert-vs-suppress question answered with the warning
  counts that decided it, stated in the commit.
- `_UNUSED` gone from the engine source, the 100 seam files, and the docs.
- The frozen `_reruns/` trees deliberately untouched, and the commit says so.
- Full-suite failure-NAME-SET diff against the baseline, plus a warning-count comparison —
  a lint change moves warnings, not failures, so a green suite proves nothing on its own here.
