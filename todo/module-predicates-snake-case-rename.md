# Standard-library module predicates → snake_case

**Requested:** 2026-07-04. **Why:** continuation of the `date_time` snake_case migration
(`todo/done/date-api-snake-case-rename.md`, closed 2026-07-04). Same rationale: the local student
models (Qwen3.6-27B dense, the 7B before it) generate snake_case far more reliably than
TitleCase/PascalCase — it's what Python's stdlib and SWI-Prolog use and what the models were
pre-trained on. Snake_case is an **un-enforced convention** (Python consistency wins over Prolog
when they conflict), but the stdlib wrappers are the highest-volume generated surface after dates,
so the payoff is high. Making the convention self-consistent is the main driver.

## Scope: this is NOT a codebase-wide rename

The built-in surface is in two states — only the second needs work:

| Population | Location | Count | State |
|---|---|---:|---|
| Core engine built-ins | `clausal/logic/builtins/*.py` (`@_builtin`) | 314 | ✅ already lowercase/snake_case |
| `date_time` module | `clausal/modules/py/datetime.py` | 16 | ✅ migrated (the precedent) |
| **Python-stdlib modules** | `clausal/modules/py/*.py` + `clausal/modules/*.py` | **~146** | ❌ still TitleCase — **the work** |

**Core engine: no work.** The only non-plain `@_builtin` names are 7 trailing-underscore spellings
for keyword/clash avoidance (`abs_`, `divmod_`, `float_`, `max_`, `min_`, `sum_`,
`ortools.cpsat.in_`). These are legitimately snake_case — leave them.

Every module predicate is called **module-qualified** (`files.FileExists`, `graphs.ShortestPath`),
so each rename is module-scoped and low-blast-radius — the property that made datetime tractable.

## What to rename (~146 predicates across 19 files)

Names registered via `ModulePredicate("<Name>")` / `_GraphPredicate` / `_UnitsPredicate`. Rename is
flag-day (no deprecated aliases, matching the datetime precedent).

| Module | # | Examples |
|---|---:|---|
| `py/files.py` | 22 | `FileExists`→`file_exists`, `MakeDirectoryPath`→`make_directory_path` |
| `graphs.py` | 18 | `ShortestPath`→`shortest_path`, `MinSpanningTree`→`min_spanning_tree` |
| `py/logging.py` | 16 | `GetLogger`→`get_logger`, `BasicConfig`→`basic_config` |
| `py/uuid.py` | 12 | `UUIDv4`→`uuid_v4`, `UUIDStr`→`uuid_str`, `IsUUID`→`is_uuid` |
| `py/os.py` | 9 | `EnvironmentVariable`→`environment_variable`, `CPUCount`→`cpu_count` |
| `py/csv.py` | 8 | `ParseRecords`→`parse_records`, `GenerateRecords`→`generate_records` |
| `py/random.py` | 8 | `RandomInteger`→`random_integer`, `Maybe`→`maybe` |
| `py/sqlite.py` | 8 | `SQLiteConnect`→`sqlite_connect` (or `connect` — see policy) |
| `reflection.py` | 7 | `ClauseHead`→`clause_head`, `GoalFunctor`→`goal_functor` |
| `py/tcp.py` | 7 | `Connect`/`Listen`/`Accept`/`Close`→lowercase |
| `py/json.py` | 6 | `Parse`→`parse`, `PrettyGenerate`→`pretty_generate` |
| `py/http.py` | 5 | `Get`/`Post`, `JSONGet`→`json_get` |
| `py/url.py` | 4 | `Encode`/`Decode`/`Parse`/`Join` |
| `py/re.py` | 4 | `Match`/`Search`/`Replace`/`Split` — see snag 2 |
| `py/process.py` | 4 | `ProcessCreate`→`process_create`, `Shell`→`shell` |
| `units.py` | 3 | `DimensionOf`→`dimension_of`, `MakeQuantity`→`make_quantity` |
| `py/hash.py` | 2 | `Hash`/`HashBytes`→`hash`/`hash_bytes` |
| `py/hmac.py` | 2 | `Verify`→`verify` (see snag 1) |
| `py/pbkdf2.py` | 1 | `Derive`→`derive` |

## Snags — decide before starting

1. **Already-mixed modules** prove the drift is happening piecemeal: `re.py` has lowercase `findall`
   next to `Match/Search/Replace/Split`; `hmac.py` has lowercase `sign` next to `Verify`. A
   systematic pass stops the bleed.
2. **`re.Match`/`re.Search` are special.** Wired into goal-expansion auto-binding
   (`clausal/logic/goal_expansion.py:247`, `clausal/pythonic_terms.py:104`) and advertised in the
   README (`Match/2,3`, `Search/2,3`). Rename needs those call-sites + docs in lockstep, not just the
   registration string.
3. **Acronym / redundant-prefix policy** (one rule up front, then mechanical): `UUIDv4`→`uuid_v4`?,
   `JSONGet`→`json_get`, `CPUCount`→`cpu_count`; and whether the module prefix is redundant under
   qualified call — `sqlite.sqlite_connect` vs `sqlite.connect`, `uuid.uuid_v4` vs `uuid.v4`.

## Docs to fix in the same series (stale / self-contradictory)

- [ ] `docs/for_prolog_programmers.md:156` — naming table says "lowercase for user predicates" but
      "**PascalCase** builtins" in the same table. Rewrite for the snake_case convention.
- [ ] `docs/syntax.md:63` — still claims titlecase is used for predicates.
- [ ] `README.md` — quick-start says "Predicate names are CamelCase"; `Match`/`Call`/`Phrase`
      examples.

## Rollout (mirror the datetime precedent)

