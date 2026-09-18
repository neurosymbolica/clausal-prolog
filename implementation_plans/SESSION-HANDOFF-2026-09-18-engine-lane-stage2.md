# Engine lane handoff — 2026-09-18 (session c) — stage 2 of the atoms-as-str flip: an atom IS the str

Follows `SESSION-HANDOFF-2026-09-18-engine-lane-b-END.md` (stage 1, frozen at `73c86686`). Branch
`feat/atoms-as-str-stage2-2026-09-18` in the CANONICAL repo (`/workspace/clausal`), off the stage-1 tip
(merge of `73c86686`). It carries C (`_variables.c`, `_list_unify.c`, `_lists_core.c`, `_chars_core.c`):
`git worktree add <path> <branch>` + `setup.py build_ext --inplace` in your OWN worktree. Nothing landed on
main. Nothing pushed. Landing order is unchanged: stage 1 lands first (after iso-export-lane's first G3 on
`73c86686`), stage 2 is a SEPARATE sha and a harness RE-BASELINE.

Spec: `docs/superpowers/specs/2026-09-18-atoms-as-str-design.md`. Plan: `docs/superpowers/plans/2026-09-18-atoms-as-str-stage2.md`
(9 tasks) + the pin brief `STAGE2-PIN-BRIEF.md` beside it.

## The rule after stage 2 (the whole of what a reader of a term must know)

* An atom IS the interned Python `str`: `mint("foo") is sys.intern("foo")`, `is_atom(x)` is `type(x) is str`,
  `spelling(a) is a`, a char atom is the 1-char str. A bare `""` is the atom `''` (only the empty carrier and
  `[]`/`b""`/`()` are nil).
* A string is UNCHANGED from stage 1: the carrier `('$chars', text)` (`cells.chars/is_chars/chars_text`), equal
  to its char list everywhere. A bare str is NEVER text now: `unify("ab", [a, b])` is FALSE, `"ab" == chars("ab")`
  is FALSE, `is_list("ab")`/`string("ab")` are false, `atom("ab")` is true.
* The 1-tuple `('x',)` is RESERVED (a future opaque Python object reference) and REFUSED from `_cell_shape`
  (`cells.refuse_reserved_1tuple`, message "the 1-tuple ('x',) is reserved ... an atom is the str 'x'"); only
  `(TUPLE_TAG,)` is excepted.
* No class is an atom (spec §4): `atom/1`, `is_atom_value`, `functor_arity` answer false/None for a zero-field
  `PredicateMeta`; a 0-arity predicate referenced as a VALUE compiles to the atom str (order caveat: only after
  its first clause/registration; a Name in call-function position never).
* A Python str crossing the seam (`++`, `to_term`, a goal argument, a dict key, a thunk result) is the ATOM
  (spec §3 Q1). Consequently a string that crosses INTO Python via `++` arrives as its text (a str) and, if
  handed back to an engine function, is read as an ATOM — `tests/fixtures/docs/io_examples.clausal`'s
  `write_canonical text: a string` row hands `canonical_text` the char-list spelling for that reason.
* A str in goal position is the call of that atom (`call("foo")`, `solve("foo", mod)` call `foo/0`).
* `normalize_seg_input` is the stage-2 TRAP: it unwraps the carrier to its str, which is now an atom, so a
  consumer that then tests `type(x) is str` / `is_atom(x)` reads a STRING as a NAME. Decomposition funnels and
  type checks use `walk_seg` (keeps the carrier); name funnels (`clpfd._op_spelling`, `attributes._storage_key`,
  `translate/3`) walk with `walk_seg` and refuse the carrier with `type_error(atom, …)`. The 8 remaining
  `normalize_seg_input` callers (dcg ×5, lists ×2, io ×1) read LISTS and re-wrap with `_text_out`; audited, not
  changed — a bare str atom handed to `phrase/2` as the list is read as text there (parked, see below).

