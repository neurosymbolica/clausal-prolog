# Term Inspection

Term inspection predicates let you decompose, construct, copy, and analyze the
structure of terms at runtime. They are the foundation for meta-programming —
writing predicates that operate on other predicates.

!!! note "Clausal Prolog and the seam"

    Examples on this page are [Clausal Prolog](clausal_prolog.md)
    (`.clausal`, ISO Prolog syntax). The [seam](syntax.md), Clausal's
    Python-syntax surface, has the same builtins; where its spelling
    differs (field-name declarations, dict literals), the page says so.

---

## Quick Example

```clausal
% The name position speaks ATOMS.
test("decompose atom") :-
    functor(hello, Name, Arity),
    Name == hello,
    atom(Name),
    Arity == 0.

test("unpack atom") :-
    unpack(hello, [hello]).
```

---

## Decomposition & Construction

### functor/3

`functor(Term, Name, Arity)` — bidirectional. Decompose a term into its functor
name and arity, or construct a term from a name and arity.

**Decompose mode** (Term bound):

```clausal
test("atom") :-
    functor(hello, hello, 0).
```

**Decompose a compound term**:

```clausal
test("decompose compound") :-
    functor(point(1, 2, 3), Name, Arity),
    Name == point,
    Arity == 3.
```

**Construct mode** (Term unbound, Name + Arity bound). The result is a
**cell** — the same term a source-written data functor `pair(A, B)` compiles
to (a plain tuple), with fresh variables as its arguments:

```clausal
test("construct") :-
    functor(Term, pair, 2),
    Term = pair(A, B),
    var(A),
    var(B).
```

### arg/3

`arg(N, Term, Value)` — access the N-th argument of a compound term (1-based):

```clausal
test("first arg") :-
    arg(1, point(10, 20, 30), 10).

test("second arg") :-
    arg(2, point(10, 20, 30), 20).

test("third arg") :-
    arg(3, point(10, 20, 30), 30).

test("out of range fails") :-
    \+ arg(4, point(10, 20, 30), _).

test("atomic term") :-
    catch(arg(1, abc, _), error(E, _), true),
    E == type_error(compound, abc).
```

Fails if N is out of range. An unbound `N` or `Term` is `instantiation_error`,
an atomic `Term` `type_error(compound, Term)` (ISO 8.5.2.3, as Scryer does;
an unbound `N` used to enumerate the `(N, Value)` pairs).

### unpack/2

`unpack(Term, List)` — the "univ" relation, ISO's `=..` (which Clausal
Prolog also spells `Term =.. List`). Converts between a term and a list
`[Functor|Args]`.

**Decompose mode**:

```clausal
test("unpack") :-
    unpack(foo(1, 2, 3), [foo, 1, 2, 3]).

test("atom") :-
    unpack(hello, [hello]).

test("univ") :-
    foo(1, 2, 3) =.. [foo, 1, 2, 3].
```

**Construct mode**:

```clausal
point(1, 2).

test("construct") :-
    unpack(Term, [point, 10, 20]),
    % the same cell a source-written point(10, 20) is
    Term == point(10, 20),
    arg(1, Term, 10),
    arg(2, Term, 20).
```

A compound term is always a **cell**, a plain tuple `(functor, *args)`: the
term `unpack/2` or `functor/3` builds, a data functor written in source, and
a predicate's name used as a term (`point(10, 20)` above, where `point/2` is
a fact) are the same cell and unify. There is no separate class of
"predicate instance".

From Python, read a cell with `clausal.cell_functor` and `clausal.cell_args`
(and build one with `clausal.make_cell`). In a `.seam` file, the
goal-position seam hands the cell back as it is (seam syntax):

```seam
from clausal import cell_functor, cell_args

point(1, 2),

def show():
    for T in --unpack(T, ['point', 10, 20]):
        print(T)                                  # ('point', 10, 20)
        print(cell_functor(T), cell_args(T))      # point (10, 20)
```

See [Python integration](python_integration.md) for the seam.

---

## Copying

### copy_term/2

