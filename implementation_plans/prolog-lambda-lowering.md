# `<-` lambdas / closures: ISO Prolog lowering

**Status:** DESIGN — no code, no test changes. Written for the class-M work item of
`docs/iso-export-pilot-2026-09.md` (§W2.3 class M, `call_goal/N`; §W2.4 "M — `call_goal/N`,
18 of 73"), following the operator decision of 2026-09-03 that shipped the interim
refusal (`884c16eb`, `d0f92892`) and deferred lambda *lifting* to this note.

**Problem in one sentence:** a Clausal `<-` lambda in term position is a **closure**, and
ISO Prolog has no closure term — so `clausal/tools/clausal_to_prolog.py` used to emit the
lambda's parse as inert `</2` operator soup that no meta-call can ever invoke, and now
refuses it, leaving 390 real corpus/kit sites untranslatable.

Everything below was re-derived in this session against
`/workspace/clausify-domains` (705 non-`_` published-domain `.clausal` files that
translate), `/workspace/clausify-executor-train/kit` (40 files that translate),
`/workspace/clausal/venv/bin/python`, the live Clausal engine, the translator at
`884c16eb^` (extracted with `git show` into a scratch module, so the pre-refusal
emission is the real one and not a reconstruction), and
`/workspace/scryer-prolog/target/release/scryer-prolog` (`--version` reports
`cargo:0.10.0`). Every output block is unedited terminal output, of one of three kinds,
and each block says which:

- **Scryer blocks** show the consulted file(s) and the exact
  `$ printf '…' | scryer-prolog …` invocation, with Scryer's own answers beneath.
  Scryer does not echo a piped query, so the queries live in the `printf` and the answers
  are in query order.
- **Engine blocks** are marked "Python driver stdout": the unedited stdout of a small
  driver that loads a `.clausal` module through `clausal.import_hook._load_module` and
  enumerates `clausal.logic.solve.call(...)`. The `CLAUSAL <name> ->` prefix is the
  driver's `print()`; the solution lists and any exception text are the engine's.
- **Census blocks** are marked as such and are the stdout of the read-only census script
  described in §2.1. No census tooling is committed.

Where this document contradicts `.superpowers/sdd/2026-09-03-in2/progress.md` or the
migration worklist, the divergence is called out explicitly.

---

## 1. The defect

### 1.1 What a `<-` lambda is, and where it goes wrong

Clausal writes an anonymous predicate as `(PARAMS <- BODY)`. In goal position that is a
clause arrow. In **term** position — as an argument to a higher-order predicate — it is a
closure, invoked by the callee through the engine's `call_goal/1..8` builtin
(`clausal/logic/builtins/higher_order.py:22-44`; `call/1..8` are registered as aliases of
the same trampolines at `:46-50`).

The kit's `call_goal` protocol is the whole idiom. `kit/formalize_lib.clausal:622-627`:

```
eval_requirements([], _, _, []),
eval_requirements([REQ, *REQS], PROFILE, REQ_PRED, [ITEM, *ITEMS]) <- (
    call_goal(REQ_PRED, REQ, PROFILE, STATUS, CITATION),
    ITEM is item(REQ, STATUS, CITATION),
    eval_requirements(REQS, PROFILE, REQ_PRED, ITEMS)
)
```

and a domain hands it a closure —
`/workspace/clausify-domains/au/aml_ctf/reporting_entity_obligations.clausal:512-517`:

```
aml_ctf_checklist(PROFILE, CHECKLIST) <- (
    aml_ctf_requirement_ids(IDS),
    eval_requirements(IDS, PROFILE,
                      ((ID, PR, S, C) <- aml_ctf_requirement(ID, PR, S, C)),
                      CHECKLIST)
)
```

The lambda arrow `<-` and the arithmetic comparison `< -` parse to an **identical** Python
AST (`Compare(Lt, UnaryOp(USub, …))`); only source spacing separates them
(`clausal/templating/term_rewriting.py:211-257`, `_is_arrow_adjacent`). The translator's
`_convert_compare` therefore used to treat a term-position lambda as a `Lt` comparison and
emit it as one.

### 1.2 The pre-refusal emission, re-derived

The translator at `884c16eb^` (the commit before the refusal), run on the real witness
file (Python driver stdout; the `.pl:NNN` prefixes are the driver's line numbers into the
emitted text):

```
=== PRE-REFUSAL emission (translator at 884c16eb^), strict=True ===
  .pl:333:     eval_requirements(Ids, Profile, (Id, Pr, S, C) < - aml_ctf_requirement(Id, Pr, S, C), Checklist).

=== TODAY, strict=True ===
  UntranslatableConstructError: `<-` lambda in term position: (ID, PR, S, C) < -aml_ctf_requirement(ID, PR, S, C) — a `<-` lambda is a clause arrow, not a closure; in term position it emits inert operator soup that never runs. Define a named auxiliary predicate and pass its name instead (class-M design note; see the 2026-09-03 decision)

=== TODAY, strict=False (permissive) ===
  .pl:339:     eval_requirements(Ids, Profile, ???, Checklist).
```

Note what `strict=True` produced **before** the refusal: a clean translation, no warning,
no marker. The file counted as `clean` in the census ratchet.

What that third argument actually is, asked of Scryer directly (no consulted file):

```
$ printf 'X = ((a,b,c,d) < - p(a,b,c,d)), write_canonical(X), nl.\n' | scryer-prolog
<(','(a,','(b,','(c,d))),-(p(a,b,c,d)))
   X = ((a,b,c,d)< -p(a,b,c,d)).
```

A two-argument `(<)/2` compound whose left argument is a `,`-chain and whose right argument
is a `(-)/1` wrapping the intended goal. **Data.** Nothing in it is callable.

### 1.3 The witness executed

File `soup.pl` — the pre-refusal emission of the witness clause, the emitted
`eval_requirements/4` verbatim from today's translator, two `aml_ctf_requirement/4` facts,
**and a one-clause `call_goal/5` shim over ISO `call/5`** (so the run reaches the real
failure and not a trivially-missing `call_goal/5`):

```prolog
eval_requirements([], _, _, []).
eval_requirements([Req|Reqs], Profile, Req_pred, [Item|Items]) :-
    call_goal(Req_pred, Req, Profile, Status, Citation),
    Item = item(Req, Status, Citation),
    eval_requirements(Reqs, Profile, Req_pred, Items).
aml_ctf_requirement("r1", _, met, "s45").
aml_ctf_requirement("r2", _, unmet, "s47").
call_goal(G, A, B, C, D) :- call(G, A, B, C, D).
soup(Ids, Profile, Chk) :-
    eval_requirements(Ids, Profile,
        (Id, Pr, S, C) < - aml_ctf_requirement(Id, Pr, S, C), Chk).
eta(Ids, Profile, Chk) :-
    eval_requirements(Ids, Profile, aml_ctf_requirement, Chk).
```

```
$ printf 'soup(["r1","r2"], p, Chk).\neta(["r1","r2"], p, Chk).\n' | scryer-prolog soup.pl
   error(existence_error(procedure,(<)/6),(<)/6).
   Chk = [item("r1",met,"s45"),item("r2",unmet,"s47")].
```

Answers in query order. The soup raises `existence_error((<)/6)`: `call/5` on a `(<)/2`
term appends the 4 extra arguments and looks for `(<)/6`. The second answer is §4.1's
proposed respelling, and it is the answer the engine gives (§4.1).

The same predicate on the live engine (Python driver stdout):

```
CLAUSAL Lam  -> [(['r1', 'r2'], 'p', [['r1', 'met', 's45'], ['r2', 'unmet', 's47']])]
```

So the defect in three lines of output: the engine computes the checklist; the export
before the refusal emitted a term that raises `existence_error((<)/6)` at G3, and did so
while counting as a **clean** strict translation at G1.

### 1.4 Why this was invisible until 2026-09-03

`progress.md` records the coupling exactly, and it re-derives: the only reason the soup was
ever *seen* is that `include/3` is missing from `LIBRARY_INJECTIONS`
(`tools/iso_export/export.py:189-201`), so a domain that used `include/3` died loudly at
G3 before the soup could fail quietly. Fixing that one entry alone would have converted a
loud failure into a silent one. §5 shows the entry cannot be added anyway.

---

## 2. The three-way census

### 2.1 Method

The operator's hypothesis is that many of the 390 lambdas are **redundant eta-expansions**
— `((A, B, C) <- pred(A, B, C))`, which is semantically just `pred`. The engine already
owns the legality analysis for that reduction: the rewrite rule
`clausal/rewrite/rules/unnecessary_lambda.clausal`, spiked and pinned in `fe43afc0`
("pin the eta-reduction spike"), hardened in `436ad553` ("legality must be a
pre-condition").

**The rule's legality clauses were used as the classifier's specification, not its
implementation, and the reason matters.** The rule runs over the *reflection* vocabulary
(`Clause`/`Goal`/`Atom`/`Variable` nodes produced by `clausal.reflection.reify_ast`),
where a lambda is a raw `Lambda` node and a parameter reference reifies as `Atom(name)`
while a captured enclosing variable reifies as `Variable(name)`. The translator never sees
that vocabulary — it works on the **Python AST**, where the same lambda is a
`Compare(Lt, UnaryOp(USub, …))` and both a parameter and a capture are a plain
`ast.Name`. Running the rule itself would have classified a representation the translator
does not consume, so each legality clause was transliterated to the Python-AST level:

| `unnecessary_lambda` legality clause | Python-AST transliteration | verified |
|---|---|---|
| argument is a raw `Lambda` node | `Compare` with `Lt` + leftmost `USub` at depth 0, adjacency confirmed by the engine's own `_is_arrow_adjacent` | site set matches the translator's refusal exactly (below) — **but see §2.2's footnote: this row is where the transliteration is one site wide** |
| every param is a plain positional param, no defaults/annotations/`*args` | every element of the head `Tuple` (or the bare head) is an `ast.Name` | 0 of 390 sites violate |
| body is a SINGLE predicate call (a `Goal`) | body is an `ast.Call` whose `func` is a `Name`/`Attribute` | 39 of 390 violate → class (c) |
| the body call has NO keyword arguments | `body.keywords == []` | 0 of 390 violate |
| body arguments are EXACTLY the params, pairwise, same order, same count | `[a.id for a in body.args] == param_names` | the class (a)/(b)/(c) split |
| params pairwise DISTINCT | `len(set(names)) == len(names)` | 0 of 390 violate |

The rule's capture fence (`Atom` vs `Variable`) transliterates to the **same** exact
name-match: an argument `Name` that equals a parameter *is* the parameter (Clausal
lambda parameters shadow the enclosing clause — pinned by
`tests/rewrite/test_reflection_contract.py::test_shadowing_param_reference_still_reifies_as_atom`);
an argument `Name` that is not a parameter is a capture, and the exact match rejects it. So
the one comparison is simultaneously the forwarding check and the capture check on both
representations.

**One legality clause the transliteration did not carry, and its cost.** Reification
builds a `Lambda` node only when the arrow's head is a valid parameter list —
`_extract_arrow_lambda_params` (`clausal/templating/term_rewriting.py:304-325`) requires
every head element to be a *logic-variable name* (`_is_logic_var_name`: ALL-CAPS, or
`_`-leading). A head element that is merely an `ast.Name` but not a logic variable makes
the whole arrow reify as a `Predicate` rule literal instead, which `unnecessary_lambda`
never matches. The Python-AST transliteration of row 1 tests `isinstance(elt, ast.Name)`
and **not** `_is_logic_var_name`, so it is strictly wider than the rule. Running the
engine's own `_extract_arrow_lambda_params` over all 390 head ASTs finds **exactly 1 site**
where the two disagree — §2.2's footnote.

**The site set is the translator's own, not a re-derivation.** The census script
monkey-patches `_ClausalToProlog._refuse_arrow_lambda_in_term_position`
(`clausal_to_prolog.py:1354-1394`) to record every node it refuses, then re-parses the same
source and matches nodes by `(lineno, col_offset, end_lineno, end_col_offset)`. Counts
therefore match the migration worklist by construction, which is what the first two lines
below confirm:

```
=== census, class-M three-way split ===
corpus: 246 sites in 97 files (705 files translated, 0 raised before translation)
   class a: 184 sites, 79 files
   class b: 10 sites, 8 files
   class c: 52 sites, 28 files
kit: 144 sites in 15 files (40 files translated, 3 raised before translation)
   class a: 134 sites, 13 files
   class c: 10 sites, 4 files
```

`246 sites / 97 files` and `144 sites / 15 files` are the worklist's own totals, row for row.

### 2.2 The split

| class | shape | corpus | kit | **total** | share |
|---|---|---:|---:|---:|---:|
| **(a)** eta-reducible † | pure same-order pass-through, no captures, no extra goals | 184 sites / 79 files | 134 sites / 13 files | **318 sites / 92 files** | **81.5 %** |
| **(b)** partial-application-shaped | prefix captures + pass-through tail | 10 sites / 8 files | 0 | **10 sites / 8 files** | **2.6 %** |
| **(c)** genuine closures | multi-goal body, reordering, interleaved captures, non-variable arguments | 52 sites / 28 files | 10 sites / 4 files | **62 sites / 32 files** | **15.9 %** |
| | | **246 / 97** | **144 / 15** | **390 / 112** | 100 % |

*(File counts do not add to 112 across classes: 95 files carry one class, 14 carry two,
3 carry all three — 92 + 8 + 32 = 132 class-file pairs over 112 distinct files.)*

† **The class-(a) row is the census figure, and it is one site wide.** The
engine-faithful count is **317 sites / 92 files (81.3 %)** — corpus 184, **kit 133** (92.4 %
of the kit's 144, not 93.1 %) — for the reason in the footnote immediately below. Every
later section quotes 317; the 318 above is retained only so the census stdout in §2.1 and
this table agree.

> **Footnote — the one classification-uncertain site, resolved.** Running the engine's own
> `_extract_arrow_lambda_params` over all 390 head ASTs returns `None` — *not a lambda
> parameter list* — for exactly one:
>
> ```
> === sites whose head is NOT a lambda param list per the engine's _extract_arrow_lambda_params: 1 ===
>    [a] /workspace/clausify-executor-train/kit/repros/callgoal_imported_lambda_repro.clausal:28 :: (ID, P, St, C) < -requirement(ID, P, St, C)
> ```
>
> `St` is mixed-case, so `"St".isupper()` is false and it is not a logic variable. The
> file is a **deliberately adversarial fixture** and says so in its own header: the arrow
> "is parsed as a `Predicate` rule literal instead of a `Lambda`", and the test at that
> line asserts `call_goal` raises `error(type_error("callable", _), _)` — the engine path
> at `clausal/logic/builtins/_registry.py:117-134`. Line 35 of the same file is the
> corrected control with an ALL-CAPS `ST`, and is a genuine class (a).
>
> So the site is **counted class (a) by the transliteration and is not eta-reducible**: it
> is not a lambda at all. The engine-faithful class-(a) count is **317 sites, not 318**
> (kit 133, not 134) — 0.26 % of 390, immaterial to every headline in this note, and
> stated because the transliteration's fidelity is the census's whole warrant. The
> translator is *right* to refuse the site (it is untranslatable either way); only the
> classification is wide. Any implementation of §4.1 A2 must carry `_is_logic_var_name`
> into its parameter test, and §4.1's test list gains a fifth item: a refusal test that
> `((ID, P, St, C) <- requirement(ID, P, St, C))` is **not** treated as eta-reducible.

**The operator's hypothesis is confirmed, and more strongly than stated: four in five
refused sites are redundant eta-expansions** — 317 of 390, 81.3 %. The kit is more extreme
than the corpus: 133 of 144 kit sites (92.4 %) are class (a), against 184 of 246 (74.8 %)
in the corpus.

Class (c), by reason (census stdout):

```
=== reasons within class c ===
-- corpus
     26  multi-goal body (conjunction)
     14  callee argument is not a bare variable
      7  captures interleaved with parameters
      5  comparison/unification body
-- kit
      4  multi-goal body (conjunction)
      4  comparison/unification body
      2  captures interleaved with parameters
```

Three further facts about class (a), each measured over the 317 engine-faithful sites:

- **0 sites** use an anonymous `_` as a parameter. This matters: `((X, _) <- p(X, _))` is
  *not* eta-equivalent to `p` (each `_` is independent, so the lambda drops the caller's
  second argument where the bare reference passes it), and `unnecessary_lambda`'s
  `Distinct/1` check does not catch a single `_`. The hazard is real and **latent, with
  zero corpus/kit instances** — worth pinning as a refusal in any implementation, not
  worth blocking on.
- **0 sites** have a dotted callee, and **0** have a callee that is not a lowercase-initial
  predicate name. 128 distinct callees.
- Parameter arities: 1 → 10 sites, 2 → 126, 3 → 39, 4 → 97, 5 → 43, 6 → 2.

### 2.3 Where the lambdas are passed

All 390 sites are a direct positional argument of a `Call` — none is a keyword argument,
none is buried inside a list or dict literal. Relative to the enclosing clause body:

```
host-Call nesting relative to a top-level body conjunct:
    356  top-level conjunct
     34  nested (depth 1)
```

`unnecessary_lambda`'s "WHERE IT LOOKS" precondition — *direct argument of a top-level
conjunct that is a plain Goal* — covers 356 of 390 sites as written. The other 34 are one
goal-transparent wrapper deeper: 27 under `once/1`, 2 under `findall/3`, 1 under `catch/3`,
and 4 deeper still (not individually characterised). Those wrappers' arguments are goals,
so the reduction is equally legal there; the rule's positional fence is *conservative*,
not *correct-at-the-boundary*, and extending it to goal-transparent wrappers is a small,
separately-testable widening.

39 distinct host predicates. The ten largest:

| host | sites |
|---|---:|
| `eval_requirements/4` | 43 |
| `plan_entry/8` | 30 |
| `what_if/5` | 25 |
| `flip_scan/4` | 24 |
| `actions_on_schema/4` | 24 |
| `bisect_flip/4` | 23 |
| `find_mus/4` | 22 |
| `thread_plan/5` | 22 |
| `failing_ids/4` | 20 |
| `verified_flips/5` | 18 |

**16 of the 390 sites pass their lambda to an engine builtin** — `include/3` (6),
`max_by/3` (5), `min_by/3` (2), `call_goal/5` (2), `call_goal/3` (1). The other **374 pass
it to a kit predicate** (`formalize_lib`, `query_combinators`, `compliance_lib`,
`optimization_lib`, the planner libraries), each of which is itself exported as a `.pl`.
That ratio decides the shape of the remedy: this is overwhelmingly a *kit-library
meta-call* problem, not a *builtin* problem.

`unnecessary_lambda`'s KNOWN CAVEAT — "a predicate that instead stores its argument and
structurally inspects it could tell a closure from an atom" — was checked by reading the
three largest kit hosts. `eval_requirements/4`
(`kit/formalize_lib.clausal:622-627`), `flip_scan/4` and `bisect_flip/4`
(`kit/query_combinators.clausal:304-355`) each thread the closure through unchanged and
only ever `call_goal` it; none unifies it against a pattern. This is a **per-host
precondition** of the remedy, not a global fact, and the remaining 36 hosts have not each
been read.

### 2.4 What fixing this is worth

Every file carrying a lambda site, re-translated under `strict=True` and its remaining
refusals classified:

```
files whose ONLY refusal class is the lambda: 74
files with a further refusal class too:       38
    also: ('negmem',)         -> 21 files
    also: ('other',)          -> 13 files
    also: ('negmem', 'other') ->  4 files

files whose lambda sites are ALL class a: 77 of 112
  ... and whose only refusal class is the lambda: 47  {'corpus': 40, 'kit': 7}
```

**Migrating class (a) alone moves 47 files from dirty to clean under strict — 40 corpus,
7 kit.** That is the honest ratchet payoff of §4.1, and it is measured over this
document's file walk (705 corpus + 40 kit files that translate), not over the ratchet's own
manifest-driven set, so the baseline must be re-measured rather than added to.
The `('other',)` residue is 43 `unsupported call target` + 14 `unsupported expression` +
11 `-import_from(py.datetime, …)` + 1 dict splat.

### 2.5 The residual: what stays refused if classes (b) and (c) are deferred

§8 recommends deferring classes (b) and (c). That deferral has a named cost, and it should
be read before the recommendation is accepted, not after.

Of the 74 files whose only refusal class is the lambda, 47 clear entirely through the
class-(a) migration (§2.4). **The other 27 stay refused solely because of a class-(b) or
class-(c) lambda** — nothing else in them is untranslatable. 23 corpus files across 22
domains (22 of the 23 are `queries.clausal` or `tests/test_queries.clausal`), 4 kit files. Census stdout, `b=`/`c=` being that file's site counts by class:

```
=== files still refused SOLELY by class (b)/(c) lambdas: 27 ===
   corpus b=0 c=1  au/merger_clearance/threshold.clausal
   corpus b=0 c=5  eu/aml/amlr_bo_chain/queries.clausal
   corpus b=1 c=0  eu/cbam/declarant_scope/queries.clausal
   corpus b=0 c=6  eu/chemicals/reach_registration_tonnage_band/tests/test_queries.clausal
   corpus b=0 c=1  eu/crypto_assets/mica_casp_authorisation_conditions/queries.clausal
   corpus b=0 c=1  eu/data_protection/gdpr_arts33_34_breach_notification/queries.clausal
   corpus b=0 c=2  eu/derivatives/emir_nfc_clearing/tests/test_queries.clausal
   corpus b=0 c=1  eu/labour/blue_card_eligibility/queries.clausal
   corpus b=0 c=1  eu/labour/posted_workers_long_term_trigger/queries.clausal
   corpus b=0 c=1  eu/labour/working_time_average/tests/test_queries.clausal
   corpus b=0 c=1  eu/labour/working_time_reference_period/tests/test_queries.clausal
   corpus b=1 c=1  eu/merger/eumr_jurisdiction_turnover/queries.clausal
   corpus b=0 c=2  eu/mifid/client_categorisation/queries.clausal
   corpus b=1 c=1  eu/peppol_einvoicing/queries.clausal
   corpus b=0 c=1  eu/procurement/light_regime/queries.clausal
   corpus b=1 c=1  eu/procurement/selection_criteria/queries.clausal
   corpus b=1 c=0  eu/procurement/shortlisting/queries.clausal
   corpus b=2 c=3  eu/schengen_90_180/queries.clausal
   corpus b=1 c=4  eu/schengen_90_180_max_stay/queries.clausal
   corpus b=0 c=1  eu/state_aid/de_minimis_cumulation/queries.clausal
   corpus b=2 c=0  eu/state_aid/de_minimis_cumulation/tests/test_queries.clausal
   corpus b=0 c=3  eu/vat/pro_rata_deduction/tests/test_queries.clausal
   corpus b=0 c=1  th/visa/queries.clausal
   kit    b=0 c=2  optimization_lib.clausal
   kit    b=0 c=3  query_combinators.clausal
   kit    b=0 c=3  tests/test_kit_gap_wave2.clausal
   kit    b=0 c=2  tests/test_validate_props.clausal
```

*(Paths abbreviated to the repo-relative form; the census prints them absolute under
`/workspace/clausify-domains` and `/workspace/clausify-executor-train/kit`.)*

Three things this list says that the aggregate does not:

- **22 of the 23 corpus files are `queries.clausal` or `tests/test_queries.clausal`** —
  `au/merger_clearance/threshold.clausal` is the single exception. These are the query / what-if
  surfaces (`flip_scan`, `bisect_flip`, `what_if_nth`, `aggregate_over`), not the normative
  rule files. A domain whose `queries.clausal` stays refused still exports its rules; it
  loses its boundary-probe and minimal-cause surface. That is a smaller loss than
  "21 domains blocked", and the distinction should not be lost when the deferral is scored.
- **Only 6 of the 27 involve class (b) at all**, and 3 of those 6 also carry class (c). So
  teaching the engine `call_goal/N` partial application (§4.2) would unblock at most
  **3 files on its own** — `eu/cbam/declarant_scope/queries.clausal`,
  `eu/procurement/shortlisting/queries.clausal`, and
  `eu/state_aid/de_minimis_cumulation/tests/test_queries.clausal`. Class (c) lifting is
  where the residual actually lives: it alone would unblock 24 of the 27.
- **Two of the four kit files are libraries** — `query_combinators.clausal` (3 class-(c)
  sites) and `optimization_lib.clausal` (2). A kit library that will not translate blocks
  every domain importing it at G2/G3 regardless of that domain's own cleanliness, so these
  two are worth more than their file count. `query_combinators` is the host of
  `flip_scan` / `bisect_flip` / `what_if`, i.e. of most of the 27.

The honest summary of the deferral: **27 files, 22 corpus domains' query surfaces, and two
kit libraries stay refused**, and the class-(c) half is 24 of the 27.

---

## 3. The constraint that governs every remedy: meta-call module scope

This is the finding that reshapes the remedies, and it is not in any prior document.

### 3.1 Clausal `call_goal/N` resolves the closure in the *caller's* module

`kit/query_combinators.clausal:15` states the contract — "The closure resolves its body in
the DOMAIN module". Verified on the live engine with a two-module layout that mirrors the
export exactly (library module `flib` owns `eval_requirements/4` and does the `call_goal`;
domain module `dquery` owns `local_req/4` and passes it). Python driver stdout:

```
CLAUSAL layered Lam  -> [(['r1'], 'p', [['r1', 'met', 's45']])]
CLAUSAL layered Eta  -> [(['r1'], 'p', [['r1', 'met', 's45']])]
```

`Lam` passes the forwarding lambda, `Eta` passes the bare atom `local_req`. Both resolve,
across the module boundary, with identical solutions.

### 3.2 ISO `call/N` resolves it in the *library's* module

The same layout in Scryer. Three files:

```prolog
% out_floor.pl
:- module(out_floor, [requirement/4]).
requirement("r1", _, met, "s45").

% formalize_lib.pl
:- module(formalize_lib, [eval_requirements/4]).
call_goal(G, A, B, C, D) :- call(G, A, B, C, D).
eval_requirements([], _, _, []).
eval_requirements([R|Rs], P, Pred, [I|Is]) :-
    call_goal(Pred, R, P, S, C), I = item(R, S, C),
    eval_requirements(Rs, P, Pred, Is).

% queries.pl
:- module(queries, [chk/3, chk_q/3]).
:- use_module('out_floor', [requirement/4]).
:- use_module('formalize_lib', [eval_requirements/4]).
chk(Ids, P, Chk)   :- eval_requirements(Ids, P, requirement, Chk).
chk_q(Ids, P, Chk) :- eval_requirements(Ids, P, out_floor:requirement, Chk).
```

```
$ printf 'chk(["r1"], p, C).\nchk_q(["r1"], p, C).\n' | scryer-prolog queries.pl
   error(existence_error(procedure,requirement/4),requirement/4).
   C = [item("r1",met,"s45")].
```

The bare atom **raises**. `call/5` runs inside `formalize_lib`, where `requirement/4` was
never imported. The module-qualified term works.

The same is true for a callee defined in the *same* module as the lambda site — this is
not a cross-module-only problem:

```
$ printf 'chk_local(["r1"], p, C).\nchk_local_q(["r1"], p, C).\n' | scryer-prolog queries2.pl
   error(existence_error(procedure,local_req/4),local_req/4).
   C = [item("r1",met,"s45")].
```

So **the naive form of remedy (a) — "respell to a bare predicate reference" — does not
work in the ISO export**, for any of the 317 sites, however the source is spelled. It works
on the engine and fails in Scryer, which is precisely the class of divergence this pilot
exists to find.

### 3.3 `meta_predicate/1` is the fix, and Scryer honours it

```prolog
% formalize_lib2.pl
:- module(formalize_lib2, [eval2/4]).
:- meta_predicate(eval2(?, ?, 4, ?)).
eval2([], _, _, []).
eval2([R|Rs], P, Pred, [I|Is]) :- call(Pred, R, P, S, C), I = item(R,S,C), eval2(Rs,P,Pred,Is).

% queries3.pl
:- module(queries3, [chk3/3]).
:- use_module('formalize_lib2', [eval2/4]).
local_req("r1", _, met, "s45").
chk3(Ids, P, Chk) :- eval2(Ids, P, local_req, Chk).
```

```
$ printf 'chk3(["r1"], p, C).\n' | scryer-prolog queries3.pl
   C = [item("r1",met,"s45")].
```

With `:- meta_predicate(eval2(?, ?, 4, ?))` on the library predicate, Scryer qualifies the
meta-argument at the **call site** — in `queries3` — and the bare atom resolves. This is
the standard module-transparency mechanism and it reproduces Clausal's `call_goal`
semantics exactly.

`meta_predicate` is already in the translator's operator table
(`clausal/tools/prolog_operators.py:175`) as a recognised directive name, but **nothing in
the translator or the exporter emits one today** (`grep -rn "meta_predicate"` over
`clausal/`, `tools/` and `docs/` returns only the operator-table entry, an unrelated
`globals_env.py` docstring, an example file, and two doc cross-references). There is no
Clausal source construct that would produce one — a Clausal library declares nothing about
which of its arguments are goals.

**Consequence for the whole note: every remedy below is conditional on emitting
`meta_predicate` declarations for the higher-order kit predicates, or on module-qualifying
every emitted predicate reference. Without one of the two, a lambda remedy converts a
silently-wrong export into a loudly-wrong one — an improvement, but not a fix.**

A last measurement, because it decides whether generated auxiliaries must be exported: a
predicate that is **not** in its module's export list is still reachable by both routes.

```
$ printf 'chk_meta(["r1"], p, C).\nchk_qual(["r1"], p, C).\n' | scryer-prolog queries4.pl
   C = [item("r1",met,"s45")].
   C = [item("r1",met,"s45")].
```

(`queries4.pl` exports only `chk_meta/3` and `chk_qual/3`; `lam_aux_1/4` is private, and is
reached once via a `meta_predicate`-declared host and once via `queries4:lam_aux_1`.) So a
lifted auxiliary need not pollute a published legal ontology's public surface.

---

## 4. Remedies, by class

### 4.1 Class (a) — 317 sites, 92 files: eta reduction

**The engine accepts a bare predicate reference wherever it accepts a forwarding lambda.**
Re-derived rather than quoted from `fe43afc0`, and through the *real corpus idiom* rather
than through `maplist` — a verbatim copy of `kit/formalize_lib.clausal:622-627`, with the
witness's own closure (Python driver stdout):

```
CLAUSAL Lam  -> [(['r1', 'r2'], 'p', [['r1', 'met', 's45'], ['r2', 'unmet', 's47']])]
CLAUSAL Bare -> [(['r1', 'r2'], 'p', [['r1', 'met', 's45'], ['r2', 'unmet', 's47']])]
IDENTICAL: True
```

and for an `-import_from`'d callee, both spellings (bare and dotted):

```
bare `requirement`                 lambda=[(['r1'], 'p', [['r1', 'met', 's45']])]
                                   eta   =[(['r1'], 'p', [['r1', 'met', 's45']])]   IDENTICAL=True
dotted `cmhelper.requirement`      lambda=[(['r1'], 'p', [['r1', 'met', 's45']])]
                                   eta   =[(['r1'], 'p', [['r1', 'met', 's45']])]   IDENTICAL=True
```

So the answer to the brief's CHECK is **yes on the engine, unconditionally** — including
the 116 of 317 class-(a) sites whose callee is not defined in the same file (201 are). The
engine imposes no qualification requirement. Scryer does (§3.2), and that is the whole
difficulty.

**Option A1 — respell the corpus and kit source; emit `meta_predicate` from the
exporter.**

`((ID, PR, S, C) <- aml_ctf_requirement(ID, PR, S, C))` becomes `aml_ctf_requirement`, in
317 places across 92 files in two sibling repos. The exported kit libraries gain a
`:- meta_predicate(…)` directive per higher-order predicate.

- *Correctness:* exact on the engine (measured above, three shapes). Exact in Scryer once
  the `meta_predicate` directives exist (§3.3, measured). The construct is **removed**
  rather than lowered, so there is nothing left for a later front end to get wrong.
- *Cost:* 317 source edits in `/workspace/clausify-domains` and
  `/workspace/clausify-executor-train/kit`, plus one directive per exported higher-order
  kit predicate. Not an engine change at all, except for the directive emission. Per the
  standing note, kit edits must be validated against the corpus's own Clausal test suites
  and checked against kit consumers in the six sibling repos before landing.
- *Benefit:* 47 files (40 corpus, 7 kit) go clean under strict (§2.4).
- *Risk:* the per-host caveat of §2.3 — a host that structurally inspects its closure
  argument would see an atom where it saw a `Lambda`. Three hosts read and clear; 36 not.
- *Tests to pin it:* (i) an engine test that
  `clausal_source_to_prolog` of the eta-reduced witness contains
  `eval_requirements(Ids, Profile, aml_ctf_requirement, Checklist)` and no `<`; (ii) a
  **Scryer-execution** test on the three-module layout of §3.2 asserting the bare atom
  resolves *with* the `meta_predicate` directive and raises `existence_error` *without* it
  — that pair is the whole point, and neither half exists today; (iii) an engine
  equivalence test on `eval_requirements/4` (lambda vs bare) whose two answer lists must be
  equal, i.e. §4.1's first block as an assertion; (iv) a refusal test that
  `((X, _) <- p(X, _))` is **not** treated as eta-reducible (§2.2's latent hazard).

**Option A2 — eta-reduce in the translator, emitting the bare name.**

The translator recognises the forwarding shape and emits `aml_ctf_requirement` for the term
that today refuses.

- *Correctness:* the same as A1 at the emission, and it needs the same `meta_predicate`
  directives, so it buys **nothing** on the ISO side that A1 does not.
- *Cost:* a second implementation of `unnecessary_lambda`'s legality analysis, over the
  Python AST, in a different repo layer from the rule. §2.1 shows the transliteration is
  faithful *for the 390 sites measured*; it is not the same code, and the two can drift.
  §6's `_detect_arrow` divergence is exactly what that drift looks like when it happens.
- *Which of `436ad553`'s preconditions apply here:* that commit's three findings are about
  `head_fold`, not `unnecessary_lambda`, but its *doctrine* — "legality must be a
  pre-condition", checked on the input before a rule rebuilds a term, because an occurs
  check cannot see into a term a rule just built — transfers directly. In A2 the
  pre-condition set is §2.1's six rows, all decidable on the input `Compare` node before
  anything is emitted, plus the `_`-parameter exclusion. Its finding 3 (reification drops
  keyword-argument *names*) has an analogue that A2 must respect: the translator must check
  `body.keywords == []` before reducing, which the rule also requires and which 0 of 390
  sites violate. Its finding 2 (`[*XS]` is not a list test) has no analogue here.
- *Verdict:* **not recommended.** It leaves 317 un-reduced lambdas in the Clausal source —
  where the engine's own rewrite rule says they should not be — and pays for a duplicated
  analysis to hide them at the boundary.

### 4.2 Class (b) — 10 sites, 8 files: partial application

All 10 are corpus, all 8 files are `queries.clausal` or `tests/test_queries.clausal`, and
all 10 are the same shape: a probe closure over a captured scenario. Verbatim:

```
eu/cbam/declarant_scope/queries.clausal:222                  bisect_flip/4  (X, V) < -cbam_what_if_kg(GOODS, N, X, V)
eu/merger/eumr_jurisdiction_turnover/queries.clausal:324     bisect_flip/4  (X, V) < -eumr_what_if_party(PARTIES, INDEX, COORD, X, V)
eu/peppol_einvoicing/queries.clausal:188                     flip_scan/4    (X, V) < -verdict_with(INVOICE, KEY, X, V)
eu/procurement/selection_criteria/queries.clausal:172        bisect_flip/4  (PROBE_VALUE_EUR_CENTS, IN_SCOPE) < -selection_criteria_scope_probe(PROFILE, PROBE_VALUE_EUR_CENTS, IN_SCOPE)
eu/procurement/shortlisting/queries.clausal:64               flip_scan/4    (X, STATUS) < -threshold_probe(PROFILE, KEY, X, STATUS)
eu/schengen_90_180/queries.clausal:163                       bisect_flip/4  (K, V) < -continuous_day_verdict(STAYS, ENTRY_YMD, K, V)
eu/schengen_90_180/queries.clausal:210                       bisect_flip/4  (K, V) < -entry_trip_verdict(STAYS, FROM_YMD, TRIP_DAYS, K, V)
eu/schengen_90_180_max_stay/queries.clausal:59               bisect_flip/4  (X, V) < -stay_eligibility(HISTORY, ENTRY_DATE, X, V)
eu/state_aid/de_minimis_cumulation/tests/test_queries.clausal:178  flip_scan/4  (X, V) < -de_minimis_what_if(GS, REF, X, V)
eu/state_aid/de_minimis_cumulation/tests/test_queries.clausal:189  flip_scan/4  (X, V) < -de_minimis_what_if(GS, REF, X, V)
```

Every one is a prefix of captures followed by the parameters in order — the textbook
`call/N` partial application. ISO does it natively:

```prolog
% partial.pl
call_goal(G, A, B) :- call(G, A, B).
probe(Goods, N, X, V) :- V is Goods + N + X.
apply2(G, X, V) :- call_goal(G, X, V).
via_compound(X, V) :- apply2(probe(10, 5), X, V).
```

```
$ printf 'via_compound(1, V).\n' | scryer-prolog partial.pl
   V = 16.
```

**But Clausal does not.** The same shape on the live engine (Python driver stdout):

```
CLAUSAL ViaLambda    -> [(1, 16)]
CLAUSAL ViaCompound  -> []
CLAUSAL ViaCallN     -> []
```

`call_goal(probe(10,5), X, V)` and its alias `call(probe(10,5), X, V)` both **fail
silently** — no solutions, no error. The mechanism is
`higher_order.py:27,37`: `_call_goal_n` tests `callable(goal_val) or
hasattr(goal_val, '_get_dispatch')`, and a partially-applied compound is neither, so
control falls to the bare `yield (_fail, DONE)`. (The neighbouring
`_registry.py:117-134` path *does* raise `type_error(callable, …)`, but only for a
`pythonic_ast` `Node`; a plain compound term does not reach it.) This is a small instance
of the standing "silence at a parsed boundary" pattern — it fails *closed*, so it is not a
soundness hole, but a meta-call given an uncallable term should say so.

That asymmetry rules out the obvious remedy.

**Option B1 — lower class (b) to a `call/N`-compatible closure term.**
Emit `cbam_what_if_kg(Goods, N)` as the third argument, and let ISO `call/4` append the
two parameters.

- *Correctness in Scryer:* exact (measured above), and the `call_goal/N` companion shim is
  the one-clause `call_goal(G, A, B) :- call(G, A, B).` used in every probe in this note.
- *The problem:* the ISO export would then accept a construct **the engine rejects**. The
  Clausal source cannot be respelled to match, because `ViaCompound` fails. The export and
  the engine would diverge in the direction of the export being *more* capable — which
  makes the export unverifiable against the engine for those 10 sites, and every G3 answer
  for them unfalsifiable.
- *Verdict:* **not recommended as a translator lowering.** Either teach the engine's
  `call_goal/N` partial application first (a separate engine change with its own design,
  and a genuine improvement independent of this note), or fold class (b) into class (c)'s
  lambda lifting, which handles it with no new semantics on either side. The population is
  10 sites in 8 files; folding is cheap.

**Option B2 — fold into (c).** `((X, V) <- cbam_what_if_kg(GOODS, N, X, V))` lifts to
`cbam_what_if_kg_probe_1(GOODS, N, X, V) :- cbam_what_if_kg(GOODS, N, X, V).` and the site
passes… a partially-applied term again. So B2 only helps if the *lifting* convention is
"aux takes the captures as leading arguments and the site passes an atom" — which it cannot
be, because the captures must be bound at the call site. **The honest statement is that
class (b) has no source-level remedy while `call_goal/N` lacks partial application**, and
that its 10 sites stay refused until either the engine gains it or the refactor's surface
provides a closure form. Both classes (b) and (c) therefore sit behind the same gate; see
§8.

- *Tests to pin whichever is chosen:* (i) an engine test asserting today's silent failure
  is either preserved deliberately or converted to `type_error(callable, …)`; (ii) a
  Scryer-execution test on `partial.pl` above; (iii) a differential test that runs the same
  probe predicate on both engines and asserts equal answer lists — the only test that would
  have caught the asymmetry.

### 4.3 Class (c) — 62 sites, 32 files: lambda lifting

The population, by reason (§2.2): 30 multi-goal bodies, 14 with a non-variable callee
argument, 9 with captures interleaved among parameters, 9 with a comparison/unification
body. Hand-verified examples, from the real source:

```
eu/merger/eumr_jurisdiction_turnover/queries.clausal:105  aggregate_over/3
    aggregate_over(PARTIES, ((P, V) <- (P is [V, _, _])), TOTAL_CENTS)

au/firb/notifiability.clausal:407  max_by/3
    (E, K) <- (E is [D2, _], K is D2)

eu/aml/amlr_beneficial_ownership_threshold/queries.clausal:131  flip_scan/4
    (B, V) <- amlr_bo_status([[B], *CHAINS], V)

eu/labour/posted_workers_long_term_trigger/queries.clausal:191  bisect_flip/4
    (N, V) <- ongoing_verdict(PRIOR_PERIODS, ONGOING_START_YMD, N, NOTIFIED, V)

eu/market_integrity/mar_insider_dealing/queries.clausal:179  include/3
    X <- (X is not E)
```

None of these is reducible to a name. The only general lowering is **lambda lifting**: for
each lambda, generate an auxiliary predicate whose arguments are the captured variables
followed by the lambda's parameters, and pass a partially-applied reference at the site.
Which runs straight back into §4.2: the site must pass captures, and Clausal's `call_goal`
cannot receive them. So class (c) is *lowerable to ISO* today but *not respellable in
Clausal* today, and lifting is therefore a **translator-side** remedy, not a source
migration.

Sketch, with the parts that are decisions rather than mechanics called out.

**Naming.** The generated name must be deterministic across runs and stable across
unrelated edits, because the exported `.pl` is diffed. Derive it from
`<enclosing predicate name>_<arity>__lam<K>`, where `K` is the ordinal of the lambda within
the enclosing top-level item in source order — not a global counter (a new lambda in an
earlier clause would renumber every later one and churn the whole file) and not a content
hash (unreadable, and it changes whenever a variable is renamed). With the per-item
ordinal, adding a lambda renumbers only the lambdas after it *within that one clause*.
Collisions with a real predicate must be refused, not silently suffixed.

**Placement.** `convert_module` (`clausal_to_prolog.py:463-545`) appends one or more
`PItem`s per top-level statement and then runs two post-passes: an export filter
(`_filter_module_exports`) and a `:- discontiguous` pass that fires for any predicate whose
clause run is interrupted by another item. **Emitting an aux clause immediately after its
host clause would interrupt the host predicate's run and cause `:- discontiguous` directives
to appear** — a visible, load-bearing change to every affected file. Aux clauses must
therefore be collected and appended in a block at the end of the module (or immediately
before the first aux's host predicate ends). This is a real constraint, discovered by
reading the post-pass, and it should be pinned by a test that asserts no new
`discontiguous` directive appears in a file that gains a lifted lambda.

**Export.** Aux predicates must **not** be added to the `:- module` export list — a
published legal ontology's export list is part of its public surface. §3.3's last block
verifies that a non-exported aux is reachable from a library meta-call, both via a
`meta_predicate`-declared host and via explicit `Module:aux` qualification. Note that
`_filter_module_exports` keeps only *locally defined* predicates in the export list, so an
aux would survive if it were ever added — the filter will not remove it. The exclusion has
to be deliberate.

**Singletons.** `_prefix_singletons` (`clausal_to_prolog.py:1666`) runs **per item**, and
its docstring says so explicitly ("Counted over *item* alone"). A lifted aux is its own
item, so its singleton analysis is computed over the aux clause and not over the host —
which is the correct scope and needs no change. A captured variable appears in both the aux
head and the aux body, so it is not a singleton; a parameter likewise. The one shape to
watch is a lambda parameter that the body never uses (`((X, Y) <- p(X))`), which lifts to
an aux with a genuinely singleton head argument and will be `_`-prefixed — correct, and
worth a test.

**Goal-position discipline.** The `goal_position` gate that `_convert_compare`
(`clausal_to_prolog.py:1396`) already carries for the `is`-RHS splat lowering exists
because a rewrite that produces a *goal* is only valid where a goal is executed. Lambda
lifting is the mirror case: it produces a *clause*, from a position that is a *term*. The
lifting must therefore not run through `_convert_expr`'s return value at all — it has to
hand a new `PClause` to `convert_module`'s item list while returning only the reference
term at the site. That is a structural change to the converter's contract (today
`_convert_*` returns exactly one `PTerm`), and it is the main implementation cost of this
class.

**Trade-offs.** Lifting is the only remedy that is correct for arbitrary bodies; it is also
the only one that makes the exported program *less* readable than the source (a legal
ontology gains 62 machine-named predicates), and the only one whose output cannot be
checked against the engine by running the same source on both, because the Clausal source
keeps the lambda. That last point is the argument for deferring it: see §7.

**Tests to pin it:** (i) a name-determinism test — translate the same file twice and byte-compare;
(ii) a churn test — add a lambda to clause 1 and assert the aux name of a lambda in clause 5
is unchanged; (iii) a no-new-`discontiguous` test; (iv) an aux-not-exported test;
(v) a name-collision refusal test; (vi) a Scryer-execution test for each of the four class-(c)
reason shapes, compared against the same predicate run on the Clausal engine.

---

## 5. `include/3` and the absent list higher-order predicates

`progress.md` records class L as "`include/3` missing from `LIBRARY_INJECTIONS`, one entry".
**That remedy does not work, and the measurement is one line.** `LIBRARY_INJECTIONS`
(`tools/iso_export/export.py:189-201`) injects `:- use_module(library(lists), [Name/Arity])`.
Scryer's `library(lists)` does not have `include/3`:

```prolog
% inj.pl
:- use_module(library(lists), [include/3]).
p(R) :- include(_, [], R).
```

```
$ printf 'p(R).\n' | scryer-prolog inj.pl
   error(existence_error(procedure,include/3),include/3).
```

The `use_module` directive itself is silently satisfied; the call raises. So injection
would move the error, not remove it.

What Scryer's `library(lists)` does and does not supply, measured in one consulted file
with the directive `:- use_module(library(lists)).`:

| present | absent |
|---|---|
| `maplist/2`, `maplist/3`, `foldl/4`, `length/2`, `member/2`, `append/3`, `nth0/3`, `sum_list/2`, `select/3` | `include/3`, `exclude/3`, `partition/4`, `msort/2`, `last/2` |

and, of the engine's own higher-order builtins
(`clausal/logic/builtins/higher_order.py:1-4`), Scryer additionally lacks
`max_by/3`, `min_by/3`, `take_while/3`, `drop_while/3`, `span/4`, `group_by/3`,
`sort_by/3`, `filter_map/3`, `tfilter/3`, `tpartition/4`, and `call_goal/1..8` itself.
Three of those reach the `.pl` from the 390 sites: `include/3` (6 sites), `max_by/3` (5),
`min_by/3` (2).

**What a pure companion needs.** The companion house style is cut-free and `->`-free
(`clausal_dates.pl`'s `valid_date/3` is documented as such). A three-clause `include/3`
with disjoint guards satisfies both:

```prolog
:- module(clausal_hof, [include/3, exclude/3]).
:- meta_predicate(include(1, ?, ?)).
:- meta_predicate(exclude(1, ?, ?)).
include(_, [], []).
include(G, [X|Xs], [X|Ys]) :- call(G, X), include(G, Xs, Ys).
include(G, [X|Xs], Ys)     :- \+ call(G, X), include(G, Xs, Ys).
exclude(_, [], []).
exclude(G, [X|Xs], Ys)     :- call(G, X), exclude(G, Xs, Ys).
exclude(G, [X|Xs], [X|Ys]) :- \+ call(G, X), exclude(G, Xs, Ys).
```

```
$ printf 'once(f(R)).\nonce(g(R)).\nfindall(R, f(R), All).\n' | scryer-prolog incuser.pl
   R = [3,4]
   R = [1,2]
   All = [[3,4]]
```

(`f(R) :- include(big, [1,2,3,4], R).`, `g(R) :- exclude(big, [1,2,3,4], R).`,
`big(X) :- X > 2.`) Solution-exact and single-solution — `findall` returns exactly one
answer, so the guard is not double-counted. It does leave a residual choice point (an
unwrapped `f(R).` at the toplevel prompts for more solutions), which is the price of being
cut-free; closing it needs either a cut, or `->`, or a reified-truth `if_/3` formulation,
and that is a companion-style decision for the operator rather than a correctness question.
Note the two `meta_predicate` directives: without them the companion has exactly §3.2's
problem — `call(G, X)` would run in `clausal_hof`.

**This is gated on closures translating at all.** Handed the pre-refusal emission of the
real `eu/market_integrity/mar_insider_dealing:179` site, the companion above raises a
*different* error, not an answer — the companion consulted with
`t(R) :- include(X < -(dif(X, e)), [a,b], R).`:

```
$ printf 't(R).\n' | scryer-prolog incsoup.pl
   error(existence_error(procedure,(<)/3),(<)/3).
```

`existence_error((<)/3)` instead of `existence_error(include/3)`. **All six** of the 390
sites that pass a lambda to `include/3` are class (c) — the four corpus sites plus two in
`kit/query_combinators.clausal` (`:165`, `:224`). Landing the companion before the lambda
remedy trades one loud error for a different loud error and moves no domain to green. **Order: lambda remedy first, companion second.** The companion
is nonetheless cheap, self-contained, and survives every refactor (Scryer will still lack
`include/3`), so it can be written now and landed second.

*Tests to pin it:* (i) companion unit tests in `companion_tests.pl` for each predicate,
including the empty-list and all-filtered cases; (ii) a test that the companion consults
without a `meta_predicate` warning and resolves a caller-module goal (§3.3's shape);
(iii) a test asserting `include/3` is **not** in `LIBRARY_INJECTIONS`, with this section's
`existence_error` as the reason in the comment; (iv) `COMPANION_SIGNATURES` gains a
`clausal_hof` entry and the signature cross-check covers it.

---

## 6. The `_detect_arrow` adjacency divergence

The refusal shipped in `884c16eb` deliberately calls the engine's own primitives — the
import at `clausal_to_prolog.py:31-34` says so: "We import the engine's own predicates
rather than re-implementing them so the translator's term-position rule cannot drift from
the clause-level rule the engine enforces." That is true of
`_refuse_arrow_lambda_in_term_position` (`:1354-1394`), which calls
`_engine_is_arrow_adjacent`.

**It is not true of the translator's own clause-level `_detect_arrow`**
(`clausal_to_prolog.py:591-599`), which uses the module-local `_leftmost_usub` (`:380-394`)
and performs **no adjacency check at all**. The engine's `_detect_arrow`
(`clausal/templating/term_rewriting.py:260-302`) does, at `:285-286`. The two disagree:

```
'X < -1'     engine _is_arrow_adjacent=False  engine _detect_arrow -> not an arrow
'X < - 1'    engine _is_arrow_adjacent=False  engine _detect_arrow -> not an arrow
'X <-1'      engine _is_arrow_adjacent=True   engine _detect_arrow -> ARROW
```

and the translator, on the same three sources (Python driver stdout, `strict=False`):

```
'X < -1\n'
   -> '_X :-\n    1.\n'
'p(X) <- (X < -1)\n'
   -> 'p(X) :-\n    X < -1.\n'
'X < - 1\n'
   -> '_X :-\n    1.\n'
```

A top-level `X < -1` — which the engine reads as a comparison — is emitted by the
translator as a **clause** `_X :- 1.` The spaced spelling `X < - 1`, which is
unambiguously a comparison in any reading, gets the same treatment. The body-position case
is correct (`p(X) <- (X < -1)` emits `X < -1`), because that path goes through
`_convert_compare`, whose refusal *does* consult adjacency and correctly declines.

So the hazard is narrow and exactly located: **only the clause-level arrow detection
diverges, and only for a top-level statement.**

**Incidence: zero — method first, then result.** This is a *different* scan from §2.1's,
and its method is not the census script's. §2.1 enumerates sites through the translator's
refusal hook, which only ever sees **term**-position arrows; the divergence here is at
**clause** level, which that hook cannot reach by construction. So this scan does not run
the translator at all:

- **File set:** the same walk as §2 — `rglob("*.clausal")` under
  `/workspace/clausify-domains` and `/workspace/clausify-executor-train/kit`, skipping any
  path with a `_`-prefixed component. 748 files; 3 fail `ast.parse` and are skipped;
  **745 walked** (705 corpus, 40 kit).
- **"Top-level" is `ast.parse(source).body`, nothing deeper.** A statement qualifies when
  it is an `ast.Expr` whose `.value` is an `ast.Compare` — exactly the shape
  `convert_module` hands to `_convert_stmt` → `_detect_arrow`
  (`clausal_to_prolog.py:463-483, 591-599`), i.e. the shape the diverging code path
  actually receives. Nested and body-position `Compare` nodes are deliberately excluded:
  this section's own transcript shows the body path is already correct.
- **Both verdicts are computed from the two real implementations, not restated.** The
  translator's rule is transcribed inline from `clausal_to_prolog.py:591-599` — `Lt` first
  op, leftmost `USub` present, `depth == 0`, `len(ops) == 1`, and *no* adjacency test; the
  engine's is the imported
  `clausal.templating.term_rewriting._is_arrow_adjacent(left, usub, source_lines)`, called
  with that file's own `source.splitlines()`, so the exact-character check at `:249-254` is
  the one running rather than the column-gap fallback. A site is DIVERGENT when the
  translator's four conditions hold and `_is_arrow_adjacent` returns `False`.

Result, with the denominators, so "zero" can be read against something (Python driver
stdout):

```
corpus: 705 files (0 unparseable), 8645 top-level Compare stmts, 8645 arrows, 0 divergent
kit:     40 files (3 unparseable),  963 top-level Compare stmts,  963 arrows, 0 divergent
```

**9,608 top-level `Compare` statements, every one of them a `<-` clause arrow both
implementations accept, and 0 divergent.** Note what the denominator is and is not: it is
not a population of comparisons among which none happened to diverge — in these trees a
top-level `Compare` statement is *always* a clause, because a bare comparison at file scope
would be a statement with no effect. The scan's real content is therefore the negative:
**no file in either tree writes a top-level `X < -N`**, so nothing today is mis-emitted as
`_X :- N.`

*(An earlier run of this same scan, before the trunk kit migration landed as
`clausify-executor-train@1587802` mid-session, returned 9,600; the 8-statement difference
is clauses that commit added to 8 kit files. The §2 lambda census was re-run against the
post-migration trees and is **row-for-row identical** — 390 rows, the same 246/97 and
144/15 splits, the same per-site class for every row.)*

**Proposed alignment.** Delete the translator's `_detect_arrow` and `_leftmost_usub` and
call `clausal.templating.term_rewriting._detect_arrow(left, ops, comparators,
self._source_lines)` at the clause level too, exactly as the refusal already does for the
term level. Two consequences to decide, not to assume:

1. The engine's `_detect_arrow` **raises** `_arrow_body_error` for `depth > 0` or a chained
   comparison, where the translator's returns `None` and falls through to a comparison.
   Adopting the engine's function wholesale converts a silent fall-through into a raise.
   That is the right direction under the standing fail-fast ruling, but it is a gating
   decision, not a refactor.
2. When `self._source_lines is None` — a programmatically constructed AST — the engine's
   `_is_arrow_adjacent` falls back to a column-gap heuristic (`1 <= usub_col - end_col <= 2`,
   `:257`) and raises `ValueError` if positions are missing entirely. The refusal path
   already catches that `ValueError` and declines (`:1379-1385`); the clause path would
   need the same guard, or `clausal_source_to_prolog_ast` callers that build AST by hand
   would start raising.

Because the census delta is zero, this is a latent-hole close with no migration cost —
structurally the same commit shape as `d0f92892`, whose census delta was also zero. It
should be a separate commit from anything in §4, and its commit message should say the
delta is zero so nobody reads it as a fix for a live bug.

---

## 7. Sequencing against the ISO-surface refactor

`docs/iso-export-pilot-2026-09.md:852-854` records that the dual front end is confirmed as
the refactor plan and that lowering decisions of this kind become refactor design inputs.
The 2026-09-03 ruling in `progress.md` already deferred lambda *lifting* to "design
note/refactor". So each remedy has to be scored on whether it survives.

| remedy | survives the refactor? | why |
|---|---|---|
| §4.1 A1 — source eta-reduction of 317 sites | **yes, entirely** | it deletes a construct from the source. Any front end over that source sees a bare predicate reference. It also aligns the corpus with the engine's own `unnecessary_lambda` rule, which is a source-quality win independent of ISO. |
| §3.3 — `meta_predicate` emission | **yes** | it is a fact about ISO module semantics, not about the Clausal surface. Whatever the front end, an exported higher-order predicate needs it. |
| §5 — `clausal_hof.pl` companion | **yes** | Scryer will still lack `include/3`. |
| §6 — `_detect_arrow` alignment | **mostly throwaway** | the refactor's ISO surface will not carry the `<-` / `< -` spacing ambiguity at all. But it is ~10 lines, it closes a latent hole today, and it removes a second copy of an engine rule — worth doing on those grounds, not on durability. |
| §4.1 A2 — translator-side eta-reduction | **throwaway** | its input representation (Python-AST `Compare`/`USub`) is what the refactor replaces, and it duplicates a rule the engine already has. |
| §4.2 B1 — `call/N` lowering for class (b) | **throwaway, and divergent meanwhile** | it encodes an ISO capability the engine lacks; the refactor's typed surface is where a closure form belongs. |
| §4.3 — class (c) lambda lifting | **algorithm survives, implementation does not** | any front end still has to lower a closure to a named predicate, so the naming/placement/export decisions of §4.3 are durable design. The converter surgery (returning a clause from a term position) is against a converter the refactor rewrites. |

The read: **§4.1 A1 + §3.3 is the only part of this note that is unambiguously durable**,
and it is also the part that covers 81.3 % of the sites and moves 47 files. Classes (b) and
(c) are 72 sites in 40 files, they need either an engine change (`call_goal/N` partial
application) or converter surgery that the refactor discards, and they are already
refused — which is the correct interim state.

---

## 8. Recommendation

**Migrate class (a) at the source, emit `meta_predicate`, land the harness first; leave
classes (b) and (c) refused until the refactor.** In order:

1. **Stage 0 — the harness, before any remedy.** As with the `==` spec, nothing here can be
   adopted on the strength of a text-shape assertion: the pre-refusal emission of §1.2 was
   pinned by the census as *clean* and by no test as *wrong*, and every claim in §3 and
   §4.2 is a claim about what an engine does, not about what a string looks like. The first
   commit must be a test harness that translates a Clausal predicate carrying a closure,
   runs the emitted `.pl` in Scryer, runs the same predicate on the Clausal engine, and
   compares answer lists. §3.1/§3.2's two blocks are its first two rows and they are red
   today, in opposite directions.
2. **Stage 1 — `meta_predicate` emission** for the exported higher-order kit predicates.
   This has to precede the source migration, not follow it: without it, eta-reduction
   turns a silently-wrong export into `existence_error` (§3.2), and the ratchet would
   record a "clean" count for files that cannot run.
3. **Stage 2 — the class-(a) source migration**, 317 sites across 92 files in the two
   sibling repos, validated against each domain's own Clausal test suites and against kit
   consumers in the six sibling repos. The migration must **skip**
   `kit/repros/callgoal_imported_lambda_repro.clausal:28` — the census counts it class (a)
   and it is not one; respelling it would destroy the fixture whose whole purpose is to
   assert `type_error(callable)` (§2.2 footnote). Expected effect, measured: 47 files (40 corpus, 7
   kit) go clean under strict; the refusal un-refuses naturally as sites migrate, exactly
   as the negated-membership migration was designed to. Before it lands, the per-host
   caveat of §2.3 should be discharged for the remaining 36 host predicates — a read, not
   a run.
4. **Stage 3 — the `clausal_hof.pl` companion** (`include/3`, `exclude/3`, and whichever
   of `max_by/3` / `min_by/3` the migrated files still need), with `meta_predicate`
   directives, cut-free, plus a test asserting `include/3` is *not* added to
   `LIBRARY_INJECTIONS` and §5's `existence_error` as the recorded reason.
5. **Stage 4 — the `_detect_arrow` alignment**, separately, with its zero census delta
   stated in the commit message, and the two fall-through-vs-raise questions of §6 put to
   the operator rather than decided in the patch.
6. **Not now:** class (b)'s `call/N` lowering (it would make the export more capable than
   the engine), class (c)'s lifting (converter surgery against a converter the refactor
   replaces), and translator-side eta-reduction (a duplicate of an engine rule). All 72
   sites stay refused, which is today's behaviour and the honest one — **at the cost named
   in §2.5: 27 files, being 22 corpus domains' `queries.clausal` surfaces plus two kit
   libraries (`query_combinators`, `optimization_lib`), stay refused for a (b)/(c) lambda
   and nothing else.** 24 of the 27 turn on class (c) alone, so if the operator wants to
   buy some of that back before the refactor, class-(c) lifting is the purchase and
   class-(b) `call/N` (3 files) is not.

Explicitly **not** recommended: adding `include/3` to `LIBRARY_INJECTIONS` (§5 — it does
not exist in `library(lists)`), and any remedy that emits a bare predicate reference
without a corresponding `meta_predicate` declaration (§3.2 — it raises).

---

## 9. What this re-derivation changed

| claim | source | re-derived verdict |
|---|---|---|
| 390 refused lambda sites — 246 corpus / 97 files, 144 kit / 15 files | migration worklist | **confirmed exactly**, through the translator's own refusal hook |
| many of the 390 are redundant eta-expansions | operator hypothesis | **confirmed and quantified — 317 of 390 sites (81.3 %), 92 files**; kit 92.4 %, corpus 74.8 %. (The census reports 318/81.5 %; one of those is not a lambda at all — §2.2's footnote and the row below.) |
| the pre-refusal emission was inert operator soup | `884c16eb` message | **confirmed**, and its canonical form measured: `<(','(Id,…), -(goal))`, a `(<)/2` term; it raises `existence_error((<)/6)` in Scryer |
| the engine's `call_goal` accepts a bare predicate reference | `fe43afc0` spike | **confirmed in the real corpus idiom** (`eval_requirements/4`), same-module and `-import_from`'d, identical solutions |
| respelling to a bare predicate reference fixes the export | implied by the refusal's own message | **FALSE as stated** — Scryer resolves the meta-call in the *library's* module and raises `existence_error`; the fix is `:- meta_predicate`, which nothing in the engine or exporter emits today (§3) |
| the engine's eta-reduction machinery can classify the 390 | brief | **partly** — the rule runs over the reflection vocabulary, which the translator never sees; its six legality clauses were transliterated to the Python AST and each was checked against all 390 sites (§2.1) |
| class (b) maps to ISO `call/N` directly | brief | **true of ISO, false of the engine** — `call_goal(p(A,B), X, V)` and `call(p(A,B), X, V)` both fail *silently* on the engine (`higher_order.py:27,37`); lowering it would make the export more capable than the engine |
| `include/3` is one missing `LIBRARY_INJECTIONS` entry (class L) | `progress.md` | **the remedy does not work** — Scryer's `library(lists)` has no `include/3`; injection moves the error rather than removing it. A companion is required (§5) |
| Scryer lacks `include/3` | brief | **confirmed**, and widened: `exclude/3`, `partition/4`, `msort/2`, `last/2`, `max_by/3`, `min_by/3`, `take_while/3`, `filter_map/3` are also absent; `maplist/2,3` and **`foldl/4` are present** |
| the translator's clause-level `_detect_arrow` does no adjacency check | refusal work | **confirmed**, with the emission measured (`X < -1` → `_X :- 1.`) — and **0 live instances** across all 9,608 top-level `Compare` statements in the two trees (§6 states the scan's method and denominators) |
| lambda lifting can emit aux clauses next to their host | — | **would fire the `:- discontiguous` post-pass** (`clausal_to_prolog.py:486-528`); aux clauses must be blocked at the module end (§4.3) |
| the Python-AST transliteration of "is a raw `Lambda` node" is faithful | §2.1, first draft | **one site wide** — it omits `_is_logic_var_name`, so the mixed-case head at `kit/repros/callgoal_imported_lambda_repro.clausal:28` classifies as (a) though the engine reifies it as a `Predicate`. Engine-faithful class (a) is **317, not 318** (§2.2 footnote) |
| deferring classes (b) and (c) is free, since they are already refused | implied by §7 | **has a named cost** — 27 files stay refused for a (b)/(c) lambda and nothing else: 22 corpus domains' query surfaces plus `query_combinators` and `optimization_lib`; 24 of the 27 are class (c) alone (§2.5) |
| a lifted aux must be exported to be reachable | — | **false** — a non-exported aux resolves both via a `meta_predicate` host and via `Module:aux` (§3.3) |

---

## 10. Stage-1 mechanism (ruled 2026-09-05)

§8's Stage 1 said *what* to emit and §3.3 proved *that* it works, but neither said how
the translator decides **which** predicates get a directive, on **which** argument
positions, with **what** mode. That gap was raised and the controller ruled it on
2026-09-05. What follows is the ruling plus the measurements that drove it; it is the
authority for the emission that now ships.

### 10.1 Why body-local detection alone is not enough — measured

A natural rule is "a predicate whose own clause bodies `call_goal` one of its
parameters is a meta host". It is necessary and it is not sufficient, in two
independent ways, both measured this session.

**The Scryer half.** With the ultimate consumer correctly declared
(`:- meta_predicate(eval_req(?, ?, 4, ?))` on `flib`), a library predicate that merely
*forwards* its argument and never calls it still raises:

```
$ printf 'thread_nometa(C).\n' | scryer-prolog dq.pl
   error(existence_error(procedure,local_req/4),local_req/4).
```

Adding `:- meta_predicate(failing_like(?, ?, 4, ?))` to that forwarding host — and
changing nothing else — fixes it:

```
$ printf 'thread_meta(C).\n' | scryer-prolog dq2.pl
   C = [item("r1",met,"s45")].
```

So **every predicate a meta-argument transits needs its own directive**, and the mode
it needs is the *ultimate consumer's* — routinely in another file.

**The population half.** A scan attributing all 390 lambda sites to their host and
classifying each kit host by whether its own bodies apply a meta-caller to a head
parameter (the scan reproduces §2.3's 390 sites / 39 hosts and its top-ten table
row-for-row, which is its warrant):

```
sites at kit hosts with a body-local meta arg : 258   (66 %)
sites at kit hosts that ONLY thread           : 116   (30 %)
sites whose host is an engine builtin         :  16   (4 %, §5's companion)
```

The 116 sit at **13 threading hosts** — `plan_entry/8` (30), `find_mus/4` (22),
`failing_ids/4` (20), `shrink_while/3` (9), `find_plan_once/7` (9), `assess/6` (7),
`override_where/4` (4), `find_plans/8` (3), `optimal_plan/8` (3), `optimize/8` (3),
`permitted_action/6` (2), `compliance_check/7` (2), `prop_missing_key_coverage/3` (2).
`find_mus/4` and `failing_ids/4` reach their consumer (`formalize_lib`'s
`eval_requirements/4`) across a **module boundary**, which a single-module translator
cannot see: `convert_module` takes one module's AST and `_convert_import_from` never
opens the imported file.

Worse than a miss: `verified_flips/5` (18 sites) is body-locally detectable for its
`DECIDE` argument but not for `APPLY`, which only the private helper `edit_flip/6`
calls. A body-local rule emits a directive there that **loads, looks emitted, and is
still wrong** — the failure mode this ladder exists to remove.

### 10.2 The ruling

**A-1 — mechanism: HYBRID, mirroring `module_signatures`.**

- The translator does **body-local detection** (`collect_local_meta_modes`, over the
  Prolog AST it is about to emit; base cases in `META_CALLER_SIGNATURES`), and
- accepts a **`meta_modes`** kwarg alongside `module_path` / `module_signatures`:
  `{module_path: {(name, arity): (per-argument modes, ...)}}`, `None` meaning "not a
  meta position". It is looked up under `module_path` **exactly as passed**, and
  unioned **per argument** with the local detection, under the single resolution rule
  of A-2: a position with one candidate mode gets that **integer**; a position whose
  sources disagree — local-vs-supplied included, neither wins — gets **`:`**; a
  position with no goal evidence gets **`?`**. Only predicates the module actually
  defines are declared.
- The **cross-module fixpoint** lives in the exporter's pass 1
  (`tools/iso_export/export.py`, `collect_meta_modes`), beside `collect_signatures`
  and built the same way: it already translates every module in the domain+kit
  universe, so it seeds each with its body-local evidence and propagates along
  argument-passing edges to a fixpoint, resolving a called predicate to its real
  defining module first (local, else whichever import defines it) so two unrelated
  modules that both define `helper/3` cannot feed each other a mode.

**A-2 — threading modes are per argument.** A threaded position inherits its ultimate
call site's mode, and the two arguments of one host resolve independently. Modes
accumulate as **sets**, so the outcome never depends on iteration order.

*The mode vocabulary Scryer honours*, probed (`cargo:0.10.0`) and pinned in
`tests/test_prolog_meta_predicate.py`:

| spelling | behaviour |
|---|---|
| integer `N` | honoured — qualifies, **and resolves the argument against `name/N` in the caller's module** |
| `0` | honoured — the `N = 0` case of the above, with the same arity-pinning |
| `:` | honoured — qualifies **without** asserting any arity |
| `?`, `+`, `-` | valid syntax, **non-meta**: the argument is not qualified |
| `*` | `syntax_error(invalid_meta_predicate_decl)` — must never be emitted |

**The arity-pinning row is the correction that decided the contract, and it overturns
this note's first reading of its own probe.** The original probe used hosts whose
argument is called at exactly ONE arity; there every integer works, and it was
tempting to conclude the integer's value is ignored. It is not — the effect is
invisible until the caller's module defines the same name at more than one arity. With
a caller defining both `p/2` and `p/3`, and a host calling its argument at both:

```
mode 2 -> L = [short]        only the 2-appended clause resolves
mode 3 -> L = [long]         only the 3-appended clause resolves
mode 0 -> L = [short,long]   ... but only because no p/0 exists
mode : -> L = [short,long]
```

and adding a `p/0` fact to that caller makes **mode `0` bind to it and hand the caller
back unbound variables** — no error, wrong answers. So neither "pick any candidate"
nor "fall back to `0`" is safe.

*The contract, as shipped:*

| candidate modes for a position | emitted | why |
|---|---|---|
| exactly one | that **integer** | most precise; the spelling §3.3's verified probe uses |
| more than one | **`:`** | it *is* a goal, but its call arity varies, and any integer would drop every other chain |
| none | **`?`** | no goal evidence; a bare reference consumed there raises `existence_error` at G3 — loud, and accepted |

`?` is the loud outcome and is reserved for genuine non-evidence; `:` is what makes an
ambiguous-but-certain goal position work at *every* arity. Step B respells only chains
that are annotated.

**A-2b — evidence is read from GOAL POSITIONS ONLY.** Both scans — the translator's
body-local detection and the exporter's threading edges — walk a clause body through
the goal combinators (`,`, `;`, `->`, `\+`, `once/1`, `findall/3`'s goal argument,
`catch/3`, …) and stop at everything else: a plain compound is a goal, but its
arguments are data. Without that fence a clause that merely *builds* a term shaped
like a meta-call —

```
mk(D, X, Y, T) <- (T is host(D, X, Y))
```

— gives `D` a mode, and the emitted directive makes Scryer module-qualify an ordinary
data argument at every call site. Measured: the caller passes `foo`, gets back
`m:foo`, and a later `X == foo` **fails with no error anywhere**. Latent in the corpus
today (every live hit is goal-position) and unguardable after the fact, so it is fenced
at the source.

For the same reason `META_CALLER_SIGNATURES` carries **only what a real host reaches** —
`call_goal/N` and its engine alias `call/N`. An earlier draft also listed `include/3`,
`exclude/3`, `max_by/3` and `min_by/3` on the reasoning that a host reaching one *would*
be a meta host; they were dropped, because no kit host reaches any of them and they are
exactly the shapes a legal corpus is most likely to use as ordinary data constructors.
Step B re-adds `include/3` when the `clausal_hof` companion exists and something
consumes it. Removing them changed no measured figure.

**A-3 — acceptance is call-through, not text.** Three shapes, each consulting real
translator output in real Scryer and CALLING a bare reference through it, each paired
with a no-directive control that must raise: (i) a body-local host, (ii) a threading
chain across two modules, (iii) a two-meta-argument host with both arguments
exercised. The trunk suite adds a fourth: export a domain end to end, then call
through the staged tree.

**A-4 — placement.** Directives follow the `:- module` directive, alongside the
`discontiguous` pass and before it, emitted in first-appearance order so output is
byte-stable. A hand-written `:- meta_predicate` in source suppresses the generated one
for that predicate.

### 10.3 What the mechanism achieves, measured on the real kit

Running the exporter's fixpoint over the real kit and corpus, all **34 kit-defined
hosts** resolve at least one meta position — covering all **374** kit-hosted sites of
the 390, **including all 116 at the 13 threading hosts** (zero under body-local
alone). Spot values, each matching the host's own documented contract:

```
find_mus/4        -> (None, None, 4, None)      three hops, across a module boundary
failing_ids/4     -> (None, None, 4, None)      across a module boundary
verified_flips/5  -> (None, None, 3, 2, None)   APPLY and DECIDE, independently
plan_entry/8      -> (None, 3, 5, 2, None, ...) ORACLE, ACTIONS, SATISFIERS
actions_on_schema/4 -> (5, 2, None, None)
```

The remaining 16 sites pass their lambda to an engine builtin (`include/3`, `max_by/3`,
`min_by/3`, `call_goal/N`) and are §5's companion work, in step B.

Re-exporting five real domains with and without the fixpoint changes **nothing but
added `:- meta_predicate` lines** — identical error sets, no other line added, none
removed. For `th/visa`, body-local detection alone emits 3 directives in
`formalize_lib.pl` and the fixpoint adds the 4th, `assess/6` — precisely the threading
host.

Both measurements in this section are re-runnable rather than transcribed:
`python -m tools.iso_export.meta_modes_audit` (trunk) regenerates the host table and
the collateral diff. Its census reproduces §2.3's 390 sites / 39 hosts by
construction, which is what licenses reading the rest of its output. The hermetic
form of the same question — does every threading host resolve? — is pinned against a
committed fixture universe in `tools/iso_export/tests/test_meta_modes.py`.

### 10.4 Still true after Stage 1

Stage 1 does **not** by itself make any refused site translate: the 390 lambdas are
still refused, exactly as §8 intends. What it removes is the trap §8's ordering names
— that Stage 2's eta-respell would otherwise convert a refusal into a runtime
`existence_error` while the ratchet counted the file clean. Scryer still has no
`call_goal/N` (§5), so a staged kit library that calls one needs the companion before
it can run; that is step B.

---

## 11. Capture semantics (proposed 2026-09-05, AWAITING OPERATOR RATIFICATION)

The designer raised, and this section records for ratification, what an
implicitly-captured variable *means* at runtime. Nothing here is settled until
the operator rules and an engine probe confirms the engine agrees; the export
consequences below are conditional on that.

### The proposal

A `<-` lambda shares its enclosing clause's scope. Parameters (the head tuple)
are explicit and fresh per call. For a **capture** — a body variable that also
appears in the enclosing clause — the proposed rule is **capture-by-value at
call time**:

- **bound capture** → its value flows into the lambda (structurally: the bound
  parts of the term flow in, unbound sub-parts become fresh — i.e. the
  `copy_term/2` rule, not a binary ground/unground test; a capture bound to
  `f(A, _)` flows `f(A, Fresh)`).
- **unbound capture** → each call gets a **fresh** unbound variable; the lambda
  does not bind the enclosing variable, and successive calls do not see each
  other's bindings.

The motivating argument (the designer's) is decisive and correct: if an unbound
capture were truly shared and the lambda is applied many times, the first call's
binding would stick and later calls would be silently constrained by it — "which
call gets the value?" has no good answer, so the safe answer is *none*: no
unbound sharing.

### Where this lands in the Prolog design space

This is exactly `library(yall)`'s **default** (`copy_term` the lambda per call)
and the complement of its `Free/` marker (which opts back into true sharing).
`library(lambda)` draws the same line with `\`/`+\`. The designer reached
yall's default from first principles rather than from the library — a strong
signal the rule is the right one. The one capability it forgoes is
**bind-and-return-through-a-capture** (the accumulator / shared-logic-variable
idiom) — which is precisely what `Free/` exists to allow, and which the corpus
does not use (its closures are passed to HOFs, never used as inline partial
goals that contribute bindings back).

### One refinement to the designer's two rules

The designer stated two principles: (A) "same identifier = shared", and (B)
"unbound capture → fresh per call". For a **bound** capture these agree. For an
**unbound** capture they conflict — (A) says share the variable, (B) says do
not. (B) is the intended resolution, and it reframes (A): capture shares the
**value**, not the **variable**. Restated as one rule: *a capture flows its
value in; an unbound capture has no value to flow, so it contributes a fresh
variable each call.* That is capture-by-value / copy-at-call, and it is
internally consistent where the two-principle phrasing is not.

### Export consequences (why this is good news)

Capture-by-value makes the export trivially ISO-safe: `copy_term/2`, `call/N`
and `=../2` are all ISO, so a class-c lift can substitute a ground capture
(the common case) or `copy_term` a partially-bound one per call, with no
true-sharing machinery. It also means the lifting sketch in §5 (captured
free vars → leading aux arguments) is only correct for **ground** captures
(where sharing and copy coincide); for an unbound capture called multiply,
lifting-by-shared-argument would implement *sharing*, the opposite of this
proposal, so a lift of that shape must `copy_term` per call or be refused.

**Today there is no export risk either way:** the export refuses every case
where the two semantics are observable — unbound captures live only in class-b
(constant/positional, refused) and class-c (refused pending the refactor); every
class-a site (Phase C) captures nothing, and the corpus's class-b/c captures are
ground constants or ground query inputs, where sharing and copy are identical.

### Open items before ratification

1. **Probe the engine.** Does the engine's meta-call (`call_goal`) currently
   copy the closure per call (capture-by-value) or share unbound captures? An
   unbound-capture-called-twice fixture answers it in minutes. The export must
   match whatever is ratified; if the engine shares today and the ruling is
   value, that is an engine change, not just a doc.
2. **The advisory lint** (`todo/lambda-implicit-capture-advisory-lint.md`) is
   well-defined only once this section is ratified — the capture/body-local
   partition it reports is this section's partition.

### Probe result (2026-09-06): the engine ALREADY implements capture-by-value

Open-item #1 is closed. Two probes against the live engine (`call_goal` on
lambdas capturing an enclosing clause variable):

- **Unbound capture is fresh per call.** Two lambdas both capturing an unbound
  `X`, one unifying `X` with `red`, the next with `blue`, then reading `X`:
  **1 solution, `X` unbound afterward.** If `X` were shared, the second call
  would unify `blue = red` and fail (0 solutions). It did not — each call bound
  a fresh copy; the enclosing `X` was untouched.
- **Bound capture flows its value in.** `X` bound to `red` before a lambda that
  checks its argument against the captured `X`: **1 solution, value `red`.**

So the designer's proposal DOCUMENTS existing behavior, not a change: ratify and
the probes become the regression guard. (The partially-bound case — a capture
bound to `f(A, _)` flowing `f(A, Fresh)` — was not independently probed; it
follows by `copy_term` composition from the two confirmed halves and should be
pinned when the semantics test is committed.)

### Explicit sharing (`free(VAR)`) and the monotonicity question

The designer asks: to regain bind-and-return-through-a-capture (which by-value
forecloses), mark truly-shared variables explicitly — `free(VAR)` / `shared` /
`nonlocal` — so the compiler keeps them shared instead of copying; term-expanded,
compile-time-checked to be in the enclosing scope, removed as a no-op goal. And:
does that subvert monotonicity?

**Mechanically this is exactly `library(yall)`'s `Free/[Params]>>Body` and
`library(lambda)`'s `+\`** — opt-IN sharing over a copy-by-default lambda. The
designer's default choice (unmarked = safe/copied, marked = shared) is the
better of the two conventions, because the *dangerous* thing — sharing — is the
one made visible, not the safe thing.

**On monotonicity — the honest answer is "no, but it opens the door":**

- A shared unbound capture is NOT inherently non-monotone. `foo(X, a), foo(X, b)`
  with a shared `X` is just `∃X. foo(X,a) ∧ foo(X,b)` — a legitimate conjunction
  with a shared existential, fully declarative and monotone. "First binding
  wins, the rest must unify" is ordinary unification, squarely inside the logical
  reading. So `free()` does not, by itself, break anything.
- The real tension is a **quantifier one, not a soundness one**: a lambda's
  parameters are ∀-like (fresh per application), a shared capture is ∃-like (one
  witness across all applications). One syntactic scope now carries two quantifier
  meanings, told apart only by the marker. That is a scoping subtlety, not a
  monotonicity violation — and making the ∃-set explicit is precisely how yall
  keeps it legible.
- Where monotonicity (really: commutativity + the declarative reading) DOES get
  lost is the **imperative use** the escape hatch enables: a `free(Acc)` threaded
  as a left-to-right accumulator, bound on one call and extended on the next. That
  pattern is order-dependent (reorder the elements, change the answer), and it
  interacts badly with `copy_term`-based HOFs (`findall`/`bagof` copy the closure
  and silently sever the shared `Acc` — the classic footgun). Such a program is
  still logically sound (it has an ∃ reading), but its author is thinking
  imperatively and the two readings diverge. That divergence, not unsoundness, is
  the cost.

**Recommendations if `free()` is adopted:**

1. Keep it opt-in over the safe default (as proposed) — this is the sound stance.
2. Prefer a HEAD-position free-set (yall's `Free/...` shape) over a standalone
   in-body `free(VAR)` goal: head position makes the sharing scope syntactic and
   order-independent, where an in-body goal invites "does its position matter?".
   If the Python-surface ergonomics favor a body pragma, fix its scope to the
   whole lambda regardless of position and say so.
3. The compile-time check ("`VAR` is actually in the enclosing context") is worth
   having and catches the typo case the advisory lint targets — a `free(VAR)`
   naming a variable that is NOT enclosing is almost certainly a mistake; make it
   an error, not a warning, since the marker is a deliberate act.
4. The marker is a precise EXPORT signal: a `free()`-marked capture is the one a
   class-c lift must implement with a genuinely shared argument — or refuse when
   it flows through a copying HOF, since ISO `findall`/`bagof` will sever it. An
   unmarked capture stays by-value and exports trivially. So `free()` also draws
   the line between "liftable today" and "refuse pending analysis" on the export
   side.

### Should free-sets exist at all? (2026-09-06) — recommendation: NO

The designer, uneasy that free-sets feel extra-logical, asked whether bindings
can escape a copying boundary some other way, and whether there is an argument
against allowing the escape at all. There is, and it is strong; this subsection
supersedes the "if `free()` is adopted" recommendations above (which stand only
as *how* one would, not *whether* one should).

**Every mechanical alternative is MORE extra-logical than free-sets.** The
Prolog-ecosystem ways to get a binding out of a copied closure — global
variables (`nb_setval`/`b_setval`), `assert`/`retract`, destructive `setarg` —
are each further from the logical reading than an explicit shared logic variable,
and none is ISO-portable in spirit. That free-sets are the *cleanest of a bad
lot* is itself the tell: the escape need should be designed away, not mechanized.

**The relational answer: output is an argument, not an escaped binding.** Every
genuine case that seems to want escape is better served by making the result a
parameter of the higher-order relation:

- accumulation → thread it through the HOF's own params (`foldl`'s `Acc0/Acc`),
  not through a capture;
- "return the first match" → the HOF binds a `Result` *argument*; the closure only
  tests, via its own params;
- collect many → `findall/bagof` already return a list argument.

Under this discipline copy-by-value is *complete*: nothing needs to escape,
because outputs flow through relation arguments into the caller's clause.

**The deeper point — sharing already lives in clause scope.** Variables in a
clause body share by default; that is what a clause body is *for*. A lambda is
the tool for the other thing — a reusable, copy-per-application closure. You never
need a lambda to *also* share, because when you want sharing you simply do not
reach for a lambda: you write the goals inline in the enclosing clause, where they
share naturally. free-sets try to make one construct do both jobs, which is
exactly why they read as extra-logical — they are. Keep the two jobs separate:
**lambda = copy-by-value, always; want sharing = use the clause you are already
in.**

**Four reasons to leave free-sets out:**

1. *Unnecessary* — output-as-argument + clause-scope-sharing cover every real
   need (no counterexample survives: generators/memoization/effects are
   tabling/`assert`/effect-goals, not lambda captures).
2. *Footgun* — a shared unbound capture is silently severed by `copy_term`-based
   HOFs (`findall`/`bagof`), the classic wrong-answer trap.
3. *Breaks a universal invariant* — without free-sets, EVERY lambda is
   copy-by-value: referentially transparent, order-independent, copy-safe. That
   invariant is worth more as a universal law than free-sets are as a feature;
   adding them makes every lambda site "check for a free-set" for tools,
   reviewers, and the exporter.
4. *Non-ISO-exportable* — copy-by-value lambdas export totally and cleanly (eta →
   atom, positional/closure → aux predicate over captured *values*). A free-set
   lambda needs true cross-copy sharing reproduced in ISO, i.e. globals/mutable
   refs — non-portable — or an export refusal, making it a two-tier feature that
   cannot appear in exportable code anyway. That cuts directly against the
   ISO-compatibility goal this whole document serves.

**Steelman and its resolution.** Coroutining / CLP genuinely rely on shared logic
variables across goals (attributed vars, residual `dif`/constraints) — but those
are clause-scope shared variables in a conjunction, NOT lambda captures, and are
always allowed. And deep result-threading can be verbose — but the fix is a
better HOF signature, not a capture escape. Both reduce to the same rule: sharing
is a property of the clause, applied-freshly is a property of the lambda; keep
them distinct and free-sets have nothing left to do.

**Recommendation:** do not add free-sets. Keep lambdas purely copy-by-value
(already the engine's behavior). If a `free`-shaped need ever surfaces that
output-as-argument genuinely cannot serve, revisit — but treat its appearance as
a signal to fix a HOF's signature first.

Awaiting operator review.
