# One name at several arities in one file (ISO) — census and plan

2026-09-29. Operator ruling (direct): "allow one name at two arities, like
ISO". Branch `feat/multi-arity-names-2026-09-29`, base canonical main
`530814b4`.

Trigger: the `.pl` import path cannot load a file that defines
`call_goal/1..8`. Minimal repro:

```
p(X) <- (X is 1)
p(X, Y) <- (X is Y)
```

```
SyntaxError: functor p/2 conflicts with the declaration of p/1 in the same file
  ... A functor name has exactly one arity in Clausal ...
```

ISO 13211-1 §7.1.1 / §7.5: a procedure is identified by its predicate
indicator `Name/Arity`; `p/1` and `p/2` are unrelated procedures. Scryer
agrees. There is no ISO notion of a field name, so everything below about
FIELDS is Clausal-only.

## Headline

The rule is enforced at **compile time only**. The runtime has been
`(functor, arity)`-keyed since the 2026-09-24 "name + ARITY" ruling, which
already lets an importer define a local `p/2` next to an imported `p/1`,
and it already lets `-dynamic(p/1)` sit beside clauses for `p/2` in one
file. So the change is **contained**:

- Python only. No C file is touched.
- `_get_dispatch` is not on the path. A predicate is a mangled handle
  resolved at the CALL arity by `_dispatch_at`, and that path is already
  arity-keyed.
- Existing programs are unchanged. Every valid program today has one arity
  per name. For such a name the rewriter takes the unchanged code path and
  emits byte-identical module code. The new path runs only where today's
  code raises.

Census: **44 sites**.

| Kind | Sites | Must change | Already OK / unchanged by design |
|---|---|---|---|
| Rewriter state + head sites (`term_rewriting.py`) | 17 | 6 | 11 |
| Runtime head declaration record (`predicate.py`, `compiler_v2.py`, `constants.py`) | 10 | 8 | 2 |
| Field-name / data-functor readers (by name) | 6 | 1 | 5 (data functors stay one arity per name) |
| Dispatch / call / solve / tabling / listing / meta | 9 | 0 | 9 |
| Diagnostics text | 3 | 1 | 2 |
| `.pl` translator + exporter | 7 | 0 now (3 follow-ups) | 4 |
| Tests pinning the rule | 32 tests, 7 files | 22 flip | 10 stay errors |
| Docs | 4 files | 4 | — |

## Semantics decisions

**D1. A procedure name may have any number of arities in one file.** This
applies when every earlier head of the name was a CLAUSE head (a rule, a
fact or a DCG rule). A `-dynamic(p/N)` placeholder or a bare `p/N`
export entry never blocks it. Both are unseated by the first clause, as
today. ISO.

**D2. A name whose field names were DECLARED stays one arity per file.**
This covers a fielded `-module`/`-private` entry (`-private([point(x, y)])`,
`-module(m, [f(A)])`) and `-edcg_pred`. A clause head at another arity is
still the old `SyntaxError`, message unchanged. A fielded declaration is
per name: `point(x=1)` names a field of THE point, and the exec-time
signature registry (`FUNCTOR_SIGNATURES_KEY`, `declared_fields_by_name`)
is keyed by name. Keeping this an error is the conservative choice: it is
an error today, and it stays one. ISO has no fields, so ISO is silent
here. Operator question Q1.

**D3. A keyword head** (`p(a=1)`) is matched against the arity it was
written at (positional + keyword count) when that arity is known.
Otherwise it goes through the old check, which gives the old error. A
keyword head never opens a new arity: keywords name fields, and fields
belong to a declared arity.

**D4. Bare `p` in a DATA position is the atom `p`**, whatever arities
`p` has. That is today's behaviour (`q(X) <- (X is p)` binds `X = 'p'`),
and it is ISO: a name alone is an atom.

**D5. A written compound `p(A, B)` in a data position is the compound at
the written arity**, `('p', A, B)`. This is ruling C (2026-09-24), already
implemented. Positional construction never needs to choose an arity.

**D6. A handle (`m.p`, a seam `--p`, `call(p, X)`) names the procedure
NAME.** The arity is chosen at the call, from the number of arguments.
This is already how handles dispatch (`_dispatch_at(handle, arity)`). The
ISO analogue is `call/N` with an atom.

