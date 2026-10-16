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
