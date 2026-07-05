# Make "one goal per line" a Clausal style standard (+ a formatter)

**Requested:** 2026-07-04. The EU corpus adopted "every parenthesised clause body lists one goal per
line" as a hard convention (readability + minimal diffs + easier for the local models to generate);
the user wants it standard in **Clausal** itself, not just the corpus.

## The rule
A `<- ( ... )` body lists exactly ONE goal per line; single-goal bodies stay on one line.
```clausal
p(X, V) <- (
    a(X, Y),
    Y > 0,
    V is ok
)
q(X) <- r(X)                     # single goal — one line
```
Only TOP-LEVEL body conjunction commas break; commas inside `findall(...)`, list literals `[...]`,
nested compounds, and strings stay put.

## Asks
1. **Document it** in the Clausal style guide (`docs/` — alongside cut-free / ALL_CAPS / `==`-vs-`:=`).
2. **Ship a formatter** — `clausal fmt` (or a `tools/` script) that applies it engine-side, so it's
   available to every Clausal project, not just this corpus. Reference impl (whitespace-only,
   idempotent, depth+quote aware): `clausify-domains/_tools/format_one_goal_per_line.py`. A proper
   engine formatter could work off the parsed AST rather than regex, and also normalise clause
   separation (facts end `,`; rules `)` no trailing comma; blank line between clauses).
3. Optionally a lint (advisory) flagging multi-goal-on-one-line bodies.