**D7. A call at an arity the name does not have is still an error.**
`PredicateArityMismatchError` / `existence_error(procedure, p/3)` is
unchanged. The message reads "defined at arity N" when there is one other
arity, and "does not accept N arguments" when there are several (it
already degrades that way). A call at an existing arity is fine.

**D8. A DCG nonterminal `s//1` next to `s//2`** is `s/3` next to `s/4`:
D1 applies (ISO 7.14 / DCG draft: `s//N` is `s/N+2`).

**D9. The `$declare_head` runtime record becomes per `(name, arity)`.**
The emitted call is unchanged (`$declare_head('p', fields)`). Only the
record it keeps changes. One observable difference: during the LOAD
window only (before `compile_module` step 4a-bis retires the record), a
file that writes `-dynamic(p/1)` and then clauses for `p/2` reports
arities `{1, 2}` for `p`, instead of `{2}`. After the load the Database
answers the same as before. This is more correct, since both are declared
predicates, and it is the only difference an existing program can observe.

## Census

### A. Rewriter (`clausal/templating/term_rewriting.py`)

| # | Site | Assumption | Change |
|---|---|---|---|
| A1 | `_seen_functors: dict[name, fields]` (~5743) | one field tuple per name | KEEP as the name's PRIMARY (first) registration; add `_functor_arities: dict[name, dict[arity, fields]]` holding every arity |
| A2 | `_functor_decl_site` (~5755) | one site per name | keep; per-arity site in A1's map is not needed for messages |
| A3 | `_register_functor` (~5904) | writes the one entry | also records the arity in A1's map; new `_register_functor_arity` for a second arity (no hide re-check needed, same name) |
| A4 | rule head (~8505) `prev_fields = _seen_functors.get` | head is at the one arity | `_prev_fields_for_head(name, n, kw, node)` (new): the fields AT n if known; a NEW arity if D1 allows it; else the primary (the old check raises) |
| A5 | fact head `_build_fact_statements` (~7006) | same | same helper |
| A6 | 0-arity fact `_build_zero_arity_fact_statements` (~7060) | `foo(1), foo,` is padding | same helper at n=0 |
| A7 | DCG `_finalize_dcg_rule` (~10580) | "One name, one arity" comment; only duplicate names trigger a check (a SHORTER `s//1` after `s//2` slipped past the check and died at run time) | same helper, n includes the two state args |
| A8 | `_check_head_signature` (~6050) messages | "A functor name has exactly one arity in Clausal" | reachable only for D2 and keyword heads now; reword to "a DECLARED functor has one arity" and point at `name/N` in the list as the ISO spelling |
| A9 | `HeadFieldNames` emission (~7758) | `{name: fields}` | also `{(name, arity): fields}` for every arity (new node field `by_arity`) |
| A10 | `_unseat_directive_minted` (~6325) | name-level | unchanged: a placeholder is unseated by the first clause of any arity, as today |
| A11 | `-dynamic` registration (~8674) | registers only the first spec per name | unchanged (a placeholder builds no head; the Database marks every `(f, a)`) |
| A12 | `_declare_predicate_export` bare `name/N` (~8898) | first spec per name | unchanged (same reason) |
| A13 | `-module`/`-private` fielded entries (9024, 9104), signature registry emission (~4700) | name-keyed | unchanged: D2 |
| A14 | `-edcg_pred` / `_edcg_preds` (~10331) | name-keyed | unchanged: D2 |
| A15 | `_emit_head_positionally` (~6226) | keyed on prev_fields + import | unchanged (a new arity passes prev=None, so it emits keywords, as a first clause does) |
| A16 | TermTransformer `_declared_functors` 0-arity value check (~3672) | primary's length | unchanged: `_zero_arity_heads` (prepass over the file text) already covers every `/0` head, whatever its order |
| A17 | name-level membership reads (`in _seen_functors`: comma-optional fact detection 8611/8636, `_settle_atom_functor_sites`, constants clash, var-shaped name check, `-hide` collision, 9202, 9671) | "is this name a functor here" | unchanged: this question is about the name |

### B. Runtime head-declaration record

