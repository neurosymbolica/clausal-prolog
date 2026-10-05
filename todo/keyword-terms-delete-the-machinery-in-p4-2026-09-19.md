# Keyword terms: the SPELLING is refused; delete the machinery in P4

Ruled by the operator 2026-09-19: disable the surface now, delete the
machinery with the class in P4.  The refusal landed with the
`KEYWORD_ARGUMENT_SEVERITY` lint (`EmbedTransformer._lint_keyword_argument`);
this note is the deletion list.

## What is already gone

The spelling `point(x=1, y=2)` in a term or a clause head is a load-time
error.  The engine's own 34 sites in 17 files were migrated to positional
terms plus a declaration (`-private([point(x, y, z)])`) where the NAMES
mattered; a lowercase declaration names the fields lowercase, which is what
the keyword head used to do.  Downstream code had **zero** sites (every source file,
control: every bare-name keyword call there is a Python `def`/import/assign in
the same file).

Two keyword spellings are deliberately kept and tested: a `-directive`'s
options (`-specialize(solve, p, alias=q)`) and an EDCG hidden argument
(`p(L, _edcg_counter_in=0)`, `_`-led by construction).

## What P4 deletes

* `KWTerm` (`clausal/terms.py`) — the open-world keyword term, a THIRD term
  representation beside the cell and the class instance. 112 mentions in 24
  Python files, **33 in `clausal/logic/variables/_variables.c`** (so it wants
  the same landing as Task 5's 17 `PredicateMeta_type` arms: one C change, one
  rebuild, one `.so` swap).  With the spelling refused, nothing in the surface
  language constructs one; reflection and `copy_term` still carry arms.
* `Database._extract_param_names` and its `param_names` plumbing in
  `define_predicate` — its only feeder was a `KWTerm` head.  **This is the
  head-cell flip's only field-name dependency**, which is why the disable came
  first.
* `**kwargs` in `PredicateMeta.__call__` / `_clausal_head` — P4 deletes the
  class anyway (R-P2-2).

## What P4 must DECIDE, not assume

`clausal/logic/builtins/keyword_ops.py` (177 lines): `vary/3`, `extend/3`,
`unbound_keys/2`, `signature/3`.  These address fields BY NAME and are
**unaffected by the spelling refusal** — the names come from the declaration.
They are not keyword-term machinery, they are field-name reflection, and
`signature/3` already reads the Database rather than a term.  Keep or delete
on their own merits.

`extend/3` is the exception: it grows a term a field it was not declared with,
which only a `KWTerm` can do.  It goes with `KWTerm`.

## Already red, and owned by P2 Task 4 (not by this note)

`vary/3` and `unbound_keys/2` read a term's fields through
`term_field_names`, so on the P2 branch they answer nothing for a term in
BODY position, which is a cell now (measured at the Task 3 checkpoint
`20b32550`: `tests/fixtures/builtins_keywords.seam` and
`tests/fixtures/docs/keyword_preds_examples.seam` read 6 failed / 3 passed
before the disable and the identical 6 after it).  The sweep's fix for that
file is the ordinary rewrite 2: `compound_cell_shape` + `db.signature_for`.