1. Decide the acronym/redundant-prefix policy (snag 3).
2. ~~Batch the **trivial modules** (tcp, url, json, http, hash, pbkdf2, process, units, reflection)~~
   ✅ **DONE 2026-07-04** — see "Trivial batch — done" below.
3. ~~Handle **`re`** carefully (goal-expansion + README)~~ ✅ **DONE 2026-07-04** — see "re — done" below.
4. Do the **big three** (files, graphs, logging) once the pattern is proven.
5. Fix the **docs** (above) in the same series.
6. Hand off the **external sweep** as a tracked follow-up (see below).

## Trivial batch — done 2026-07-04

Renamed 9 modules (units, tcp, process, reflection, hash, hmac, pbkdf2, http, json, url) —
39 predicates. Full suite: **8278 passed** (only the pre-existing perf-timing flake
`test_F026_multi_star_splits_bounded` remains, fails identically on clean baseline). Tool:
`scripts/snake_rename.sh <files...> -- Old=new …` (word-boundary sed over an **explicit, scoped**
file set — never repo-wide).

**Two gotchas that WILL recur in the remaining batches (files/os/csv/uuid/sqlite/graphs/random/
logging/re — all stdlib wrappers):**

1. **Stdlib-attribute collision.** A predicate name that matches a Python stdlib attribute gets
   corrupted by the sed. `Request`→`request` broke `urllib.request.Request` in `http.py:49`. Before
   renaming a module, grep its source for `\.<OldName>\b` / stdlib class refs (`.Request`, `.Parse`,
   `.Match`, `.Get`, capitalised stdlib classes) and hand-fix any that are Python API, not the
   predicate. `dict.get()` / `.encode()` are lowercase already so untouched — it's the *capitalised*
   stdlib names to watch.
2. **Cross-module doc/import references.** Generic names leak across pages: `docs/csv.md` and
   `docs/process.md` `-import_from(py.json, [Parse, Get])`, so renaming `json.Get` broke *their*
   snippets (caught by `test_doc_snippet_coverage.py`). After each rename, scan the **whole live
   tree** for `import_from(py.<mod>` and qualified `py.<mod>.<OldName>`, not just the module's own
   files. Exclude historical dirs (`implementation_plans/`, `docs/superpowers/`, `todo/`) and
   `build/`/`dist/`.

**Known cosmetic debt:** a few doc table *description* cells now start lowercase ("connect to TCP
server", "accept incoming connection") because the verb doubled as the predicate name. Reads fine;
not hand-fixed. Worth a capitalisation polish pass across `docs/*.md` at the end of the whole
migration.

**Verify green:** `PYTHONPATH=/workspace/clausal-bug-fix /home/node/.pyenv/versions/3.13.3/bin/python
-m pytest tests/ -q -p no:cacheprovider` (baseline: 8278 passed + the one perf flake).

## re — done 2026-07-04

`Match`→`match`, `Search`→`search`, `Replace`→`replace`, `Split`→`split` (findall was already
lowercase). Chose bare snake_case — under qualified call it reads `re.match`/`re.search`/`re.split`,
matching Python's own `re.*` function names exactly. Verified no core-builtin/module already claims
those lowercase names (no collision).

**This one could NOT be blanket-renamed — done surgically:**
- **Functional wiring:** `goal_expansion.py:247` `if short_name not in ("Match","Search")` gates the
  regex auto-binding (Match/2→Match/3 rewrite). Updated to `("match","search")`. Miss this and
  auto-binding silently stops firing (tests catch it, but it's the load-bearing line).
- **Protected `_re.Match`** — the Python stdlib match-object *type annotation* in `re.py:46`. The sed
  hit it; restored by hand. (Same family as the `urllib.request.Request` gotcha.)
- **`Match`/`Search`/`Split`/`Replace` are heavily overloaded** and MOST occurrences are NOT the
  regex predicate: `Split/3` is a user-defined list-split in several fixtures
  (`Split([*A,*B],A,B)`), `continuation_search.Search` is an engine function, `_ast.Match` /
  `pythonic_terms.py:104 "Match"` are Python AST match-statement nodes. Discriminator that works:
  only rename where the name is reachable via `import_from(regex|py.re, [...])` or qualified
  `re.Name`/`py.re.Name`, or is a regex-pattern call `Name(r"...")`. Grepping bare `Name(` is too
  broad.
- **Two aliases:** the module is importable as both `py.re` and the bare alias `regex`
  (`ModulesFinder` redirect) — cover both spellings.
- **Prose collisions in mixed docs** (`compiler.md` "Search exhausted" = trampoline, not regex;
  `term_expansion.md` "Replace the goal" = English verb) — edited those pages by hand, not by sed.

## Done when
- [ ] `grep -rhoE '(ModulePredicate|_[A-Za-z]+Predicate)\(\s*"[A-Z]' clausal/modules/` is empty.
- [ ] Module test suites green (`tests/` for files/graphs/logging/uuid/os/csv/random/sqlite/tcp/
      json/http/url/re/process/units/hash/hmac/pbkdf2/reflection).
- [ ] Docs above updated; no `CamelCase`/`PascalCase` predicate guidance remains.

## Related / follow-ups (separate repos & todos)
- **External rulebase sweep** — `clausify-domains` rulebases + `kit/scaffolding/*` reference these
  names and live in another repo. Flag-day rename here means that sweep must be coordinated (same as
  datetime).
- Sibling `formalize_lib` rename (`prof_get`→`profile_get`, `attr`→`attribute`, …) — same rationale.
- `todo/date-max-min-ordinal-apis.md` — remaining clean date APIs, all snake_case.
