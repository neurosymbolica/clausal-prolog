# clausal/tools/toklex/ — the spec-driven lexer behind every Prolog reader

toklex compiles a token grammar written as Prolog terms (`specs/*.toklex.pl`)
into a DFA and runs it. The public ISO tokenizer
(`../prolog_tokenizer.py`) and the incremental `PrologReader`
(`../prolog_reader.py`) both drive the lexer built from
`specs/iso.toklex.pl`, so **lexical rules live in the spec file, not in Python**.
Design: [../../../implementation_plans/toklex-token-formalism-design.md](../../../implementation_plans/toklex-token-formalism-design.md).

Up: [../AGENTS.md](../AGENTS.md)

## Pipeline

```
specs/iso.toklex.pl --_bootstrap reader--> spec.py (Spec: classes, token/trivia rules, RE IR)
   --> automaton.py (Thompson NFA -> subset DFA over a charset.Partition)
   --> annotate.py (Lexer: extend sets, follow map, backup bound, builders)
   --> driver.py IncrementalLexer   (reference driver)
       regex_target.py RegexLexer   (fast path: one Python `re` pattern)
       dcg.py render_dcg            (standalone Prolog DCG tokenizer, for Scryer)
```

`load_lexer(name="iso")` in `__init__.py` does spec -> `Lexer`, cached.

## Map

| File | What it is |
|---|---|
| `__init__.py` | `load_lexer(name)` (reads `specs/<name>.toklex.pl`); re-exports `IncrementalLexer`, `Tok`, `EOF`, `NEED_MORE`. |
| `specs/iso.toklex.pl` | The ISO token layer actually used by the readers (`'_'` digit groups, nested block comments as a driver flag). |
| `specs/clausal.toklex.pl` | ISO base copied verbatim plus deltas (reserves US `0x1F`, the hidden separator). Loaded only by tests today (`tests/toklex/test_clausal_dialect.py`, `test_regex_target.py`). |
| `spec.py` | Spec IR (`Lit`, `Seq`, `Alt`, `Star`, `ButNot`, `TokenRule`, `TriviaRule`) and the term loader; `SpecError`. |
| `_bootstrap.py` | Frozen copy of the ORIGINAL hand-written tokenizer, used only to read `.toklex.pl` files (avoids the spec reading itself). |
| `charset.py` | Codepoint interval sets and alphabet partitioning. |
| `automaton.py` | RE -> NFA -> DFA; language subtraction (`ButNot`); no minimization (deliberate). |
| `annotate.py` | DFA -> runnable `Lexer`; proves bounded backup or raises `UnboundedBackupError`. |
| `builders.py` | Token value builders (escape decoding, numbers); a bit-parity mirror of the old tokenizer's escape rules. |
| `driver.py` | `IncrementalLexer`: maximal munch, `followed_by`, bounded pushback, trivia/`Glue`, error tokens, `NEED_MORE` suspension. The semantic authority. |
| `regex_target.py` | `RegexLexer`: same surface as `IncrementalLexer`; raises `SpecError` for specs it cannot render, and callers then fall back to the driver. |
| `decode.py` | `Utf8Feeder`: incremental bytes -> str feed with invalid-UTF-8 error tokens. |
| `dcg.py` | `render_dcg(lexer)`: emits a Prolog DCG tokenizer from the same DFA (v1: chars mode, no value builders). |

## Common tasks

- Change what a token is (quoting, escapes, numbers, comments): edit `specs/iso.toklex.pl`. If you add a token **kind**, also map it in `../prolog_tokenizer.py` `_KIND_MAP` (also used by `../prolog_reader.py` `_to_compat_token`).
- A lexer behaves differently through `tokenize()` vs `RegexLexer` vs `IncrementalLexer`: the driver is the reference; `tests/toklex/test_regex_target.py` is the differential.
- Tests: `tests/toklex/` (`test_driver.py`, `test_iso_spec.py`, `test_parity.py` vs the old tokenizer, `test_reader_*.py` for `PrologReader`).

## Gotchas

- Do not read spec files with `prolog_tokenizer.tokenize` — that tokenizer is generated from the spec. `spec.py` must keep using `_bootstrap.bootstrap_tokenize`; `_bootstrap.py` is frozen.
- `specs/iso.toklex.pl` is hashed into the bytecode cache key (`_COMPILATION_FILES` in `clausal/import_hook.py`); editing it invalidates cached compiled `.pl`/`.clausal`.
- `clausal.toklex.pl`'s reserved char must equal `clausal.logic.atoms.HIDDEN_SEP` (`"\x1f"`); the two are kept in sync by hand. Its ISO part is a copy of `iso.toklex.pl` — an ISO spec edit does not reach it automatically.
- `test_parity.py`'s corpus sweep reads `/workspace/scryer-prolog/src/lib/*.pl`, outside the repo.
