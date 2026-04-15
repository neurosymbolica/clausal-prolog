# Internal-name audit — where compiler/runtime names can leak into user code

**Status:** not started.

**Motivation:** Slice G added a `position` attribute to `Compound`,
`KWTerm`, `DictTerm`, `SetTerm`, `PyThunk` — source-location metadata
for tracebacks.  On `KWTerm` the `position` keyword is consumed by the
constructor as metadata, not stored as a user field.  That's one
specific collision we already reasoned about; the broader question is
whether there are other internal names that silently overlap with
names a user might reasonably write in `.clausal` code or in Python
that constructs terms directly.

This audit surveys the collision surfaces, decides per site whether
the risk is real, and proposes mitigations.  Outputs may include:

- A reserved-names doc block in `clausal/terms.py` for each class.
- A constructor-time error for names the templater definitely never
  emits but users might try (e.g. `position` on KWTerm).
- A user-facing predicate (`term_position/2` or similar) so
  self-hosted compiler code reads the metadata through a stable API
  rather than poking `.position` directly.

---

## 1. Known collision surfaces

### 1.1 `terms.Compound`
- Fields: `functor`, `args`, `position` (new).
- Risk: a user `.clausal` term `foo(functor=X, ...)` is rewritten by
  the templater to a bespoke dataclass `foo`, not to a `Compound`, so
  no collision today.  But Python code that constructs
  `Compound(functor=..., args=..., functor=user_value, ...)` isn't a
  thing — functor and args are positional.  Real risk: user writes a
  dataclass-like term and expects `.functor` to mean their field.
- Mitigation: `Compound` is for runtime-constructed/unknown-functor
  terms only; the user-visible shape for known functors is the
  generated dataclass.  Document reserved names on `Compound`.

### 1.2 `terms.KWTerm`
- Slots: `_functor`, `_fields`, `position` (new).
- User-level fields: arbitrary keyword args stored in `_fields`.
- Risk: `position` is consumed by the constructor (Slice G) — users
  who construct `KWTerm('event', position=...)` intending a
  coordinate field silently lose it to metadata.  `functor` /
  `_functor` / `_fields` would collide with existing slots but are
  blocked because they aren't in `_fields`.
- Mitigation (done): docstring warns about `position`.  Consider
  adding a constructor-time check that rejects any user field starting
  with `_` or matching the reserved name `position` with a clear
  error.

### 1.3 `terms.DictTerm` / `terms.SetTerm`
- Slots: `_data` / `_elements`, `position` (new).
- Risk low: these are container terms whose user-level content is
  data (keys/values, elements) — not named fields.  The `position`
  kwarg is keyword-only (`*, position=None`), so runtime constructions
  with `DictTerm({...}, position=X)` are unambiguous.

### 1.4 `terms.PyThunk`
- Slots: `fn`, `var_objects`, `position` (new).
- Risk low: PyThunks are compiler-generated from `++(...)` escapes
  and f-strings in `.clausal`.  No user-facing attribute API.

### 1.5 Module namespaces — `$module`, `$ast`, `__dict__["$module"]`
- `_load_module` stashes a `LogicModule` on `mod.__dict__["$module"]`.
- Risk: a user module that defines its own `$module` top-level name
  would collide.  The `$`-prefix is not valid Python syntax so this
  only surfaces through `.clausal` escape tricks, but it's worth
  documenting.

### 1.6 Templater-reserved identifiers
- Grep: `trail`, `unify`, `deref`, `_table_store`, `_naf_tabled`,
  `_tramp_parent`, `this_generator`, `_get_dispatch`, `_tro`,
  `_tro_state`, `_found`, `_el`, `_m<N>`, `_t<N>`, `_ite_cond`,
  `_disp_*`, `_dr_*`, etc.
- Risk: these appear in compiler-emitted code.  A user predicate with
  a colliding name in scope might shadow a runtime helper.  Compiler
  emits them in compiled-function bodies where the user normally
  can't reach, but the `base_globals` dict is shared.
- Mitigation: compiler-emitted locals are reasonably hygienic (leading
  underscore, numeric suffix).  Worth a pass to confirm no bare names
  like `trail` or `unify` get emitted in user-reachable scope.

### 1.7 Dataclass-generated predicate field names
- When a `.clausal` clause head uses keyword args (e.g.
  `Factorial(N=0, RESULT=1)`), the templater generates a dataclass
  with those as fields.  `functor`, `args`, `position`,
  `_something` would collide with reserved dataclass internals or
  with Slice G metadata.
- Risk: user writes `Event(position=P, time=T)` as a predicate head.
  The generated dataclass would have a `position` field — but so does
  the base if they subclass.  Need to check whether generated
  dataclasses inherit from `Compound` / `Node` / similar.
- **Action item:** verify the generated dataclass base class and
  whether `position` in a user-authored clause head triggers a silent
  collision with inherited metadata.

---

## 2. Proposed user-facing predicates

For self-hosted compiler support (and general introspection):

```
term_position(Term, SourcePos)
  % Succeeds and binds SourcePos to pos(StartLine, StartCol, EndLine, EndCol)
  % when Term carries source-location metadata.  Fails otherwise.
  % Implementation: getattr(term, 'position', None); unify with a record.

term_functor(Term, Functor, Arity)
  % Already exists?  Check.  Reads .functor / arity from Compound or
  % generated dataclass.  Needed by any metacircular compiler.

term_args(Term, Args)
  % Returns the positional args as a list.
```

Decision point: expose raw 4-tuple or a dedicated record like

```python
@dataclass
class SourcePos:
    start_line: int
    start_col: int
    end_line: int
    end_col: int
```

— a record insulates user code from internal shape changes and reads
more naturally (`Pos.start_line` vs `Pos[0]`).  Cost: the record must
be constructed on every `term_position/2` call.  For a self-hosted
compiler the construction is negligible.

---

## 3. Audit method

1. Grep generated-code emitters (`_ast_helpers`, `control_constructs`,
   `goal_shallow`, `goal_trampoline`, `tro`, `head_match`) for every
   bare identifier used as `_name("foo")` or `ast.Name(id="foo")`.
2. For each, decide: is it a runtime helper (must be reserved) or a
   compiler-local (needs hygienic mangling)?  Document in a table.
3. Grep the `.clausal` templater for every kwarg it strips or
   reserves — these are names users can't use as term fields.
4. For each `terms.py` class with `__slots__`, enumerate the slots
   and compare with expected user-field names.
5. Write a "reserved names" docstring block on each affected class.

---

## 4. Not in scope

- Performance: this is a hygiene/naming audit, not a renaming sweep.
- The `position` field itself — Slice G landed it deliberately; this
  audit covers downstream collision risk, not Slice G's design.
- Full Prolog flag compatibility.  If we decide any reserved names
  need public-API equivalents (`term_position/2`), those become
  separate slices.
