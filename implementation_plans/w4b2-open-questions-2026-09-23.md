# W4b-2 open questions, answered from the code — 2026-09-23

Read-only pass over `/workspace/clausal` main (`ad882878`). Every claim below
is either (a) a file:line citation, (b) the verbatim output of a probe run
via `./venv/bin/python -c "..."` from the repo root during this session, or
(c) explicitly marked INFERENCE where I could not run a probe. No source was
changed; no test suite was run to a green/red verdict (that is out of scope
for a read-only pass and is called out explicitly wherever it matters).

---

## Question 1 — the handle discriminator

### 1.1 What actually distinguishes a handle from a `-hide` data atom

**Not `db.declared_kind` alone, and not the landed `sys.modules`-membership
test alone.** Three facts, each verified by a probe:

**Fact A — mangling convention differs by declaration kind.** A `-hide` data
atom is mangled with the *declared* `-module(name, …)` name
(`clausal/templating/term_rewriting.py:8130-8168`, `module_name = args[0].id`
— a bare, non-dotted identifier; dotted names are refused at that line). A
future predicate handle (piece "mint handles with the import name", not yet
built) is specified to mangle with the *Python import name*
(`clausal/logic/cells.py:544`: "the module half is the IMPORT name, dotted
for a nested module"). These are two different strings that can coincide.

**Fact B — `declared_kind` cannot see a `-hide` atom at all.** `-hide` never
calls `declare_functor` (verified: `grep -rn "mangle(" clausal/` shows only
two call sites, both in `-hide` compilation,
`clausal/templating/term_rewriting.py:3509,8430`; `declare_functor` is
called only from `compiler_v2._process_directives` for field-carrying
`-module`/`-private`/`-import_from` entries — scope doc §"Three homes").
Probe:

    db.declared_kind('hide_secret', 0)  ->  None   # not "data", not "predicate"

on `tests/fixtures/hide_owner.clausal`'s own db. An *undeclared, nonexistent*
name in the same module answers the same `None`. **`declared_kind` alone
cannot tell a genuine `-hide` atom apart from a typo** — both are simply
absent from `db._declared` and `db._rows`.

**Fact C — the landed `qualify_mangled_goal` (`clausal/logic/cells.py:530`)
uses neither.** It checks only `module_name in sys.modules` (lines 557, 563).
That is weaker than either fact above, and it is demonstrably wrong in two
reproduced ways:

**Probe 1 — module-half collides with an unrelated loaded module.** A
`.clausal` file declaring `-module(os, [holds/1]) -hide([hide_secret])`,
loaded while the real `os` is also imported (always true in practice):

    mangle('os', 'hide_secret')  ->  qualify_mangled_goal(...)  ->  (':', 'os', 'hide_secret')
    solve(that_atom)  ->  PredicateNotFoundError: Predicate hide_secret/0 not found
                            os defines no predicates of its own.

`PredicateNotFoundError` is `clausal/predicate_diagnostics.py:78`, a plain
`KeyError` subclass — **not** `LogicException`. This is not a wrong-message
bug, it is an **uncatchable Python exception escaping through `catch/3`**
where the engine's own contract promises a `LogicException`.

**Probe 2 — module-half is the module's own declared name, loaded under
that same key (the ordinary, non-package-nested case).** Loading
`hide_owner.clausal` at `sys.modules['hide_owner']` (matching its
`-module(hide_owner, …)` name — the common case for a top-level module, as
opposed to `tests/test_hide_directive.py`'s own fixture loading, which
deliberately uses the dotted `tests.fixtures.hide_owner` key and so never
triggers this):

    mangle('hide_owner', 'hide_secret')  ->  qualify_mangled_goal(...)
        ->  (':', 'hide_owner', 'hide_secret')     # WRONG: not a handle
    solve(that_atom)
        ->  error(existence_error(procedure, hide_owner:hide_secret/0),
                   "... (reached through a module-qualified handle)")

Compare the *intended* path — module truly not loaded
(`tests/test_w4_qualified_handle.py:163-171`,
`test_a_mangled_atom_whose_module_is_not_loaded_keeps_the_atom_error`):

    _dispatch_at(mangle('no_such_module_anywhere', 'secret'), 1)
        ->  error(existence_error(procedure, no_such_module_anywhere.secret/1),
                   "atom '...' is not callable at arity 1 (resolved via a
                    data reference; define or import the predicate, ...)")

Both happen to be `error(existence_error(procedure, …), …)` — so a
`catch(G, error(existence_error(procedure,_),_), _)` does not distinguish
them functionally — but the **indicator shape differs** (module-qualified
`M:(name/N)` vs. bare `name/N`) and the **message actively misdescribes the
mechanism** ("reached through a module-qualified handle" for something that
is not a handle). Probe 1's collision is strictly worse: a different,
uncatchable exception *type*. This is exactly the gap the scope doc names at
risk #4 and the landed commit's own docstring half-answers ("mangling alone
does not discriminate; the row does") without actually implementing the
row check.

### 1.2 The concrete discriminator proposal

Two tests, composed, replacing the bare `module_name in sys.modules` at the
two call sites inside `qualify_mangled_goal`:

```python
# clausal/logic/cells.py, inside qualify_mangled_goal, replacing the two
# `if module_name in sys.modules:` guards:
from clausal.logic.predicate import _db_for_module_name  # noqa: PLC0415  (lazy: avoids the existing predicate<->cells cycle predicate.py:1400 already routes around)

def _is_handle(module_name: str, name: str, arity: int) -> bool:
    db = _db_for_module_name(module_name)          # None unless module_name
    if db is None:                                  # is a LOADED .clausal module
        return False
    return db.declared_kind(name, arity) != "data"
```

`_db_for_module_name` (`clausal/logic/predicate.py:1537-1554`) already
exists and already does exactly the right module-validity check: it reads
`sys.modules.get(module_name)` and then requires
`mod.__dict__["$module"].db`, which the real `os` module (Probe 1) does not
have and a genuine `.clausal` module (Probe 2) does — so this closes Probe 1
outright (`_db_for_module_name('os')` verified `None`).

Probe 2 needs more than module validity — `hide_owner`'s db is real. Here
the `!= "data"` (rather than `== "predicate"`) shape matters and was chosen
against a specific counter-example, verified: `test_a_missing_predicate_
error_names_the_module_in_its_indicator` calls `mangle(LIB, "nope")` where
`nope` is declared nowhere at all in `LIB`, and the landed test requires
this to STILL qualify and raise a proper `existence_error` naming the
module — i.e. an unknown name in a real module must keep qualifying, only a
name **known to be data** must not. `declared_kind(name, arity) == "predicate"`
would wrongly reject `nope` too (breaks that test); `!= "data"` accepts
`nope` (`None != "data"`) and rejects only a name affirmatively recorded as
data — but **Fact B says `-hide` never produces that record**, so `!= "data"`
alone leaves Probe 2 exactly where it is (`declared_kind('hide_secret',0)`
is `None`, and `None != "data"` is `True`) — I verified this by running the
candidate function above against all six cases (script preserved at
`/tmp/.../scratchpad/probe_discriminator.py` for this session); it fixes
Probe 1 and the "nope" test, but **does not** fix Probe 2.

**The missing piece, not yet built:** `-hide` must register into
`db._declared` the same way `-module`/`-private` field-carrying entries do
— `db.declare_functor(atom_name, ())` (empty fields, since `-hide` entries
are always bare 0-arity atoms — enforced at
`clausal/templating/term_rewriting.py:8143-8148`) at the same compile site
that already calls `mangle()` (`term_rewriting.py:8430`), paired with a
runtime emission alongside the existing hidden-atom-assign statement. Once
that lands, `declared_kind('hide_secret', 0)` answers `"data"` and the
`!= "data"` test above closes Probe 2 too. This is genuinely new work, not
a read of an existing accessor — flagging it rather than asserting it is
done, per the standards note. A side effect worth a second look by whoever
implements it: `field_names_for`'s arm 3 (`clausal/logic/predicate.py:1592-
1631`) would then also start answering `()` instead of `None` for a hidden
atom — arguably *more* correct ("declared with zero fields" is true), but
I did not exhaustively check every `field_names_for` caller for a behavior
that depends on the `None`-vs-`()` distinction specifically for a hidden
name; that check is unmade work, not a finding.

### 1.3 Real handle at an undefined arity

Verified against a real fixture (`w4qlib2`, `-module(w4qlib2, [pred(A), flag])`,
only `pred/1` defined), calling the mangled atom at the wrong arity:

    solve((mangle('w4qlib2','pred'), 1, 2))
      ->  PredicateArityMismatchError: pred takes 1 argument, but this call passes 2
          pred/1 is defined at .../w4qlib2.clausal:1.
          -> pass 1 argument to pred, or give the 2-argument predicate a
             different name: ...

This is already a good, specific error — **but it is produced by
`PredicateMeta._refuse_call_at`/`_clause_arity`** (`clausal/logic/
predicate.py:1280-1324`), a method on the CLASS that today's module
attribute is still bound to (piece "mint handles" is unbuilt, so `pred` in
`w4qlib2`'s namespace is still a `PredicateMeta` class; the mangled atom in
the probe was constructed by hand with `mangle()`, not produced by the
compiler). **Whether this arity-mismatch path survives W4b-3's class
deletion is unverified and not obviously safe** — it currently depends on
`cls._row`/`cls._clause_arity`, both retired-at-W4b-3 machinery. This is a
concrete risk to flag for whoever plans W4b-3, not resolved here.

For the `-hide` side, "arity the module doesn't define" does not apply the
same way: `-hide` entries are always arity 0 by construction
(`term_rewriting.py:8143`), so there is no analogous "wrong arity" case for
data.

### 1.4 Does `qualify_mangled_goal` already make the distinction?

No — read directly (`clausal/logic/cells.py:554-565`): both branches test
only `is_mangled(...)` then `module_name in sys.modules`. It assumes any
mangled functor whose module half happens to be a loaded module name is a
goal. Its own docstring (lines 543-549) states the *intended* rule in prose
("a mangled atom whose module half is a LOADED module … A `-hide` data atom
carries the BARE declared module name instead, which need not be an import
name") but the code does not implement the "need not be an import name"
half — it cannot, from `sys.modules` membership alone, because (per 1.1
Fact A) a declared name and an import name are drawn from the same string
space and can collide. The three other call sites all funnel through this
one function (`clausal/logic/solve.py:229,866,931,1024`,
`clausal/logic/predicate.py:1400-1401`,
`clausal/logic/builtins/higher_order.py:156`) — six call sites, one
function — so **the fix in 1.2 needs to land in exactly one place** to
reach all of them; nothing needs threading through `solve`, `call/N`, or
`_dispatch_at` individually. Compile-time sites (`seam.py:141`) do not need
the fix: they only decide whether to *build* a mangled cell, and defer
correctness to whatever resolves it at solve time, which is this function.

---

## Question 2 — the 49 IDENTITY sites, in families

**Correction to the brief's "42":** `implementation_plans/w4b1-site-
classification-2026-09-22.md`'s own "Fix round 2" (same document, its
Task 5 implementation pass) reclassified 7 more rows from SHAPE to IDENTITY
*after* the Task 4 count of 42 was written (rows 5, 9, 14, 18, 30, 31, 39).
The document's own final total is **49**, stated in its second table. I
independently re-extracted every row tagged `I` in its table (including the
fix-round-2 rows, which are marked `I` in the S/I column even though their
prose cites "fix round 2") and counted **49**, matching the document's own
stated total exactly — a positive control that the extraction is right, not
just trust in the stated number (per the running "trust a baseline number"
caution). Building families on 42 would silently drop 7 real sites,
including the two most subtle ones in the table (18/39, the coupled pair,
and 9, the shared-helper hazard). Families below are built on the 49.

| family | replacement test | rows (of 49) | n |
|---|---|---|---|
| **F1 — row-bearing machinery.** The site reads `._row`, `.clauses`, `.dispatch_fn`, `.locked`, calls `_lock()`, or hands the object to `_install`/`analyze_mi`/a mutation gate's `through=`. It needs the live `PredRow`, not a boolean. | Demangle if the binding is a handle (`_db_for_module_name`), then `db.row(functor, arity)` — `PredRow \| None`. `is not None` replaces the `isinstance` boolean; every `cls._row` read becomes the row object directly (today `cls._row` literally **is** this call, per `_state_row()`). | 4, 14, 15, 24, 25, 27, 28, 29, 32, 33, 34, 35, 36, 51, 53, 54, 55, 56, 57, 58, 59, 60, 61 | 23 |
| **F2 — "is this specifically a predicate, not data?"** The predicate-name-as-atom coercion (a bare predicate reference in term position denotes the atom of its own name; a same-shaped data functor must NOT) plus the directive-target typo guards (`-table`/`-discontiguous`/`-shallow`: "is the named thing actually a defined predicate"). Both need the identical test. | `db.declared_kind(functor, arity) == "predicate"`, **exact arity**, against the *locally compiling module's* db in the ordinary case. | 6, 12, 19, 20, 21, 23, 30, 31, 38, 43, 44, 46, 49, 50, 52 | 15 |
| **F3 — shared public helper, callers outside the 63/49 population.** `is_zero_field_class`/`_is_zero_field_class_py` is aliased and called from 4 sites the grep population never sees (`solve.py:514`, `database.py:1502`, `builtins/_helpers.py:207`, `terms_to_ast.py:1099`) — one of which (`database.py:1502` `head_key`) is itself an F2-shaped predicate-vs-data question. **Flagged NOT OBVIOUS**: the true site count for this one row is 1 declaration + ≥4 unlisted callers, so W2's census discipline (a completeness census, not a grep count) applies here specifically. | Same F2 test at the call sites; the shared function itself needs a census of its own callers before it is touched, not a drop-in swap. | 9 | 1 |
| **F4 — diagnostic with a stated must-not-raise contract.** `_arity_of` (`predicate_diagnostics.py:194`) deliberately answers `None` via `getattr(...,"_fields",None)` for a bare `class X(metaclass=PredicateMeta): pass` with no `_fields` of its own — a real, documented shape. `field_names_for`'s PredicateMeta arm reads `value._fields` with no guard and would raise. **Flagged NOT OBVIOUS**: the replacement needs to preserve graceful-`None`, i.e. cannot be a bare `field_names_for`/`declared_kind` call without a wrapping guard. | A `try/except AttributeError: return None` around whatever accessor replaces `._fields`, or an explicit `hasattr`/`getattr` reformulation — not yet designed. | 5 | 1 |
| **F5 — coupled pair: head-pattern-matcher coverage.** `terms_to_ast.py:101` (`_is_opaque_head_literal`) mirrors what `head_match.py:858`'s `head_to_match_pattern` actually handles. **Flagged NOT OBVIOUS and load-bearing**: migrating one without the other reopens the accept-all-wildcard bug the pair's own docstrings say it exists to prevent (A02-F003) — these two must move in the same commit or not at all. | Whatever test row 39 needs (post-flip: is this a predicate reference in HEAD position, same F2-shaped question but for the matcher side, not yet designed at this pass) — but *identical* logic on both sides. | 18, 39 | 2 |
| **F6 — class object used as a mutable storage carrier.** `database.py:1117` stamps `cand._tabled_home_db = self` on the class; `term_expansion.py:112,165` stamp/read `te_cls._te_predicate_nodes`. Neither is a shape or an identity question — it is using the class object itself as a place to hang cross-call state. **Flagged NOT OBVIOUS**: post-flip there is no object to stamp; this needs a NEW home (a field on `PredRow`, or a side dict on `Database` keyed by `(functor, arity)`), not an accessor swap. | New storage, not yet designed. | 17, 47, 48 | 3 |
| **F7 — frozen dispatch protocol.** `_get_dispatch(arity)` — the arity-aware overload only `PredicateMeta` implements; per project memory this protocol's signature is frozen with ~22 out-of-tree implementors. **Flagged NOT OBVIOUS**, highest blast-radius single row in the table. | Not a simple isinstance replacement — needs its own design pass respecting the frozen protocol; out of scope for this document to propose. | 8 | 1 |
| **F8 — cross-copy class identity.** `_describe_term_identity_mismatch` exists specifically to diagnose two `PredicateMeta` classes minted for the same name by two copies of the engine (a double-import bug). **Flagged NOT OBVIOUS**: this failure mode may become impossible rather than needing a migration — two interned equal `str`s from two engine copies ARE equal, so the bug this diagnoses may not exist post-flip. Needs a decision (migrate vs. delete), not a mechanical swap. | Possibly moot; needs a ruling, not a test. | 11 | 1 |
| **F9 — import/attribute-listing filter.** `import_diagnostics.py:201` filters a module's attributes down to "predicate/atom names" for a diagnostic listing. **Flagged NOT OBVIOUS**: once a predicate binding is a plain (mangled) `str`, the whole "is this a class sitting in the module dict" framing this filter is built on no longer applies — this may need to be rewritten around a different population (module dict values that are mangled atoms), not just a swapped isinstance. | Rewrite around `is_mangled`/`db.declared_kind`, not a straight substitution. | 1 | 1 |
| **F10 — dead code, not a migration target.** `terms_to_ast.py:1141` gates on a generated-constructor artifact the code's own comment says is unreachable since W4a. | Delete at W4b-3 (or sooner as cleanup); do not migrate. | 22 | 1 |

23+15+1+1+2+3+1+1+1+1 = **49**. Verified the family lists partition the
full 49-row set with no overlap and no omission (listed every ID once,
cross-checked against the extracted set from §Q2's correction).

**Where the replacement is NOT obvious**, ranked by how much it will cost:
F7 (frozen protocol, engine-wide blast radius) and F6 (needs genuinely new
storage, two call sites with no row-shaped home) are the two most likely to
eat time; F5's coupling and F3's unlisted callers are the two most likely to
produce a silent regression if handled site-by-site instead of as a unit.

---

## Question 3 — what's done, what's left

### 3.1 `feat/seam-local-handle-2026-09-22` (`7d843d35`) vs. today's main

    git log main..feat/seam-local-handle-2026-09-22 --oneline
      7d843d35  seam review round: a local handle runs in GOAL position too, and a handle carries its module
      c312622a  seam: a predicate handle held in a Python LOCAL reaches `--` by VALUE

Diffstat: 52 files, +1578/-3957 (net negative — the branch also deletes
several superseded planning docs and a retired test file,
`tests/test_declaration_registration.py`, `test_field_names_for.py`,
`test_functor_construction_declared_term.py`,
`test_w4b1_builtin_fallback_removed.py`,
`test_w4b1_census_positive_control.py`, `tools/w4b1_census/`, and several
`implementation_plans/*` docs — consistent with a branch that also carried
forward W4b-1's own landing/cleanup, not just the seam fix).

`git merge-tree $(git merge-base main feat/...) main feat/...` — **zero
`<<<<<<<` conflict markers in 407 lines of output**; every file reports
`merged` (auto-resolved) or `added in remote` (new files, e.g.
`tests/test_seam_local_handle.py`, `tests/test_fast_construction.py`). **It
applies cleanly as a 3-way merge against today's main tip (`ad882878`).**
This is a *textual* mergeability verdict only — I did not build the `.so`,
did not run the test suite, and did not check whether the branch's own
tests (or main's newer tests) still pass once merged; that verification is
unmade and would need the usual same-sha-worktree build discipline before
anyone treats it as landable. No merge or rebase was performed; the working
tree is untouched.

### 3.2 The two-out-paths decision, for the operator

`todo/two-out-paths-disagree-about-atom-tagging-2026-09-22.md`: the `--`
seam's `export()` tags an atom as `atoms.atom` (a `str` subclass) on the way
out to Python; `solve(goal, module=m)` + `deref` hands back plain term-space
values (`str` for an atom). A Python body that uses both cannot write one
"is this an atom" test that is correct against both — `type(v) is str` is
right for `solve`+`deref`, wrong for `export()`, and vice versa for
`isinstance(v, atom)`. **The operator has to rule: does the export tagging
belong at "wherever a value reaches Python" (so `solve`+`deref` would need
an exporting twin, and the codebase gets one out-boundary contract), or does
it stay "only through `--`" (so `solve` callers are documented as living in
term space, and mixing the two paths in one body is simply not supported)?**
The first choice is a small new API surface with a wider, more uniform
contract; the second is zero new code but a permanent "don't mix these"
discipline a future body can still get wrong. This is exactly what parks
the `--handle(X)` seam form for the 31 hold-and-call sites (they currently
sidestep the question entirely by writing literal tuples under a dated
exception, per the ruling recorded in `implementation_plans/w4-python-
boundary-plan-2026-09-22.md`).

---

## Summary of what is verified vs. inferred

**Verified by probe, this session** (scripts left under this session's
scratchpad, not in the repo): the `sys.modules`-collision bug (real `os`);
the same-bare-name collision bug (`hide_owner`); that both raise different
things (`KeyError` subclass vs. `LogicException`, respectively); that
`declared_kind` cannot see a `-hide` atom at all (`None`, not `"data"`);
that `arities_for`/`declared_kind` behave as documented on real fixtures;
that a real handle's arity-mismatch error is produced by class-bound
`PredicateMeta` machinery, not by the demangling path; that the candidate
`_is_handle` function (module-validity + `!= "data"`) fixes the
`sys.modules` collision and preserves the landed "undeclared name still
qualifies" test, but does *not* fix the same-bare-name collision without
the unbuilt `-hide`-registers-into-`_declared` change; that
`feat/seam-local-handle-2026-09-22` merges cleanly (no conflict markers)
against today's main.

**Read from code/docs, not independently re-derived**: the 49-row IDENTITY
table's individual classifications (I trust `w4b1-site-classification`'s
own per-row reasoning, which itself documents two review rounds; I did not
re-open all 49 call sites myself, only enough to build the families and
spot-check the four rows discussed at length in 1.1-1.4 and Q2's F3-F9).

**Explicitly not established**: whether F1's arity-mismatch error mechanism
(3.1's `_refuse_call_at`) survives W4b-3's class deletion; whether
`field_names_for`'s `None`→`()` shift for a hidden atom (were `-hide` to
register into `_declared`) breaks any existing caller; whether the
`feat/seam-local-handle` branch's own tests pass on today's main (textual
mergeability only, not built or run).
