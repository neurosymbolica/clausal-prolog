# clausal/templating/ — the seam compiler (source text -> Python AST)

Up: [../AGENTS.md](../AGENTS.md)

This folder lowers seam (`.seam`) source, which is Python syntax, into the Python
module the import hook compiles to bytecode. `ast.parse` reads the file; then
`EmbedTransformer` rewrites every clause, fact, directive, `--term` seam and DCG
rule into *constructor code*: calls that build `clausal.pythonic_ast.nodes`
("simple_ast") nodes when the module runs. Clause bodies stay DATA here. The
logic compiler (`clausal/logic/compiler_v2.py` `compile_module`, see
[../logic/AGENTS.md](../logic/AGENTS.md)) turns them into code after the module
body has run. The name "templating" is historical: the `@{}` template feature is
the smallest part of the folder.

Who runs it:
- `clausal/import_hook.py` `transform_seam_source` (`PredicateLoader`) for `.seam` files.
- `.pl` files through the translator front end (`PrologLoader`: `prolog_to_clausal`
  -> seam text -> `EmbedTransformer`).
- `clausal/reflection.py` (`reify=True`), `clausal/seam_audit.py`,
  `clausal/tools/dump_transformed.py`, and helper imports from
  `clausal/tools/iso_l3_directives.py` and `prolog_to_clausal.py`.
- `.clausal` (Clausal Prolog) files do NOT go through here as a whole. The native
  front end (`tools/iso_l3.py`) lowers them straight to AST.

## Map

| File | What it is |
|---|---|
| `term_rewriting.py` | The compiler, about 11.5k lines, no module docstring. It holds two transformers and the helper functions for them (sections are marked with `# ─── ... ───` banners). |
| `desugar.py` | `desugar_surface`: a pure, syntax-only `ast`->`ast` pass that expands surface sugar (`P.key` -> `P[key]`). It is shared with an external SMT prover, so it has no engine imports and no semantics. |
| `quote_map.py` | Recovers `'x'` vs `"x"` (an atom vs a mode-dependent string), which `ast` loses. The map is keyed by source position from `tokenize`. |
| `parser.py`, `compiler.py` | `@{}` template functions. `parser.is_template_func` detects them and `compiler.compile_template_func` turns them into AST-building functions. `EmbedTransformer.visit_FunctionDef` calls both. |

Inside `term_rewriting.py` (find these with `grep -n "^class \|^def "`):
- `TermTransformer` turns one expression (head, goal or term) into constructor AST.
  Its `visit_<Node>` methods are the per-syntax rules: `visit_Name` decides between a
  variable and an atom, `visit_Call` handles compounds and builtins,
  `visit_Compare` handles `<-` inside expressions, and `visit_Constant` handles
  strings and quotes.
- `EmbedTransformer` works at module and statement level. `visit_Module` is the
  entry point. `visit_Expr` handles facts (`head,`), rules (`head <- body`) and
  DCG rules (`>>`). Directives are dispatched through `_handle_directive` to
  `_handle_<name>_directive` (`module`, `import_from`, `private`, `hide`,
  `double_quotes`, `translations`, `specialize`, EDCG, ...). `visit_With`
  handles the `with --{}` / `with ~~{}` block forms.
- Free-function sections cover arrow (`<-`) detection, the logic-variable naming
  rules (`_is_logic_var_name`), read-once dict-read lowering
  (`_lower_dict_reads`), DCG rewriting (`_rewrite_dcg_body`), EDCG rewriting,
  unit/currency literals, and the lints (TitleCase, keyword arguments, scale
  names).

## Where to start

- See what a file lowers to: `python -m clausal.tools.dump_transformed FILE.seam`.
- New or changed surface syntax: find the `visit_*` method for the Python node
  that the construct parses as. If it is pure spelling sugar, put it in
  `desugar.py` and keep that file's rules (pure, keeps source positions, returns
  any shape it does not handle unchanged).
- New directive: add a `_handle_<name>_directive` and its dispatch in
  `_handle_directive`. Module-level items it records are `clausal.pythonic_ast.nodes`
  item classes, imported at the top of `term_rewriting.py`.
- Tests: `tests/test_desugar.py`, `tests/test_quote_map.py`,
  `tests/test_template_compiler.py`. About 50 other test files import
  `term_rewriting` (`grep -rl term_rewriting tests`).
- Docs: [syntax](../../docs/syntax.md), [import](../../docs/import.md),
  [compiler](../../docs/compiler.md), [dcg](../../docs/dcg.md),
  [caching](../../docs/caching.md).

## Gotchas

- **Bytecode cache key.** `templating/` and `pythonic_ast/` are listed in
  `_COMPILATION_ROOTS` in `clausal/import_hook.py`, so any edit here changes the
  `.pyc` fingerprint by itself. If you make the transformer read a NEW data table
  from another file, add that file to `_COMPILATION_FILES` and add a row to
  `tests/test_pycache.py::test_every_module_that_decides_bytecode_is_fingerprinted`.
- `tests/test_reflection_render.py` parses this file's source for
  `node_ast("<ClassName>", ...)` calls and reads the `BINOP_CLS`/`UNARYOP_CLS`/
  `BOOLOP_CLS`/`CMPOP_CLS` tables. Emit body nodes through `node_ast` with a
  literal class name, or reflection's renderer coverage check will miss them.
- `ast` column offsets are UTF-8 BYTE offsets and `tokenize` columns are
  characters. `quote_map.py` converts between them; arrow detection reads raw
  source columns. Keep source positions on every node you create (`replace`,
  `pos_ast` helpers).
- `desugar._is_logic_var_name` deliberately duplicates
  `term_rewriting._is_logic_var_name`, so that `desugar.py` imports nothing from
  the engine. Change both together.
- Warning classes live in `clausal/lint_warnings.py` and are re-exported here.
  Define new ones there, not here.
- Docstrings and comments in this folder often say `.clausal` where they mean
  seam source, because the 2026-10-02 extension flip came later. Read
  `.clausal` in this folder as `.seam` unless the text is about Clausal Prolog.