| # | Site | Change |
|---|---|---|
| B1 | `predicate.declare_head` / `PREDICATE_HEADS_KEY` (`predicate.py` ~1961) | record `{functor: {arity: (fields, site)}}` |
| B2 | `_declares_over` (~1916) | "fields differ" is compared AT the declared arity; a new arity counts as declaring (rebinds the same handle value, a no-op) |
| B3 | `declared_head(namespace, binding, arity=None)` (~1829) | an `arity` parameter; with none, it returns the first-declared entry (only existence and single-arity callers use that) |
| B4 | `loading_head_fields(binding, arity=None)` (~1888) + new `loading_head_arities` | per arity |
| B5 | `is_declared_predicate` (~1688) | `arity in loading_head_arities` |
| B6 | `predicate_arities_for` (~2263) | the set of loading arities |
| B7 | `field_names_for` (~2326) | passes the arity through |
| B8 | `head_cell` (~2047) | builds against the record AT the written arity (`len(args) + len(kwargs)`); with a single record, the old behaviour byte for byte |
| B9 | `compiler_v2._local_binding` / step 4 (~1234, ~326) | per-arity `declared_at` and per-arity signature from A9 |
| B10 | `constants.py:260` (construction through a local predicate) | picks the record at the written arity |

### C. Field-name / data-functor readers keyed by NAME

| # | Site | Verdict |
|---|---|---|
| C1 | `Database.declared_fields_by_name` (`database.py:1323`) | data declarations only; D2 keeps them one arity per file; unchanged |
| C2 | `terms_to_ast.functor_signature_for` (~378) | same; unchanged |
| C3 | `FUNCTOR_SIGNATURES_KEY` exec-time registry (`cells.py:219`) | same; unchanged |
| C4 | `terms_to_ast.cell_signature_for_name` handle arm (~483): `term_field_names_of_class(binding)` has no arity | CHANGE: when the name has several arities it answers `None` today, so positional data construction must still build the compound at the written arity. Ask `field_names_for(binding, arity=...)` when an arity is known. Verified by test |
| C5 | `seam.py:122-140` keyword placement for `--p(k=v)` | keyword construction of a multi-arity PREDICATE name goes through C4 at the written arity; nothing else changes. Operator question Q3 |
| C6 | `term_expansion.py:275-300` `functor_arities.setdefault` | pre-minting of unbound DATA functors in expansion patterns; data only, unchanged |

### D. Already arity-keyed (verified, no change)

`Database` rows/dispatch/signatures/dynamic/tabled/discontiguous/meta
specs keyed `(functor, arity)`; locked-dispatch cache `$disp_<name>_<n>`;
`_dispatch_at` (handle resolved at the call arity; frozen `_get_dispatch`
not involved); `solve.call` phase 5 + `binding_grants_arity`;
`_term_to_goal`; `_tabled_call_site` / `tabled_home_of`;
`meta_predicate.lookup(fname, arity)`; `listing` (lists each arity);
`clause/2`; `_plant_imported_rows` (plants every arity of an imported name).

### E. Diagnostics

| # | Site | Change |
|---|---|---|
| E1 | `predicate_diagnostics._describe_mismatch` remedy (~245-268): "one name has one arity, and the head is refused at load" | CHANGE: now false; the remedy becomes "define `f/N` (a clause head with N arguments), or call it with M" |
| E2 | `_refuse_if_known_at_another_arity` / `_refuse_unqualified_other_arity` `others[0] if len(others)==1` | unchanged (degrades to "does not accept N arguments"; a follow-up could list the arities) |
| E3 | `_declared_export_entry` (first exported arity for an unloaded sibling) | unchanged; suggestion text only (follow-up) |

### F. `.pl` translator / exporter