`copy_term(Original, Copy)` — create a deep copy of a term with all unbound
variables replaced by fresh variables. Shared variables remain shared in the
copy.

```clausal
% _X stands for "some unbound variable"; copy_term/2 gives the copy a
% fresh one in its place.
test("copy list") :-
    copy_term([1, _X, 3], Copy),
    Copy = [1, V, 3],
    var(V).

test("sharing is preserved") :-
    copy_term(f(X, Y, X), Copy),
    Copy = f(A, B, C),
    A == C,
    A \== B,
    A \== X,
    var(Y).
```

---

## Variable Analysis

### term_variables/2

`term_variables(Term, Vars)` — collect all unbound variables in a term into a
list, in left-to-right order, with duplicates removed (by identity).

```clausal
test("collect vars") :-
    term_variables([X, 1, Y, Z, X], Vars),
    Vars == [X, Y, Z].

test("ground term") :-
    term_variables([1, 2, 3], []).
```

### numbervars/3

`numbervars(Term, Start, End)` — bind each unbound variable to the cell
`'$VAR'(N)`, numbered sequentially from `Start`. `End` is unified with the
next available number.

```clausal
test("number vars") :-
    numbervars([X, Y, Z], 0, End),
    End == 3,
    X == '$VAR'(0),
    Z == '$VAR'(2),
    Y \== Z.
```

This is useful for displaying terms with readable variable names.

### gensym/2

`gensym(Prefix, Atom)` — generate a unique atom by appending a monotonically
increasing counter to `Prefix`.

```text
--8<-- "tests/fixtures/docs/term_inspection_sigs.txt:gensym_example"
```

The counter is **impure** — it does not reset on backtracking. This matches
Prolog's `gensym/2` semantics and is useful for generating fresh names in
meta-programming or code generation.

---

## Fields by Name

A term's fields can also be addressed by NAME. The names come from the
functor's **declaration**, in Clausal Prolog a `constructors/1` directive
(the seam declares them with `-private([point(x, y, z)])`). A declared
constructor is data: `point/3` is then built as a term and never defined
by clauses.

```clausal
--8<-- "tests/fixtures/docs/keyword_preds_examples.clausal:declaration"
```

`vary/3` copies a term with some fields replaced, `unbound_keys/2` lists the
fields that are still unbound, and `signature/3` reflects the declared field
names of a functor.

!!! note "The keyword CONSTRUCTION spelling was retired on 2026-09-19"

    A term used to be writable as `point(x=1, y=2, z=3)`, and the first clause
    written that way was what named the fields. A term is built positionally
    now, and a keyword argument in a term or a clause head is a load-time
    error. The spelling had no ISO Prolog reading, and it made a functor's
    field names depend on which of its clauses came first.

    Two keyword spellings are unaffected: a `-directive`'s options
    (`-specialize(solve, p, alias=q)`) and an EDCG hidden argument
    (`p(L, _edcg_counter_in=0)`).

    The `KWTerm` class and the `extend/3` builtin (which grew a term by new
    keyword fields) went with it: a compound term is a plain cell, and its
    fields are fixed by its declaration.

```clausal
--8<-- "tests/fixtures/docs/keyword_preds_examples.clausal:quick_example"
```

A term is never padded: a construction with fewer arguments than the declared
functor has fields is not filled with fresh logic variables. (The seam
refuses one; in Clausal Prolog `point(1)` is simply another functor,
`point/1`, with no field names.) A field you want to leave open is written
as a variable -- which is what a partial term is:

```clausal
--8<-- "tests/fixtures/docs/keyword_preds_examples.clausal:partial_terms"
```

### vary/3

`vary(Overrides, Term, NewTerm)` — copy a term, replacing specified fields with
new values. `Overrides` is a dict mapping field names to new values; Clausal
Prolog builds it with `dict_pairs/2` (see [Dicts & Sets](dicts_sets.md)),
the seam writes a dict literal, `{"x": 100}`.

```clausal
--8<-- "tests/fixtures/docs/keyword_preds_examples.clausal:vary_examples"
```

Works for declared functor cells and term (dataclass) instances.

