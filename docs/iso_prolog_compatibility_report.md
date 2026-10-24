# ISO Prolog Compatibility Report

*Re-measured on engine `main` at e7a59c8f, 2026-10-16. Every goal on this
page was run through the `.pl` front end, and a sample through `.clausal`;
both gave the same answer for every goal sampled. The previous edition was
measured at 9fe1ee48 on 2026-09-28. Earlier editions (March 2026) recorded
design decisions taken with Markus Triska; their outcome is summarised
under [History](#history).*

*For practical instructions on importing and running Prolog programs, see
[Importing Prolog Code](importing_prolog.md). For why we measure against
ISO and the order of authority we use (Ulrich Neumerkel's conformity tables
first, then the standard text, then Scryer), see
[ISO Prolog Conformity](iso_conformity.md).*

## Two Prolog dialects, one standard

Clausal Prolog reads two kinds of Prolog source, and both aim to conform to
ISO/IEC 13211-1:

| | `.clausal` files | `.pl` files |
|---|---|---|
| **What it is** | Clausal Prolog proper: a deliberately **restricted subset** of ISO Prolog | A **compatibility mode** for existing ISO Prolog code |
| **What it is for** | Encoding ontologies, rules and policy, where we want firm guarantees about what can be expressed: every predicate stays monotonic and explainable | Running Prolog programs written for other ISO systems |
| **Cut, if-then-else, committed choice** | Not part of the dialect, by design (see [Purity and Monotonicity](purity.md)) | Part of ISO, so part of this mode: the native front end runs them (ISO 7.8); `*->` and a cut over a tabled call are refused |
| **Status** | Supported | Experimental ([Public API](public-api.md)) |

The restriction in `.clausal` does not take it outside the standard. A
program that uses only part of what ISO defines is still ISO Prolog text,
as long as it does not redefine what the standard defines. `.clausal` leaves
out cut and committed choice so that properties like monotonicity can be
guaranteed. The `.pl` mode reads and runs files under the full ISO rules, so
existing code can be used unchanged.

Both dialects share one reader and one engine. Every ISO builtin either
offers must behave as ISO 13211-1 specifies; this page records where that
holds and where it does not yet. A third route runs Prolog alongside
Clausal Prolog in a complete external ISO system, by embedding Scryer or
Trealla (optional packages).

The **seam** (`.seam` files) is a different thing: a Python-syntax surface
for the boundary between Python and Clausal Prolog. It is not Prolog syntax
and is not measured against ISO; see [Syntax](syntax.md).

---

## Syntax

Measured against Ulrich Neumerkel's
[Conformity Testing I: Syntax](https://www.complang.tuwien.ac.at/ulrich/iso-prolog/conformity_testing)
on 2026-10-16. Of its 366 numbered rows, judged against the expected-answer
("Codex") column: **323 pass, 40 fail, 3 untestable** (rows that wait for
more interactive input).

- 27 of the 40 come from lexer leniency (unknown escapes, bare-exponent
  floats, uppercase radix prefixes, raw tabs in quotes, `0''`). A change
  that tightens the lexer to ISO is under review.
- The rest are listed under [Known gaps](#known-gaps): `[]` and `'[]'`,
  the `double_quotes` flag at run time, and `get_char/1`. The answer
  printer's brackets and a bare prefix-operator atom are fixed (see
  [What conforms](#reading-and-writing-terms)).

Re-run row by row against Scryer on 2026-10-24 (each row's goals in one
session, through the `.pl` native front end and Scryer's own toplevel):
every row answers as Scryer does except `get_char/1` (#270, #271),
`writeq(-0.0)` (#364: Clausal keeps the sign, Scryer writes `0.0`), and
eight rows where Scryer departs from the Codex and Clausal follows it
(#348, #352, #353, #357, #358, #360, #361, #362 are syntax errors).

---

## What conforms

### Error terms

Errors are terms in ISO's form, `error(Formal, Context)`, with the
predicate indicator as context, as Scryer reports them (or an unbound
variable when there is no single culprit). The explanatory prose, when there
is any, is `LogicException.message`. See [Exceptions](exceptions.md).

| Goal | Clausal Prolog raises |
|---|---|
| `atom_length(1, X)` | `error(type_error(atom, 1), atom_length/2)` |
| `atom_length(X, 3)` | `error(instantiation_error, atom_length/2)` |
| `atom_length(abc, foo)` | `error(type_error(integer, foo), atom_length/2)` |
| `atom_length(abc, -1)` | `error(domain_error(not_less_than_zero, -1), atom_length/2)` |
| `atom_chars(1, X)` | `error(type_error(atom, 1), atom_chars/2)` |
| `char_code(ab, X)` | `error(type_error(character, ab), char_code/2)` |
| `char_code(C, -1)` | `error(representation_error(character_code), char_code/2)` |
| `sub_atom(X, B, L, A, S)` | `error(instantiation_error, sub_atom/5)` |
| `call(1)` | `error(type_error(callable, 1), call/1)` |
| `undefined_pred(1)` | `error(existence_error(procedure, undefined_pred/1), undefined_pred/1)` |
| `functor(F, N, A)` | `error(instantiation_error, functor/3)` |
| `functor(F, foo, a)` | `error(type_error(integer, a), functor/3)` |
| `functor(F, foo, -1)` | `error(domain_error(not_less_than_zero, -1), functor/3)` |
| `arg(x, f(a), X)` | `error(type_error(integer, x), arg/3)` |
| `X =.. Y` | `error(instantiation_error, (=..)/2)` |
| `sort(a, L)`, `msort(a, L)` | `error(type_error(list, a), sort/2)`, `… msort/2)` |
| `length(L, -1)` | `error(domain_error(not_less_than_zero, -1), length/2)` |
| `number_chars(X, [a])`, `number_codes(X, [])` | `error(syntax_error(…), number_chars/2)`, `… number_codes/2)` |
| `between(1, a, X)` | `error(type_error(integer, a), between/3)` |
| `X is foo + 1` | `error(type_error(evaluable, foo/0), (is)/2)` |
| `X is Y + 1` | `error(instantiation_error, (is)/2)` |
| `X is 1 / 0` | `error(evaluation_error(zero_divisor), (/)/2)` |
| `X is 7.5 // 2` | `error(type_error(integer, 7.5), (//)/2)` |
| `X is 2 ^ -1` | `error(type_error(float, 2), (^)/2)` |
| `assertz(p(2))`, `retract(p(1))` on a static `p/1` | `error(permission_error(modify, static_procedure, p/1), assertz/1)`, `… retract/1)` |

The earlier edition listed thirteen of these goals as failing silently.
Every one of them now raises the ISO error.

### Arithmetic

`is/2` and the comparison predicates are ISO's. Evaluation is described in
[Arithmetic](arithmetic.md).

| Expression | Result | Matches |
|---|---|---|
| `+`, `-`, `*`, unary `-` | exact | ISO |
| `7 / 2`, `6 / 2` | `3.5`, `3.0` | Scryer |
| `-7 // 2` | `-3` (truncates) | ISO |
| `div(-7, 2)` | `-4` (floors) | ISO |
| `mod(-7, 2)` | `1` (sign of divisor) | ISO |
| `2 ** 3` | `8.0` | ISO / Scryer |
| `2 ^ 3` | `8` | ISO |
| `rdiv(7, 2)` | `7 rdiv 2` (exact rational) | Scryer |
| `abs(-3)`, `abs(-3.5)` | `3`, `3.5` | ISO |
| `max(2, 5)`, `min(1, 2.0)`, `max(1, 1.0)` | `5`, `1`, `1.0` | ISO Cor.2 / Scryer |
| `rem(-7, 2)`, `sign(-2.5)`, `gcd(12, 18)` | `-1`, `-1.0`, `6` | ISO / Scryer |
| `truncate(-3.7)`, `round(-2.5)`, `ceiling(2.1)`, `floor(-2.1)` | `-3`, `-3`, `3`, `-3` | ISO / Scryer |
| `float(3)`, `float_integer_part(-3.7)`, `float_fractional_part(3.75)` | `3.0`, `-3.0`, `0.75` | ISO / Scryer |
| `sqrt(4)`, `sin`, `cos`, `tan`, `asin`, `acos`, `atan`, `atan2`, `exp`, `log` | floats (`sqrt(4)` is `2.0`) | ISO / Scryer |
| `sqrt(-1)`, `log(0)`, `atan2(0, 0)` | `evaluation_error(undefined)` | ISO |
| `atan(1, 1)` | `0.7853981633974483` | ISO Cor.2 (Scryer: not evaluable) |
| `pi`, `e` | `3.141592653589793`, `2.718281828459045` | ISO / Scryer |
| `-7 >> 1`, `1 << 3`, `12 /\ 10`, `12 \/ 10`, `\ 5`, `xor(12, 10)` | `-4`, `8`, `8`, `14`, `-6`, `6` | ISO / Scryer |
| a zero divisor | `evaluation_error(zero_divisor)` naming the operator | ISO |

Scryer's non-ISO evaluables (`msb/1`, `log/2`, `max_tagged_integer`, …) are
not provided: they raise `type_error(evaluable, F/N)`. An evaluation error
names the evaluable (`error(evaluation_error(undefined), sqrt/1)`), where
Scryer names `is/2`.

Inside an arithmetic **constraint** (CLP(ℤ)'s `#=` family) `/` is exact and
a zero divisor makes the constraint fail, as in Scryer's clpz. See
[Constraints](constraints.md).

### Comparison and standard order

| Goal | Result |
|---|---|
| `1 == 1.0` | fails |
| `1 = 1.0` | fails (an integer and a float are distinct terms, ISO 7.3; so do `f(1) = f(1.0)`, `[1] = [1.0]` and `X = 1, X = 1.0`) |
| `a \== b` | succeeds |
| `compare(O, 1, 1.0)` | `O = (>)` (a float precedes an equal integer) |
| `compare(O, 1, a)` | `O = (<)` |
| `compare(O, f(a), b)` | `O = (>)` |
| `compare(O, "abc", abc)` | `O = (>)` (a string is a list, a compound) |
| `f(b) @> f(a, a)` | fails (arity is compared before name) |
| `sort([1, 1.0, 1], L)` | `L = [1.0, 1]` |
| `1 =:= 1.0` | succeeds |
| `1 < a` | `type_error(evaluable, a/0)` |

`==/2` compares the whole term: a variable bound anywhere inside reads as
its value, as ISO 8.4.1.1 requires.

### Builtins that behave as ISO specifies

Type tests: `var/1`, `nonvar/1`, `atom/1`, `number/1`, `integer/1`,
`float/1`, `atomic/1`, `compound/1`, `callable/1`, `ground/1`, `is_list/1`.
Terms: `functor/3`, `arg/3`, `(=..)/2`, `copy_term/2`, `term_variables/2`,
`numbervars/3`, `unify_with_occurs_check/2`, `subsumes_term/2`.
Atoms and characters: `atom_length/2`, `atom_chars/2`, `atom_codes/2`,
`atom_concat/3`, `sub_atom/5`, `char_code/2`, `number_chars/2`,
`number_codes/2`, `atom_number/2`, `upcase_atom/2`.
Control and all-solutions: `call/1..8`, `once/1`, `\+/1`, `catch/3`,
`throw/1`, `findall/3`, `bagof/3`, `setof/3`, `forall/2`, `halt/0,1`.
Lists and sorting: `length/2`, `member/2`, `memberchk/2`, `append/3`,
`nth0/3`, `nth1/3`, `between/3`, `sort/2`, `msort/2`, `keysort/2`,
`compare/3`.
Operators: `op/3`, `current_op/3`.
Output: `write/1`, `writeq/1`, `write_canonical/1`, `write_term/2`, `nl/0`.
`write_canonical([a])` writes `'.'(a,[])`, as Ulrich's tables expect.
Database: `asserta/1`, `assertz/1`, `retract/1`, `retractall/1`,
`abolish/1`, `clause/2`, `current_predicate/1` (a static predicate raises
`permission_error(modify, static_procedure, PI)`).
The ISO built-ins are static (7.5.1): a `.pl` or `.clausal` file with a
clause for one, or `dynamic/1` of one, is refused at load with
`permission_error(modify, static_procedure, PI)`, the whole file, as Scryer
refuses it (Scryer ignores `dynamic/1` of a builtin instead). A library
predicate such as `append/3` or `length/2` is no ISO built-in and a file may
define it.
Grammar rules: `phrase/2,3`.
Common non-ISO extras, as SWI-Prolog defines them (Scryer has none):
`sort/4`, `predsort/3`, `print/1`, `atom_string/2`, `term_to_atom/2`,
`atom_to_term/3`, errors included (`tests/iso/test_common_extras_scryer.py`).
`predsort/3` tries every answer of its comparator, so it is cut-free.
Constraints: [`dif/2`, CLP(ℤ)](constraints.md), [CLP(B)](clpb.md),
[CLP(ℚ)](clpq.md).

### Reading and writing terms

The `-g` answer printer writes a binding as `writeq/1` writes the right
operand of `=`, as Scryer's toplevel does: `T = (a,b)`, `X = (-)`, and
`F = ('.')` while `.` is an operator. A prefix operator followed by a token
that cannot start a term is an atom (ISO 6.3.4.2): `- .` and `\ .` read as
`-` and `\`, and `- (1)` and `-(1)` are both `-(1)`.

### Procedures and modules

A procedure is a name **and** an arity, as in ISO: `p/1` and `p/2` in one
file are two procedures, and a DCG nonterminal `s//1` is `s/3`. See
[Predicates](predicates.md).

ISO 13211-1 has no module system, so here Scryer is the reference.
`use_module(m, [p/1])` imports one arity of `p`, and a bare name imports
every arity. A name clash between two modules is resolved with a
module-qualified call, `m:p(X)`. Renaming an import with `as` is not
supported, because neither ISO nor Scryer has it.

### Flags

`set_prolog_flag/2` and `current_prolog_flag/2` are provided, with every ISO
flag and ISO's error terms ([Prolog Flags](flags.md)). A read-only flag gives
`permission_error(modify, flag, F)` and a bad value
`domain_error(flag_value, F+V)`, following ISO 8.17.1.3 (for
`set_prolog_flag(unknown, foo)` Scryer reports
`domain_error(prolog_flag, unknown)`). `char_conversion` is `off`;
`max_integer` and `min_integer` have no value (integers are unbounded), and
`max_arity` is `unbounded`. `assert_creates_dynamic` (implementation-defined)
selects ISO 7.5.2(2)'s assert, and is on in a `.pl` module. `unknown`
takes `error`, `fail` and `warning` (ISO 7.11.2.4), process-wide.
`char_conversion/2` and `current_char_conversion/2` (ISO 8.14.5–8.14.6, the
directive too) keep the process-wide conversion table with ISO's errors;
no reader applies it, so the `char_conversion` flag stays `off` (Scryer has
none of the three). ISO 7.11.2.1 makes `on` the flag's default; Clausal
keeps it `off` and refuses `on` because its reader does not convert, so a
program that tests `current_prolog_flag(char_conversion, on)` fails here.

---

## Known gaps

### Flags

- `double_quotes` is never changed at run time (a design choice, ruled
  2026-10-18): `set_prolog_flag(double_quotes, V)` as a goal gives
  `permission_error(modify, flag, double_quotes)`, where ISO allows the
  change (Ulrich #170). A `.pl` file sets it by directive (`chars`, `codes`
  or `atom`); in `.clausal` it is always `chars`. The question is
  [Q2](iso_questions_for_ulrich.md#q2-a-double_quotes-flag-that-cannot-change-at-run-time)
  for Ulrich.

### Missing builtins

Not provided (calling one raises `existence_error(procedure, PI)`):

- **ISO stream input and output (8.11–8.13):** `open/3,4`, `close/1,2`,
  `set_input/1`, `set_output/1`, `current_input/1`, `current_output/1`,
  `flush_output/0,1`, `at_end_of_stream/0,1`, `set_stream_position/2`,
  `stream_property/2`, `get_char/1,2`, `peek_char/1,2`, `put_char/1,2`, the
  `_code` and `_byte` versions of those, `nl/1`, and the stream arguments
  of the writers (`write/2`, `writeq/2`, `write_canonical/2`,
  `write_term/3`);
- **ISO term reading (8.14.1):** `read/1,2`, `read_term/2,3`;
- **common non-ISO extras:** `ignore/1`, left out by design: it is
  committed choice (ruling D13).

### Reading and writing

These are from the [syntax](#syntax) measurement:

- `[]` and `'[]'` are the same atom, as ISO says (ruling D70, 2026-10-17):
  `X = '[]', X == []` succeeds and `writeq('[]')` prints `[]`, which reads
  back as itself.

---

## History

The first edition of this report (2026-03-25) recorded decisions reached
with Markus Triska. Their outcome:

| Question | Decision then | Where it stands |
|---|---|---|
| Cut and if-then-else | Out of scope; reject on import | Split: never in `.clausal`, by design; part of the `.pl` compatibility mode (done on the native front end) |
| Strings | Lists of characters | Done: `"…"` is a list of characters by default |
| Atoms | A distinct type | Done |
| Modules | `use_module` | `.pl` import works for plain programs and is experimental |
| Operators and arithmetic | Translation layer only | Superseded: `.clausal` and `.pl` are read with ISO syntax and operators directly |
| Names | Rename between conventions | Superseded: predicate and variable names cross unchanged in both directions |
| Missing builtins | Add incrementally, `compare/3` first | Most are done; the rest are listed above |
| Error terms | Verify ISO structure | Done: `error(Formal, Context)` in Scryer's form |

The Scryer and Trealla embeddings were added later as the route for
programs that need a complete ISO system today.
