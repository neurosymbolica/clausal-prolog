# Standard Modules Plan — Scryer Prolog Alignment

## Motivation

Scryer Prolog ships ~51 standard library modules covering core logic programming
infrastructure: coroutining, formatted I/O, data formats, OS interaction, random
numbers, and more. Clausal already covers many of these via its builtins and
Python-native module system, but there are meaningful gaps — particularly in
coroutining primitives, resource management, and "batteries-included" utilities
that working programmers expect.

This plan maps Scryer's standard modules onto Clausal's existing capabilities,
identifies gaps worth filling, and organises the work into phases. Each phase
has (or will have) its own detailed implementation plan.

---

## Design Principles

1. **Python-native where possible.** Where Scryer provides a pure-Prolog data
   structure (assoc lists, ordered sets, queues), Clausal should prefer wrapping
   Python's native data structures (dict, frozenset, collections.deque) via
   DictTerm/SetTerm or `++()` interop. Better performance, more Pythonic.

2. **Don't re-implement what Python already does.** Scryer needs `crypto`,
   `sockets`, `http_server`, `ffi` because Prolog has no ecosystem. Clausal
   runs on Python — `++hashlib.sha256(...)`, `++requests.get(...)`, etc. are
   one line away. Modules in this space should be thin convenience wrappers
   at most, not full reimplementations.

3. **Preserve logical purity where it matters.** Coroutining (`freeze/2`,
   `when/2`), attributed variable APIs, reified conditionals — these are
   fundamental to logic programming and can't be faked with `++()`. They
   get first-class treatment.

4. **Clausal naming conventions apply.** TitleCase predicates, ALLCAPS or
   leading-underscore variables, expanded names (no abbreviations).

---

## Module-by-Module Mapping

### Already Covered (full or near-full overlap)

