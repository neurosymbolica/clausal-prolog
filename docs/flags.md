# Prolog Flags

`set_prolog_flag/2` and `current_prolog_flag/2` read and change the Prolog
flags of ISO 13211-1 (7.11, 8.17), plus one flag of Clausal's own,
`assert_creates_dynamic`.

Flag names and values are atoms. In `.clausal` source, write them quoted
(`'unknown'`), or declare them with `-private([...])`, as with any atom. A
truth value is `true` / `false`, which compile to Python's `True` / `False`.

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
| `unknown` | `error` | `error` only | process | `error` (settable) |
| `double_quotes` | `chars` | by directive | module | `chars` |
| `assert_creates_dynamic` | `false` (`true` in an imported `.pl` module) | yes | module | not a flag (ISO assert always creates) |
| `require_end_module` | `default` | `true` / `false` / `default` | process (file-local as a `.pl` directive) | not a flag |

- **Integers are unbounded** (Python `int`), so `bounded` is `false` and
  `max_integer` / `min_integer` have no value:
  `current_prolog_flag('max_integer', X)` fails, as in Scryer.
- **`integer_rounding_function`** is `toward_zero`: the ISO evaluable
  `'//'(-7, 2)` is `-3`. (A bare `-7 // 2` in source is Python's floor
  division, which is not the ISO evaluable; see [Operators](operators.md).)
- **`max_arity`** is `unbounded`: a compound term is a Python tuple, and there
  is no arity limit.
- **`unknown`** is always `error`: calling an unknown procedure raises
  `existence_error(procedure, PI)`. The ISO values `fail` and `warning` are not
  implemented.
- **`debug`** can be set, but changes nothing yet.
- **`double_quotes`** is the module's [`-double_quotes`](directives.md#-double_quotes)
  mode: `chars` (the default: `"…"` is a string) or `atom`. It decides how the
  compiler reads the module's `"…"` literals, so it is set by a directive, never
  at run time. `codes` is not a mode: codes are spelled `b"…"`.
- **`assert_creates_dynamic`**: see [below](#assert_creates_dynamic).
- **`require_end_module`**: whether a Prolog module file must end with
  `:- end_module(Name).` -- see
  [Importing Prolog Code](importing_prolog.md#end_module-closing-a-module).

`current_prolog_flag(F, V)` with `F` unbound enumerates every flag that has a
value.

```seam
test("bounded") <- current_prolog_flag('bounded', false)

test("unknown is error") <- current_prolog_flag('unknown', 'error')

test("no max_integer") <- (not current_prolog_flag('max_integer', _M))

test("enumerate") <- (
    findall(F, current_prolog_flag(F, _V), FLAGS),
    in_('double_quotes', FLAGS)
)
```

---

## Scope

A **process** flag has one value for the whole process.

A **module** flag has a value per module:

- `set_prolog_flag/2`, run as a goal, sets it for the **calling** module;
- `current_prolog_flag/2` reports the calling module's value;
- the directive `-set_prolog_flag(Flag, Value)` sets it for the module that
  carries the directive.

```seam
test("a module flag") <- (
    set_prolog_flag('assert_creates_dynamic', true),
    current_prolog_flag('assert_creates_dynamic', true)
)
```

### The directive

`-set_prolog_flag(Flag, Value)` sets a flag when the module loads. For
`double_quotes` it is the same as `-double_quotes(Value)`, and like that
directive it governs the literals below it. A setting that `set_prolog_flag/2`
would refuse is a load-time `SyntaxError` that carries the ISO error term.

```seam
-set_prolog_flag(assert_creates_dynamic, true)
-set_prolog_flag(double_quotes, chars)
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
| a read-only flag, or an ISO value this engine does not implement (`unknown` = `fail`, `char_conversion` = `on`, `double_quotes` = `codes`), or `double_quotes` set at run time | `permission_error(modify, flag, Flag)` |

Scryer departs from ISO on two rows. It reports a read-only flag
(`set_prolog_flag(max_arity, 5)`) and a bad `unknown` value as
`domain_error(prolog_flag, Flag)`. Here ISO decides.

```seam
test("not a flag") <- catch(
    set_prolog_flag('nosuch', 1),
    error(domain_error('prolog_flag', 'nosuch'), _),
    true)

test("read-only") <- catch(
    set_prolog_flag('bounded', true),
    error(permission_error('modify', 'flag', 'bounded'), _),
    true)

test("not a value") <- catch(
    set_prolog_flag('unknown', 'bogus'),
    error(domain_error('flag_value', '+'('unknown', 'bogus')), _),
    true)
```

---

## assert_creates_dynamic

What `assertz/1` and `asserta/1` do with a procedure that does not exist yet.

- **`false`** (the default in `.clausal` / `.seam` modules): the dynamic database
  is declare-first. Asserting into a procedure nothing declares raises
  `permission_error(modify, static_procedure, PI)`, because ISO makes an
  undeclared procedure static (7.5.2). Declare it with `-dynamic` first.
- **`true`** (the default in an imported `.pl` module): ISO 7.5.2(2). Asserting
  into a procedure that does not exist **creates** it, as a dynamic procedure of
  the module.

With either value, these are still refused with
`permission_error(modify, static_procedure, PI)`:

- a static predicate that has clauses;
- a builtin;
- a declared data functor.

The flag is module-scoped: it governs asserts into the module whose flag is set.

```seam
-set_prolog_flag(assert_creates_dynamic, true)

remember(X) <- assertz(seen(X))

test("assertz creates the procedure") <- (
    remember(1),
    remember(2),
    findall(X, seen(X), XS),
    XS == [1, 2]
)
```

An [imported Prolog module](importing_prolog.md) starts with
`assert_creates_dynamic` set to `true`. A
`:- set_prolog_flag(assert_creates_dynamic, false).` in the file turns it off.

---

*See also: [Database Operations](database_ops.md) — assertz, asserta, retract;
[Directives](directives.md); [Importing Prolog Code](importing_prolog.md).*
