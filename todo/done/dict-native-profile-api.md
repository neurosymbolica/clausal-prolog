# Dict-native profile API — `P[k]` / `get` / `in` / `{**P, k:V}` / `delete`

**Status:** design pinned (brainstormed 2026-07-14 w/ Michael); umbrella for the Clausal-interpreter
capability work. The corpus migration that consumes this is a *separate, dependent* effort in a
downstream rulebase corpus (do NOT start that until the pieces below are green).

## Why

Clausal callers commonly model an eligibility "profile" (a.k.a. case / scenario / features) as a bag
of key→value facts. In the wild there are **three incompatible dialects**:
- generated `profile_find_<key>/2` accessor families — codegen boilerplate, ~100 lines per caller;
- direct `profile_get(P, atom_key, V)` list-scan reads;
- legacy string-key `profile_get(P, "key", V)` holdouts.

The representation underneath every one of them is `attribute(KEY, VALUE)` — a pair compound in a **flat
list, looked up by O(n) recursive scan**. We are unifying on ONE representation + ONE surface, chosen for
**LLM-training uniformity** and **Python familiarity** (a standing Clausal goal): the profile simply **is a
native `DictTerm`**, read/written with Python's own dict surface. Bonus: dicts map 1:1 onto **JSON objects**,
so this is also the natural shape for JSON-API ingestion, LLM tool-use results, and serialization.

The SMT prover is *representation-neutral*: it projects a profile onto `has_k`/`val_k` Z3 consts from the
declared `profile_keys.yaml` schema and abstracts the read away — so switching list→dict does not weaken
provability, as long as reads use recognized forms with **ground, declared keys** (see the prover todo).

## The pinned surface (Python dict API, 1:1)

| Operation | Clausal form | Python analogue | Semantics |
|---|---|---|---|
| read (strict) | `V is P[filing_status]` | `d[k]` | **throws** if key absent (KeyError-analogue) |
| read (soft) | `get(P, filing_status, V)` | `d.get(k)` | **fails** the clause if absent (None→fail is the logic analogue) |
| read (defaulted) | `get(P, filing_status, V, Default)` | `d.get(k, default)` | binds `Default` if absent |
| membership | `filing_status in P` | `k in d` | key presence |
| set (functional) | `P2 is {**P, filing_status: V}` | `{**d, k: v}` | always succeeds; **last-wins** merge |
| default-merge | `P2 is {filing_status: Default, **P}` | `{k: default, **d}` | P wins if present (this is the *default* order) |
| delete (functional) | `delete(P, filing_status, P2)` | `del d[k]` | **throws** if absent; `del` keyword → `delete/3` |

Reserved sibling names (claim now, implement on demand — see `done/dict-delete-builtin.md`): `discard/3`
(no-throw removal, Python `set.discard`), `pop/4` (remove+retrieve, throws), `pop/5` (remove+retrieve,
defaulted). Relational `pop` outputs the residual dict, so it is `/4` + `/5`, not Python's `/1` + `/2`.

### Binding operator: `is/2`
`is/2` is Clausal's `=/2`-analogue and already binds computed/constructed RHSs (`W is [applicant_age(16), …]`).
It evaluates the RHS — so `V is P[k]` evaluates the subscript and `P2 is {**P, k: V}` evaluates the merge.
- **NOT `=`** — that is assignment in Clausal's Python surface syntax.
- **NOT `==`** — reserve for CLP.
- **NOT `:=`** — reads as a backdoor.

### Naming: overloaded `get`, not `get_or_default`
`get/3` (soft, fails) + `get/4` (defaulted). This mirrors Python's `dict.get` exactly (one verb, arity
distinguishes the default), so the read family `P[k]` / `get/3` / `get/4` / `in` *is* Python's dict-read
surface. `get_or_default` is the Java idiom and was rejected: two verbs, off-brand for the Python goal.

## What already exists vs. what's missing (probed 2026-07-14)

Present: `DictTerm` (terms.py:1635 — ground keys, value-unification, `__contains__`, `__getitem__`, hashed);
parser support for `{k:v}` (`visit_Dict`), `P[k]` (`visit_Subscript` → `LoadSubscript`, term_rewriting.py:1064),
and a `**`-splat node.

Missing / immature (the work below):
1. ~~**Subscript read runtime** over `DictTerm` under `is/2`, throw-on-missing~~ — **DONE 2026-07-14**
   (`$subscript` runtime helper + `LoadSubscript` case in `term_to_ast_expr`; str/int/atom keys, throw
   on missing/non-ground; tests in `tests/test_dict_set_compiler.py`). → `dict-subscript-read-throw-on-missing.md`.
   **Blocker surfaced:** bare-atom dict-key *literals* (`{filing_status: V}`) don't load — the ergonomic
   atom-key surface needs `dict-atom-key-literal-parser-gap.md` (pre-existing; affects items 2–5 too).
2. ~~**`in`-over-dict** = key membership~~ — **DONE 2026-07-14** (already worked: the `in` operator
   compiles inline to `$in_iter`, and `DictTerm.__iter__`/`__contains__` are key-based; `(K,V) in D`
   pair-mode too). Locked with tests. → `dict-key-membership-in-operator.md`.
