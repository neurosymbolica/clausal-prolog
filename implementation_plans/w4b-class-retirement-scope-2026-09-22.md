# W4b — retiring the `PredicateMeta` CLASS: a scope, measured 2026-09-22

**Status: SCOPE ONLY, plus a decomposition ruled by the operator.** Nothing
here is a plan of record except the split itself. The first sub-project
(W4b-1) has a design spec:
`docs/superpowers/specs/2026-09-22-w4b1-term-shape-rehome-design.md`.

Written by the session that picked up the W4a handoff. Every number below was
re-measured on `main` (tip `11623ba4`, W4a landed); none is carried over from
an earlier document.

## Where W4b starts from

W4a retired the INSTANCE path, Python and C. The class itself, its minters,
its registration in the C extension and the detached-row compatibility mode
all survive. The handoff treated "the class goes" as one unit. Measured, it
is not.

| | measured on main |
|---|---|
| `PredicateMeta` references, engine + tests | **842** (excl. `venv/`, `packages/`, `.claude/`) |
| `isinstance(…, PredicateMeta)` | **63** engine / **47** tests |
| `type(x) is PredicateMeta`, `__name__ == "PredicateMeta"` | **0** in-tree |
| `make_predicate(` call sites | **15** engine, 7 files (6 are real minters; the rest are prose) |
| `_fields` mentions | **289** engine |
| `_state_row()` callers | **27** (19 inside `predicate.py`) |
| `.detached` | **54** mentions, 6 engine files |
| C arms | 4 CLASS arms in `_variables.c` + `PredicateMeta_type` + `py_register_predicate_meta` |

The W4a spec's "293 references / 64 isinstance sites / 12 make_predicate
minters" was a floor: 293 counted one spelling. `_tabling_core.c` and
`_constraints_dif.c` mention `PredicateMeta` only in comments — they have no
arm to delete.

## The finding that forced the split: the class does TWO jobs

Reading the 63 engine `isinstance` sites, they ask two different questions.

* **The predicate HANDLE** — "is this module binding a declared predicate?"
  (`compiler_v2` ×13, `compiler/predicate.py` ×5, `head_match`, `globals_env`,
  `database_ops`, `term_expansion`, `seam`, `constants`, the two diagnostics
  modules). This one **has a ruled destination**: the module-qualified mangled
  atom plus the Database row (operator, 2026-09-22), and pieces 1–2 of it
  landed at `f73ccc65`.
* **The TERM SHAPE** — "what are this value's field names; is it zero-field,
  i.e. an atom?" (`terms_to_ast` ×6, `inspection` ×5, `arg_index` ×3,
  `predicate` ×4, `io` ×2, `type_checks`, `_lower_goalop_shared`, `terms`,
  `iso_l3`, `goal_expansion`, `testing` ×3). This one **has no ruling
  anywhere in the handoff**, and it is the half the 289 `_fields` reads hang
  off.

The ~30/~33 split above came from reading grep context, not from reading the
sites. It is an estimate and W4b-1's first task replaces it with a read.

## Three homes already hold a functor's field names

Not one, and their precedence has never been stated:

| home | populated by | scope |
|---|---|---|
| `cls._fields` | every minter | the class |
| `db._declared` — `declare_functor` / `declared_fields` / `declared_fields_by_name` / `declared_kind` | `compiler_v2._process_directives`, **2 call sites** | per-Database |
| `__clausal_functor_signatures__` (`cells.FUNCTOR_SIGNATURES_KEY`) | generated code in `term_rewriting`, copied by `-import_from` | per-module namespace |

`declare_functor` fires only for `-module`/`-private` entries carrying fields
and for `-import_from` carriers. **Six engine minters bypass it**:
`specialization.py` ×3 (`-specialize` aliases), `compiler_v2.py:1229`
(`-rename`), `term_expansion.py:314`, `builtins/_registry.py` ×2 (the builtin
registry), and `modules/py/datetime.py:204` (`_DatePattern`, a direct
`metaclass=` mint). Bare `make_predicate` out of tree has no db at all — that
is the detached-row population.

## W2 already did this once, and that is the pattern

`clausal/reflection.py` retired nine `make_predicate` classes into a
`_VOCAB_FIELDS` map plus generated constructor FUNCTIONS (`_vocab_ctor`),
with readers on `is_v` / `vfield` / `vkind` / `vfields` / `vitems`.
`clpb`'s `BoolEq` / `BoolImpl` went the same way. That is the term-shape
rehome, done for a fixed nine-name vocabulary with no Database. W4b-1 is the
same move for the open, per-module, db-backed population — which is why it
lands on the registry rather than on a module-level map.

## The decomposition (ruled by the operator, 2026-09-22)

### W4b-0 — the W4a inbox. No design; cleanup.

