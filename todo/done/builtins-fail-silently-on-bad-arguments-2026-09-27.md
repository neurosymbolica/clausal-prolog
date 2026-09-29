# Several builtins FAIL silently on an argument ISO/Scryer reject with an error

**Status: OPEN. Found 2026-09-27 during Compound retirement slice 2; not fixed.**

## Measured (main 03f70a71)

Each goal was run as `catch((G, R is no_error), E, R is E)`. "fails" means
no answer at all: no error, and no success either.

| goal | Clausal | Scryer |
|---|---|---|
| `sort(a, _)` | fails | `error(type_error(list,a),sort/2)` |
| `functor(_, foo, -1)` | fails | `error(domain_error(not_less_than_zero,-1),functor/3)` |
| `length(_, -1)` | fails | `error(domain_error(not_less_than_zero,-1),length/2)` |
| `arg(x, [1], _)` | fails | `error(type_error(integer,x),arg/3)` |
| `sub_atom(abc, _, -1, _, _)` | fails | `error(domain_error(not_less_than_zero,-1),sub_atom/5)` |
| `char_code(_, -1)` | fails | `error(representation_error(character_code),char_code/2)` |

(The report that led here said these *succeed* silently. They do not: they
fail. Both are wrong, and the failure is the harder one to notice.)

## ISO

Check each against ISO 13211-1 before implementing; Scryer only where ISO is
silent. From memory, to be confirmed against the text:

- `arg/3` (8.5.2.3): N neither a variable nor an integer, `type_error(integer, N)`.
- `char_code/2` (8.16.6.3): Code neither a variable nor a character code,
  `representation_error(character_code)`.
- `functor/3` (8.5.1.3): Term a variable and Arity negative,
  `domain_error(not_less_than_zero, Arity)` (confirm the clause letter).
- `sort/2` (Cor.2 8.4.3): List a partial list or not a list, `type_error(list, List)`.
- `sub_atom/5` (8.16.3.3): confirm whether ISO specifies the negative-Length case.
- `length/2` is not in ISO core (Cor.2 / the prologue); follow Scryer.

## Repro

    -allow_singletons
    -private([a, abc, foo, x, no_error])
    t_sort(R) <- (catch((sort(a, _), R is no_error), E, R is E)),
    t_functor(R) <- (catch((functor(_, foo, -1), R is no_error), E, R is E)),
    t_length(R) <- (catch((length(_, -1), R is no_error), E, R is E)),
    t_arg(R) <- (catch((arg(x, [1], _), R is no_error), E, R is E)),
    t_subatom(R) <- (catch((sub_atom(abc, _, -1, _, _), R is no_error), E, R is E)),
    t_charcode(R) <- (catch((char_code(_, -1), R is no_error), E, R is E)),

Each query returns no answers.

## Closed 2026-09-30

Fixed on fix/todo-batch-1-2026-09-30. Every row now raises Scryer's error
term (checked against /workspace/scryer-prolog): functor/3 (unbound
Name/Arity, non-integer and negative Arity), arg/3 (unbound Term, atomic
Term, non-integer and negative N), sort/2 and msort/2 (partial list, non-list
List or Sorted), sub_atom/5 (non-integer and negative Before/Length/After,
non-atom Sub), char_code/2 (out-of-range code), atom_length/2 (non-integer
and negative Length). `length(_, -1)` had already been fixed. Pinned by
tests/test_builtin_bad_argument_errors.py.

Left alone on purpose: `arg(N, T, A)` with N unbound still ENUMERATES (ISO:
instantiation_error) -- a deliberate extension documented in arg/3. And
keysort/2 does not exist at all (existence_error) -- see the missing-ISO-
builtins todo.
