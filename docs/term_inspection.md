# Term Inspection

Term inspection predicates let you decompose, construct, copy, and analyze the
structure of terms at runtime. They are the foundation for meta-programming —
writing predicates that operate on other predicates.

---

## Quick Example

```clausal
Test("decompose atom") <- (
    Functor("hello", NAME_, ARITY_),
    NAME_ == "hello",
    ARITY_ == 0
)

Test("unpack atom") <- Unpack("hello", ["hello"])
```

---

## Decomposition & Construction

### Functor/3

`Functor(Term, Name, Arity)` — bidirectional. Decompose a term into its functor
name and arity, or construct a term from a name and arity.

**Decompose mode** (Term bound):

```clausal
Test("atom") <- Functor("hello", "hello", 0)
```

**Decompose a compound term** — define the predicate first so it is a known term:

```clausal
point(1, 2, 3),

Test("decompose compound") <- (
    Functor(point(1, 2, 3), NAME_, ARITY_),
    NAME_ == "point",
    ARITY_ == 3
)
```

**Construct mode** (Term unbound, Name + Arity bound):

```clausal
Test("construct") <- (
    Functor(TERM_, "pair", 2),
    Functor(TERM_, "pair", 2)
)
```

### Arg/3

`Arg(N, Term, Value)` — access the N-th argument of a compound term (1-based).
Define the predicate first so its terms are recognized:

```clausal
point(10, 20, 30),

Test("first arg") <- Arg(1, point(10, 20, 30), 10)
Test("second arg") <- Arg(2, point(10, 20, 30), 20)
Test("third arg") <- Arg(3, point(10, 20, 30), 30)
```

Fails if N is out of range or Term is atomic.

### Unpack/2

`Unpack(Term, List)` — the "univ" operator (`=..` in Prolog). Converts between a
term and a list `[Functor | Args]`.

**Decompose mode**:

```clausal
foo(1, 2, 3),

Test("unpack") <- Unpack(foo(1, 2, 3), ["foo", 1, 2, 3])
Test("atom") <- Unpack("hello", ["hello"])
```

**Construct mode**:

```clausal
Test("construct") <- (
    Unpack(TERM_, ["point", 10, 20]),
    Arg(1, TERM_, 10),
    Arg(2, TERM_, 20)
)
```

---

## Copying

### CopyTerm/2

`CopyTerm(Original, Copy)` — create a deep copy of a term with all unbound
variables replaced by fresh variables. Shared variables remain shared in the
copy.

```clausal
Test("copy list") <- (
    CopyTerm([1, X_, 3], COPY_),
    Length(COPY_, 3)
)
```

---

## Variable Analysis

### TermVariables/2

`TermVariables(Term, Vars)` — collect all unbound variables in a term into a
list, in left-to-right order, with duplicates removed (by identity).

```clausal
Test("collect vars") <- (
    TermVariables([X_, 1, Y_, Z_], VARS_),
    Length(VARS_, 3)
)

Test("ground term") <- TermVariables([1, 2, 3], [])
```

### NumberVars/3

`NumberVars(Term, Start, End)` — bind each unbound variable to a
`$VAR(N)` atom, numbered sequentially from `Start`. `End` is unified with the
next available number.

```clausal
Test("number vars") <- (
    NumberVars([X_, Y_, Z_], 0, END_),
    END_ == 3
)
```

This is useful for displaying terms with readable variable names.

---

## Patterns & Recipes

### Generic term transformer

Transform all arguments of any term by applying a goal:

```clausal
# skip
point(1, 2, 3),

map_args(GOAL_, TERM_, RESULT_) <- (
    Unpack(TERM_, [FUNCTOR_, *ARGS_]),
    MapList(GOAL_, ARGS_, NEW_ARGS_),
    Unpack(RESULT_, [FUNCTOR_, *NEW_ARGS_])
)
```

### Count variables in a term

```clausal
var_count(TERM_, N_) <- (TermVariables(TERM_, VARS_), Length(VARS_, N_))

Test("count") <- var_count([X_, 1, Y_, Z_], 3)
```

### Clone a predicate call with different arguments

```clausal
# skip
edge("a", "b"),

rewrite_first_arg(TERM_, NEW_ARG_, RESULT_) <- (
    Unpack(TERM_, [F_, _, *REST_]),
    Unpack(RESULT_, [F_, NEW_ARG_, *REST_])
)
```

---

## Gotchas

- **`Arg` is 1-based** — `Arg(1, ...)` is the first argument, not `Arg(0, ...)`.
- **`CopyTerm` preserves sharing** — if the same variable appears twice in the
  original, the copy will have the same fresh variable in both positions.
- **`NumberVars` mutates the term** — it binds variables in place. Use
  `CopyTerm` first if you need the original term unchanged.
- **`Unpack` constructs `Compound` terms** — when building from a list, the
  result is a generic `Compound`, not a known predicate class.

---

*See also: [Type Checking](type_checking.md) — test term types without
decomposition, [Meta-Predicates](meta_predicates.md) — FindAll, BagOf for
collecting solutions, [Predicates](predicates.md) — defining predicate
structures.*