| # | Site | Verdict |
|---|---|---|
| F1 | `tools/prolog_to_clausal.py` translates `foo/1` + `foo/2` as-is | no change; the load was the only blocker (the call_goal/1..8 trigger) |
| F2 | translator `_data_functors` skips a DATA name used at two arities (~565) | consistent with D2; unchanged |
| F3 | translator `_emit_import_list` drops the arity: `use_module(bar, [baz/1, baz/2])` → `-import_from(bar, [baz, baz])` | DONE (2026-09-29, `fix/batch-f-import-arity`): the translator emits a repeated name once, the loader imports a repeated entry once, and one local name bound to two different predicates is a `SyntaxError` |
| F4 | exporter `_convert_module_directive`: export list not deduplicated (`[foo/1, foo/2, foo/1]`) | follow-up |
| F5 | exporter `_import_list` with no signatures: bare name → bare atom (not valid ISO) | pre-existing, follow-up |
| F6 | `BUILTIN_NAME_MAP` / `resolve_name` name-only | pre-existing, unrelated to this rule |
| F7 | `META_CALLER_SIGNATURES`, `_export_pairs` | already `(name, arity)` |

### G. Module lists

- `-module(m, [p/1, p/2])` works today (each entry is marked per
  `(f, a)`).
- `-import_from(m, [p])` imports EVERY arity the exporter has.
  `-import_from(m, [p/1])` imports one arity, as Scryer's
  `use_module(m, [p/1])` does (Q2, ruled D20).
- `-private([p/1, p/2])` works (bare entries).

## Operator questions (each has a default that is implemented)

- **Q1.** Should a FIELDED declaration (`-private([point(x, y)])`,
  `-module(m, [f(A)])`) coexist with clauses at another arity of the same
  name? ISO has no fields, so it is silent. **Default: no, it stays the
  old error** (D2). The ISO spelling `f/1` in the list gives the ISO
  behaviour. To lift it, the name-keyed registry (C1–C3) has to be
  re-keyed.
- **Q2.** Should `-import_from` accept `name/N` to import one arity?
  **RULED yes (D20, operator 2026-09-29), built on
  `fix/batch-f-import-arity-2026-09-29`.** `name/N` (and `name//N`) imports
  one arity, as Scryer's `use_module(m, [p/1])`; a bare name still imports
  every arity; lists mix; `alias(p/1, q)` works. An indicator the exporter
  lacks is a load-time `ImportError` (`existence_error(procedure, p/N)`,
  file, line, what the module has for `p`). An unimported arity is refused
  like a missing arity (`PredicateArityMismatchError`, ISO term
  `existence_error(procedure, p/N)`) plus a line naming the entry to add.
- **Q3.** `--p(k=v)` / `p(k=v)` keyword construction when `p` has several
  arities: which arity's fields? **Default:** the written arity (positional
  + keyword count), the same rule `_head_signature_for` already uses for
  heads; `AmbiguousArityConstructionError` when that does not decide it.
- **Q4.** Should an `-edcg_pred` name allow a plain predicate at another
  arity? **Default: no** (D2).

## Slices

1. **Runtime record per arity** (B1–B10). Exit test: a namespace whose
   body runs `$declare_head('p', ('x',))` then `$declare_head('p',
   ('x', 'y'))` builds heads at both arities; `loading_head_arities` is
   `{1, 2}`. Single-arity behaviour is unchanged (the existing suite).
2. **Rewriter opens a new arity** (A1–A9, C4). Exit test: the minimal repro
   loads, `p(X)` answers 1 and `p(X, 3)` answers 3; facts `f(1), f(1, 2),`
   in either order; `foo(a, b), foo,`; DCG `s//1` + `s//2`; D2 cases still
   raise; the emitted source of a single-arity file is byte-identical to
   base.
3. **Pinned tests and diagnostics** (E1, test flips). Exit: the pinned tests
   assert the new behaviour and the D2 errors keep their assertions.
4. **`.pl` trigger** (F1). Exit: a `.pl` module defining `call_goal/1..8`
   imports and answers.
5. **Docs** (`docs/predicates.md`, `docs/import.md`,
   `docs/importing_prolog.md`). Exit: nothing says "exactly one arity" for
   procedures.

## Implementation record (2026-09-29, same branch)

Built, because the census showed the change is contained. Slices 1–5 are
landed on the branch in one feature commit plus a docs commit.

- **No-change evidence.** The rewriter output (module code plus module
  items) was compared for every `.clausal` file in the tree against base
  `530814b4`, with `PYTHONHASHSEED=0` and the base tree in a scratch copy.
  453 files compile; 0 differ apart from `HeadFieldNames.by_arity`, which is
  new. The one hash difference (`edcg_counter`) is an `ast` object address
  in a repr, and it is identical once addresses are masked. As a positive
  control, the new test file run against the base engine gives 15 failed,
  5 passed.