Recorded by W4a rather than smuggled into it:

* the five dead `_clausal_new` gates (`solve`, `inspection`, `terms_to_ast`,
  `arg_index`, and three C arms) plus the interned `str__clausal_new` in both
  extensions — each site says it is dead and points at the rule in `solve.py`;
* `c_term_field_names`, now a constant `NULL`, and its seven call sites;
* `reflection.py`'s vestigial `_clausal_head` call-node rewrite;
* a class BODY can still carry `_clausal_instances` as inert data — the
  tombstone is a metaclass data descriptor and a namespace key bypasses it.
  Refusing it needs a check in `PredicateMeta.__new__` against every retired
  name, a refusal W2 deliberately did not make. Nothing reads the flag.

The last item is a decision, not a cleanup: make it or record that it stays.

### W4b-1 — the term-shape rehome. Additive; the class stays. **SPEC WRITTEN.**

One accessor generalised from `term_field_names_of_class`; the six bypassing
minters register their declarations; the sites that ask about SHAPE migrate,
the sites that ask about IDENTITY are classified and left for W4b-2. Gated on
a completeness census, not on a green suite. Full design in the spec.

### W4b-2 — the handle flip. Migration-shaped, not a flag day.

A module attribute for a predicate becomes the mangled atom; the ~33
identity sites query `db.declared_kind(functor, arity)`, which already
exists. Pieces 1–2 landed (`f73ccc65`: the seam's functor slot accepts a
name bound to a mangled atom; `cells.qualify_mangled_goal` demangles at
`solve`, `call` by name, `call/N` and `_dispatch_at`). Piece 3 — the hosted
dotted-base seam — is fixed on `feat/seam-local-handle-2026-09-22` and not
landed. W1's ruling governs the shape: **a migration, not a flag day**, so
both bindings resolve for a window.

Open for W4b-2, not settled here:

* a `-hide` data atom is a mangled atom that is NOT a handle (landed note on
  `f73ccc65`). Mangling alone does not discriminate; the row does. State the
  discriminator once, in the spec, before any site moves.
* `todo/two-out-paths-disagree-about-atom-tagging-2026-09-22.md` is unruled
  and the parked `--handle(X)` form waits on it
  (`todo/seam-handle-form-for-hold-and-call-sites-parked-2026-09-22.md`).

### W4b-3 — the deletion.

`PredicateMeta`, `make_predicate`, `_state_row` and the detached-row
compatibility mode, the `db=None` compile default, the four C CLASS arms,
`PredicateMeta_type` and `py_register_predicate_meta`, and arm 2 of the
W4b-1 accessor. This is the landing that needs the `.so` built in a same-sha
worktree and rename-swapped under live importers, with a positive control
that OBSERVES the removal — W4a's hardest-won procedure, and W4a's note that
a parity probe passes equally on the old `.so` once no constructor is left
applies here too.

## What the downstream cliff is: zero, as far as any instrument can see

The three-lane census closed on 2026-09-22
(`todo/w4-alias-sweep-before-sizing-2026-09-22.md`): the 31 hold-and-call
sites migrated in six bodies to literal tuples under a dated exception, the
silently-dead assessment module repaired onto `reflection.vkind`, all three
broken export-lane gates closed. The re-run sweep reports **0 in every shape,
shape 4 included**.

Two qualifications that survive, and belong in any W4b sizing:

* shapes 4 and 5 (a predicate class held as a value; `__name__`/`__module__`
  read off one) are **not statically answerable**. The instrument would be a
  runtime hook, as for the division census. It has not been built.
* shape 3's figure is a LOWER BOUND with its rule stated and the remainder
  unexamined; the "6 files that import reflection" denominator was withdrawn
  because a callee receiving a cell as a parameter reads its fields with no
  import.

So W4b's remaining work is engine work. That is the one thing the handoff
and the measurement agree on.

## Risks, in the order they are likely to bite

1. **The accessor is wider than the `isinstance` it replaces.** A
   `@dataclass` class answers arm 1; `isinstance(x, PredicateMeta)` refuses
   it. Migrating a site blindly widens it, silently, in a way the house suite
   is poor at seeing. W4b-1 classifies each site by reading it — the
   discipline W4a's test triage used, for the same reason.
2. **A green suite cannot show the registry is a substitute**, because
   `cls._fields` will answer every call while the class exists. Hence W4b-1's
   completeness census with a planted positive; see the fail-open ledger.
3. **Three registries with no stated precedence** can already disagree;
   nothing checks. W4b-1 states the precedence and measures agreement.
4. **W4b-2's discriminator is not stated.** A mangled atom is not by itself a
   handle. Settle it before sites move, not during.
5. **W4b-3's `.so` swap** under live importers. The procedure and its traps
   are in the durable record; W4a hit two live importers holding the old
   inode at landing time.
