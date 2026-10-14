# catch(fail, C, R) does not compile; the CLP(Q) refusal checks ignore hook_dispatch_depth()

Found in the Fable review of the C changes in a8b6a077 and a3a62e67. Both items are important and pre-existing.

1. **Under the trampoline strategy, `catch(fail, C, R)` fails to compile.** So do `catch(false, …)`, `catch_error(fail, …)` and `not catch(fail, …)`. A raw `ValueError: empty body on Try` escapes from `load_clausal_module`. The cause: `_lower_inner_trampoline` returns `[]` for `fail`, and `_compile_catch_impl` puts that list into `ast.Try(body=…)`. The one-line fix is `or [ast.Pass()]`. `-shallow` handles this case correctly, and Scryer simply fails the goal.
2. **`hook_dispatch_depth()` landed without its in-repo consumer.** The refusal checks at clausal/logic/clpq/attributes.py:70 (R30) and holzbaur.py:261 and :318 (R28c) still test only `trail.hooks_running`, so the fresh-trail bypass the feature was built to close is still open. Move those checks to `hook_dispatch_depth() > 0`. Then flip `tests/clpq_port/test_refused_inside_a_hook.py::test_a_fresh_trail_inside_a_hook_is_not_seen_by_the_check`, which currently pins the bypass.
