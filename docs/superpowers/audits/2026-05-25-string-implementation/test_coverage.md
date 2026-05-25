# Existing string test coverage

**Purpose:** inventory what existing pytest tests cover so Phase 1
(adversarial tests per class) doesn't duplicate coverage.

**Method:** read every test file whose name suggests string / SegList /
SegString / DCG / chars / higher-order coverage. For each, jot the
predicates / classes it exercises. Then per audit class C1–C17, note
what is NOT covered.

**Convention:** "happy path" = positive assertion of intended
behaviour, no edge probing. "Adversarial" = drives the boundary that
findings F018, F031, etc. exposed. The existing suite is heavily
happy-path; this is exactly what Phase 1 needs to supplement.

## Test files surveyed

| Test file | Lines | Surfaces covered | Classes likely tested (depth) |
|-----------|------:|------------------|-------------------------------|
| `tests/test_string_list_unification.py` | 453 | C-level `unify(str, list)` (`TestStringUnifiesWithCharList`, `TestStringListMismatch`, `TestStringListVarBinding`, `TestBacktracking`, `TestNestedStringList`, `TestEdgeCases`); `SegList.__unify__` against str/list (`TestSegListStringUnification`); `_body_multi_star_unify` against str (`TestBodyMultiStarUnifyString`); `_seglist_unify_gen` driven directly | C1 (happy), C2 (only via `_seglist_unify_gen` driver — not via `__unify__`), C7 (Unicode + emoji + surrogate-pair happy), C16 (basic `same_var_repeated` only — no FT stress) |
| `tests/test_seglist_core.py` | 504 | `SegList` ctor / `__walk__` / `is_ground` / `to_list` / `__occurs_check__` / `__unify__` / `_seglist_unify_gen` / sequence protocol (`len`, `iter`, `contains`, `getitem`) / `__add__`/`__radd__` / `__eq__` / `__hash__` (negative — TypeError) / `__repr__`; also `_multi_star_splits` edge cases | C1 (walk happy), C2 (gen happy — multiple splits enumerated directly), C5 (unhashable check), C8 (`getitem_unground_raises`, `len_unground_raises`, `iter_unground_raises` — these pin F021's TypeError-on-unground behaviour as intentional) |
| `tests/test_seglist_creation.py` | 425 | Compiler creation paths: `_head_list_unify_output`, `_body_star_unify`, `_body_multi_star_unify`, `_build_star_list`, `_build_multi_star_list` for unbound targets/stars; compiled `append`, `last`, `Split` predicates with unbound list args | C1 (creation happy — every assertion is "result IS SegList"; locks in F033/F042/F043 unconditional-list/SegList behaviour as intended), C2 (enumerated splits inside the gen) |
| `tests/test_seglist_passthrough.py` | 230 | Compiled predicates with single-star and multi-star heads receiving ground SegLists (`append`, `last`, `Split`, `Split3`, `Around`); body-star (`HeadTail`, `InitLast`); `SegList + list` concat passthrough; one negative case for non-ground SegList → 0 solutions (locks F047 sibling behaviour for SegList) | C1 (passthrough happy), C3 (only the SegList side — explicit assertion that non-ground SegList gives 0 solutions matches F040/F041's body-side cluster but for SegList, not SegString) |
| `tests/test_segstring.py` | 486 | SegString ctor / `__walk__` (ground, bound var, unbound, empty, adjacent merge, list-bound, nested) / `is_ground` / `to_str` / `__unify__` against str (ground, varseg binding, two varseg, empty, symmetric, ground-vs-char-list) / `__occurs_check__` / `_segstring_unify_gen` (multiple solutions); SegList VarSeg binding to str (substring preserving); `_body_multi_star_unify` on str; `_build_star_list`/`_build_multi_star_list` str support (incl. non-ground SegString → SegList demotion via F043's `all_str = False`); clause-level `HeadTail` on str | C1 (str preservation happy + locks in F043's non-ground-SegString-to-SegList demotion as intended at `test_star_nonground_segstring_mixed`), C2 (gen driven directly — happy), C3 (only the SegString-vs-str direction; no SegString-as-target-in-list-head, no SegString-vs-list at head match) |
| `tests/test_string_head_patterns.py` | 177 | Compiled predicates from `list_edge_cases.clausal`: `HeadTail`, `CaptureAll`, `ThreeAndRest`, `ExactlyTwo`, `IsEmpty`; from `lists.clausal`: `length`, `last`. Type-preservation through recursion (tail is str, capture is str, rest is str). | C1 (str-preservation happy across recursion), C4 (negative — none; the F046 failure mode of literal-string-head clauses is not probed) |
| `tests/test_string_higher_order.py` | 180 | `include`, `exclude`, `maplist/2`, `maplist/3`, `foldl/4`, `partition`, `take_while`, `drop_while`, `span` on string inputs with a per-char predicate fixture (`is_vowel`, `is_upper`, `char_to_code`, `concat_chars`). Locks in str-preservation for filter family. | C9 (higher-order happy — locks in `_seq_result` str promotion on str input only; F062's "list-of-1-char-str input should also promote" is NOT exercised here) |
| `tests/test_string_list_builtins.py` | 408 | Polymorphic list builtins on str input: `in_`, `in_check`, `append`, `length`, `reverse`, `last`, `get_item`, `take`, `drop`, `split_at`, `msort`, `sort`, `list_to_set`, `select`, `subtract`, `intersection`, `union`, `max_list`, `min_list`, `permutation`, `zip_`, `split_with`, `same_length`, `is_chars`. Includes the F080 codification — `is_list("hello")` asserted False as intended. | C9 (str-input happy — but every test path is `str` input, never `SegList`/`SegString` input; F051's silent-fail on ground Seg* is NOT probed), C13 (`is_chars` happy; `is_list("hello")` False *codified*) |
| `tests/test_chars.py` | 557 | `char_type/2` (both bound, enum types, enum chars, control, ASCII), `char_code/2`, `upcase_atom`, `downcase_atom`, `atom_length`, `atom_chars`, `atom_codes`, `atom_concat/3` (forward, reverse enumerate, prefix/suffix bound), `sub_atom/5` (all bound, search, length-bound enumerate, all-unbound enumerate, edge cases), `number_chars`, `number_codes` | C7 (none — ASCII-only; F002/F003/F004/F007 multi-codepoint cases NOT probed), C12 (some — `chr(0)` control char only; no F073 out-of-range probe), C13 (none — type-check coverage lives in `test_string_list_builtins.py`'s `is_chars` only) |
| `tests/test_dcg.py` | 798 | DCG terminals / non-terminals / inline goals / conjunction / disjunction / negation / if-then-else / pushback / `phrase/2` and `phrase/3` / recursive DCGs / state threading (counter, leaf counting, accumulator, state-only) / phrase/3 with str-as-state. Phase 3 string input: `TestDCGStringInput` covers `phrase(rule, "hi")` happy + remainder list, recursive on string, inline goal on str. | C10 (str-input-to-phrase happy; F068's "phrase/3 splits str state-thread into chars" is NOT probed — the state-threading tests use list state `[0]` or `[[]]`, not bare str; F069's "phrase on SegString" not probed; F067's "Rest is char list not str" partially probed — `test_phrase3_string_remainder` asserts Rest = `["X","Y"]`, codifying the F067 gap), C7 (none — all tokens are ASCII letters) |
| `tests/test_higher_order.py` | 355 | `_map_list__2`, `_map_list__3`, `_include__3`, `_exclude__3`, `_foldl__4` driven via trampoline; rename aliases (`msort`, `get_item`, `in_check`, `unpack`); builtin-as-arg to maplist/include/exclude. Inputs are int lists or compounds. | (Mostly non-string; relevant to C9 only via `test_non_list_fails` which uses str "abc" as expected-failure input to `_map_list__3` — but this is a pre-Phase-5 test that contradicts the newer `test_string_higher_order.py`. Needs deeper read.) |
| `tests/test_term_inspection.py` | 801 | `copy_term/2` (atom/int/None/list/compound/var/sharing/nested/bound), `term_variables/2`, `numbervars/3`, `gensym/2`, `copy_term` with KWTerm and DictTerm and SegList (the latter three explicitly *gap-documenting* — assert F092/F093 current behaviour as the expected output), `global_atom/2`. | C14 (lock-in of F092/F093 gaps as intended behaviour at `TestCopyTermSegList`/`TestTermVariablesSegList` — if Phase 2 fixes F092, those tests must be updated), C5 indirectly (DictTerm gap parallel) |

## Out-of-scope adjacent test files

These were checked and found to not exercise strings/Seg* in any
meaningful way:

- `tests/test_first_arg_index.py` — has a `test_string_keys` test
  that uses string first-args to pin down indexed-dispatch happy
  path, but does NOT mix str and list callers (which is F095's
  surface). Needs deeper read if Phase 1 covers C15.
- `tests/test_body_star_decon.py` — pure star-decon over compound
  args; no str/Seg* paths.

## Gaps identified

Per class, what surface is NOT covered by existing tests. (Only
classes with open findings or test gaps are listed.)

### C1 — Type preservation

- **F018** (SegList walk char expansion of VarSeg-bound str): NOT
  TESTED as adversarial. `test_segstring.py::test_walk_handles_string_bound_varseg`
  pins the same behaviour for `SegList` as intended, so any Phase 1
  test must decide whether to invert the assertion (under the
  "input-type wins" reading) or document the existing pin.
- **F033** (`_head_list_unify_output` always builds list): pinned-in
  by `test_seglist_creation.py::TestOutputUnboundStar` —
  unconditional `assert isinstance(sl, SegList)`. Phase 1 needs an
  adversarial test that exposes a caller for whom the list-vs-str
  shape matters (e.g. downstream str-typed builtin).
- **F020** (`SegList.__add__`/`__radd__` rejects str): NOT TESTED.
  `test_seglist_core.py::TestConcat` only covers list + SegList and
  SegList + list.
- **F042** (`_body_multi_star_unify` unbound-target always SegList):
  pinned-in by `test_seglist_creation.py::TestBodyMultiStarUnifyUnbound`
  — same situation as F033.
- **F043** (`_build_*_star_list` lose str type for list-of-1-char-strs
  and non-ground SegString stars): partially pinned — the
  non-ground-SegString-to-SegList demotion is asserted at
  `test_segstring.py::test_star_nonground_segstring_mixed`. The
  list-of-1-char-strs branch has NO coverage either way.

Phase 1 implication: every C1 finding is either un-tested or has the
*opposite* of the audit's "should be" pinned in. Tests are written
*from the implementation's POV*, not the contract's.

### C2 — Non-det collapsed to first

- **F015** (`SegList.__unify__` returns only first split): the
  generator path (`_seglist_unify_gen` direct) is tested with all 4
  splits expected (`test_seglist_core.py::test_two_vars_all_splits`,
  `test_string_list_unification.py::test_two_stars`,
  `test_seglist_creation.py::test_seglist_then_unified_against_ground`).
  The protocol-boundary path (`unify(SegList, list)` → only first
  split) is NOT tested as a gap — `test_string_list_unification.py`
  consistently uses the generator helper for multi-solution checks
  and `unify()` for single-solution checks, codifying the
  collapse-to-first.
- **F016** (SegString twin): same situation —
  `test_segstring.py::TestSegStringGenerator::test_multiple_splits`
  uses the gen helper for 2-solution check; `test_two_varseg` uses
  `unify()` for the single-solution case.

Phase 1 implication: needs adversarial tests that drive
`unify(SegList([*A,*B]), [1,2,3], trail)` and assert that *all four*
splits are reachable through the protocol (currently only the first
is). Same for SegString.

### C3 — SegString blind spots vs SegList

- **F031/F032** (`_head_list_unify_input` no SegString branch):
  partially covered indirectly — `test_segstring.py::TestClauseLevelStringPatterns::test_head_tail_string`
  drives `HeadTail("hello", ...)` (str, not SegString), which works.
  The Var-bound-to-SegString case is NOT tested.
- **F012** (Var bound to SegString in list-element position): NOT
  TESTED. `test_segstring.py::test_segstring_vs_char_list` covers
  the top-level case but not the in-list-element case.
- **F034** (`_head_list_unify_output` SegString star_val): NOT
  TESTED.
- **F040/F041** (`_body_multi_star_unify` ground & non-ground
  SegString rejection): NOT TESTED.
- **F047** (multi-star head guard ignores SegString): NOT TESTED.
- **F075** (every char/atom builtin in `chars.py` SegString-blind):
  NOT TESTED. `test_chars.py` is pure-str input.
- **F051** (cluster — every polymorphic list builtin silently fails
  on ground Seg*): NOT TESTED.
  `test_string_list_builtins.py` is pure-str input.

Phase 1 implication: C3 is almost wholly un-covered. Needs a
systematic SegString-as-input sweep across (head pattern, body
pattern, char builtin, list builtin) — this is the largest single
class to populate.

### C4 — Head-pattern literal mismatch

- **F046** (rule heads with str literal fail on char-list caller):
  NOT TESTED. `test_string_head_patterns.py` covers list-literal
  heads accepting str callers (the side that *works*) but not the
  symmetric str-literal heads accepting list callers.

Phase 1 implication: needs an inline-clausal test that defines
`Quux("abc") <- Helper(1)` and drives `Quux(["a","b","c"])`.

### C5 — Hash/eq asymmetries

- **F017** (`SegString.__hash__` violates eq/hash invariant): NOT
  TESTED. SegList unhashability is tested
  (`test_seglist_core.py::test_not_hashable`); SegString
  hashability is NOT.
- **F019** (`SegList`/`SegString` `__eq__` asymmetry vs str/list):
  `test_seglist_core.py::test_seglist_neq_non_list` covers
  `SegList.__eq__("hello") is NotImplemented`; the reverse
  direction (`"hello" == SegList(...)`) and the SegString variants
  are NOT tested.
- **F025** (`SegList.__hash__` unconditional TypeError vs
  `SegString.__hash__` conditional): NOT TESTED.

### C7 — Unicode / multi-codepoint

(All open findings are `doc-only`. No fix needed; tests *would*
document behaviour.)

- **F002** (emoji split at codepoint not grapheme boundary):
  partial — `test_string_list_unification.py::test_emoji` covers
  the 2-emoji `"👋🌍"` case but NOT grapheme clusters like family
  emoji or combining marks.
- **F003** (NFC vs NFD not unified): NOT TESTED.
- **F004** (multi-char list element rejected): partial —
  `test_string_list_unification.py::test_str_vs_multi_char_elements`
  pins it as expected behaviour.
- **F007** (lone surrogate halves treated as codepoints): NOT
  TESTED.
- **F071** (`char_type/2` silently fails on multi-codepoint
  graphemes): NOT TESTED.
- **F074** (`upcase_atom`/`downcase_atom` change string length):
  NOT TESTED.
- **F076** (`sub_atom`/`atom_concat` split at codepoint, not
  grapheme): NOT TESTED.

Phase 1 implication: C7 is doc-only — tests should pin current
behaviour as expected (lock-in style), not drive adversarial.

### C8 — Partial-term short-circuits

- **F021** (SegList sequence protocol crashes on non-ground):
  partially pinned — `test_seglist_core.py::test_len_unground_raises`,
  `test_iter_unground_raises`, `test_getitem_unground_raises` all
  assert TypeError as expected (the "crash" half of the finding).
  Phase 1 question is whether the audit considers TypeError-the-fix
  or "should not raise" the desired contract.
- **F022** (`SegList.__contains__` silently incomplete on VarSegs):
  partially pinned — `test_seglist_core.py::test_contains_in_concrete_seg_unground`
  and `test_contains_not_found_unground` codify the
  "False on can't-confirm" branch as intended.
- **F023** (`SegString.__unify__(list)` silently fails when
  non-ground): NOT TESTED.
- **F024** (`SegString.__walk__` raises TypeError on non-str list
  binding): NOT TESTED.
- **F038/F039** (`_in_iter` on ground/non-ground SegString/SegList):
  NOT TESTED.

### C9 — Polymorphic builtin mode matrix

- **F050** (`split_with/3` join mode drops str parts): NOT TESTED.
  `test_string_list_builtins.py::TestSplitWithString` only covers
  the split direction.
- **F051** (cluster): see C3 above.
- **F052** (`sum_list`/`max_list`/`min_list` swallow TypeError):
  NOT TESTED.
- **F053** (`length(Var, N)`, `replicate`, `same_length` always
  build list): NOT TESTED at output side. `same_length(str, str)`
  forward direction is tested in
  `test_string_list_builtins.py::TestSameLengthString` but the
  X-unbound output mode is not.
- **F054** (`_seq_result` asymmetry list-of-1-char-strs vs str):
  NOT TESTED. Every `test_string_list_builtins.py` test uses str
  input and asserts str output; no test passes a
  semantically-equivalent list of 1-char strs.
- **F055** (`transpose/2` rejects str outer): NOT TESTED.
- **F056** (`flatten/2` str-as-atom): NOT TESTED.
- **F061** (`higher_order.py` predicates fail on Seg*): NOT
  TESTED. `test_string_higher_order.py` is pure-str.
- **F062** (higher-order list-of-1-char-strs input not promoted):
  NOT TESTED. Same pattern as F054.
- **F063** (`maplist/3`, `filter_map/3`, `group_by/3`, `sort_by/3`
  always list): NOT TESTED.
- **F072** (`char_type/2` Char-bound vs Type-bound non-ASCII
  disagreement): NOT TESTED.
- **F077** (`atom_concat/3` instantiation_error for mis-typed
  bound args): NOT TESTED.

### C10 — DCG / phrase interaction

- **F068** (`phrase/3` splits str state-thread into chars): NOT
  TESTED as adversarial — all state-threading tests in
  `test_dcg.py::TestStateThreading` use list state `[0]`, never
  bare str.
- **F069** (`phrase/2,3` silently fails on SegString): NOT TESTED.
- **F067** (`phrase/3` Rest does not preserve str input shape):
  pinned in `test_dcg.py::test_phrase3_string_remainder` —
  `Rest = ["X","Y"]` asserted as intended. Same lock-in pattern as
  F033.
- **F070** (`sequence//1` drops str across binding modes): NOT
  TESTED.

### C11 — Trail/backtracking around partials

No findings yet. Existing trail coverage in
`test_string_list_unification.py::TestBacktracking` and
`test_seglist_core.py::TestUnify`'s per-iteration `trail.undo`
patterns is adequate as a smoke test but does not stress the
SegList/SegString partial-bind/undo cycle.

### C12 — Char representation drift

- **F073** (`char_code`/`atom_codes`/`number_codes` leak
  `ValueError` for out-of-range codes): NOT TESTED.
  `test_chars.py::TestCharCode::test_non_char_error` only covers
  the multi-char string case.

### C13 — Type-check predicates

- **F080** (`is_list` rejects strings while every list builtin
  accepts): codified-as-intended at
  `test_string_list_builtins.py::TestIsChars::test_is_list_string_still_fails`
  — needs Phase 1 decision whether to flip or document.
- **F081** (`string/1` not registered, only `is_str/1`): NOT
  TESTED.
- **F082** (`atomic/1` not registered): NOT TESTED.
- **F083** (`ground/1` returns True for Seg*-with-VarSeg): NOT
  TESTED.
- **F084** (`callable_/1` accepts every str): NOT TESTED.

### C14 — Term inspection drift

- **F088** (`unpack` on non-empty list yields `[".", ]` no args):
  NOT TESTED.
- **F090** (`arg(N, "abc", X)` silent fail): NOT TESTED.
- **F091** (`arg/3` on list uses Python indexing not cons-cell):
  NOT TESTED.
- **F092** (`copy_term` doesn't recurse into Seg*): codified-as-gap
  at `test_term_inspection.py::TestCopyTermSegList::test_copy_seglist_var_not_freshened`
  — comment header says "These tests document the current
  behaviour so any future fix breaks visibly." Phase 1 / Phase 2
  must update these.
- **F093** (`term_variables` doesn't see Seg* VarSegs): same —
  codified-as-gap at
  `test_term_inspection.py::TestTermVariablesSegList::test_seglist_vars_not_collected`.
- **F094** (`numbervars` can't number Seg* Vars): NOT TESTED
  (`test_term_inspection.py::TestNumberVars` covers compound /
  list / nested cases only; no Seg* probe).
- **F089** (`functor/3` and `=..` give different shapes str vs
  list): NOT TESTED as an asymmetry.

### C15 — First-arg indexing on strings

- **F095** (indexed dispatch routes list callers away from
  str-headed buckets): NOT TESTED. `test_first_arg_index.py::test_string_keys`
  pins the all-str-keys happy path but never mixes str-keyed and
  list-keyed clauses at the same arg position. Phase 1 needs the
  mixed-shape fact-table scenario from `probes/probe_F095.py`.

### C16 — Free-threaded build safety

- **F011** (str↔list C block holds no critical section on list
  arg): NOT TESTED. The audit notes "test harness runs with GIL
  enabled, so the race cannot be reproduced here" — Phase 1 may
  legitimately defer this to a `Py_GIL_DISABLED` CI lane.

### C17 — Performance, memory, leaks

- **F009** (per-element `PyUnicode_Substring` alloc): NOT TESTED
  (no perf assertions in the suite). The probe at
  `probes/probe_F009.py` is bench-only.
- **F026** (`_multi_star_splits` combinatorial cost): NOT TESTED.
- **F078** (dead non-ASCII alloc branch in `_chars_core.c`):
  static-review only — no runtime probe possible.

## Phase 1 implications

Per class, whether Phase 1 should write tests *from scratch* or
*complement existing tests*:

| Class | Approach | Note |
|-------|----------|------|
| C1 | **complement + invert** | Every finding has the *opposite* contract pinned in `test_seglist_creation.py` and `test_segstring.py`. Phase 1 adversarial tests must either invert those pins (requires deleting/updating existing tests) or add a parallel "contract gap" suite alongside. Choice depends on Phase 2 fix direction. |
| C2 | **from scratch** | The protocol-boundary collapse-to-first behaviour (F015/F016) is uncovered. Existing tests use `_*_gen` helpers for multi-solution checks, never `unify()`. New tests must drive `unify()` and assert all solutions reachable through the protocol. |
| C3 | **from scratch** | Largest class to populate. SegString-as-input has zero coverage across head/body/builtin paths. Build a SegString sweep mirroring `test_seglist_passthrough.py`'s structure. |
| C4 | **from scratch** | F046 (str-literal head + list caller) is uncovered. |
| C5 | **from scratch** | Hash/eq asymmetries have no targeted tests. |
| C7 | **complement** (lock-in style) | C7 findings are doc-only. Phase 1 should pin current behaviour as expected; not adversarial. |
| C8 | **complement** | SegList sequence-protocol crash behaviour is partly pinned; needs F023/F024/F038/F039 added. |
| C9 | **from scratch** | Polymorphic mode-matrix gaps (F050/F052/F054/F055/F056/F063/F072/F077) are entirely uncovered. F051 cluster overlaps with C3. |
| C10 | **complement + invert** | F067 (Rest as char list, not str) is pinned-as-intended; Phase 1 must decide whether to invert. F068/F069/F070 need from-scratch tests. |
| C11 | **from scratch** | No findings yet; if Phase 0 finds any, no existing coverage. |
| C12 | **from scratch** | F073 (out-of-range chr error) uncovered. |
| C13 | **from scratch** | Type-check predicates (`string`, `atomic`, `ground` on Seg*, `callable_` on str) uncovered. F080 codified as-is. |
| C14 | **complement + invert** | F092/F093 pinned-as-gap in `test_term_inspection.py` with explicit "future fix breaks visibly" intent — those tests are *designed* to be updated. F088/F090/F091/F094/F089 from-scratch. |
| C15 | **from scratch** | F095 (mixed-shape dispatch) uncovered. |
| C16 | **defer** | F011 needs FT build to reproduce; out of scope for the GIL-enabled test lane. |
| C17 | **complement** | Perf findings already have bench probes; convert to assertion-light test only if Phase 2 fixes warrant it. |

## Notes for Phase 1 planner

- **Lock-in tests are the single biggest hazard.** Several findings
  (F033, F042, F067, F080, F092, F093) have existing tests that
  assert the *current* behaviour as expected. Any Phase 2 fix that
  changes that behaviour will break those tests. Phase 1's
  adversarial test for these findings should be written so that the
  Phase 2 fix can switch a single assertion (or be added as a new
  test next to the existing one, with the older test marked
  `xfail` or removed depending on the fix direction).
- **`test_higher_order.py::test_non_list_fails`** uses `"abc"` as a
  "should fail" input to `_map_list__3`. This pre-dates the
  Phase 5 string-acceptance work and now contradicts
  `test_string_higher_order.py`. A deeper read is needed to confirm
  whether this is an active bug-test or a vestigial assertion.
- **No FT (Py_GIL_DISABLED) test lane is exercised** by the
  current suite. F011 cannot be reproduced without one.
- **`probes/probe_F*.py`** are NOT pytest tests — they're
  standalone reproducers. Phase 1 should pull the reproducer code
  out of each probe and re-encode as a pytest case in the
  appropriate test module.
