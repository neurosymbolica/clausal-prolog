# The native `.pl` front end refuses a `?-` query with a message that shows internals

Filed/found: 2026-10-14, in review of the change that made the native front end the default for `.pl`. Low severity: both front ends refuse, so nothing regresses; only the wording got worse.

## What

A `?-` query inside a `.pl` file is refused at load by both front ends. The translator's message told the user what to do. Native's message prints the lowering's internal representation of the goal, `VarRef(i=0)`, and gives no advice.

## Repro

`q.pl`:

```prolog
p(1).
?- p(X).
```

`import q`, with `CLAUSAL_PL_FRONTEND` unset (native, the default):

```
SyntaxError: Cannot import q.pl: q.pl:2: Query is not lowered (a query `?-` is no clause): ('p', VarRef(i=0))
```

With `CLAUSAL_PL_FRONTEND=translator`:

```
SyntaxError: Cannot import q.pl: line 2: ?- p(X): a query in program text is not run on load (ISO 6.2: prolog text is clauses and directives). Remove it, or write the goal as a test/1 clause.
```

Scryer loads the clauses and prints nothing for the query.

## Where

`clausal/tools/iso_l3.py:1277` builds the native message from the lowered goal (`refuse(f"{kind} is not lowered ...")`).

## Expected

Native's message should show the goal as the user wrote it (`?- p(X)`) and say what to do, as the translator's does: a query in program text is not run on load; remove it, or write the goal as a `test/1` clause. Whether to keep refusing, rather than load the clauses and ignore the query as Scryer does, is a separate question for a ruling.
