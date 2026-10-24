# Prolog Flags

`set_prolog_flag/2` and `current_prolog_flag/2` read and change the Prolog
flags of ISO 13211-1 (7.11, 8.17), plus one flag of Clausal Prolog's own,
`assert_creates_dynamic`.

Flag names and values are atoms, written bare (`unknown`) as in ISO. A
truth value is `true` / `false`.

!!! note "Clausal Prolog and the seam"

    Examples on this page are [Clausal Prolog](clausal_prolog.md)
    (`.clausal`), ISO Prolog syntax. In the [seam](syntax.md) (`.seam`),
    Clausal's Python-syntax surface, flag names are written quoted
    (`'unknown'`) or declared with `-private([...])`, as with any atom,
    `true` / `false` compile to Python's `True` / `False`, and the
    directive is spelled `-set_prolog_flag(Flag, Value)`.

---

## The flags

| Flag | Value here | Settable | Scope | Scryer |
|---|---|---|---|---|
| `bounded` | `false` | no | process | `false` |
| `max_integer` | none (integers are unbounded) | no | process | none |
| `min_integer` | none | no | process | none |
| `integer_rounding_function` | `toward_zero` | no | process | none (the query fails) |
| `char_conversion` | `off` | `off` only | process | not a flag |
| `debug` | `off` | `on` / `off` | process | not a flag |
| `max_arity` | `unbounded` | no | process | `255` |
| `unknown` | `error` | `error` / `fail` / `warning` | process | `error` (settable) |
| `double_quotes` | `chars` | `.clausal`: no (always `chars`); `.pl`: by directive | module | `chars` |
| `assert_creates_dynamic` | `false` (`true` in a `.clausal` or imported `.pl` module) | yes | module | not a flag (ISO assert always creates) |
| `require_end_module` | `default` | `true` / `false` / `default` | process (file-local as a `.pl` directive) | not a flag |

- **Integers are unbounded** (Python `int`), so `bounded` is `false` and
  `max_integer` / `min_integer` have no value:
  `current_prolog_flag(max_integer, X)` fails, as in Scryer.
- **`integer_rounding_function`** is `toward_zero`: the ISO evaluable
  `-7 // 2` is `-3`. (In the seam, a bare `-7 // 2` is Python's floor
  division, which is not the ISO evaluable; the seam's quoted
  `'//'(-7, 2)` is. See [Operators](operators.md).)
- **`max_arity`** is `unbounded`: a compound term is a Python tuple, and there
  is no arity limit.
- **`unknown`** (ISO 7.11.2.4) says what a call to a procedure that does not
  exist does. `error` (the default) raises `existence_error(procedure, PI)`;
  `fail` fails the call; `warning` writes
  `% Warning: predicate PI is undefined` to standard error (the `user_error`
  stream; Scryer writes the same line to standard output) and fails the call.
  It governs every call: a clause body, `call/N`, `maplist/N` and the other
  meta-calls, `phrase/2,3`, a call at an arity the predicate does not have,
  and `M:G` into a module that does not exist. The flag is process-wide, as
  ISO makes every flag global, and a call that finds its procedure never
  reads it. A refusal of committed choice (`*->`, a cut in a meta-called
  body), reported with the same error term, is not a missing procedure and
  stays an error. In the [sandbox](sandbox.md) a program cannot set it.
- **`char_conversion`** is `off`. The table `char_conversion/2` and
  `current_char_conversion/2` keep (ISO 8.14.5–8.14.6) exists, process-wide,
  but no reader applies it: there is no `read_term/2`, and a source file is
  read before its directives run, so a conversion could not reach the text
  after it. `on` is therefore refused, `permission_error(modify, flag,
  char_conversion)`. Scryer has neither the flag nor the builtins.