| Scryer Module | Clausal equivalent | Notes |
|---|---|---|
| **builtins** (core ISO) | `builtins/*` | unify, call/N, assert/retract, copy_term, findall, bagof, setof, once, catch/throw, write |
| **lists** | `builtins/lists.py` | member, append, reverse, length, select, permutation, sort, flatten, plus extras (take, drop, zip, replicate) |
| **clpz** (CLP integers) | `clpfd.py` | Same concept. Missing some global constraints — see Phase 5. |
| **clpb** | `clpb.py` | sat/1, taut/2, sat_count/2, labeling/1 |
| **dif** | `constraints.py` | dif/2 |
| **dcgs** | `builtins/dcg.py` + term_rewriting | `>>` syntax, phrase/2,3. Missing `seq//1`, `seqq//1` — see Phase 5. |
| **tabling** | `tabling.py` | SLG tabling. Missing `abolish_all_tables/0` — see Phase 5. |
| **pairs** | `builtins/pairs.py` | pairs_keys_values, pairs_keys, pairs_values. Missing `group_pairs_by_key` — Phase 5. |
| **between** | `builtins/arithmetic.py` | between/3, succ/2. Missing `numlist`, `gen_int`, `gen_nat` — Phase 5. |
| **terms** | `builtins/inspection.py` | numbervars/3, copy_term/2, term_variables/2, functor/3, arg/3, unpack/2 |
| **reif** | V2-8 (reified ITE) | Reified if-then-else done. Missing dedicated `If_/3`, `tfilter/3` — Phase 5. |
| **lambda** | V2-9 (goal closures) | Clausal uses Pythonic lambdas — `\` notation not needed. |
| **error** | `exceptions.py` | throw/catch done. Missing `must_be/2`, `can_be/2` — Phase 5. |
| **time** | `builtins/control.py` | time_goal done. Missing `Sleep/1`, `current_time/1` — Phase 5. |
| **arithmetic** (extended) | `builtins/arithmetic.py` | sign, gcd, divmod_, abs_, max_, min_, plus. Missing `lcm`, `exp_mod`, `popcount` — Phase 5. |
| **assoc** (AVL dicts) | `builtins/dict_set.py` | DictTerm (Python dict-backed) covers the practical use case. AVL trees not needed. |
| **ordsets** | `builtins/dict_set.py` | SetTerm (Python frozenset-backed). Ordered-set operations not needed separately. |
| **simplex** (LP) | `scipy_optimize` | `LinearProgram`/`MixedIntegerLinearProgram` are strictly superior. |
| **special_functions** | `scipy_special` | 48 predicates, far exceeds Scryer's coverage. |
| **uuid** | `modules/uuid_mod.py` | Already done. |

### Not Applicable / Skip

| Scryer Module | Why |
|---|---|
| **ffi** (C FFI) | `++()` Python interop is Clausal's FFI. No C boundary needed. |
| **wasm** | Scryer-specific (Rust/WASM compilation target). |
| **lambda** (`\` notation) | Clausal's Pythonic lambdas + goal closures are the idiom. |
| **ops_and_meta_predicates** | Clausal handles operator setup via Python AST, not directives. |
| **debug/diag** (WAM inspection) | Clausal doesn't use WAM. `tools/visualize.py` serves the debugging role. |
| **simplex** | scipy_optimize covers this better. |
| **cont** (reset/shift) | Delimited continuations — powerful but niche. Revisit if demand arises. |

---

## Phased Plan

### Phase 1 — Coroutining & Resource Control ✓

**Status: COMPLETE** (commit `659c532`)

| Item | Description |
|---|---|
| `freeze/2` | Delay goal until variable is bound. AttVar-based. |
| `when/2` | Generalized coroutining with compound conditions. |
| `setup_call_cleanup/3` | Resource cleanup guarantee (try/finally for logic). |
| `call_cleanup/2` | Sugar: `setup_call_cleanup(true, Call, Cleanup)`. |
| `call_nth/2` | Succeed on Nth solution only. |
| `count_all/2` | Count solutions without collecting. |

All implemented as compiler special forms. 71 tests. Docs at `docs/coroutining.md`.

**Detailed plan:** [`STD_MODULES_PHASE1.md`](STD_MODULES_PHASE1.md)

---

### Phase 2 — Character/String Utilities & Clause Inspection ✓

**Status: COMPLETE** — Logic-aware string predicates + runtime introspection.

Format/2,3 intentionally omitted — Python f-strings and `str.format()` cover
formatted output. These predicates exist because they participate in
unification and backtracking (e.g., `atom_concat(A, B, "hello")` enumerates
splits, `char_type(C, digit)` enumerates digits) — things Python string
methods can't do.

| Item | Description |
|---|---|
| `char_type/2` | Character classification: alpha, digit, space, etc. Multi-modal. |
| `char_code/2` | Bidirectional char ↔ code point. |
| `upcase_atom/2`, `downcase_atom/2` | Case conversion. |
| `atom_length/2` | String length. |
| `atom_chars/2`, `atom_codes/2` | Bidirectional atom ↔ char/code list conversion. |
| `atom_concat/3` | String concatenation as a relation (reverse enumerates splits). |
| `sub_atom/5` | Substring extraction — 5-arg multi-modal relation. |
| `listing/1` | List all clauses for a predicate from `pred_cls._clauses`. |
| `portray_clause/1` | Pretty-print a term with indentation via `term_pformat`. |

All implemented as `@_builtin` predicates in `chars.py` and `io.py`. 73 tests
across `tests/test_chars.py` and `tests/test_listing.py`.

**Detailed plan:** [`STD_MODULES_PHASE2.md`](STD_MODULES_PHASE2.md)

---

### Phase 3 — Random & Data Formats ✓

**Status: COMPLETE** — Batteries-included utilities.

| Item | Description |
|---|---|
| `py.random` module | `Maybe/0,1`, `Random/1`, `RandomFloat/3`, `RandomInteger/3`, `RandomMember/2`, `RandomPermutation/2`, `RandomSample/3`, `RandomSeed/1`. Wrap Python `random`. |
| `py.json` module | `Parse/2`, `Generate/2`, `PrettyGenerate/2`, `Get/3`, `ReadFile/2`, `WriteFile/2`. JSON objects ↔ DictTerm. Unprefixed — module namespace provides context. |
| `py.csv` module | `Parse/2`, `ParseRow/2`, `ParseRecords/3`, `Generate/2`, `GenerateRecords/3`, `ReadFile/2`, `ReadRecords/2`, `WriteFile/2`. Unprefixed — module namespace provides context. |

**Detailed plan:** [`STD_MODULES_PHASE3.md`](STD_MODULES_PHASE3.md)

---

### Phase 4 — OS & File System ✓

**Status: COMPLETE** — System interaction for scripting use cases.

| Item | Description |
|---|---|
| `py.os` module | `EnvironmentVariable/2`, `SetEnvironmentVariable/2`, `UnsetEnvironmentVariable/1`, `WorkingDirectory/1`, `ChangeDirectory/1`, `Pid/1`, `Argv/1`, `Platform/1`, `CPUCount/1`. |
| `py.files` module | `FileExists/1`, `DirectoryExists/1`, `PathExists/1`, `DirectoryFiles/2`, `DirectoryEntries/2`, `FileSize/2`, `FileModificationTime/2`, `DeleteFile/1`, `DeleteDirectory/1`, `RenameFile/2`, `CopyFile/2`, `MakeDirectory/1`, `MakeDirectoryPath/1`, `ReadFileToString/2`, `WriteStringToFile/2`, `AppendStringToFile/2`, `AbsolutePath/2`, `JoinPath/3`, `SplitPath/3`, `FileExtension/2`, `TempFile/1`, `TempDirectory/1`. |
| `py.process` module | `Shell/1,2`, `ShellOutput/2,3`, `ProcessCreate/3,4`, `Sleep/1`. |

**Detailed plan:** [`STD_MODULES_PHASE4.md`](STD_MODULES_PHASE4.md)

---

### Phase 5 — extend Existing Builtins (Gap-Filling) ✓

**Status: COMPLETE** — Small additions to modules that are already mostly complete.

| Area | Additions |
|---|---|
| CLP(FD) | `sum_/3`, `scalar_product/4`, `element/3`, `circuit/1` (global constraints). |
| Lists | `numlist/2,3`, `same_length/2`, `transpose/2`. |
| DCGs | `Seq//1`, `Seqq//1` (sequence matching helpers). |
| Tabling | `AbolishAllTables/0`, `AbolishTable/1`. |
| Arithmetic | `lcm/3`, `exp_mod/4`, `popcount/2`, `msb/2`, `lsb/2`. |
| Pairs | `group_pairs_by_key/2`. |
| Error | `must_be/2`, `can_be/2` (type-checking with ISO error terms). |
| Reif | `If_/3`, `tfilter/3`, `tpartition/4` as explicit builtins. |
| Time | `current_time/1`, `statistics/2`. (`Sleep/1` already in `py.process`, Phase 4.) |

