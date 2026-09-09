# Term Inspection

Term inspection predicates let you decompose, construct, copy, and analyze the
structure of terms at runtime. They are the foundation for meta-programming —
writing predicates that operate on other predicates.

---

## Quick Example

```clausal
# The name position speaks ATOMS. `'hello'` is single-quoted, so it is the
# atom in every -double_quotes mode and needs no -private declaration.
test("decompose atom") <- (
    functor('hello', NAME_, ARITY_),
    NAME_ is 'hello',
    atom(NAME_),
    ARITY_ == 0
)

test("unpack atom") <- unpack('hello', ['hello'])
```

---

## Decomposition & Construction

### functor/3

`functor(Term, Name, Arity)` — bidirectional. Decompose a term into its functor
name and arity, or construct a term from a name and arity.

**Decompose mode** (Term bound):

```clausal
test("atom") <- functor('hello', 'hello', 0)
```

**Decompose a compound term** — define the predicate first so it is a known term:

```clausal
point(1, 2, 3),

test("decompose compound") <- (
    functor(point(1, 2, 3), NAME_, ARITY_),
    NAME_ is 'point',
    ARITY_ == 3
)
```

**Construct mode** (Term unbound, Name + Arity bound). The result is a
**cell** — the same term a source-written data functor `pair(A, B)` compiles
to, not a `Compound` object:

```clausal
-implicit_functors

test("construct") <- (
    functor(TERM_, 'pair', 2),
    TERM_ is pair(A_UNUSED, B_UNUSED)
)
```

### arg/3

`arg(N, Term, Value)` — access the N-th argument of a compound term (1-based).
Define the predicate first so its terms are recognized:

```clausal
point(10, 20, 30),

test("first arg") <- arg(1, point(10, 20, 30), 10)
test("second arg") <- arg(2, point(10, 20, 30), 20)
test("third arg") <- arg(3, point(10, 20, 30), 30)
```

Fails if N is out of range or Term is atomic. With `N` unbound, `arg/3`
enumerates the `(N, Value)` pairs in order on backtracking (SWI-style), and
is semidet when `Value` is given:

```clausal
kv(10, 20),

test("enumerates args") <- findall([N, V], arg(N, kv(10, 20), V), [[1, 10], [2, 20]])
test("finds the index") <- arg(N2, kv(10, 20), 20)
```

### unpack/2

`unpack(Term, List)` — the "univ" operator (`=..` in Prolog). Converts between a
term and a list `[functor | Args]`.

**Decompose mode**:

```clausal
foo(1, 2, 3),

test("unpack") <- unpack(foo(1, 2, 3), ['foo', 1, 2, 3])
test("atom") <- unpack('hello', ['hello'])
```

**Construct mode**:

```clausal
-implicit_functors

test("construct") <- (
    unpack(TERM_, ['point', 10, 20]),
    TERM_ is point(10, 20),   # the same cell a source-written point(10, 20) is
    arg(1, TERM_, 10),
    arg(2, TERM_, 20)
)
```

!!! note "Constructed terms are data functors, not predicates"
    The cell `("point", 10, 20)` unifies with a source-written `point(10, 20)`
    when `point` is a **data functor** (declared as data, or under
    `-implicit_functors`). If `point/2` is a declared *predicate*, a
    source-written `point(10, 20)` in a body is a predicate instance instead
    and does **not** unify with the constructed cell — build with `functor/3`
    or `unpack/2` on both sides, or compare with `functor/3` + `arg/3`.

---

## Copying

### copy_term/2

`copy_term(Original, Copy)` — create a deep copy of a term with all unbound
variables replaced by fresh variables. Shared variables remain shared in the
copy.

```clausal
-allow_singletons
# X_ stands for "some unbound variable" — its identity is never used
# again, only that copy_term/2 gives it a fresh one in COPY_.
test("copy list") <- (
    copy_term([1, X_, 3], COPY_),
    length(COPY_, 3)
)
```

---

## Variable Analysis

### term_variables/2

`term_variables(Term, Vars)` — collect all unbound variables in a term into a
list, in left-to-right order, with duplicates removed (by identity).

```clausal
-allow_singletons
# X_, Y_, Z_ each stand for "some unbound variable" — the point is that
# term_variables/2 collects three of them, not what they're named.
test("collect vars") <- (
    term_variables([X_, 1, Y_, Z_], VARS_),
    length(VARS_, 3)
)

test("ground term") <- term_variables([1, 2, 3], [])
```

### numbervars/3

`numbervars(Term, Start, End)` — bind each unbound variable to a
`$VAR(N)` atom, numbered sequentially from `Start`. `End` is unified with the
next available number.

```clausal
-allow_singletons
# X_, Y_, Z_ each stand for "some unbound variable" — numbervars/3 binds
# them to $VAR(0..2); their names are never referenced again.
test("number vars") <- (
    numbervars([X_, Y_, Z_], 0, END_),
    END_ == 3
)
```

This is useful for displaying terms with readable variable names.

### gensym/2

`gensym(Prefix, Atom)` — generate a unique atom by appending a monotonically
increasing counter to `Prefix`.

```clausal
--8<-- "tests/fixtures/docs/term_inspection_sigs.txt:gensym_example"
```

The counter is **impure** — it does not reset on backtracking. This matches
Prolog's `gensym/2` semantics and is useful for generating fresh names in
meta-programming or code generation.

---

## Patterns & Recipes

### Generic term transformer

Transform all arguments of any term by applying a goal (using [maplist](higher_order.md)):

```clausal
--8<-- "tests/fixtures/docs/term_inspection_sigs.txt:map_args_recipe"
```

### Count variables in a term

```clausal
-allow_singletons
var_count(TERM_, N_) <- (term_variables(TERM_, VARS_), length(VARS_, N_))

# X_, Y_, Z_ each stand for "some unbound variable" fed into var_count/2.
test("count") <- var_count([X_, 1, Y_, Z_], 3)
```

### Clone a predicate call with different arguments

```clausal
--8<-- "tests/fixtures/docs/term_inspection_sigs.txt:rewrite_arg_recipe"
```

---

## Gotchas

- **`arg` is 1-based** — `arg(1, ...)` is the first argument, not `arg(0, ...)`.
- **`copy_term` preserves sharing** — if the same variable appears twice in the
  original, the copy will have the same fresh variable in both positions.
- **`numbervars` mutates the term** — it binds variables in place. Use
  `copy_term` first if you need the original term unchanged.
- **`unpack` constructs CELLS** — when building from a list, the result is a
  plain tuple `("point", 10, 20)`, not a `Compound` object and not a known
  predicate class. Python code that tested `isinstance(x, Compound)` on a
  constructed term needs a cell-shape test instead. `functor/3` in construct
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
structures.*