- **`debug`** can be set, but changes nothing yet.
- **`double_quotes`** is the module's double-quotes mode. It decides how the
  compiler reads the module's `"…"` literals, so it is never changed at run
  time: `set_prolog_flag(double_quotes, _)` as a goal raises
  `permission_error(modify,flag,double_quotes)`, even for the value already in
  force (ruled 2026-10-18: a reading that changes while the program runs is
  asking for trouble). In a `.clausal` file it is always `chars` (`"…"` is a
  string); `:- set_prolog_flag(double_quotes, chars).` is accepted but
  redundant, and any other mode is refused when the file loads. An ISO Prolog
  (`.pl`) file sets it by directive, as ISO: `chars` (the default), `codes`
  or `atom`. The seam has the transitional
  [`-double_quotes`](directives.md#-double_quotes) (`chars` or `atom`; it
  spells codes `b"…"`). Whether ISO permits the run-time refusal is
  [Q2](iso_questions_for_ulrich.md#q2-a-double_quotes-flag-that-cannot-change-at-run-time)
  for Ulrich.
- **`assert_creates_dynamic`**: see [below](#assert_creates_dynamic).
- **`require_end_module`**: whether a Prolog module file must end with
  `:- end_module(Name).` -- see
  [Importing Prolog Code](importing_prolog.md#end_module-closing-a-module).
- **`clpq_max_nodes`, `clpq_max_work`, `clpq_max_projection`,
  `clpq_max_expansion`, `clpq_max_expansion_bits`,
  `clpq_max_coefficient_bits`** (implementation-defined,
  under `CLAUSAL_CLPQ=holzbaur` only): the resource caps of the clp(q,r)
  1.3.3 port, each a positive integer, process wide and settable. Past one
  the port raises `error(resource_error(R), _)`: `clpq_nodes` (the nodes of
  one `bb_inf/3` search), `clpq_work` (the rows that search's pivots read
  and write), `clpq_projection` (the same for one projection, as `dump_q/2`
  and the `-g` answer printer make) or `clpq_expansion` (the terms, or the
  coefficient bits, of the powers and products one constraint expands, or
  the bits of the largest single coefficient one power or product builds;
  a coefficient past 2,500,000 bits counts its bits squared over
  2,500,000 against `clpq_max_expansion_bits`, as building it costs more
  than its size). Defaults 20,000, 4,000,000, 4,000,000, 40,000,
  200,000,000 and 20,000,000. The caps bound how much one call computes,
  not how long it takes: the time to reach the work cap still grows with
  the size of the numbers in the store (a store whose row constants have
  20,000 digits reaches it in about 43 s, 50,000 digits in about 105 s,
  on an idle 32-core box), so the host's own time limit applies
  (DEVIATIONS.md D24).
  Adding two big rationals is not charged either: a sum such as
  `{X = (1/3)^4000000 + (1/5)^2730000}` can run for minutes and can build
  a coefficient past `clpq_max_coefficient_bits`. Coefficients past 64 bits
  in a linear constraint count their bits, so about ten 19,000,000-bit
  coefficients in one constraint answer and an eleventh raises. The legacy
  solver has no such flags. In the [sandbox](sandbox.md) a program sets no
  process-wide flag, as a goal or as a load-time directive.

`current_prolog_flag(F, V)` with `F` unbound enumerates every flag that has a
value.

```clausal
test("bounded") :-
    current_prolog_flag(bounded, false).

test("unknown is error") :-
    current_prolog_flag(unknown, error).

test("unknown = fail makes a missing procedure fail") :-
    set_prolog_flag(unknown, fail),
    findall(X, call(no_such_procedure, X), L),
    set_prolog_flag(unknown, error),
    L == [].

test("no max_integer") :-
    \+ current_prolog_flag(max_integer, _M).

test("enumerate") :-
    findall(F, current_prolog_flag(F, _V), FLAGS),
    in_(double_quotes, FLAGS).
```

---

## Scope

A **process** flag has one value for the whole process.

A **module** flag has a value per module:

- `set_prolog_flag/2`, run as a goal, sets it for the **calling** module;
- `current_prolog_flag/2` reports the calling module's value;
- the directive `:- set_prolog_flag(Flag, Value).` sets it for the module that
  carries the directive.

A `.clausal` module starts with `assert_creates_dynamic` set to `true`, so
the test turns it off and back on:

```clausal
test("a module flag") :-
    set_prolog_flag(assert_creates_dynamic, false),
    current_prolog_flag(assert_creates_dynamic, false),
    set_prolog_flag(assert_creates_dynamic, true),
    current_prolog_flag(assert_creates_dynamic, true).
```

### The directive

`:- set_prolog_flag(Flag, Value).` sets a flag when the module loads. For
`double_quotes` it governs the literals below it (in the seam it is the same
as `-double_quotes(Value)`). A setting that `set_prolog_flag/2`
would refuse is a load-time `SyntaxError` that carries the ISO error term:
`:- set_prolog_flag(bounded, true).` fails to load with
`error(permission_error(modify,flag,bounded),set_prolog_flag/2)`.

```clausal
:- set_prolog_flag(assert_creates_dynamic, true).
:- set_prolog_flag(double_quotes, chars).
```

---

## Errors

The errors are ISO's (8.17.1.3, 8.17.2.3). The context is
`set_prolog_flag/2` or `current_prolog_flag/2`.

| Case | Error |
|---|---|
| `Flag` or `Value` unbound | `instantiation_error` |
| `Flag` not an atom | `type_error(atom, Flag)` |
| `Flag` not a flag | `domain_error(prolog_flag, Flag)` |
| `Value` not a value ISO allows for the flag | `domain_error(flag_value, Flag+Value)` |
| a read-only flag, or an ISO value this engine does not implement (`char_conversion` = `on`, `double_quotes` = `codes`), or `double_quotes` set at run time | `permission_error(modify, flag, Flag)` |

Scryer departs from ISO on two rows. It reports a read-only flag
(`set_prolog_flag(max_arity, 5)`) and a bad `unknown` value as
`domain_error(prolog_flag, Flag)`. Here ISO decides.

```clausal
test("not a flag") :-
    catch(set_prolog_flag(nosuch, 1),
          error(domain_error(prolog_flag, nosuch), _),
          true).

test("read-only") :-
    catch(set_prolog_flag(bounded, true),
          error(permission_error(modify, flag, bounded), _),
          true).

test("not a value") :-
    catch(set_prolog_flag(unknown, bogus),
          error(domain_error(flag_value, unknown + bogus), _),
          true).
```

---

## assert_creates_dynamic

What `assertz/1` and `asserta/1` do with a procedure that does not exist yet.

- **`false`** (the default in `.seam` modules): the dynamic database
  is declare-first. Asserting into a procedure nothing declares raises
  `permission_error(modify, static_procedure, PI)`, because ISO makes an
  undeclared procedure static (7.5.2). Declare it dynamic first (the seam's
  `-dynamic(PI)`, `.clausal`'s `:- dynamic(PI).`).
- **`true`** (the default in a Clausal Prolog `.clausal` module and in an imported `.pl` module): ISO 7.5.2(2). Asserting
  into a procedure that does not exist **creates** it, as a dynamic procedure of
  the module.

With either value, these are still refused with
`permission_error(modify, static_procedure, PI)`:

- a static predicate that has clauses;
- a builtin;
- a declared data functor.

The flag is module-scoped: it governs asserts into the module whose flag is set.

```clausal
% true is already the .clausal default; the directive makes it explicit
:- set_prolog_flag(assert_creates_dynamic, true).

remember(X) :-
    assertz(seen(X)).

test("assertz creates the procedure") :-
    remember(1),
    remember(2),
    findall(X, seen(X), XS),
    XS == [1, 2].
```

With the flag off, the same assert is refused:

```clausal
:- set_prolog_flag(assert_creates_dynamic, false).

remember(X) :-
    assertz(seen(X)).

test("assertz into an undeclared procedure raises") :-
    catch(remember(1),
          error(permission_error(modify, static_procedure, PI), _),
          true),
    PI == seen/1.
```

A [Clausal Prolog](clausal_prolog.md) (`.clausal`) module or an [imported Prolog module](importing_prolog.md) starts with
`assert_creates_dynamic` set to `true`. A
`:- set_prolog_flag(assert_creates_dynamic, false).` in the file turns it off.

---

*See also: [Database Operations](database_ops.md) — assertz, asserta, retract;
[Directives](directives.md); [Importing Prolog Code](importing_prolog.md).*