3. ~~**`get/3` + `get/4`** builtins~~ — **DONE 2026-07-14** (`get(Dict,Key,Value)` soft-fail +
   `get(Dict,Key,Value,Default)` in `clausal/logic/builtins/dict_set.py`). → `dict-get-builtins-fail-and-default.md`.
4. ~~**`{**P, k:V}` splat/merge**~~ — **DONE 2026-07-14** (already worked at runtime; the "Phase 3"
   comment was stale — `term_to_ast_expr`'s `DictLiteral` case folds splats last-wins). Locked with tests,
   incl. multi-splat + value-var. → `dict-splat-merge-functional-set.md`.
5. ~~**`delete/3`** functional key removal~~ — **DONE 2026-07-14** (`delete(Dict,Key,NewDict)`, throw on
   absent/non-ground/non-dict, immutable). Reserved siblings `discard/3`, `pop/4`, `pop/5` still
   YAGNI-parked. → `done/dict-delete-builtin.md`.
6. **SMT prover dict-read projection** — separate todo filed in the SMT prover's own repo, not here.

## Sequencing / acceptance — ✅ ALL DONE (2026-07-14)
Interpreter items 1–5 landed; the ergonomic bare-atom surface works
(`{filing_status: V}` / `P[filing_status]` / `get(P, filing_status, V)` / `filing_status in P`; atom keys
distinct from string keys — `dict-atom-key-literal-parser-gap.md` DONE). Item 6 (SMT prover projection)
landed downstream. The downstream rulebase corpus migration that consumes this is reported complete
and green (every domain decision-preserving; all SMT domains re-proved G3 PROVED ≥ baseline). DictTerm
read/op coverage lives in `tests/test_dict_set_compiler.py` + `tests/fixtures/dict_set_patterns.clausal`.

## Core promotion — STATUS + remaining (2026-07-14)
The design planned "kit module now, promote to Clausal core later." The implementation **skipped the kit
step and put the dict ops directly in the interpreter as global core builtins**, so the "promotion" is
effectively already realized at the runtime level:
- `get/3`, `get/4`, `delete/3` — registered builtins in `clausal/logic/builtins/dict_set.py`
  (`@_trampoline_builtin("get", 3)` etc.), auto-loaded via `clausal/logic/builtins/__init__.py`.
- `P[key]` subscript, `key in P` membership, `{**P, k:V}` splat/merge — lowered in the compiler
  (`term_to_ast_expr` / `$subscript` / `$in_iter` / `$splat_data` runtime helpers).
- **No import required** — the downstream corpus uses `get`/`in`/`P[k]` with zero `-import_from`, proving
  they are always-available core.

**Remaining to call the promotion formally "done" (finalization, not runtime work):**
1. **Language-reference docs** — add the dict-profile ops to the canonical Clausal builtins reference
   (a downstream cheat-sheet + scaffolding doc sweep is in progress on the consumer side). Ensure
   `get`/`in`/subscript/`{**}`/`delete` are documented as first-class core, alongside list/set ops.
2. **Reserved-name siblings** (from `done/dict-delete-builtin.md`, still YAGNI) — implement `discard/3` (no-throw
   remove), `pop/4`/`pop/5` (remove+retrieve) if/when a consumer appears; no known consumer currently needs one.
3. **Builtins registry / spec entry** — confirm the dict ops appear in whatever canonical builtin catalog
   or language spec Clausal maintains (they are registered for execution; make sure they're *catalogued*
   for discoverability + tooling, same as `in_/2`, `append/3`, etc.).
4. **`length/2` on DictTerm** — a domain (diversity) hit `length/2` returning None on a `DictTerm` and used
   `dict_size/2` instead. Decide whether `length/2` should also count dict keys, or standardize on
   `dict_size/2` and document it.

---

## CLOSED 2026-09-02 — promotion finalization complete

The runtime shipped 2026-07-14 and the corpus migration is reported complete
(above). The four finalization items:

1. **Language-reference docs — DONE.** `docs/dicts_sets.md` gains "The
   Python dict surface": the full pinned table (`P[k]` / `get/3` / `get/4` /
   `tri_get/3` / `in` / `{**P, k: v}` / `delete/3`), read-choice guidance,
   atom-vs-string key distinctness, and the plain-dict acceptance rule.
2. **Reserved siblings (`discard/3`, `pop/4`, `pop/5`) — still YAGNI**, by
   design ("implement on demand"); no consumer has appeared. The names stay
   reserved in this file's table and in done/dict-delete-builtin.md.
3. **Builtins catalog — DONE.** `docs/builtins.md`: the family is in the
   section summary table and has a catalog entry pointing at the full doc;
   the stale "plain Python dict and set are not accepted" sentence is
   corrected (falsified by the 2026-09-02 widening,
   todo/done/dictterm-only-builtins-sweep.md).
4. **`length/2` on DictTerm — decided + documented:** standardize on
   `dict_size/2`; a dict is not a sequence, `length/2` does not count keys.
   Stated in the new docs section.
