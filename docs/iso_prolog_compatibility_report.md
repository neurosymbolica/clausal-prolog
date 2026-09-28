# ISO Prolog Compatibility Report

*Measured on engine `main` at 9fe1ee48, 2026-09-28. Earlier editions (March
2026) recorded design decisions taken with Markus Triska; their outcome is
summarised under [History](#history).*

*For practical instructions on importing and running Prolog programs, see
[Importing Prolog Code](importing_prolog.md).*

Clausal is not an ISO Prolog system, and it does not try to become one by
adding cut. What it aims for is that every ISO builtin it **does** offer
behaves as ISO 13211-1 specifies, and, where ISO is silent, as
[Scryer Prolog](https://www.scryer.pl) does. SWI-Prolog is not a reference.
This page lists what already conforms, and the known gaps, honestly.

There are three ways to bring Prolog to Clausal:

| Route | Status in 1.0 | What you get |
|---|---|---|
| Write Clausal, using the **quoted ISO spellings** (`'is'(X, E)`, `'=='(A, B)`, `'@<'(A, B)`, `'='(A, B)`) where Clausal's bare operators mean something else | supported | ISO meaning for the builtins listed below; see [Operators](operators.md) |
| Import a `.pl` file | **experimental** ([Public API](public-api.md)) | a translation into Clausal syntax; no cut, no if-then-else, and the gaps in [Importing Prolog Code](importing_prolog.md#known-limitations) |
| Embed Scryer or Trealla (optional packages) | separate packages | a real ISO engine running alongside Clausal |

---

## Standing design decisions

These are settled and not gaps:

- **No cut, no if-then-else, no committed choice.** `!/0`, `(C -> T ; E)`,
  `(C -> T)` and `*->` do not exist. The `.pl` importer refuses them with a
  `SyntaxError` that lists the pure alternatives: `dif/2`, `once/1`,
  first-argument [indexing](indexing.md), [reified if-then-else](reified_ite.md).
- **Strings are lists of characters**, as in ISO with
  `double_quotes(chars)` and in Scryer and Trealla: `"…"` is a string by
  default, carried as `('$chars', text)` and unifying with the list of
  one-character atoms. `-double_quotes(atom)` is a temporary per-module
  setting. See [Atoms vs strings](syntax.md#atoms-vs-strings).
- **Atoms are a distinct type:** an atom IS the Python `str` (`'red'`); a
  compound term is a cell tuple (`('f', 1, 2)`); `('x',)` is reserved.
- **Negation** is `not Goal`, ISO `\+/1` exactly; for [tabled](tabling.md)
  predicates, [Well-Founded Semantics](wfs.md) extends it.

---

## What conforms

### Error terms

Errors are plain cells in Scryer's form, `error(Formal, Culprit)`, where the
culprit is the predicate indicator (or an unbound variable when there is no
single culprit). The explanatory prose, when there is any, is
`LogicException.message`. See [Exceptions](exceptions.md).

| Goal | Clausal raises |
|---|---|
| `atom_length(1, X)` | `error(type_error(atom, 1), atom_length/2)` |
| `atom_length(X, 3)` | `error(instantiation_error, atom_length/2)` |
| `atom_chars(1, X)` | `error(type_error(atom, 1), atom_chars/2)` |
| `char_code(ab, X)` | `error(type_error(character, ab), char_code/2)` |
| `sub_atom(X, B, L, A, S)` | `error(instantiation_error, sub_atom/5)` |
| `call(1)` | `error(type_error(callable, 1), call/1)` |
| `undefined_pred(1)` | `error(existence_error(procedure, undefined_pred/1), undefined_pred/1)` |
| `'is'(X, foo + 1)` | `error(type_error(evaluable, foo/0), (is)/2)` |
| `'is'(X, Y + 1)` | `error(instantiation_error, (is)/2)` |
| `'is'(X, 1 / 0)` | `error(evaluation_error(zero_divisor), (/)/2)` |
| `'is'(X, '//'(7.5, 2))` | `error(type_error(integer, 7.5), (//)/2)` |
| `'is'(X, '^'(2, -1))` | `error(type_error(float, 2), (^)/2)` |
| `X == foo(1)` (a constraint) | `error(domain_error(clpz_expression, foo(1)), (==)/2)` |

An uncaught one prints the term first:

```
Uncaught logic exception: error(type_error(evaluable,a/0),(is)/2)
```

### Arithmetic

`'is'(X, E)` is ISO `is/2`. (Bare `X is Y` in today's syntax is
**unification**; `eval_(E, X)` evaluates with the bare operators' Python
meaning.) The full operator table, bare vs quoted, is in
[Operators](operators.md); evaluation is in [Arithmetic](arithmetic.md).

| Quoted evaluable | Result | Matches |
|---|---|---|
| `'+'`, `'-'`, `'*'`, unary `'-'` | exact | ISO |
| `'/'(7, 2)`, `'/'(6, 2)` | `3.5`, `3.0` | Scryer |
| `'//'(-7, 2)` | `-3` (truncates) | ISO |
| `div(-7, 2)` | `-4` (floors) | ISO |
| `mod(-7, 2)` | `1` (sign of divisor) | ISO |
| `'**'(2, 3)` | `8.0` | ISO / Scryer |
| `'^'(2, 3)` | `8` | ISO |
| `rdiv(7, 2)` | `Fraction(7, 2)` | Scryer (exact rational) |
| `abs(-3)`, `abs(-3.5)` | `3`, `3.5` | ISO |
| `max(2, 5)`, `min(1, 2.0)`, `max(1, 1.0)` | `5`, `1`, `1.0` | ISO Cor.2 / Scryer |
| `rem(-7, 2)`, `sign(-2.5)`, `gcd(12, 18)` | `-1`, `-1.0`, `6` | ISO / Scryer |
| `truncate(-3.7)`, `round(-2.5)`, `ceiling(2.1)`, `floor(-2.1)` | `-3`, `-3`, `3`, `-3` | ISO / Scryer |
| `float(3)`, `float_integer_part(-3.7)`, `float_fractional_part(3.75)` | `3.0`, `-3.0`, `0.75` | ISO / Scryer |
| `sqrt(4)`, `sin`, `cos`, `tan`, `asin`, `acos`, `atan`, `atan2`, `exp`, `log` | floats (`sqrt(4)` is `2.0`) | ISO / Scryer |
| `sqrt(-1)`, `log(0)`, `atan2(0, 0)` | `evaluation_error(undefined)` | ISO (Scryer: `log(0)` is `float_overflow`) |
| `atan(1, 1)` | `0.7853981633974483` | ISO Cor.2 (Scryer: not evaluable) |
| `pi`, `e` | `3.141592653589793`, `2.718281828459045` | ISO / Scryer |
| `'>>'(-7, 1)`, `'<<'(1, 3)`, `'/\\'(12, 10)`, `'\\/'(12, 10)`, `'\\'(5)`, `xor(12, 10)` | `-4`, `8`, `8`, `14`, `-6`, `6` | ISO / Scryer |
| a zero divisor | `evaluation_error(zero_divisor)` naming the operator | ISO |

Inside an arithmetic **constraint** (`==`, `<`, ...; Prolog's `#=` family)
`/` is exact and a zero divisor makes the constraint fail, as in Scryer's
clpz. See [Constraints](constraints.md).

### Comparison and standard order

| Goal | Result |
|---|---|
| `'=='(1, 1.0)` | fails |
| `'\\=='(a, b)` | succeeds |
| `compare(O, 1, 1.0)` | `O = '>'` (a float precedes an equal integer) |
| `compare(O, 1, a)` | `O = '<'` |
| `compare(O, f(a), b)` | `O = '>'` |
| `compare(O, "abc", abc)` | `O = '>'` (a string is a list, a compound) |
| `'@>'(f(b), f(a, a))` | fails (arity is compared before name) |
| `sort([1, 1.0, 1], L)` | `L = [1.0, 1]` |
| `'=:='(1, 1.0)` | succeeds |
| `'<'(1, a)` | `type_error(evaluable, a/0)` |

The quoted ISO comparisons `'=:='`, `'=\\='`, `'<'`, `'>'`, `'=<'`, `'>='`
evaluate both sides; `'@<'`, `'@>'`, `'@=<'`, `'@>='`, `'=='`, `'\\=='` and
`compare/3` use the standard order of terms.

### Builtins that behave as ISO specifies

Type tests: `var/1`, `nonvar/1`, `atom/1`, `number/1`, `integer/1`,
`float/1`, `atomic/1`, `compound/1`, `ground/1`, `is_list/1`.
Terms: `functor/3`, `arg/3`, `'=..'/2`, `copy_term/2`, `term_variables/2`,
`numbervars/3`.
Atoms and characters: `atom_length/2`, `atom_chars/2`, `atom_codes/2`,
`atom_concat/3`, `sub_atom/5`, `char_code/2`, `number_chars/2`,
`number_codes/2`, `upcase_atom/2`.
Control and all-solutions: `call/1..8`, `once/1`, `catch/3`, `throw/1`,
`findall/3`, `forall/2`, `halt/0,1`.
Sorting: `sort/2`, `msort/2`, `compare/3`.
Output: `write/1`, `writeq/1`, `write_canonical/1`, `write_term/2`, `nl/0`.
Database: `asserta/1`, `assertz/1`, `retract/1`, `clause/2` on predicates
declared `-dynamic` (a static predicate raises
`permission_error(modify, static_procedure, PI)`).
Constraints: [`dif/2`, CLP(ℤ)](constraints.md), [CLP(B)](clpb.md),
[CLP(ℚ)](clpq.md).

The first argument of each is checked as ISO requires for the error rows
above; the next section lists where the checking stops short.

---

## Known gaps

### Evaluable functors

Every ISO evaluable (ISO 13211-1 9.1.7, 9.3, 9.4 and Cor.2) is in the table
above (added 2026-09-28). Scryer's non-ISO extras are not: `msb/1`,
`max_tagged_integer`, `integer/1` (not evaluable in Scryer either), `log/2`
and the rest raise `type_error(evaluable, F/N)`. An evaluation error names
the evaluable (`error(evaluation_error(undefined), sqrt/1)`), where Scryer
names `is/2`. The relational predicates `abs_/2`, `sign/2`, `max_/3`,
`min_/3`, `gcd/3` and `divmod_/4`
([Arithmetic](arithmetic.md#numeric-functions)) remain.

### Builtins that fail silently where ISO or Scryer raise

Each of these **fails** in Clausal. The right-hand column is the error ISO
13211-1 specifies or Scryer reports.

| Goal | Clausal | ISO / Scryer |
|---|---|---|
| `sort(a, L)` | fails | `type_error(list, a)` |
| `msort(a, L)` | fails | `type_error(list, a)` |
| `length(L, -1)` | fails | `domain_error(not_less_than_zero, -1)` |
| `char_code(C, -1)` | fails | `representation_error(character_code)` |
| `atom_length(abc, foo)` | fails | `type_error(integer, foo)` |
| `atom_length(abc, -1)` | fails | `domain_error(not_less_than_zero, -1)` |
| `functor(F, N, A)` (all unbound) | fails | `instantiation_error` |
| `functor(F, foo, a)` | fails | `type_error(integer, a)` |
| `functor(F, foo, -1)` | fails | `domain_error(not_less_than_zero, -1)` |
| `arg(x, f(a), X)` | fails | `type_error(integer, x)` |
| `'=..'(X, Y)` (both unbound) | fails | `instantiation_error` |
| `number_chars(X, [a])` | fails | `syntax_error(...)` |
| `number_codes(X, [])` | fails | `syntax_error(...)` |
| `between(1, a, X)` | fails | `type_error(integer, a)` |

### Unification conflates integers and floats

`'='(1, 1.0)` succeeds, and so does `'is'(X, 1), '='(X, 1.0)`. In ISO,
unification never unifies terms of different types, so both fail in Scryer.
`'=='(1, 1.0)` is correct (it fails).

### Flags

`set_prolog_flag/2` and `current_prolog_flag/2` are provided, with every ISO
flag and ISO's error terms ([Prolog Flags](flags.md)). The limits:

- `unknown` is always `error`: `fail` and `warning` are not implemented
  (setting one is `permission_error(modify, flag, unknown)`);
- `char_conversion` is always `off`;
- `double_quotes` is `chars` or `atom` (no `codes`), and is set by a
  directive, never at run time;
- `max_integer` / `min_integer` have no value (integers are unbounded), and
  `max_arity` is `unbounded`.

Scryer reports a read-only flag and a bad `unknown` value as
`domain_error(prolog_flag, F)`; Clausal follows ISO 8.17.1.3 here
(`permission_error(modify, flag, F)` and `domain_error(flag_value, F+V)`).
`assert_creates_dynamic` (implementation-defined) selects ISO 7.5.2(2)'s
assert, and is on in an imported `.pl` module.

### Missing builtins

Not provided (calling one raises `existence_error(procedure, PI)`):

- **terms:** `unify_with_occurs_check/2`, `subsumes_term/2`,
  `term_to_atom/2`, `atom_to_term/3`;
- **atoms:** `atom_number/2`, `atom_string/2`;
- **lists and sorting:** `keysort/2`, `sort/4`, `predsort/3`, `nth0/3`,
  `nth1/3` (`member/2` is spelled `in_/2`, `callable/1` is `callable_/1`);
- **database:** `retractall/1`, `abolish/1`, `current_predicate/1`;
- **control:** `ignore/1`; the quoted name `'\\+'/1` (write `not G`);
- **reading:** `read/1`, `read_term/2,3`, `op/3`, `current_op/3`;
- **streams:** `open/3,4`, `close/1`, `get_char/1,2`, `put_char/1,2`,
  `peek_char/1,2`, `stream_property/2`;
- **output:** `print/1`.

### Other differences

- **List syntax.** Today's syntax writes a partial list `[H, *T]`; in a
  `.seam`/`.clausal` clause, `[H|T]` is a list holding one bitwise-or term.
  The `.pl` importer translates `[H|T]` for you.
- **`call/N` with a builtin name** can leak a Python `TypeError`
  (`call(in_, X, [1])`) instead of an ISO error.
- **`write_canonical/1`** prints a list with the `'.'` functor
  (`'.'(s,[])`), not in list notation.

---

## History

The first edition of this report (2026-03-25) recorded decisions reached
with Markus Triska. Their outcome:

| Question | Decision then | Where it stands |
|---|---|---|
| Cut and if-then-else | Out of scope; reject on import | Unchanged, and ruled permanent (no committed choice either) |
| Strings | Lists of characters | Done: `"…"` is a string by default |
| Atoms | A distinct type | Done; the representation has changed twice and is now the plain `str` (the zero-field class it once was is retired) |
| Modules | `use_module` for Prolog, `-import_from` for Clausal | `.pl` import works for plain programs and is experimental |
| Operators and arithmetic | Translation layer only | Superseded: the engine itself now offers the quoted ISO spellings, with Scryer's meaning |
| Names | Rename between conventions | Superseded: predicate and variable names cross unchanged in both directions |
| Missing builtins | Add incrementally, `compare/3` first | `compare/3`, `@</2` and the standard order are done; the rest is listed above |
| Error terms | Verify ISO structure | Done: Scryer's `error(Formal, Culprit)` form |

The Scryer and Trealla embeddings were added later as the route for
programs that need a complete ISO system.
