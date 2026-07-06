# fix(A10-F003): EDCG sequences mis-thread state through non-EDCG (plain DCG) nonterminals

**Problem.** In `_rewrite_edcg_body` (clausal/templating/term_rewriting.py:1999-2036),
the non-EDCG `case Name` / `case Call` branches emit
`callee(in_var, out_var)` using the accumulator's FINAL out var and set the
new state to `(out_var, out_var)`. In a sequence, a non-last plain-DCG callee
therefore consumes straight to the rule's final output, and every following
element degenerates to `out = out`. `-edcg_pred(p, 0, [dcg])` +
`p >> (a, b)` (plain DCG `a`, `b`) yields 0 solutions on every input, while
the plain-DCG control `p >> (a, b)` works. `_rewrite_edcg_subcall` (EDCG
callees) mints a fresh mid var correctly — the non-EDCG branches just don't.

**Repro/test.** test_10_rewriting_import.py::test_F003_edcg_sequence_of_plain_dcg_nonterminals
(xfail); guards ::test_F003_guard_plain_dcg_sequence, ::test_F003_guard_edcg_accumulator_with_plain_call.

**Fix.** In both non-EDCG branches, mirror `_rewrite_edcg_subcall`: mint
`mid = f"_edcg_dcg_{counter}_"`, emit `callee(in_var, mid)`, set
`new_acc_states["dcg"] = (mid, out_var)`. The rule-level/sequence closers
already unify the final mid with the head's out var.
