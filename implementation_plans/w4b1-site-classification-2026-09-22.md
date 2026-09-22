# W4b-1 — site classification: SHAPE vs IDENTITY (2026-09-22)

Task 4 of the W4b-1 plan. This document supersedes the spec's "~30 SHAPE /
~33 IDENTITY" figure — that number was a grep-context **estimate**, made
without opening any site. The numbers below are read, not estimated, and
they differ from the estimate.

## Denominator

```
grep -rn "isinstance([^)]*PredicateMeta" --include='*.py' clausal/ > sites.txt
wc -l sites.txt
```

Result: **63**, matching the plan's expectation for `main` at `11623ba4` —
no drift to report.

## Totals

| bucket | count |
|---|---|
| SHAPE (migrates to `field_names_for` in Task 5) | **23** |
| IDENTITY (stays `isinstance`, feeds W4b-2) | **40** |
| UNRESOLVED | **0** |
| **denominator** | **63** |

23 + 40 + 0 = 63. No sites lost.

Zero UNRESOLVED does not mean every row was equally easy — nine rows below
are flagged **(moderate confidence)** with the specific reason the call was
harder than the rest, so a reader auditing this document knows where to look
first if a later defect turns up. None of them was a guess: each has a
traced reason, just a less clean-cut one than the majority.

## The question asked, restated

For every site: *could a `@dataclass` class ever reach this expression, and
if it did, would taking the `isinstance` `True` branch be wrong?* If wrong
(or would silently change protected machinery — `_row`, `_get_dispatch`,
`_lock()`, dispatch installation, mutation-gate `through=`), the site is
IDENTITY. If the site is reading field names / arity / zero-field-ness, or
already calls `term_field_names_of_class`/`field_names_for` nearby, it is
SHAPE, and widening to accept a dataclass is the deliberate, wanted effect.

## The table

Legend: **S** = SHAPE, **I** = IDENTITY.

