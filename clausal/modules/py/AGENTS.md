# clausal/modules/py/ — Python-library wrappers (py adapters)

One module per wrapped Python library: `py.<name>` in seam
(`-import_from(py.json, [parse])`), `py/<name>` in a `.pl`
(`:- use_module(py/json, [parse/2])`), and `library(<name>)` or
`library(py_<name>)` in Clausal Prolog via the generated facades. Third-party
wrappers (torch, sympy, jax, opencv, scipy, sklearn, spacy, yaml) live in
`packages/clausal-*/clausal/modules/py/` and join this package's `__path__`
(site-packages and editable installs; see `__init__.py`).

Up: [../AGENTS.md](../AGENTS.md)

## Map

| File | What it is |
|---|---|
| `__init__.py` | The adapter base and shared conventions: `ModulePredicate`, `simple_to_trampoline`, text helpers (`to_text`, `require_text`, `text_or_str`, `text_result`, `unify_result`, `symbol`), option lookup (`option`), error raisers (`expect_type`, `raise_domain_error`, `raise_os_error`, `raise_http_status`, `raise_syntax_error`), `_import_stdlib`. |
| `_helpers.py` | Dispatch builders shared by wrappers (many used by the extension packages): `_pred(name, (arity, fn), ...)`, `_pure`, `_bidir_2`/`_bidir_3_*`, `_check_*`, `_property_2`, `_fact_table_2`; re-exports `to_python` (alias `_deep_deref`). |
| `csv.py`, `datetime.py`, `files.py`, `json.py`, `logging.py`, `os.py`, `process.py`, `random.py`, `re.py`, `sqlite.py`, `uuid.py` | Stdlib wrappers; each docstring lists its predicates and type mapping. |
| `hash.py`, `hmac.py`, `pbkdf2.py` | hashlib / hmac wrappers (doc: `docs/crypto.md`). Smallest complete examples of the pattern below. |
| `http.py`, `tcp.py`, `url.py` | urllib.request, socket, urllib.parse wrappers. |
| `units.py`, `imperial.py` | Star-import shims of `../units.py` / `../imperial.py` (back-compat). |

## How an adapter is written (see `hash.py`)

1. Import the wrapped library with `_lib = _import_stdlib("hashlib")`, not a plain
   `import` — a wrapper named like the library (`uuid.py`, `re.py`) would otherwise import itself.
2. Write one generator per predicate/arity in "simple mode":
   `def _hash_3(algorithm, data, hex_out, trail, k):` — `deref` the inputs, convert
   text with `require_text`/`to_text` (never `str()` a term), compute, then
   `if unify(out, text_result(value), trail): yield None` once per solution.
3. Errors: wrong type -> `expect_type(...)`/`type_error`, unbound -> instantiation error,
   out of range -> `raise_domain_error(...)`. A legitimate "no" just yields nothing.
   Any other Python exception escaping the dispatch becomes a catchable
   `python_error_term` (`_catchable_dispatch`).
4. Export a public module attribute per predicate name, registering each arity:
   ```python
   hash = ModulePredicate("hash")
   hash._register(3, simple_to_trampoline(_hash_3))
   ```
   The arity excludes `trail`. A raw trampoline function
   (`this_generator, _proceed, _fail, _catcher, *args`, last arg the trail) can be registered directly instead of a wrapped simple fn.

There is no registry to edit: `py.X` resolves via `ModulesFinder`
(`clausal/import_hook.py`), and `clausal.logic.solve.module_signatures` reads
the public adapters and their `_dispatch_fns` arities. Private names (`_x`) are
not exported.

## After adding or changing a wrapper

- Regenerate facades: `python -m clausal.tools.gen_library_facades` (writes `../../library/<name>.seam` and `../../_py_facades.py`). If the name is a Scryer library name (`clausal.library.SCRYER_LIBRARIES`), the facade is `library(py_<name>)`.
- Optional bare-name alias for seam imports: `_IMPORT_ALIASES` in `clausal/templating/term_rewriting.py`.
- Tests: `tests/test_<name>_module.py` (e.g. `test_json_module.py`, `test_crypto_modules.py`, `test_date_time.py`, `test_regex.py`); facade/import behavior in `tests/iso_l3/test_l3_library_facades.py` and `tests/iso_l3/test_l3_py_module_imports.py`.
- User docs: `docs/<topic>.md` (e.g. [json](../../../docs/json.md), [date_time](../../../docs/date_time.md), [regex](../../../docs/regex.md), [crypto](../../../docs/crypto.md)).

## Gotchas

- Text in is atom **or** string (`to_text`); text out is the chars carrier (`text_result`), atoms out only via `symbol(...)`. `str(term)` on a cell gives a tuple repr — the bug these helpers exist to prevent.
- `_helpers._pure` turns any exception into plain failure, unlike `ModulePredicate`'s raising dispatch; prefer explicit errors in new code.
- Out-of-tree packages import `_deep_deref`, `_pred` and friends from `_helpers.py` by name; do not rename them.
