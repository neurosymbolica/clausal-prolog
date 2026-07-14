# Dict-native profile API — `P[k]` / `get` / `in` / `{**P, k:V}` / `delete`

**Status:** design pinned (brainstormed 2026-07-14 w/ Michael); umbrella for the Clausal-interpreter
capability work. The corpus migration that consumes this is a *separate, dependent* effort in the
`clausify` / `clausify-domains` repos (do NOT start that until the pieces below are green).

## Why

Clausal legal domains model an eligibility "profile" (a.k.a. case / scenario / features) as a bag of
key→value facts. Today there are **three incompatible dialects** across 54 domains:
- generated `profile_find_<key>/2` accessor families (31 rulebases) — codegen boilerplate, ~100 lines/domain;
- direct `profile_get(P, atom_key, V)` list-scan reads (5 rulebases);
- legacy string-key `profile_get(P, "key", V)` holdouts (7 rulebases).

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
| delete (functional) | `delete(P, filing_status, P2)` | `del d[k]` (functional) | `del` is a Python keyword → predicate is `delete/3` |

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
1. **Subscript read runtime** over `DictTerm` under `is/2`, throw-on-missing — untested. → `dict-subscript-read-throw-on-missing.md`
2. **`in`-over-dict** = key membership (today `in_/2` is list-element) — → `dict-key-membership-in-operator.md`
3. **`get/3` + `get/4`** builtins — → `dict-get-builtins-fail-and-default.md`
4. **`{**P, k:V}` splat/merge** — code comment says "full splat/merge support is Phase 3" (term_rewriting.py:728); unimplemented at runtime. → `dict-splat-merge-functional-set.md`
5. **`delete/3`** functional key removal — → `dict-delete-builtin.md`
6. **SMT prover dict-read projection** (CLAUSIFY repo, `auto/formal`) — separate todo filed there, not here.

## Sequencing / acceptance
Land 1–4 (read surface + set) first; 5 (`delete`) is YAGNI-gated (no current consumer — implement when the
corpus migration needs it, but it is small and self-contained). The capability is "done" when a **single
pilot domain** rewritten to the dict-native surface passes its full gate end-to-end (oracle refutations=0 +
G3 baseline-identical) — that pilot is the hand-off signal to start the corpus-migration spec (Spec B).

Every piece ships with Clausal unit tests in `clausal/tests/` (there are currently **zero** tests exercising
`DictTerm` reads — establish that coverage as part of this work).