- **A7 extra.** In the DCG path, a head at an arity other than a DECLARED
  one is now checked even when no field name repeats. A shorter
  `state//1` under a fielded `state/4` declaration used to slip past the
  check and die while building the head at load, with a construction error
  rather than the positioned SyntaxError. It was an error before and it is
  still one; only the message changed.
- **A8.** The messages now say "a functor declared with field names has
  one arity in a file", and a -module/-private template conflict adds the
  ISO way out (spell the entry `name/N`).
- **E1.** The runtime remedy reads "pass N arguments to f, or define f/M:
  a f clause head with M arguments is a procedure of its own, unrelated to
  f/N (as in ISO)". A test follows it literally and the result loads.
- **C4.** `cell_signature_for_name`'s handle arm answers a several-arity
  predicate name at the arity asked for, or its widest arity when none is
  asked. `construction_signature_for_name` re-asks a keyword construction
  at the written arity (Q3's default).
- **roborev round 1** gave 1 Medium and 3 Low findings; the Medium and 2 of the Lows are fixed. Medium: D2 depended on ORDER. A fielded
  `-private`/`-module`/`-edcg_pred` entry placed BELOW clauses that already gave the name
  two arities loaded silently. It is now refused (`_refuse_late_fielded_declaration`).
  This fires only when there are 2+ arities, so a late declaration after ONE arity
  behaves as before. Low: a clause head unseating a `-dynamic` placeholder
  no longer wipes an arity another head opened. Low: a `-constants`
  construction at an undeclared arity of a several-arity name is the
  compound at the written arity (ruling C), agreeing with the compile-time
  path. Low (tests) is covered by `TestReviewRound1`.

## Q1 ruled: declared fields are per (name, arity) (2026-09-29, later)

Operator ruling (direct): "-module(lib, [q(X), q(X, Y)]): allow it."
Branch `feat/fields-per-arity-2026-09-29`, base `32894d0c`.

- **Rewriter.** A -module/-private template entry at an arity the name does
  not have yet declares THAT arity with its own fields
  (`_declare_fielded_entry`: `_register_functor_arity` + its own
  `$declare_head`). A clause head of a fielded name must be at a declared
  arity: a template entry, or a field-free `name/N` entry / `-dynamic(name/N)`
  (`_procedure_decl_arities`). An undeclared arity stays the old error; its
  note now says "declare it in the same list, as `f(A, ARG_1)` ... or as
  `f/2`". The late-declaration check is per arity: a list below clauses at
  several arities must declare each of them (`_refuse_late_fielded`).
- **Exec-time registry (C3).** Still keyed by name. A name declared at
  several arities gets a DICT value `{arity: fields}`; a single-arity name
  keeps its tuple, so its emitted update is byte-identical, and the
  `-import_from` copy carries the dict unchanged. Read through
  `cells.registry_signatures` / `registry_fields`.
- **Database (C1).** `declared_fields_by_name` answers `None` for a name
  declared at several arities (it answered the last one);
  `declared_signatures_by_name` gives all of them.
- **C2.** `functor_signature_for(name, ns, arity=None)`: one declared arity
  answers it whatever is asked (unchanged); several answer the one at
  `arity`, else the widest (a construction re-asks at the written arity).
  `functor_signatures_for` gives the whole map.
- **Keyword construction (Q3).** Seam, compile-time lowering, head
  patterns and `-constants` choose with the runtime's own
  `_head_signature_for`: the written arity when declared, else the one the
  keywords fit, else `AmbiguousArityConstructionError`.
- **-edcg_pred (Q4)** stays one arity: `_edcg_preds` is name-keyed with a
  visible arity and the EDCG expander looks it up by name, so re-keying the
  field registry does not make it free.
- **`.pl` translator.** A name used as data at several arities is declared
  at each (`box(_), box(_, _)`); it used to be left undeclared.
- **No-change evidence.** The 453 rewritable `.clausal` files compared as
  before against base `32894d0c`: 0 differ in module code, 0 in module
  items. Positive control: `q(1), -private([q(A, B)])` differs (it now
  emits a `$declare_head` for `q/2`; that shape loaded before and still
  does).
