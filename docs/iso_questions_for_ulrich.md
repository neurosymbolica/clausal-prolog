# Open Questions for the Standard

Some cases come up while building Clausal Prolog that ISO/IEC 13211-1 seems
not to settle, either because the standard doesn't address the situation or
because two of its rules seem to point different ways. This page collects
them as questions for Ulrich Neumerkel, whose
[conformity-testing pages](https://www.complang.tuwien.ac.at/ulrich/iso-prolog/conformity_testing)
are our primary reference (see [ISO Prolog Conformity](iso_conformity.md)).

Each entry gives the question, what the standard seems to say about it, and
what Clausal Prolog does today. That behaviour is a provisional choice, to
be revised once the question has an answer. Each entry says which clauses
we checked and which are still unverified. If Ulrich points to a clause we
missed, the entry becomes a bug or a documented choice and moves
off this page.

For lexer rules that the standard does settle but that many systems relax,
see [ISO Lexer Edge Cases](iso_lexer_edge_cases.md) instead.

## Q1. A file's own `op/3` directives when `op/3` is refused as a goal

**The situation.** In [sandbox mode](sandbox.md), a process runs programs
it does not trust, and `op/3` as a goal is refused, because the operator
table it changes is shared by the whole process. Every later query's
`current_op/3` and every term writer would see the change. The question is
what should happen to a sandboxed *file's* own `:- op(...)` directives.

**What the standard says.** Part 1 has one operator table, used for all
reading and writing that follows. An `op/3` directive acts like the `op/3`
built-in (8.14.3), so it affects everything read and written afterwards.
Part 1 has no restricted mode and no modules. The errors `op/3` may raise
are listed in 8.14.3.3, and "refused by policy" is not one of them, so the
error term below is our own choice. The nearest provision is 5.5.1, which
allows implementation-specific extensions. Our reading is that the standard
does not settle this case. *(The clause numbers 8.14.3, 8.14.3.3 and 5.5.1
also appear on Ulrich's syntax page. The directive clause, 7.4.2.4, has not
yet been checked against the standard text.)*

**What Clausal Prolog does today** (provisional, 2026-10-16). Inside the
sandbox, an `op/3` directive keeps its local effect: the file is read with
its own operator, so its text means what its author intended. This applies
to a module's exported operators and to those brought in by `use_module`,
for example `library(clpz)`'s `#=`. The directive does not write to the
process-wide table, so `current_op/3` does not list the operator and the
writers do not use it. `op/3` called as a goal is refused with a
`permission_error(access, private_procedure, op/3)`.

**The questions.**

1. May a restricted mode refuse `op/3` as a goal? If it may, which error
   term should it use? We raise `permission_error(access, private_procedure,
   op/3)`.
2. May a restricted mode make a text's `op/3` directives local to that
   text, separate from the global table? Or must a directive have exactly
   the goal's effect?
3. If an implementation may not change the global table, is it more
   conforming to refuse the directive as well, so the file does not load,
   than to accept it with a local effect only?
4. Does ISO/IEC 13211-2 (modules) say anything about operator scope that
   applies here?

## Q2. A `double_quotes` flag that cannot change at run time

**The situation.** The `double_quotes` flag decides what a double-quoted
token reads as: a list of chars, a list of codes, or an atom. Clausal Prolog
compiles a whole file before it runs. If the flag could change while a
program runs, the same `"..."` would mean different terms depending on when
it was read, and text read before and after the change would not agree. We
think that is a source of bugs, so the flag never changes at run time.

**What the standard says.** As we read Part 1, `double_quotes` is a
changeable flag (7.11.2.5) with the values `chars`, `codes` and `atom`, and
`set_prolog_flag/2` (8.17.1) may set it at any time. The new value then
governs the double-quoted tokens of everything read afterwards. Ulrich's
conformity row #170, `set_prolog_flag(double_quotes, chars)`, expects
success. *(The clause numbers are from memory and have not yet been checked
against the standard text.)*

**What Clausal Prolog does today** (ruled 2026-10-18).

- `set_prolog_flag(double_quotes, V)` as a goal raises
  `permission_error(modify, flag, double_quotes)` for every `V`, including
  the value already in force. So row #170 fails.
- In Clausal Prolog (`.clausal`), `"..."` always reads as chars. A
  `:- set_prolog_flag(double_quotes, chars).` directive is accepted but
  redundant. A directive asking for `codes` or `atom` is refused when the
  file loads, with the same error term.
- In an ISO Prolog (`.pl`) file, a `:- set_prolog_flag(double_quotes, V).`
  directive works as ISO says for the text below it: `chars` (the default),
  `codes` or `atom`.

**The questions.**

1. May a conforming processor treat `double_quotes` as fixed while a
   program runs, and settable only by a directive that governs the rest of
   the text being read? If it may, is `permission_error(modify, flag,
   double_quotes)` the right error term for the refused goal?
2. Should setting the flag to the value it already has succeed, as a no-op,
   even where changing it is refused? Row #170 is exactly that case.
3. May a dialect fix the flag at `chars` altogether, refusing even the
   directive for the other values, while staying a conforming processor in
   its ISO mode?

## Q3. The argument of `syntax_error/1`, and what the context may carry

**The situation.** When text does not read as a term, the error is
`error(syntax_error(Why), Context)`. Programs that read user input catch
it, and tools that load files report it. Clausal Prolog reads `.pl` and
`.clausal` files, `read_term/2,3`'s stream, `term_to_atom/2`'s text and
`number_chars/2`'s list with the same reader, so the question of what goes
in `Why` and in `Context` comes up on every surface at once.

**What the standard says.** 7.12.2 h makes the argument of `syntax_error/1`
implementation dependent, and 7.12.2 leaves the context implementation
defined. 8.14.1.3 e and 8.16.7.3 e only say that a syntax error is raised.
So the standard settles neither the vocabulary nor the context's shape.
*(These clause numbers have not yet been checked against the standard
text.)* Systems differ: Scryer has a small fixed vocabulary
(`incomplete_reduction`, `invalid_single_quoted_character`,
`missing_quote`, `unexpected_char`, `unexpected_end_of_file`,
`back_quoted_string`, `infinite_float`, `cannot_parse_big_int`,
`utf8_conversion_error`, ...) and a context `read_term/3:Line`; SWI-Prolog
uses descriptive atoms (`operator_clash`, `end_of_clause_expected`, ...) and
`context(PI, Message)`; SICStus and GNU Prolog have their own.

**What Clausal Prolog does today** (operator ruling 2026-10-24). The formal
term follows Scryer: for the same input, the same atom, measured row by row
against Scryer (`tests/iso/test_syntax_error_terms_scryer.py`). The context
is `context(PI, Details)` with `Details` a list of `line(L)`, `column(C)`
(1-based), and where the reader knows them `expected(What)` and
`found(Token)`:

| Text read | Clausal Prolog raises |
|---|---|
| `foo(a,` then the end of the text | `error(syntax_error(incomplete_reduction), context(read_term/3, [line(1), column(7), expected(end), found(end_of_file)]))` |
| `a :- b :- c.` | `error(syntax_error(incomplete_reduction), context(read_term/3, [line(1), column(8), expected(priority(1199)), found(priority(1200))]))` |
| `X = 'abc` then a newline | `error(syntax_error(invalid_single_quoted_character), context(read_term/3, [line(1), column(5), expected('\''), found('\n')]))` |
| `X = 1.0e400.` | `error(syntax_error(infinite_float), context(read_term/3, [line(1), column(5), found('1.0e400')]))` |
| `number_chars(N, [a])` | `error(syntax_error(unexpected_end_of_file), context(number_chars/2, [line(1), column(2), found(end_of_file)]))` |

A file that fails to load reports the same term (and a message with the
line, a caret, the expected token and, where it is certain, a hint such as
`a float needs a fraction: write 1.0e+9`).

**The questions.**

1. Is there a recommended or common vocabulary for `syntax_error/1`'s
   argument beyond Scryer's? Clausal follows Scryer's atoms, for
   portability of programs that match them, even where another atom
   would be more descriptive (`incomplete_reduction` for an operator
   priority clash or for `f()`).
2. May the context of a syntax error carry a position and the expected
   and found tokens, as above, while a conforming program is expected to
   match only `error(syntax_error(_), _)`? Is `context(PI, Details)` a
   reasonable shape, or is a bare predicate indicator preferable?
3. For a syntax error raised while a file is being loaded, which predicate
   indicator belongs in the context? Clausal and Scryer both say
   `read_term/3`, the predicate the loader reads with.