**Detailed plan:** [`STD_MODULES_PHASE5.md`](STD_MODULES_PHASE5.md)

---

### Phase 6 — User-Facing Attributed Variables ✓

**Status: COMPLETE** — Enable users to build custom constraint solvers in `.clausal`.

| Item | Description |
|---|---|
| `PutAtts/2` | Attach attributes to a variable. |
| `GetAtts/2` | Retrieve attributes from a variable. |
| `term_attvars/2` | Collect all attributed variables in a term. |

The internal infrastructure already exists (CLP(FD), CLP(B), dif all use it).
This phase exposes it as a public API.

**Detailed plan:** [`STD_MODULES_PHASE6.md`](STD_MODULES_PHASE6.md)

---

### Phase 7 — Optional / Low Priority ✅ DONE

| Item | Status | Description |
|---|---|---|
| `gensym/2` builtin | ✅ | Unique atom generation. Thread-safe monotonic counter. |
| `number_chars/2`, `number_codes/2` builtins | ✅ | Bidirectional number ↔ char-list / code-point-list. |
| `py.hash` module | ✅ | `Hash/3`, `HashBytes/3`. Wraps `hashlib`. |
| `py.hmac` module | ✅ | `sign/3,4`, `Verify/3,4`. Wraps `hmac`. Constant-time verify. |
| `py.pbkdf2` module | ✅ | `Derive/4,5`. Wraps `hashlib.pbkdf2_hmac`. |
| `py.http` module | ✅ | `Get/2,3`, `Post/3,4`, `Request/3`, `JSONGet/2`, `JSONPost/3`. Wraps `urllib`. |
| `py.url` module | ✅ | `Encode/2`, `Decode/2`, `Parse/2`, `Join/2`. Wraps `urllib.parse`. |
| `py.tcp` module | ✅ | `Connect/3`, `Listen/3`, `Accept/2`, `Send/2`, `Receive/2,3`, `Close/1`, `SetTimeout/2`. Wraps `socket`. |

**Detailed plan:** [`STD_MODULES_PHASE7.md`](STD_MODULES_PHASE7.md)
