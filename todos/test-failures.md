# Test Failures (2026-03-25)

Full suite: 6,873 passed, 804 skipped, 364 failed → after installing deps: ~330 fixed, ~34 remaining.

## sklearn (1 failure)

- [ ] `tests/fixtures/sklearn_basic.clausal::param from est term` — no solutions

## sympy (1 failure)

- [ ] `tests/fixtures/sympy_basic.clausal::<load>` — `unsupported operand type(s) for +: 'clausal.logic.variables.AttVar' and 'int'`

## spacy Python tests (14 failures)

The `.clausal` fixture tests all pass; these are Python-level `test_spacy_module.py` failures:

- [ ] `TestModelRegistry::test_current_model_enumerate`
- [ ] `TestModelRegistry::test_current_model_check_known`
- [ ] `TestModelRegistry::test_current_model_check_unknown`
- [ ] `TestTokenPredicates::test_token_2_yields_multiple`
- [ ] `TestTokenPredicates::test_token_2_first_is_apple`
- [ ] `TestTokenPredicates::test_token_3_by_index`
- [ ] `TestTokenPredicates::test_token_3_out_of_range`
- [ ] `TestTokenPredicates::test_token_3_iterate_with_index`
- [ ] `TestNERPredicates::test_entity_2_yields_entities`
- [ ] `TestNERPredicates::test_entity_3_filter_by_label`
- [ ] `TestNERPredicates::test_entity_3_unknown_label_empty`
- [ ] `TestSentencePredicates::test_sentence_2_yields_sentences`
- [ ] `TestNounChunks::test_noun_chunk_2_yields_chunks`
- [ ] `TestNounChunks::test_noun_chunk_has_keys`

## Prolog golden snapshots (6 failures)

Generated Prolog output doesn't match golden files:

- [ ] `test_prolog_golden.py::test_golden_snapshot[edge_graph]`
- [ ] `test_prolog_golden.py::test_golden_snapshot[fibonacci]`
- [ ] `test_prolog_golden.py::test_golden_snapshot[dcg_grammar]`
- [ ] `test_prolog_golden.py::test_golden_snapshot[meta_test]`
- [ ] `test_prolog_golden.py::test_golden_snapshot[clpfd_queens]`
- [ ] `test_prolog_golden.py::test_golden_snapshot[iso_type_checking]`

## Docs code blocks (10 failures)

Compile errors in inline code examples:

- [ ] `docs/constraints.md::L331`
- [ ] `docs/constraints.md::L350`
- [ ] `docs/io.md::L228`
- [ ] `docs/metainterpreters.md::L218` — `tree path(a,c) transitive` test failure
- [ ] `docs/metainterpreters.md::L241` — compile error
- [ ] `docs/random.md::L90`
- [ ] `docs/random.md::L100`
- [ ] `docs/scipy_constants.md::L9`
- [ ] `docs/scipy_linalg.md::L264`

## Examples (1 failure)

- [ ] `clausal/examples/symbolic_diff.clausal::<load>` — load failure