| # | file:line | S/I | what it asks | would arm 1 change the answer, and is that wrong? |
|---|---|---|---|---|
| 1 | `import_diagnostics.py:201` | I | filters module attrs to "predicate/atom names this module binds", for an import-diagnostic listing | yes/wrong — a bare `@dataclass` class sitting in the module dict is a term SHAPE, not something `from M import f` should list as a predicate/atom name |
| 2 | `testing.py:894` | S | `declared_here` test: db row OR `isinstance(declared, PredicateMeta) and len(declared._fields) == arity` — comment: "the key IS the field-count check the class read had to make for itself" | yes, and it's the wanted widening — a dataclass class matching name+arity is exactly as "declared here" as a PredicateMeta one |
| 3 | `testing.py:1703` | S | `_reify_value`: a bare CLASS value (not instance) → `Atom(name=value.__name__)` for diagnostic rendering | yes; consistent with how the same function already renders dataclass *instances* via `is_term_instance` a few lines below — the class case was just never generalised |
| 4 | `testing.py:2259` | I | `isinstance(cls, PredicateMeta) and cls._row is not None and cls._row.clauses` — locating a callable predicate class for a failure trace | wrong — reads `._row`/`.clauses` directly; a dataclass has neither |
| 5 | `predicate_diagnostics.py:194` | S | `_arity_of`: "Declared arity of a predicate class, or None if it is not one" — reads `_fields`, falls back to `_arity` | yes, wanted — this is a shape query stated in its own docstring |
| 6 | `logic/seam.py:153` | I | after `functor_signature_for(fname, ns, classes=False)` (SHAPE, deliberately excluding classes) came back empty, asks "is `binding` a predicate class" to decide whether `--(...)` is refused as a goal cell | wrong — the SHAPE half of this exact decision is already handled one line above with `classes=False`; this isinstance is the deliberately separated identity half |
| 7 | `logic/predicate.py:524` | S | arity of a clause head shape; docstring: the class-as-value 0-arity case "reached `term_field_names` and raised... `_fields` answers it directly" | yes, wanted |
| 8 | `logic/predicate.py:1384` | I | `_get_dispatch` protocol dispatch: "predicates are instances of that metaclass while foreign implementors are instances of plain classes, so `isinstance` separates them exactly" | wrong — calls `obj._get_dispatch(arity)`, an arity-aware overload that ONLY `PredicateMeta` implements; every other `_get_dispatch` implementor (frozen duck-typed protocol) takes no arity |
| 9 | `logic/predicate.py:1522` | S | `_is_zero_field_class_py`: `isinstance(obj, PredicateMeta) and not obj._fields` — literally the definition the spec quotes as becoming `field_names_for(x) == ()` | yes, wanted; this IS the case the spec's example is built from |
| 10 | `logic/predicate.py:1573` | S* | this is arm 2 of `field_names_for` **itself** — self-referential, not a call site | N/A — cannot migrate to itself; DELETED AT W4b-3 per its own docstring. Bucketed as SHAPE because it answers the shape question, but flagged: **Task 5 should exclude this line from its migration list** — there is nothing to change here until the class goes |
| 11 | `logic/predicate.py:1797` | I | `_describe_term_identity_mismatch`: is `cls` recognised as *this process's own* `PredicateMeta` (cross-copy double-import diagnostic) | wrong — the function is named for exactly this; it is asking about copy identity, not shape, and explicitly "introspects objects minted by a foreign copy" |
| 12 | `logic/constants.py:258` | I | `-constants` RHS construction: PredicateMeta binding → `binding(*args,**kwargs)` (direct class construction); else → build a cell from `functor_signature_for`'s fields | wrong — `functor_signature_for` (called just below) **already** resolves a dataclass binding's fields via its `term_field_names_of_class` fallback, so a dataclass binding is *already*, deliberately, routed to the cell-construction path, not the direct-call path. Migrating this line would collapse two paths the code keeps apart on purpose |
| 13 | `logic/goal_expansion.py:116` | S | `_cell_slot_names`: field NAMES of a cell's slots for regex auto-binding, arity-checked | yes, wanted |
| 14 | `compiler/globals_env.py:193` | S | `signature_for` fallback (no `$module`): "the fallback counts the class's fields for itself", arity-exact | yes, wanted |
| 15 | `compiler/globals_env.py:602` | I | bake dispatch for a call site: `obj._row`, `row.locked`, `row.dispatch_fn` read right after | wrong — `_row`/dispatch-bake machinery; a dataclass has no `_row` |
| 16 | `compiler/_lower_goalop_shared.py:129` | S | `_is_const_element`: `isinstance(term, PredicateMeta): return is_zero_field_class(term)` | yes, wanted — literally calls the SHAPE helper |
| 17 | `logic/database.py:1117` | I | `mark_tabled`: stamps `cand._tabled_home_db = self` on the class object | wrong — mutates class-level state used as a cross-module carrier; a dataclass stamped this way is not the actual predicate row-bearer |
| 18 | `compiler/terms_to_ast.py:101` | S | `_is_opaque_head_literal`: is this term already structurally known to the compiler (vs. an opaque foreign Python value to capture)? | yes, wanted — a declared dataclass class is exactly as "already handled structurally" as a PredicateMeta class |
| 19 | `compiler/terms_to_ast.py:385` | I | resolves a name to `(spelling, fields)` for term construction; PredicateMeta arm applies a PREDICATE-specific arity rule ("a class is not the authority on arity the way a data-functor DECLARATION is" — over-supply is lenient here, strict for data) | wrong — this is the sharpest one in the table. A dataclass binding *already* reaches the function's tail (`functor_signature_for`) and gets the STRICT (data-functor) arity rule. Widening the PredicateMeta arm would silently move it to the LENIENT rule |
| 20 | `compiler/terms_to_ast.py:578` | I | live class-instance head construction; docstring says this path is nearly dead (Task 6 emptied the bridge) but the ruling is explicit: only a `PredicateMeta`-instance's class gets "class emission" AST; anything else must fall through to cell construction or the two sides "disagree with their own matching half" | wrong — a dataclass instance reaching this must NOT take class-emission; that is the exact hazard the docstring says the ruling exists to prevent |
| 21 | `compiler/terms_to_ast.py:1067` | I | OWA fallback: "OWA still defers to a PREDICATE binding — a goal is not data, even in a flagged module" | wrong — the predicate/data distinction is the whole point; a dataclass is data |
| 22 | `compiler/terms_to_ast.py:1141` | I | `isinstance(cls, PredicateMeta) and isinstance(vars(cls).get("_clausal_new"), classmethod)` — gates a generated-fast-constructor path | N/A in practice (comment: "DEAD SINCE W4a: no class carries the generated constructor any more, so this gate never matches") — bucketed IDENTITY because the ask (a class-specific generated-constructor artifact) is identity-shaped, but this row is dead code; flagged for **W4b-3 deletion candidate**, not a migration target |
| 23 | `compiler/terms_to_ast.py:1261` | I | "A predicate CLASS ... in term position. Almost always the atom/predicate name clash" — a bare predicate class reference in argument position renders as the ATOM of its name | wrong — this is the predicate-name-as-atom coercion rule, specific to predicates; there is no established rule that a bare dataclass CLASS reference means "the atom of its name" |
| 24 | `logic/compiler_v2.py:272` | I | Step 4 assertz: guards `_bind_row` — comment: "34 [arrivals] find something other than a predicate class... dropping the test would hand a tuple to `_bind_row`" | wrong, explicitly measured and stated in-repo |
| 25 | `logic/compiler_v2.py:489` | I | walks `module_dict.values()`, on a class match calls `obj._lock()` | wrong — `_lock()` is PredicateMeta-only |
| 26 | `logic/compiler_v2.py:626` | S | zero-field-class test ("only a zero-field class is answered with the spelling") for the declared-atom pivot rewrite | yes, wanted — same `is_zero_field_class` shape as #9/#16 |
| 27 | `logic/compiler_v2.py:836` | I | `-import_from` alias RESOLVER feeding the load-gate/mutation-gate machinery (docstring: "answers 'which class does this head name reach'... the mutation gate answers 'may this load write it'") | wrong — feeds `_load_gate`/dispatch write authority |
| 28 | `logic/compiler_v2.py:899` | I | `_refuse_foreign_writes`: resolves `pred_cls` to hand `db.refusal_for(..., through=pred_cls)` | wrong — mutation-gate `through=` argument |
| 29 | `logic/compiler_v2.py:932` | I | `_imported_class`: docstring — "Used to hand the mutation gate the shared class a write would land on" | wrong — same mutation-gate feed as #27/#28 |
| 30 | `logic/compiler_v2.py:1052` | S | calls `term_field_names_of_class(cls)` immediately after (already the accessor) to check declared-at-this-arity | yes, wanted — textbook "already calls the accessor nearby" signal |
| 31 | `logic/compiler_v2.py:1094` | S | same pattern as #30, for `-table` target refusal ("is_pred") | yes, wanted |
| 32 | `logic/compiler_v2.py:1217` | I | `_preregister_specializations`: guards `analyze_mi(mi_cls)`, which reads `pred_cls._row` and `.clauses` directly | wrong — `analyze_mi` needs `._row`/clauses, not merely field names |
| 33 | `logic/compiler_v2.py:1258` | I | `_run_specialization`: same `mi_cls` / `analyze_mi` use as #32 | wrong, same reason |
| 34 | `logic/compiler_v2.py:1286` | I | decides whether `source_cls` is a predicate to `call(source_cls, ...)` vs. a literal list | wrong — `call()` needs a genuinely callable predicate/dispatch target |
| 35 | `logic/compiler_v2.py:1308` | I | "Reuse pre-registered class if available" — reuses a specific class OBJECT as the specializer's mutation target | wrong — the specializer attaches clauses/dispatch to this exact class object |
| 36 | `logic/compiler_v2.py:2031` | I | `existing._row` / `.clauses` read right after, to decide predicate-vs-data-functor binding survival across a rewrite | wrong — `._row` read, matches the IDENTITY signal directly |
| 37 | `terms.py:3486` | S | `term_str` locale rendering: `isinstance(t, type) and isinstance(t, PredicateMeta) and not t._fields` — the same `is_zero_field_class` shape, inlined | yes, wanted |
| 38 | `compiler/head_match.py:757` | I | OWA head-match fallback: comment explicitly parallels terms_to_ast's Site A — "a goal is not data, even under OWA" | wrong — same predicate/data distinction as #21 |
| 39 | `compiler/head_match.py:858` | S (moderate confidence) | "PredicateMeta atom (a zero-arity predicate class used as a value)" — routes a bare class value through a `unify()`-guard capture | leans yes/wanted (parallels #9/#16/#26/#37's zero-field-atom shape), but the code does **not** re-check `not term._fields` at this exact line the way its siblings do — it relies on the surrounding control flow already having peeled off the fielded case. Flagged because I could not fully rule out a fielded class reaching here by a path I didn't trace to the end |
| 40 | `logic/builtins/inspection.py:52` | S | `_copy_term_py`: exact `is_zero_field_class` inline pattern | yes, wanted |
| 41 | `logic/builtins/inspection.py:142` | S | `_collect_vars_py`: same pattern as #40 | yes, wanted |
| 42 | `logic/builtins/inspection.py:327` | S | `functor/3` decompose: "Only the class arm resolves... `_fields` is the field list whatever minted the class" | yes, wanted |
| 43 | `logic/builtins/inspection.py:394` | S (moderate confidence) | `functor/3` construct: is `name_val` ATOMIC (ISO 8.5.1.3e)? `PredicateMeta` accepted regardless of field count, "resolves it for itself" downstream | leans yes — the declaredness framing ("a declared functor class is an atom value") matches SHAPE, but the check itself doesn't gate on zero-fields, unlike its siblings, so I can't be certain a dataclass reaching this and being accepted as "atomic" is harmless in the same way |
| 44 | `logic/builtins/inspection.py:524` | S (moderate confidence) | `=../2` construct direction, identical pattern to #43 | same caveat as #43 |
| 45 | `tools/iso_l3.py:98` | S | generated-code TEMPLATE string (P1 lowering): `isinstance({name}, PredicateMeta) and getattr({name}, "_fields", None) != {fields_src}` — a redeclaration guard reading `_fields` | yes, wanted (this is a text template, not a direct call site — the generated code performs the SHAPE read when it runs) |
| 46 | `logic/builtins/type_checks.py:363` | I (moderate confidence) | `callable_/1` (ISO `callable`): a bare PredicateMeta class is callable/atomic per the predicate-name-as-atom rule (same rule as #23) | leans wrong — parallels #23's predicate-specific coercion, but ISO "callable" (atomic-or-compound) is a broad enough concept that treating any term-shaped class as atomic might also be defensible; kept IDENTITY for consistency with #23 |
| 47 | `logic/term_expansion.py:112` | I | stamps `te_cls._te_predicate_nodes = ...` on the class, a cross-module carrier | wrong — same class-stamping pattern as #17 |
| 48 | `logic/term_expansion.py:165` | I | reads the same stamped `_te_predicate_nodes` attribute back | wrong, same carrier pattern |
| 49 | `compiler/arg_index.py:184` | I | compile-time index key for a clause-head argument: predicate-class-as-atom → `(name, 0)`, mirroring #23's coercion rule | wrong — same predicate-name-as-atom rule as #23; not a generic "any term-shaped class is an atom" rule |
| 50 | `compiler/arg_index.py:386` | I | runtime companion of #49 (`_runtime_arg_key`), comment: "mirror `_arg_to_index_key`" | wrong, same reasoning as #49 |
| 51 | `compiler/arg_index.py:552` | I | `obj._row`, `cand.key[1] == arity` read directly; comment: "spelled with an explicit isinstance so P4 can find its removal site by grep" (a DIFFERENT retirement track than this one) | wrong — `._row` read, and the code itself says this belongs to the handle-flip (P4/W4b-2/3), not the shape rehome |
| 52 | `compiler/control_constructs.py:717` | I | catch/3 catcher-lowering: `isinstance(resolved, PredicateMeta) or cell_signature_for_name(...)` — docstring: "PredicateMeta binding -> class construction, `cell_signature_for_name` answers -> cell literal" | wrong — the SHAPE half of this exact OR is already the other disjunct; the isinstance half is deliberately the identity half |
| 53 | `compiler/predicate.py:917` | I | "Resolve pred_cls" feeding `_install(...)` | wrong — dispatch-install feed |
| 54 | `compiler/predicate.py:1042` | I | same "Resolve pred_cls" pattern as #53 | wrong, same reason |
| 55 | `compiler/predicate.py:1761` | I | same pattern again (shallow-strategy compile path) | wrong, same reason |
| 56 | `compiler/predicate.py:1876` | I | same pattern again | wrong, same reason |
| 57 | `compiler/predicate.py:2247` | I | "bind first, then write the ROW the class faces" | wrong — explicit row-write |
| 58 | `logic/builtins/database_ops.py:365` | I | "THE REDIRECT TEST, on rows": `named_row is not own_row and isinstance(own, PredicateMeta)...` — resolves a class the caller will lock/recompile | wrong — feeds locking/recompiling via row identity |
| 59 | `logic/builtins/database_ops.py:379` | I | `_arity_checked` helper for the same "what this function RETURNS is a class — the caller locks it, recompiles through it" contract | wrong, same reason as #58 |
| 60 | `logic/builtins/io.py:594` | I | `listing/1`: "The class knows its own row; the name does not" | wrong — explicit row-dependency |
| 61 | `logic/builtins/io.py:740` | I | `listing/1` instance/class resolution; `val._row`, `.clauses` read two lines later | wrong — `._row` read |
| 62 | `templating/term_rewriting.py:4319` | S† | inside a DOCSTRING (an illustrative generated-code example), not executable code | yes, wanted — describes the same `_fields`-equality redeclaration guard as #45; see note below |
| 63 | `templating/term_rewriting.py:4358` | S† | inside a DOCSTRING (prose: "The guard is deliberately narrowed to `isinstance(.., PredicateMeta)`") | same as #62 |

\* row 10 is self-referential (it is inside `field_names_for` itself) — see note.
† rows 62–63 are prose/docstring text, not executable `isinstance` calls — see note.

## Notes on rows 62–63 (and the population's mechanical edge)

`grep -rn "isinstance([^)]*PredicateMeta"` matched these two lines because
the regex doesn't distinguish code from docstring. The function's **actual**
generated-code template, a few lines further down
(`templating/term_rewriting.py` around line 4390), builds the identical guard
through an f-string using `{_PM_PLACEHOLDER}` — a template variable, not the
literal text `PredicateMeta` — so it does **not** match the grep and is
correctly absent from the population. Both matched lines describe the same
`_fields`-reading redeclaration guard that `iso_l3.py:98` spells directly (a
real f-string with the literal name), so I classified them the same way:
SHAPE. This is a quirk of the population's mechanical definition worth
knowing before Task 5 tries to "migrate" these two lines — there is no code
at 4319/4358 to change; the real site to touch (if this guard is ever
migrated) is the f-string template a few lines below it, which grep's
regex — correctly, per the brief's own instruction to use my number, not a
guessed one — did not count.

## Note on row 10 (self-referential)

`predicate.py:1573` is arm 2 of `field_names_for` itself
(`if isinstance(value, PredicateMeta): return value._fields`). It cannot
"migrate to `field_names_for`" because it IS `field_names_for`. Its own
docstring says it is "DELETED AT W4b-3." I bucketed it SHAPE for the
arithmetic (it answers the shape question), but Task 5 should simply skip
this line — there is nothing to migrate here until the class itself goes.

## Observed pattern: "predicate vs. data" is usually IDENTITY, not SHAPE

The single largest source of IDENTITY sites (rows 6, 12, 19, 21, 23, 38, 46,
49, 50, 52 — 10 of the 40) is not dispatch/row machinery but a **different**
recurring question: "is this specifically a PREDICATE reference (as opposed
to a data functor, which may legitimately be `@dataclass`-shaped), because a
goal is not data and a predicate class in term position denotes the ATOM of
its name." This reads like a shape question on first pass (it's asking
"what kind of term is this") but it is not answerable by field names at
all — a data functor can have the exact same field shape as a predicate and
still need the OPPOSITE answer here. This is why the SHAPE count (23) came
in well under the spec's ~30 estimate: the estimate's grep-context pass
couldn't see that this pattern, which shows up over and over, is identity
even though it superficially resembles a declaredness check.

## Bug found while reading (not fixed, per instructions)

`compiler/terms_to_ast.py:1141` (row 22) gates on
`vars(cls).get("_clausal_new")` being a `classmethod`. The surrounding
comment says plainly: "DEAD SINCE W4a: no class carries the generated
constructor any more, so this gate never matches." This isn't a correctness
bug (the `and`-chain simply never turns True, so the branch is unreachable
but harmless) — it's dead code the W4a migration left behind. Worth a
cleanup todo, not a fix here.

Nothing else read during this pass looked like a live, un-flagged
correctness bug — several sites document historical bugs already fixed
(`compiler_v2.py:836`'s alias-clobber note, `terms_to_ast.py:1067`'s dotted-
OWA finding), but none of those are still open.
