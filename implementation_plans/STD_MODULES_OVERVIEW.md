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
   trailing-underscore variables, expanded names (no abbreviations).

---

## Module-by-Module Mapping

### Already Covered (full or near-full overlap)

| Scryer Module | Clausal Equivalent | Notes |
|---|---|---|
| **builtins** (core ISO) | `builtins/*` | unify, call/N, assert/retract, copy_term, findall, bagof, setof, once, catch/throw, write |
| **lists** | `builtins/lists.py` | member, append, reverse, length, select, permutation, sort, flatten, plus extras (take, drop, zip, replicate) |
| **clpz** (CLP integers) | `clpfd.py` | Same concept. Missing some global constraints — see Phase 5. |
| **clpb** | `clpb.py` | sat/1, taut/2, sat_count/2, labeling/1 |
| **dif** | `constraints.py` | dif/2 |
| **dcgs** | `builtins/dcg.py` + term_rewriting | `>>` syntax, phrase/2,3. Missing `seq//1`, `seqq//1` — see Phase 5. |
| **tabling** | `tabling.py` | SLG tabling. Missing `abolish_all_tables/0` — see Phase 5. |
| **pairs** | `builtins/pairs.py` | Unzip, PairKeys, PairValues. Missing `GroupPairsByKey` — Phase 5. |
| **between** | `builtins/arithmetic.py` | Between/3, Succ/2. Missing `numlist`, `gen_int`, `gen_nat` — Phase 5. |
| **terms** | `builtins/inspection.py` | NumberVars/3, CopyTerm/2, TermVariables/2, Functor/3, Arg/3, Unpack/2 |
| **reif** | V2-8 (reified ITE) | Reified if-then-else done. Missing dedicated `If_/3`, `TFilter/3` — Phase 5. |
| **lambda** | V2-9 (goal closures) | Clausal uses Pythonic lambdas — `\` notation not needed. |
| **error** | `exceptions.py` | throw/catch done. Missing `MustBe/2`, `CanBe/2` — Phase 5. |
| **time** | `builtins/control.py` | TimeGoal done. Missing `Sleep/1`, `CurrentTime/1` — Phase 5. |
| **arithmetic** (extended) | `builtins/arithmetic.py` | Sign, Gcd, DivMod, Abs, Max, Min, Plus. Missing `Lcm`, `ExpMod`, `Popcount` — Phase 5. |
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
| `Freeze/2` | Delay goal until variable is bound. AttVar-based. |
| `When/2` | Generalized coroutining with compound conditions. |
| `SetupCallCleanup/3` | Resource cleanup guarantee (try/finally for logic). |
| `CallCleanup/2` | Sugar: `SetupCallCleanup(true, Call, Cleanup)`. |
| `CallNth/2` | Succeed on Nth solution only. |
| `CountAll/2` | Count solutions without collecting. |

All implemented as compiler special forms. 71 tests. Docs at `docs/coroutining.md`.

**Detailed plan:** [`STD_MODULES_PHASE1.md`](STD_MODULES_PHASE1.md)

---

### Phase 2 — Character/String Utilities & Clause Inspection ✓

**Status: COMPLETE** — Logic-aware string predicates + runtime introspection.

Format/2,3 intentionally omitted — Python f-strings and `str.format()` cover
formatted output. These predicates exist because they participate in
unification and backtracking (e.g., `AtomConcat(A, B, "hello")` enumerates
splits, `CharType(C, digit)` enumerates digits) — things Python string
methods can't do.

| Item | Description |
|---|---|
| `CharType/2` | Character classification: alpha, digit, space, etc. Multi-modal. |
| `CharCode/2` | Bidirectional char ↔ code point. |
| `UpcaseAtom/2`, `DowncaseAtom/2` | Case conversion. |
| `AtomLength/2` | String length. |
| `AtomChars/2`, `AtomCodes/2` | Bidirectional atom ↔ char/code list conversion. |
| `AtomConcat/3` | String concatenation as a relation (reverse enumerates splits). |
| `SubAtom/5` | Substring extraction — 5-arg multi-modal relation. |
| `Listing/1` | List all clauses for a predicate from `pred_cls._clauses`. |
| `PortrayClause/1` | Pretty-print a term with indentation via `term_pformat`. |

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

### Phase 5 — Extend Existing Builtins (Gap-Filling) ✓

**Status: COMPLETE** — Small additions to modules that are already mostly complete.

| Area | Additions |
|---|---|
| CLP(FD) | `Sum/3`, `ScalarProduct/4`, `Element/3`, `Circuit/1` (global constraints). |
| Lists | `Numlist/2,3`, `SameLength/2`, `Transpose/2`. |
| DCGs | `Seq//1`, `Seqq//1` (sequence matching helpers). |
| Tabling | `AbolishAllTables/0`, `AbolishTable/1`. |
| Arithmetic | `Lcm/3`, `ExpMod/4`, `Popcount/2`, `Msb/2`, `Lsb/2`. |
| Pairs | `GroupPairsByKey/2`. |
| Error | `MustBe/2`, `CanBe/2` (type-checking with ISO error terms). |
| Reif | `If_/3`, `TFilter/3`, `TPartition/4` as explicit builtins. |
| Time | `CurrentTime/1`, `Statistics/2`. (`Sleep/1` already in `py.process`, Phase 4.) |

**Detailed plan:** [`STD_MODULES_PHASE5.md`](STD_MODULES_PHASE5.md)

---

### Phase 6 — User-Facing Attributed Variables

**Priority: Medium** — Enable users to build custom constraint solvers in `.clausal`.

| Item | Description |
|---|---|
| `PutAtts/2` | Attach attributes to a variable. |
| `GetAtts/2` | Retrieve attributes from a variable. |
| `TermAttributedVariables/2` | Collect all attributed variables in a term. |

The internal infrastructure already exists (CLP(FD), CLP(B), dif all use it).
This phase exposes it as a public API.

**Detailed plan:** TBD

---

### Phase 7 — Optional / Low Priority

These are nice-to-have. They can be thin wrappers or deferred indefinitely since
`++()` interop covers the functionality.

| Item | Description |
|---|---|
| `crypto` module | Hash, HMAC, encrypt/decrypt. Wrap `hashlib`/`cryptography`. |
| `sockets` module | TCP client/server. Wrap Python `socket`. |
| `http` module | `HttpGet/3`, `HttpPost/4`. Wrap `requests` or `urllib`. |
| `Gensym/2` | Unique atom generation. Trivial counter wrapper. |
| `charsio` extras | `ReadFromChars/2`, `WriteTermToChars/3` if f-strings prove insufficient. |

**Detailed plan:** TBD (may not be needed)
