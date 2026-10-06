# clausal/tools/ — Prolog front ends, translators and developer tools

Everything that reads or writes Prolog text lives here: the ISO tokenizer
(toklex) and reader, the native front end that compiles `.clausal` and (opt-in)
`.pl` files, the older `.pl` -> seam translator, the seam -> `.pl` exporter, and
a handful of developer CLIs. All front ends end in the same place: the
transformed Python AST the seam compiler (`clausal/templating/term_rewriting.py`,
`EmbedTransformer`) produces, so from `exec` onward every surface runs the same code.

Up: [../AGENTS.md](../AGENTS.md)

## Which front end compiles what

| Source | Loader (in `clausal/import_hook.py`) | Path through this folder |
|---|---|---|
| `.clausal` (Clausal Prolog) | `NativePrologLoader`, always | `prolog_reader` -> `iso_l3` (+ `iso_l3_directives`) |
| `.pl` | `PrologLoader` by default; `NativePrologLoader` when `CLAUSAL_PL_FRONTEND=native` | default: `prolog_to_clausal` -> seam text -> `EmbedTransformer` |
| `.seam` | `PredicateLoader` | not here (seam compiler is in `clausal/templating/`) |

## Map

**Reading ISO text (shared by both front ends)**

| File | What it is |
|---|---|
| `toklex/` | Spec-driven lexer generator; `specs/iso.toklex.pl` *is* the ISO token grammar. See [toklex/AGENTS.md](toklex/AGENTS.md). |
| `prolog_tokenizer.py` | `tokenize()`: thin shim mapping toklex tokens to `Token`/`TokenType` via `_KIND_MAP`. No lexical rules live here. |
| `prolog_operators.py` | `OperatorTable`: ISO defaults plus SWI/Scryer/GNU/Trealla tables (`scryer_builtin_default()` is the reader's default). |
| `prolog_parser.py` | Pratt parser: tokens -> `prolog_ast` P-nodes; applies `op/3` mid-file. `parse()`, `parse_term()`, `PrologParser`. |
| `prolog_ast.py` | Frozen-dataclass Prolog AST (`PAtom`, `PCompound`, `PClause`, `PModule`, ...), visitors, builders. |
| `prolog_reader.py` | The "§1c contract": `PrologReader` (incremental, item-at-a-time over toklex) and `transform_term` (P-tree -> functor-first tuple cells, `VarRef`s, spans). Items: `Clause`, `Directive`, `DCGRule`, `Query`, `SyntaxIssue`. Must not import the engine (`clausal.logic.*`). |

**Native front end (`.clausal`, and `.pl` with `CLAUSAL_PL_FRONTEND=native`)**

| File | What it is |
|---|---|
| `iso_l3.py` | Lowers reader items to the seam's transformed AST: clauses, control constructs, `m:G`, `if_/3`, `{C}`, DCG rules. `lower_source()` is what the loader calls. Refuses (raises `LoweringRefused`) `!`, `->`, `*->`, `initialization/1`, queries, unknown directives — never skips. |
| `iso_l3_directives.py` | ISO directives -> the seam's own directive handlers (`module/2`, `use_module/1,2`, `dynamic`, `table`, `op`, `set_prolog_flag`, `end_module`, `constructors`, constants). Holds `_BUILTIN_LIBRARIES` / `_LIBRARY_MODULES` (what `library(L)` means), library operators (`CLPZ_OPS`, ...), the `library(...)` facade lookup (`_library_facade`) and the Python-import refusals. |

**Translators and exporter**

| File | What it is |
|---|---|
| `prolog_to_clausal.py` | `.pl` -> seam text (the default `.pl` front end, "translator"). `prolog_to_clausal(src, dialect=...)`. Has its own `_BUILTIN_LIBRARIES` / `_LIBRARY_TO_MODULE` tables. |
| `clausal_to_prolog.py` | seam -> Prolog AST -> `.pl` text (the exporter). `clausal_source_to_prolog()`, `emit_term/item/module`. Raises `UntranslatableConstructError`. |
| `prolog_dialect.py` | `Dialect` (`iso`, `swi`, `scryer`, `scryer_reader`, `gprolog`, `trealla`): operator table, library map, CLP module, how constants cross; name maps (`BUILTIN_NAME_MAP`, var-name conversion). |
| `prolog_preludes/` | `clausal_constants_scryer.pl`, `clausal_constants_trealla.pl`: term_expansion preludes an exported file loads for constants under an `expansion` dialect (referenced from `prolog_dialect.py`). |
| `translate.py` | CLI: `python -m clausal.tools.translate in.seam --to scryer` / `in.pl --to clausal`. `--to clausal` writes **seam** text, not Clausal Prolog. Dialects offered: iso, swi, scryer. |

**Generators, ratchets, developer CLIs**

| File | What it is |
|---|---|
| `gen_library_facades.py` | Generates `clausal/library/*.seam` and `clausal/_py_facades.py` from `clausal/modules`. `--check` exits 1 on drift. See [../library/AGENTS.md](../library/AGENTS.md). |
| `transition_census.py` + `transition_census_baseline.json` | "Count must not grow" ratchet for `\+`, `once/1`, `forall/2`, `memberchk/2`, `findall(_,G,[])`, `make_quantity/3` across `clausal/ tests/ docs/`. `--update` re-baselines. Tested by `tests/test_seam_transition_constructs.py`. |
| `doc_snippet_check.py` | Shared check functions for `tests/test_doc_snippet_*.py` and per-package doc tests. |
| `dump_transformed.py` | Dump the transformed AST of seam files as Python (`__transformed__/`). |
| `visualize.py` | Pretty-print a compiled predicate's generated Python. |
| `clear_pycache.py` | Remove `__pycache__` dirs (stale bytecode). |
| `eq_analysis/` | `instrument.py`: records which mode each `==` site runs in (is/=:=/#=/==); used by `tests/test_eq_mode_instrument.py`. |

## Where to start

- A `.clausal`/native `.pl` compile bug: `iso_l3.lower_source` -> `lower_items` -> `_ClauseLowering`; directives in `iso_l3_directives.py` (the `_DIRECTIVES` table maps `(name, arity)` to `_module`, `_use_module`, ...).
- A `use_module(library(X))` resolution question: `iso_l3_directives._use_module` / `_use_library` / `_library_facade`; the translator's equivalent is in `prolog_to_clausal.py` (search `_LIBRARY_TO_MODULE`).
- A tokenizing/syntax bug: edit `toklex/specs/iso.toklex.pl`, not Python. A parse (operator) bug: `prolog_parser.py` / `prolog_operators.py`.
- An export bug: `clausal_to_prolog.py` plus the target `Dialect` in `prolog_dialect.py`.
- Tests: `tests/iso_l3/` (native front end), `tests/toklex/` (lexer + reader), `tests/test_prolog_*.py` (translator/exporter/dialects).

## Gotchas

- Two `.pl` front ends coexist. Library tables exist in both (`iso_l3_directives._BUILTIN_LIBRARIES`/`_LIBRARY_MODULES` and `prolog_to_clausal._BUILTIN_LIBRARIES`/`_LIBRARY_TO_MODULE`); `tests/iso_l3/test_l3_library_facades.py` reads both. Change both.
- Bytecode cache keys hash engine sources: the translator files and `toklex/specs/iso.toklex.pl` are in `_COMPILATION_FILES`, and `iso_l3.py`, `iso_l3_directives.py`, `prolog_reader.py` are in `_NATIVE_FRONTEND_FILES` (both in `clausal/import_hook.py`). Moving or renaming one of these files means updating those lists.
- Names say "clausal" where they mean **seam**: `prolog_to_clausal`, `clausal_to_prolog`, `clausal_source_to_prolog`, `--to clausal`. These predate the 2026-10-02 extension flip.
- Refusal is the rule in the native front end: an unsupported construct must raise `LoweringRefused`/`DirectiveRefused` with a span, never be dropped.
- `prolog_reader.py` must stay engine-free (no `clausal.logic` imports); it builds atom/string cells inline.

## Docs

[../../docs/clausal_prolog.md](../../docs/clausal_prolog.md),
[../../docs/importing_prolog.md](../../docs/importing_prolog.md),
[../../docs/prolog_translation.md](../../docs/prolog_translation.md),
plans: [../../implementation_plans/native-iso-reader-step2-2026-09-29.md](../../implementation_plans/native-iso-reader-step2-2026-09-29.md),
[../../implementation_plans/toklex-token-formalism-design.md](../../implementation_plans/toklex-token-formalism-design.md).