## What is built (each task gated on the neighbour set + docs fixtures; the survey population of 108 files
## is 5109 passed / 0 failed at 2a476126)

    task 1  1d927057  atoms API: mint -> interned str; ('x',) refused as reserved; '' is an atom
    task 2  a8013e83  reader: str constants; 0-arity predicate as a value = the atom; head_match; arg_index str
    task 3  a93dbde3  C twins: str<->list arms only via the carrier flags; 1-char strs are chars; Python twin
    task 4  c2c5c7b3  interim rule RETIRED (refuse_bare_str + CLAUSAL_BARE_STR_TEXT gone); entry points:
                      _as_items(str) None, string/1 false, atom/1 true, atom goals; walk_seg; _text_list_eq
    task 5  9f9cf7dd  seam: to_term str passthrough; wrap_text identity
    task 6  d9884522  writers: str prints as an atom, carrier as the string; zero-field-class-as-atom gone;
                      1-tuple arms -> refuse; tools/iso_l3._is_atom
    task 7  acbd55f7  exporter goldens unchanged (1086 passed)
    task 8  f46d3a6d  the PIN rewrite (six agents, 82 test files + 2 fixtures) -- tests only
    task 8b 30b9efc0  the engine rows the agents refused (21 files, C rebuilt): first-arg index keys (s, 0) for a
                      str atom and _INDEX_VAR for a carrier call-site literal (goldens regenerated: PURE shape,
                      residual 0 after normalising ('x',) -> 'x'); type checks on walk_seg; _is_non_empty_list /
                      _is_atomic_term / callable_/1 / must_be(list) know the carrier; _functor_name_py/_arity_py
                      + C _functor_name/_arity: str = name/0, carrier = '.'/2 or '[]'/0; _cell_functor never
                      reads the carrier as a cell; C do_unify hands a Seg* __unify__ the CARRIER (it unwrapped
                      it, and the hook then saw an atom); Seg* __unify__/__eq__ flag-based (other_text), a text
                      Seg walking to '' is nil, a SegString slice is the carrier; DictTerm/SetTerm/mapping_of
                      fold chars('') onto the nil key; reify: str -> Atom, carrier -> the string, $intern_atom
                      dict keys and lambda params stay names; const-set: the spellings set IS the atoms, emitted
                      guard `elem.__class__ is $str`, lookup `elem in set` (the old slot-0 read keyed a str atom
                      by its FIRST CHAR); exact_arith._operand refuses a str (compiled eval_(yes * 2) answered
                      'yesyes'); _dims_from_term; head_key(str) = name/0; prolog_reader PAtom -> str, PString
                      -> carrier; chars.py F075 SegString-as-char arms deleted
    task 8c 2a476126  the gate's NEW 20 (all outside the survey population): reflection._raw_node reads a node
                      field declared `str` (a lambda PARAM name) raw; 5 pins
    task 9a 0c9b16f1  roborev round-1 fixes (7 findings, each verified first): must_be(callable, atom) had
                      drifted from callable_/1 (HIGH); call/N built the RESERVED 1-tuple as the culprit of a
                      0-arity control-construct goal so the diagnostic could not render; the 0-arity-
                      predicate-as-value arm reads the existing _in_callable_position flag (no id() set);
                      no class is a term to ANY functor/arity twin (C + Python, all four answer None);
                      stale docstrings; the two imports this branch orphaned; one spelling of CHARS_TAG
    task 9b eaea192d  roborev round-2 fixes (6 findings): solve/1 refuses ','/0 like call/N; _str_typed_fields
                      (Optional[str] name fields reify raw, memoised); precedence/arity hoist; 3 docstrings;
                      head_key's class arm kept WITH its reason (the head channel names a predicate)
    task 9c 1c578685  roborev round-3 fixes (4 Low): the name-field rule accepts Union origins only (list[str]
                      stays out, pinned), is_atom_value docstring, helper placement + import order
    task 9  (this handoff) final gate + announcement

## Instruments and their controls (all observed; every extraction printed its size)

* Clean-base A/B: base = stage-1 freeze `73c86686` in a detached worktree with its OWN build + the stray
  `clausal/logic/_trampoline` .so mirrored (13 extensions) = 144 failed / 16665 passed = the canonical baseline
  exactly; candidate = a DETACHED worktree at the tip with the same 13 extensions copied, positive controls
  (`mint('x')` is a str, `unify(SegString(['ab']), chars('ab'))` True and against the bare `'ab'` False,
  `_functor_name(chars('ab')) == '.'`, `is_cell(('x',))` refused) before the run.
  - at 30b9efc0: 164 failed / 16658 passed, NEW 20 / GONE 0, skip sets identical (52) -> task 8c
  - at 2a476126: 144 failed / 16678 passed, NEW 0 / GONE 0, skip sets identical (52)
  - at 0c9b16f1 (after the round-1 fixes): 144 failed / 16682 passed, NEW 0 / GONE 0, skip sets identical (52);
    the one collection error (`tests/test_clportools.py`, ortools) is in both arms
  - at eaea192d (the 9b tip): 144 failed / 16684 passed, NEW 0 / GONE 0, skip sets identical (52)
  - at 1c578685 (the 9c tip, FINAL): 144 failed / 16685 passed, NEW 0 / GONE 0, skip sets identical (52)
