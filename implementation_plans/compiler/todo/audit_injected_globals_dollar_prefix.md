# Audit injected compiler globals — `$`-prefix the unreachables

## Precedent

Commit `be6fd06` renamed the generated-code alias for the `DONE`
sentinel from `_DONE` to `$DONE` and updated the matching AST
construction + globals injection sites.  Rationale: Clausal allows
Python code to be injected into the compiler's AST-emission path
(user-authored term-to-AST transforms can produce arbitrary
`ast.Name(id=...)` nodes).  Any name that the compiler injects into
a compiled predicate's globals dict is therefore silently reachable
from that user code — an implicit-namespace-pollution hazard.

`$` is rejected by Python's lexer, so a user's parseable source can
never produce `Name(id='$X')`.  But CPython's `LOAD_GLOBAL` only
cares about the string value in `co_names`, not identifier syntax,
so `Name(id='$X')` + `globals_={'$X': X}` works end-to-end.  This
makes injected helpers unreachable from any parseable user code
while leaving the normal hand-written API (`from module import X`)
completely unchanged.

## Scope — every other injection site

`clausal/logic/compiler/predicate.py:605-703` is the main injection
site (`base_globals` dict assembled per compiled predicate).  Also
check:

- `predicate.py:696-698` — destructive-reuse dispatch names
  (`_dr_append__3`, `_dr_dict_put__4`, `_dr_set_union__3`).
- Any other `globals_=` or `base_globals[...] = ...` write reachable
  from `compile_predicate_trampoline` / `compile_predicate_shallow` /
  their helpers.

### Categorisation of current injections

Three dispositions for each name:

**A. Rename to `$`-prefix** — internal compiler helpers with no
legitimate user-code reference:

- Sentinels: `_TABLING_SUSPEND` → `$TABLING_SUSPEND` (matches
  `$DONE`).
- Constraint helpers: `_dif`, `_reify_eq`, `_structural_eq`,
  `_structural_neq`, `_reify_fd`, `_fd_eq`/`_fd_ne`/`_fd_lt`/
  `_fd_le`/`_fd_gt`/`_fd_ge`.
- Head-pattern lowering: `_head_list_unify_input`,
  `_head_list_unify_output`, `_head_multi_star_error`,
  `_body_star_unify`, `_body_multi_star_unify`, `_build_star_list`,
  `_build_multi_star_list`.
- Runtime glue: `_tramp_call`, `_deref_walk`, `_set_of_dedup`,
  `_LogicException`, `_python_error_term`, `_in_iter`, `_type_error`,
  `_get_attr`, `_put_attr`, `_seglist_unify_gen`, `_Fraction`.
- Freeze/when installers: `_install_when_ground`,
  `_install_when_disjunction`, `_install_when_condition`.
- Tabled-NAF: `_naf_tabled`, `_table_store`.
- Destructive-reuse dispatch: `_dr_append__3`, `_dr_dict_put__4`,
  `_dr_set_union__3`.
- Dispatch-cache keys (locked predicates, `_disp_` prefix).

**B. Keep as bare names** — legitimately user-addressable:

- `Compound`, `KWTerm`, `DictTerm`, `SetTerm`, `Var`, `SegList`,
  `ConcreteSeg`, `VarSeg` — term-constructor classes that user
  code may reference directly when authoring Python-side term
  builders or when inspecting compiled output.
- `unify`, `deref`, `is_var` — runtime primitives that hand-written
  builtin predicates call directly.
- `StepGenerator` — used by hand-written builtins to construct
  child generators.
- Builtin predicate classes (`_BUILTIN_CLASSES` contents:
  `Member`, etc.) — referenceable by name when passed as goal
  arguments to meta-predicates.  Renaming breaks `maplist(Member,
  ...)`-style constructs.

**C. Audit case-by-case** — names that *look* internal but may be
referenced by user-authored meta-calls or introspection:

- Collected `_head_types`, `_py_thunks` from
  `_collect_globals_info` — contents depend on the clauses.  Check
  whether names emerge from `.clausal` source syntactically (if so,
  they must remain valid identifiers).
- `_inject_resolved_targets` output — resolved call targets are
  keyed by `functor` names from user source.  Must stay bare.

## Sequencing

Single mechanical commit, same shape as `be6fd06`:

1. Rename `"_X": X` → `"$X": X` in the injection dict for every
   group-A entry.
2. Rename `_name("_X")` → `_name("$X")` at every AST-construction
   site that references one of the renamed names.  Grep for
   `_name("_` in `clausal/logic/compiler/` to enumerate.
3. Update any invariant assertions that match against the AST
   literal string (see `invariants.py:252` as precedent).
4. Do NOT touch `from ... import _X` in hand-written modules — those
   are the legitimate public/internal API and stay as plain names.
5. Do NOT touch prose / docstrings / READMEs — they describe the
   semantic name, which remains the module-level `X` (not the
   generated-code alias).

## Cost and risk

- Pure mechanical rename inside the compiler subtree plus a handful
  of AST-construction sites.  Behaviour-preserving.
- Validation: full test suite green (baseline 11927 passed / 32
  pre-existing doc failures as of commit `be6fd06`).
- Each group-A name is localised — renaming one name at a time
  keeps bisection surface small if anything regresses.

## Why this is worth doing

Currently every compiled predicate exposes ~40 internal helper
names in its globals dict.  Any clausal-authored AST transform that
produces `Name(id='_dif')` (accidentally or maliciously) silently
binds to the compiler's internal `_dif_fn`.  Renaming the
injection keys to `$`-prefix removes that entire attack surface at
the cost of a mechanical refactor.

Analogous to Python's name-mangling for `__x` class attributes —
except using a character the lexer rejects outright rather than
relying on convention.

## Open questions

- Is there a reason the current code uses `_` prefix rather than
  `$`?  Presumably it predates the insight that `$` bytecode lookup
  works.  Check commit history for any documented rationale before
  assuming this is a safe rename.
- `_dr_append__3` and friends — these names are synthesised by the
  destructive-reuse pass and referenced in emitted code.  Confirm
  the pass's emission site also updates to `$dr_append__3` in
  lockstep.
- Locked-dispatch cache keys (`_disp_` prefix) — these are
  constructed via `_disp_key(name, arity)`.  Changing the prefix
  means updating the `_DISP_PREFIX` constant and the key-construction
  helper, plus any invariant check that greps keys by prefix.
