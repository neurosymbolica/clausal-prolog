# Adapter text boundary: census leftovers (2026-10-04)

**Status: DONE 2026-10-04 (commits b0d33c54..e156e5f1, 50512517..502b5b86, 3b0bab17).** Free-form adapter outputs are strings, adapter inputs accept an atom or a string, and spacy `shape` is ruled an atom. The provenance `aggregate/4` input is moot while clausal-provenance is disabled (fd92cb9e). Pinned in packages/*/tests/test_*_free_form_outputs*.py and tests/test_adapter_bad_input_text_iso.py.

The 2026-10-04 ruling ("atom out, text in": a SYMBOLIC name an adapter
returns crosses as an atom, free-form strings stay text) was applied on
feat/package-triage-rulings-2026-10-04 to every site where a symbolic name
crossed as TEXT. The same census (static read of every adapter + a dynamic
`text_result` trace over the package suites) found these, which the ruling
does not settle and which were NOT changed:

## Free-form strings that cross as ATOMS (the opposite mismatch) -- DONE

**Done on feat/adapter-free-form-strings-2026-10-04** (ruled 2026-10-04,
D12: Reading A -- an adapter is its own entry point; free-form outputs are
strings, identifiers/keys/names stay atoms; the `++` escape is unchanged).
One Breaking commit per package: sympy (printers + the `str(expr)`
fallback), yaml (scalar VALUES and written documents; keys stay atoms),
scipy (`unit/2`, `lookup/4` unit, integrate/optimize `message`; constant
names stay atoms), opencv (`haar_cascade_path/2` path), spacy (token /
entity / chunk text, `head_text`, sentences; `lemma` and labels stay
atoms). torch `named_*` paths were ruled atoms: unchanged. Still open:
spacy `shape` (not covered by the ruling) -- see
todo/adapter-free-form-outputs-as-strings-needs-ruling-2026-10-04.md.

The census as it stood:

Adapters that unify a plain `str` without `text_result`:

- clausal-sympy `sym_str/2`, `latex/2`, `pretty/2`, `math_ml/2`, and the
  `str(expr)` fallback in `_from_sympy_ctx` (printed representations).
- clausal-spacy token `.text` / `head_text` / `lemma`, `sentence/2`,
  `sentence_list/2` (POS/tag/dep/label are symbolic and correctly atoms).
- clausal-yaml `write/2`, `write_all/2` output, and scalars read in.
- clausal-scipy `scipy_integrate` `message`; `scipy_constants` unit
  strings and constant names (names contain spaces).
- clausal-opencv `haar_cascade_path/2` (a path); clausal-torch `named_*`
  names (module paths such as `0.weight`; arguably symbolic).

Question for a ruling: should these become text (a Breaking change per
package), or is "free-form stays text" only a rule for NEW adapters?

Ruled 2026-10-04 (D11, U2 b): yes, as strings -- on condition that it does
not conflict with the Python-boundary spec. It does read two ways, so it is
not built: see
todo/adapter-free-form-outputs-as-strings-needs-ruling-2026-10-04.md.

## Inputs that reject text (violate "text in") -- FIXED by U2(a)

All of these were fixed on feat/package-triage-rulings-2026-10-04 (U2 a,
one commit per package, each with a regression test): the shared
`_helpers._text_arg` / fact table, torch, scipy, sympy, yaml, spacy,
sklearn, opencv. Inputs accept an atom or a string.

The list as it stood:

- `str(deref(x))` on an argument turns text into the repr
  `"('$chars', 'x')"`: clausal-spacy (process/3 text, entity/3 label,
  similarity/4), clausal-sklearn (10 sites), clausal-torch `save/2`,
  `load/2`, clausal-opencv `imwrite/2,3`, clausal-scipy spatial rotation
  method and sparse format/order.
- `_helpers._fact_table_2` (and the copy in clausal-torch torch_nn.py)
  reads the name with plain `deref`, so a TEXT name never matches a fact
  (jax nn/optax/random/scipy/flax names, torch layers/distributions,
  opencv color/threshold/interpolation/border/morph/haar/video props).
- clausal-torch `dtype_info/3` key; clausal-scipy constants `lookup/4`,
  `find/2`; clausal-sympy `sym/2` (`isinstance(name, str)`), and
  `_to_sympy_ctx` reads the text carrier as the compound `'$chars'(x)`;
  clausal-provenance `aggregate/4` op; clausal-yaml `write*/2` pass nested
  text to `safe_dump` as tuples.

These are bugs under the existing spec (§9.4: a wrapper that takes text
accepts an atom or a string) rather than ruling questions; each wants a
`to_text` at the read and a regression test.

## Borderline, decided as SYMBOLIC (flag if wrong)

- jax/torch `device/2` (`cpu:0`, `TFRT_CPU_0`, `cuda:0`): a device name.
- opencv `fourcc/2` backward (`MJPG`): a codec tag.
- py.sqlite `current_connection/1`: an alias, like an ISO stream alias.
- py.logging `get_level/2`: a LOWERCASE atom, `warning` -- the spelling
  `set_level/2` takes (U3, ruled 2026-10-04; it was `'WARNING'`); custom
  level names lowercase too, and a bound level is read in either case.

Kept as TEXT: py.sqlite `column/4` type ("VARCHAR(20)"), table and column
names (rows ruling R15); py.url `parse/2` scheme (spec §9.4 comment).