* Survey population (`snap_s2.log` at acbd55f7: 856 failed / 712 NEW over 106 files) -> the agents' brief; the
  population + the red files named in their reports = 108 files, 5109 passed / 0 failed at 2a476126.
* Spelling parity (`tests/test_chars_carrier.py`, 40 goals, carrier vs char list) green; stage-2 pins in
  `tests/test_atoms_as_str_stage2.py` (tasks 1–6) green.
* Codegen goldens (`tests/golden/*.codegen.txt`): regenerated ONLY after the diff was normalised and read
  (residual 0 in all four) — the index strategy is intact.
* roborev review of the branch against `73c86686` (13 commits): 7 findings (1 High, 3 Medium, 3 Low), all
  verified against the code before acting and fixed in 9a; the findings' rows are pinned in
  `tests/test_atoms_as_str_stage2.py::TestReviewRound1` and the two funnel tests. A second review of the
  post-review commits (8c, 9a): 6 findings (2 Medium: solve/1 lacked the control-construct refusal call/N
  has for a str goal; the reflection name-field rule missed `Optional[str]`; 4 Low), all verified and fixed
  in 9b with pins. A third pass (9b + handoff): 4 Low, fixed in 9c with pins. Review is closed on the branch.

## Rulings applied this session (each is a test that says so)

* G6: a predicate name in dict-key position is the ATOM of that spelling; `PredicateAsTermError` is retired
  (`tests/test_query_atom_dict_key_identity.py::test_predicate_in_key_position_is_the_atom`).
* The class-route acceptance tests (`tests/test_global_atoms_default.py`) pin "no class is an atom".
* `is_cell(('atom',))` pins the RESERVED refusal (`tests/test_cells.py`).
* A bad body arithmetic in term expansion is the engine's `type_error(evaluable, nil)` (a `LogicException`),
  not the raw Python `TypeError` that `str + int` used to leak (`tests/test_term_expansion.py`).
* `head_key("x")` is `("x", 0)`; the non-term that raises is a float (`tests/test_database.py`).
* The reflection vocabulary: an atom is `Atom(name)`, a string is the plain `str` (rendered double-quoted), a
  node field declared `str` is a name (`tests/test_reflection.py`, `tests/rewrite/test_reflection_contract.py`).

## Open / parked

* The functor/arity twins' zero-field-class arms are RETIRED (9a): `functor/3`, `arg/3`, `=..` on a live
  0-arity predicate CLASS fail (no class is a term). Nothing in the suite depended on it.
* Unused imports that predate this branch (arg_index `StarUnpack`/`_name`/`_call`/`_assign`, solve `DONE`,
  python_terms `dataclasses`, py/re `StepGenerator`, higher_order `is_var`): left, out of scope.
* The 0-arity-predicate-as-value ORDER caveat: a reference before the first clause still loads the class.
* `phrase/2,3`, `same_length/2`, `write_term/2` options still go through `normalize_seg_input` (they read lists
  and re-wrap text with `_text_out`): a bare str ATOM in list position is read as text there. Not a regression
  (the base has it); a stage-2 tightening for later.
* `const_set`: the carrier is now an ELIGIBLE mixed-list element (hashable, equal only to an equal carrier;
  a char-list operand takes the scan). Measured only by the tests.
* The six pin agents ran on the session model (no `model:` override) — ~224k tokens each. Pass
  `model: sonnet` for mechanical rewrites.
* Stage 1 items unchanged: Q3 writeq recommendation; STR_SITES.tsv disposition; the C twin
  `_head_list_unify_input` note.

## Peers / landing

* harness-batch-lane: stage 2 is a RE-BASELINE (spec §5 step 6), announced beside the stage-1 freeze file in
  the lanes' shared announcement directory as `ATOMS-AS-STR-STAGE2-BUILT-2026-09-18.md`; its sweep runs AFTER
  stage 1 lands.
* iso-export-lane: G3 on the frozen stage-1 sha `73c86686` still gates the stage-1 landing window; the
  exporter goldens are unchanged under stage 2 (task 7).
* NEXT for the engine lane: nothing is open on the branch. Landing waits on stage 1 (iso-export-lane's G3 on
  `73c86686`) and is the operator's call; stage 2 then lands as its own sha and re-baseline.
* corpus-lane: the silent-unmatch grep from the stage-1 announcement covers stage 2 too, plus: a `++` escape
  that yields Python strs now yields ATOMS (`++sorted(["a","b"])` is `[a, b]`), so a fixture that compared
  such a result against `"..."` strings under chars mode must compare against atoms or take the string side
  through `atom_chars`.
