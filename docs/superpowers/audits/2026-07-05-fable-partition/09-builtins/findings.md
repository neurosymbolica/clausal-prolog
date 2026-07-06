# Findings — A09 builtins & stdlib predicates

Severity order: correctness > memory > design > perf > doc-drift.
Confirmed correctness findings have a Test ref AND a Todo ref.

All findings below are **confirmed by executed pytest** (test_09_builtins.py)
unless marked otherwise. `HO` = higher_order.py, `L` = lists.py, `CH` = chars.py.

| ID | Severity | Title | Location (file:line) | Repro | Expected vs Actual | Test ref | Todo ref |
|----|----------|-------|----------------------|-------|--------------------|----------|----------|
| A09-F001 | correctness | sort/2 & msort/2 do not deref elements — bound-Var elements sort by type-name fallback and never dedup against their value | L:432–469 | `X is 5, msort([X,1,2],S)` | `[1,2,5]` vs `[5,1,2]`; `sort([X,5,1],S)` → `[5,1,5]` (unsorted AND dup kept — "sort dedups" contract broken) | test_F001_* | fix-A09-sort-msort-deref.md |
| A09-F002 | correctness | filter_map/3 captures the output term after trail.undo — inner bindings of compound outputs are silently lost | HO:471–479 | `fmg(X,P)<-(Y is 1, P is pair(X,Y))`, `filter_map(fmg,[5],R)` | `[pair(5,1)]` vs `[pair(5,_unbound)]` — silent wrong answer | test_F002_* | fix-A09-filter-map-binding-capture.md |
| A09-F003 | correctness | include/exclude/partition/take_while/drop_while/span append `deref(elem)` after undoing the goal's bindings — Var elements lose the bindings the test goal made | HO:127–134 (+ same pattern ×5) | `include(one_,[X,2],R)` with `one_(1)` | X=1 (SWI) vs X unbound; take_while same | test_F003_* | fix-A09-ho-var-element-bindings.md |
| A09-F004 | correctness | maplist/2,3 and foldl/4 commit to the first solution per element — solutions requiring later alternatives are unreachable | HO:69–75, 99–107, 180–188 | `maplist(pick,[1],[Y]), Y is "b"` with `pick(1,"a"),pick(1,"b")` | Y="b" reachable (SWI) vs 0 solutions; foldl analog | test_F004_* | investigate-A09-ho-committed-choice.md (D001) |
| A09-F005 | correctness | assertz/1 of a rule term half-works and poisons the predicate: assert succeeds, then EVERY query of that predicate raises `NotImplementedError: terms_to_goalop` (existing facts included) | database_ops.py:56–61, 90–107 | `assertz(seen2(Z) <- q3(Z))`, then `seen2(V)` | clean error at assert time or a working rule vs predicate bricked | test_F005_assertz_rule | fix-A09-assertz-rule-lowering.md |
| A09-F006 | correctness | assertz/asserta/retract on a locked predicate raise `RuntimeError`, which the trampoline drive loop swallows as generator exhaustion → documented "permission error" is actually a **silent failure** (root cause of the known "assertz on non-dynamic fails silently" pitfall) | database_ops.py:97–101, 130–134, 172–176; swallow: runtime/_trampoline.c:664–666, 719–721 | `assertz(locked_(2))` in a module without `-dynamic` | permission_error LogicException (per docs/database_ops.md) vs silent False | test_F006_* | fix-A09-db-permission-logic-exception.md |
| A09-F007 | correctness | RecursionError (a RuntimeError subclass) raised by builtin helpers is converted to silent failure by the same drive-loop catch — cyclic/deep input to flatten/2 or copy_term/2 answers "no" instead of erroring | L:394–415, inspection.py:22–82; root: runtime/_trampoline.c:664–666 (boundary A03/A12) | `L=[1,L], flatten(L,F)` | resource/type error vs silent failure (direct generator call DOES raise) | test_F007_* | investigate-A09-runtimeerror-swallow.md (D002) |
| A09-F008 | correctness | retract/1 undoes head-unification bindings — `retract(seen2(X))` succeeds with X left unbound (ISO/SWI bind the retracted clause's args); also not re-satisfiable on backtracking | database_ops.py:181–204 (undo at 204; documented in docstring) | `assertz(seen2(5)), retract(seen2(X))` | X=5 vs X unbound | test_F008_retract_binds_pattern | fix-A09-retract-bindings.md (D003) |
| A09-F009 | correctness | sequence//1 checks the terminal prefix with Python `==` instead of unification — var terminals always fail in Mode A | dcg.py:131–141 | `sequence([X], "a", S)` | X="a", S="" vs 0 solutions | test_F009_* | fix-A09-sequence-unify-terminals.md |
| A09-F010 | correctness | copy_term/2 drops attribute constraints — the copy of a dif-constrained var unifies with the excluded value (SWI copies constraints) | inspection.py:28–32 (`var_map[vid] = Var()`), C twin in _variables.c | `dif(X,1), copy_term(X,Y), Y is 1` | fails (constraint copied) vs succeeds | test_F010_copy_term_copies_dif | investigate-A09-copy-term-attrs.md (D004) |
| A09-F011 | correctness | plus/3, max_/3, min_/3 have no numeric type check: `plus("a","b",Z)` binds Z="ab" (string concat), `plus([1],[2],Z)`=[1,2]; mixed types leak **raw TypeError** through the query | arithmetic.py:156–183, 199–227 | `plus("a","b",Z)`; `plus(1,"a",Z)` | type_error or failure vs concat / raw TypeError | test_F011_* | fix-A09-arith-type-checks.md |
| A09-F012 | correctness | Raw Python exceptions escape builtins as uncatchable non-logic errors: pairs_values short pair → IndexError; dict_pairs/set_list unhashable → TypeError; exp_mod non-invertible base → ValueError; max_by incomparable keys → TypeError (while sort_by silently falls back — inconsistent) | pairs.py:16–17,39,52; dict_set.py:140–160, 356–363; arithmetic.py:337; HO:404 | `pairs_values([[1]],V)` etc. | typed LogicException or failure vs raw IndexError/TypeError/ValueError | test_F012_* | fix-A09-raw-exception-escapes.md |
| A09-F013 | correctness | char_type/2 test-mode is full-Unicode but enumeration is ASCII-only for digit/space/punct — the F072 fix covered only alpha/alnum/upper/lower/print | CH:109 (`_UNICODE_TYPES`), 76–87 | `char_type('٣',"digit")` ✓ but `findall(C, char_type(C,"digit"))` = 10 ASCII chars | mode-consistent relation vs test⊅enum | test_F013_* | fix-A09-char-type-unicode-enum.md |
| A09-F014 | correctness | char_type/2 char-bound Python fallback uses the ASCII-only `_CHAR_TO_TYPES` table — with the C helper absent, `char_type('α',T)` enumerates NOTHING (C path yields alpha/alnum/lower/print). Latent C-vs-Python divergence | CH:191–197 | disable `_c_char_type_find_types`, query `char_type('α',T)` | same types as C path vs [] | test_F014_* | fix-A09-char-type-py-fallback.md |
| A09-F015 | correctness | bool-as-int acceptance is inconsistent across builtins, and between/3 C vs Python fallback **diverge**: succ/sign/popcount/msb/lsb + C-between reject bool; Python-between, plus, length, list_item, take, arg, functor(arity), sub_atom, numlist, char_code accept it (`length(L,True)`→[_], `char_code(C,True)`→'\x01') | L:275,353,694; arithmetic.py:120 (py) vs C; inspection.py:197,238; CH:267,546–551 | `between(False,True,X)`: C=[] vs Py=[0,1] | uniform policy (A01-D001) vs matrix above | test_F015_* | fix-A09-bool-acceptance-matrix.md (blocked on A01-D001) |
| A09-F016 | correctness | must_be/can_be type "list" rejects str — `must_be("list","abc")` raises type_error while `is_list("abc")` succeeds (F080 lock-in) — strings-as-lists contract violation | type_checks.py:310–311 | `must_be("list","abc")` | succeeds vs type_error | test_F016_must_be_list_string | fix-A09-must-be-list-strings.md |
| A09-F017 | correctness | atom_chars/atom_codes/number_chars/number_codes reject the str/bytes form of their char/code-list argument with type_error("list") — but a str IS a char list and a bytes IS a code list (Liskov) | CH:354, 396–397, 610–611, 658–659 | `atom_chars(A,"abc")` | A="abc" vs type_error(list,"abc") | test_F017_* | fix-A09-atom-chars-str-args.md |
| A09-F018 | correctness | pairs_keys_values/pairs_keys/pairs_values silently drop non-list "pair" entries (succeed with shortened K/V lists) | pairs.py:16–17, 39, 52 | `pairs_keys_values([[1,"a"],"junk"],K,V)` | failure/type_error vs K=[1],V=["a"] | test_F018_* | fix-A09-pairs-malformed-pairs.md |
| A09-F019 | correctness (low) | same_length/2 ground-Seg* support is dead code: docstring + `_fresh_same_shape` promise SegString/SegBytes siblings, but the entry check only admits (list,str,bytes) → ground SegString input fails | L:899–911 (vs docstring 887–897) | `same_length(SegString(["ab"]), L)` | binds L (2 holes) vs fails | test_F019_* | fix-A09-same-length-seg.md |
| A09-F020 | memory | _chars_core.c has **no Trail_Check** before Trail_CAST in any of its 5 trail-taking functions (cross-cutting issue #1, new instance — file absent from that issue's list) → garbage-memory read on a non-Trail arg (surfaces today as a bogus cross-thread RuntimeError, itself swallowed per F006); also `PyUnicode_READ_CHAR(char_str, 0)` OOB read on an empty string returns a garbage classification | _chars_core.c:163, 223, 266, 320, 399; 162 | `char_type_find_types("a",0,Var(),"not a trail")`; `("",0,Var(),Trail())` → `(7,0)` | TypeError vs UB | test_F020_* | fix-A09-chars-core-trail-check.md |
| A09-F021 | memory | _lists_core.c calls PyList_GET_SIZE/GET_ITEM on the unvalidated `items` arg — `member_find("abc",…)` **segfaults** (cross-cutting #6 family; Trail_Check itself is present here) | _lists_core.c:132, 176, 228, 306, 444 | subprocess: `member_find("abc",0,Var(),Trail())` | TypeError vs SIGSEGV | test_F021_lists_core_non_list_segfault | fix-A09-lists-core-arg-validation.md |
| A09-F022 | design (parked) | Cross-type Python `==`/`in`/hash conflation in equality-family builtins: subtract/intersection/union/split_with/sort-dedup/group_by/group_pairs_by_key treat 1≡True≡1.0 (`subtract([1],[True])`→[]; sort([1,1.0,True])→[1]; group keys merge), and group_pairs_by_key splits EQUAL unhashable keys via id() | L:457–459, 536, 554, 573–575, 797; HO:321; pairs.py:80–88 | see Repro col | inherits A01-D001 (unify semantics must lead — A05-D001 precedent) | test_F022_* | investigate-A09-parked-design-decisions.md (D005) |
| A09-F023 | doc-drift | union/3 docstring + docs/lists.md say "no duplicates", but duplicates within S1 are kept (`union([1,1],[],U)`→[1,1] — SWI-consistent; fix the doc) | L:562–564; docs/lists.md:258 | `union([1,1],[2],U)` | doc vs [1,1,2] | (probe P47/P63) | fix-A09-doc-drift.md |
| A09-F024 | doc-drift | transpose/2 F055 docstring claims `transpose("ab")` yields `[['a'],['b']]`; actual (and Liskov-correct) result is `[['a','b']]` — the `items=[r]` fallback branch it describes is dead for str rows | L:914–941 | `transpose("ab",T)` | doc vs [["a","b"]] | (probe P56) | fix-A09-doc-drift.md |
| A09-F025 | doc-drift | docs/lists.md: append/3 "works in all directions" — but append(+,−,−) has no partial-list mode and fails; same open-mode gaps: maplist(−,+), zip_(−,−,+), same_length(−,−), length(−,−), in_(?,−) | L:195–257; docs/lists.md:73–75 | `append([1],L2,L3)` | partial list `[1|L2]` (SWI) vs failure | test_F025_* | fix-A09-doc-drift.md |
| A09-F026 | doc-drift | docs/database_ops.md: "assertz adds facts, not rules — not supported" (code half-supports rules, see F005) and "without -dynamic, assertz and retract will raise a permission error" (actually silent failure, see F006) | docs/database_ops.md:121–127 | — | doc vs F005/F006 behaviour | test_F005/F006 | fix-A09-doc-drift.md |
| A09-F027 | design (low) | functor/3 & unpack/2 non-atom functor handling: `functor(3,N,0)` → N="3" (repr-string; ISO gives the number back, and the result does not roundtrip); `unpack(T,[3,1,2])` silently builds Compound("3",(1,2)); `functor(T,f(1),2)` builds functor string "f(1)" | _helpers.py:44–45; inspection.py:202, 292 | see Repro | ISO: number back / type_error(atomic) vs repr-strings | test_F027_* | fix-A09-functor-nonatom-names.md |
| A09-F028 | design (low) | must_be/2 with an unknown type name raises `type_error(<bogus type>, Term)` instead of `domain_error(type, Type)`; unbound/non-str Type silently fails despite must_be's error-raising contract | type_checks.py:296–354 | `must_be("nonsense",5)` | domain_error vs misleading type_error | (probe Q12/Q13) | fix-A09-minor-iso-divergences.md |
| A09-F029 | design (low) | Seg*-consistency matrix of type checks is incoherent: for a ground SegString, is_str ✓ / string ✓ / is_list ✓ but atomic ✗ and is_chars ✗ (is_str implies atomic for every other value; is_chars claims "list or string") | type_checks.py:126–155, 255–263 | Q14–Q17 | consistent normalize-at-surface policy vs matrix | (probes Q14–Q17) | fix-A09-typecheck-seg-consistency.md |
| A09-F030 | design (low) | number_chars/number_codes accept Python-lenient forms ISO rejects: `" 1"`→1 (whitespace), `"1_0"`→10 (underscore), `"inf"`→float inf | CH:620–627, 670–677 | P32–P34 | parse failure vs accepted | (probes P32–P34) | fix-A09-minor-iso-divergences.md |
| A09-F031 | design (low) | atom_concat/3 error behaviour is mode-dependent for a non-atom bound arg: open mode raises type_error(atom,12) (F077) but check mode `atom_concat(12,"a","12a")` silently fails | CH:444–457 vs 475–489 | P58/P59 | uniform type_error vs silent fail in check mode | test_regression_atom_concat_typed_error | fix-A09-minor-iso-divergences.md |
| A09-F032 | correctness (low) | str-promotion flag inconsistency: msort/sort/list_to_set/take/drop/split_at/select/permutation/split_with use `isinstance(lst_val, str)` while reverse/2 uses `_was_string` — ground SegString input yields a *list* result where reverse yields a str | L:442, 464, 479, 504, 594, 697, 711, 729, 792 | `msort(SegString(["ba"]),S)` | "ab" vs ['a','b'] | test_F032_* | fix-A09-seq-promotion-was-string.md |

## Coverage map

Dimensions per predicate: **I** input mode (all ground), **O** output/var mode
(unbound in answer positions), **R** reverse/generative mode, **P** partial
(inner vars), **E** empty/singleton, **B** backtracking + trail restoration,
**X** error path (type/instantiation), **S** strings-as-lists (str input),
**Y** bytes-as-codes, **T** cross-type (bool/int, 1/1.0), **Seg** ground Seg*.

### lists.py
| predicate | dims to hit |
|---|---|
| in_/2, in_check/2 | I O R(elem var enum) E B S Y T |
| append/3 | I O(all splits) R(+,-,+ / -,+,+) (+,-,-) mode-gap E S Y mixed-type promotion |
| length/2 | I O(measure) R(generate) T(bool N) E S Seg |
| last/2, reverse/2 | I O R(reverse backward) E S Seg |
| list_item/3 | I O R(enum) T(bool N, negative N) S |
| flatten/2 | I O E nested-str cyclic |
| msort/2, sort/2 | I O E S **P (bound-Var elements — deref?)** T(1/1.0/True dedup) mixed-type fallback order |
| permutation/2 | I O E S B |
| select/3 | I O R E S B |
| subtract/3, intersection/3, union/3, list_to_set/2 | I O E S T(cross-type `in`/`not in`) dup handling vs docs |
| sum_list/2, max_list/2, min_list/2 | I O E X(type_error) P(bound vars) T |
| take/3, drop/3, split_at/4 | I O T(bool/negative N) E S |
| zip_/3 | I O(reverse? mode gap) E unequal-len |
| replicate/3 | I O E str-promotion |
| split_with/3 | I(split) R(join) E S T(sep ==) |
| numlist/2,3 | I O R X(low>high, bool, non-int) |
| same_length/2 | I O(fresh shape) both-var E **Seg (docstring claims vs entry check)** |
| transpose/2 | I O E ragged S(outer str) doc-claim |
| _append_dr__3 / DR variants | mutation-before-unify on failed unify; caller wiring |

### higher_order.py
| predicate | dims to hit |
|---|---|
| call/1..8, call_goal/1..8 | I O X(unbound/non-goal → silent fail?) arity range |
| maplist/2,3 | I O(ys var) R(xs var — mode gap) E S **nondet goal: committed choice?** B(bindings escape) |
| include/exclude/partition | I E S **P(var elements — binding kept?)** committed-choice(doc) |
| foldl/4 | I O E B acc-threading |
| take_while/drop_while/span | I E S P |
| group_by/3 | I E S T(key `==` cross-type) |
| sort_by/3, max_by/3, min_by/3 | I E X(incomparable keys — raw TypeError vs caught) |
| filter_map/3 | I E S **P(compound out w/ inner vars — undo loses bindings?)** |
| tfilter/3, tpartition/4 | I E **user-defined (clause-compiled) reified goal via _run_goal_once** |

### arithmetic.py
| predicate | dims to hit |
|---|---|
| between/3 | I(check) R(generate) O T(bool bounds/x C-vs-Py) E(low>high) |
| succ/2 | I O(backward) T(bool — Py rejects; C?) X(negative) |
| plus/3 | I O(any-arg) **X(non-numeric: str+str concatenates? raw TypeError?)** T |
| abs_/2, sign/2 | I O T(bool) X |
| max_/3, min_/3 | I **X(no numeric check — strings compare?)** T |
| gcd/3, lcm/3, divmod_/4 | I O X(zero divisor silent fail) T Quantity-dims |
| exp_mod/4 | I X(mod 0; negative exp raw ValueError?) |
| popcount/msb/lsb | I T(bool rejected) X(negative/zero) |

### inspection.py
| predicate | dims to hit |
|---|---|
| functor/3 | I(decompose: Compound/KWTerm/instance/list/str/num/atom) O(construct) **roundtrip num→"repr" asymmetry** T(bool arity) E("" / []) |
| arg/3 | I **X(n=0, negative — C _nth_arg Python-indexing leak?)** list/str cons semantics |
| unpack/2 | I O(construct) **X(non-atom functor → Compound(str(f)))** E |
| copy_term/2 | I P(sharing preserved) **attr/constraint copying (dif)** Seg cyclic |
| term_variables/2 | I P order dedup Seg |
| numbervars/3 | I P X(start non-int) B(undo on backtrack) |
| gensym/2, global_atom/2 | I O modes enumerate |

### type_checks.py
| predicate | dims to hit |
|---|---|
| var/nonvar/number/integer/float_/atom/atomic/compound/callable_/ground | I T(bool) Seg-consistency (is_str vs atomic vs is_chars) |
| is_list/1, is_chars/1, is_codes/1 | S Y Seg **consistency matrix** |
| must_be/2, can_be/2 | X **("list" vs strings-as-lists contradiction)** unknown-type-name behavior |

### chars.py
| predicate | dims to hit |
|---|---|
| char_type/2 | I O(enum types) R(enum chars) **T-mode vs enum-mode Unicode consistency (digit/space/punct)** X(both unbound) **C-vs-Py fallback divergence (non-ASCII char-bound)** |
| char_code/2 | I O R T(bool code) X out-of-range |
| upcase/downcase_atom/2 | I X Seg atom(PredicateMeta) |
| atom_length/2 | I X |
| atom_chars/2, atom_codes/2 | I O R **X(chars as str — strings-as-lists violation?)** Y(bytes as codes) |
| atom_concat/3 | I O(splits) R(prefix/suffix) X(F077 typed errors) partial-bound-non-atom |
| sub_atom/5 | I(all bound) O(enum) R(sub bound) fixed B/L T(bool) E |
| number_chars/2, number_codes/2 | I O R X(parse edge: whitespace/underscore/inf) |

### dict_set.py / pairs.py
| predicate | dims to hit |
|---|---|
| dict_* (size/keys/values/pairs/get/put/put_pairs/remove/merge/gen_dict/sub_dict) | I O R(pairs→dict) E X(**unhashable key raw TypeError**) B |
| set_* (size/list/union/intersection/subtract/sym_diff/subset/disjoint/add/remove/gen_set) | I O R E X(unhashable elem) |
| pairs_keys_values/3, pairs_keys/2, pairs_values/2 | I R E **X(short pair raw IndexError; non-list pair silently skipped)** |
| group_pairs_by_key/2 | I E **T(hash conflation 1/True/1.0; unhashable id-split)** |
| DR variants (dict_put_dr, set_union_dr) | mutation-before-unify; caller wiring |

### dcg.py
| predicate | dims to hit |
|---|---|
| phrase/2,3 | I O(rest var) S Seg X(non-rule) oracle: examples/dcg_state.clausal |
| sequence//3 | Modes A–D **P(var terminals — `==` vs unify)** S Y E |

### database_ops.py
| predicate | dims to hit |
|---|---|
| assertz/asserta | I(fact) **rule term (docs say unsupported; code supports)** X(locked) output-mode query after assert |
| retract/1 | I **O(pattern retract — do bindings escape?)** re-satisfiability E X |
| abolish_table/2, abolish_all_tables/0 | I X (behavioral overlap with A04 — smoke only) |

### keyword_ops.py / control.py / io.py / translations_builtin.py
| predicate | dims to hit |
|---|---|
| vary/3, extend/3, unbound_keys/2, signature/3 | I O X E |
| time_goal/1,2 | I B(multi-solution) X(non-goal) |
| current_time/1, statistics/2 | I O(enum) X(unknown key) |
| write/writeln/print_term/nl/tab/write_to_string/term_to_string/listing/portray_clause | I X(listing non-pred type_error; tab bool/negative) smoke |
| translate/3 | I X smoke |

### C files
| file | dims |
|---|---|
| _chars_core.c | **Trail_Check missing (cross-cutting #1 — new instance)**; empty-string READ_CHAR; refcount_stable loops over char_type/atom_concat/sub_atom; error-path trail marks |
| _lists_core.c | Trail_Check present (fixed); PyList_GET_SIZE on unvalidated arg; refcount loops over member/append-split/select/permutation/nth0; error-path trail marks |

Prior art consulted (not re-reported): `todo/cross_cutting_issues.md` (#1 Trail cast,
#2 IsInstance −1, #5 m_size=−1, #6 GET_SIZE macros, #8 int64), 
`todo/audit-tests-input-output-mode-coverage.md` (2026-06-26 sweep: append/length/
succ/plus/between/in_/list_item/select/subtract/sort/msort/numlist/reverse both-mode
results; reverse backward-mode since fixed), `tests/audit_2026_05_25/` C1–C17 class
tests (F051/F052/F053/F055/F056/F061 lists; F067/F069/F070 DCG; F072/F075/F077/F078
chars; F080–F084 type checks; F092/F093 inspection), `DUPLICATE_TESTS.md`.