### unbound_keys/2

`unbound_keys(Term, Keys)` — list the field names that are still unbound
(contain logic variables).

```clausal
--8<-- "tests/fixtures/docs/keyword_preds_examples.clausal:unbound_keys_examples"
```

### signature/3

`signature(FunctorName, Arity, Names)` — reflect the registered signature of a
predicate. Given a functor name and arity, unifies `Names` with the tuple of
field names.

```clausal
--8<-- "tests/fixtures/docs/keyword_preds_examples.clausal:signature_example"
```

This is a database-dependent operation — the functor must have been declared
(with its field names) before `signature` is called.

### Recipes: fields by name

Default values via `vary`:

```clausal
--8<-- "tests/fixtures/docs/keyword_preds_examples.clausal:default_values"
```

Inspect which fields need filling:

```clausal
--8<-- "tests/fixtures/docs/keyword_preds_examples.clausal:inspect_fields"
```

Reflect on predicate structure:

```clausal
--8<-- "tests/fixtures/docs/keyword_preds_examples.clausal:reflect_predicate"
```

### Gotchas: fields by name

- **A term cannot grow new fields** — a functor's fields are the ones it is
  declared with. Use `vary` to change existing fields.
- **`signature` requires the functor to be declared** — if you call it
  before the declaration is loaded (e.g., in a different module that hasn't
  been imported), it will fail.
- **Field names are atoms** — `unbound_keys` and `signature` answer atoms
  (`[x, y, z]`). An override dict's keys may be atoms (`dict_pairs(D,
  [x-10])`) or strings (`dict_pairs(D, ["x"-10])`).
- **Field names come from the declaration** — `:- constructors([point(x, y,
  z)]).` in Clausal Prolog. A functor without one has no field names:
  `signature/3` fails and `unbound_keys/2` answers `[]`, even for a
  predicate defined by clauses. (In the seam the names come from
  `-private([point(x, y, z)])` or the `-module` export list, and an
  undeclared predicate's fields are `arg_0`, `arg_1`, … , which `vary` and
  `unbound_keys` will happily use but nobody wants to read.)

---

## Patterns & Recipes

### Generic term transformer

Transform all arguments of any term by applying a goal (using [maplist](higher_order.md)):

```clausal
--8<-- "tests/fixtures/docs/term_inspection_examples.clausal:map_args_recipe"
```

### Count variables in a term

```clausal
var_count(Term, N) :-
    term_variables(Term, Vars),
    length(Vars, N).

% _X, _Y, _Z each stand for "some unbound variable" fed into var_count/2.
test("count") :-
    var_count([_X, 1, _Y, _Z], 3).
```

### Clone a predicate call with different arguments

```clausal
--8<-- "tests/fixtures/docs/term_inspection_examples.clausal:rewrite_arg_recipe"
```

---

## Gotchas

- **`arg` is 1-based** — `arg(1, ...)` is the first argument, not `arg(0, ...)`.
- **`copy_term` preserves sharing** — if the same variable appears twice in the
  original, the copy will have the same fresh variable in both positions.
- **`numbervars` mutates the term** — it binds variables in place. Use
  `copy_term` first if you need the original term unchanged.
- **`unpack` constructs CELLS** — when building from a list, the result is a
  plain tuple `('point', 10, 20)`. Python code
  reads it with `clausal.cell_functor` / `clausal.cell_args`. `functor/3` in construct
  mode does the same.
- **The name position is an atom** — `functor/3` and `unpack/2` hand back an
  atom for the name and require one to build with; a string there raises
  `type_error(atom, …)` (or `type_error(atomic, …)` for the 1-element case).
  A list and a string both decompose as the `'.'/2` structure they denote;
  see [`functor/3`](builtins.md#functor3) for the full table.

---

*See also: [Type Checking](type_checking.md) — test term types without
decomposition, [Meta-Predicates](meta_predicates.md) — findall, bagof for
collecting solutions, [Predicates](predicates.md) — defining predicate
structures, [Dicts & Sets](dicts_sets.md) — DictTerm for general key-value
data.*
