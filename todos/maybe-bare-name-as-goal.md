# Bare uppercase name as zero-arity goal doesn't compile

The docs originally used `Maybe` (bare name, no parens) as a zero-arity goal
in clause bodies:

```clausal
maybe_print(X) <- (Maybe, Writeln(X))
```

The compiler rejects this because a bare uppercase name is treated as a logic
variable (`LoadName`), not a zero-arity predicate call. The docs were changed
to `Maybe()` as a workaround.

This may be intentional (uppercase = variable is a core Clausal rule), or it
may be a missing convenience feature — Prolog allows `maybe` as a bare goal.
If it's intentional, the docs were just wrong. If bare zero-arity goals should
work, the compiler's `compile_goal_trampoline` needs to handle `LoadName`
nodes that resolve to known predicates.
