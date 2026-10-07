# Optional Packages

`pip install clausal` ships only the core: the DSL, import hooks, unifier,
indexer, the standard `.seam` library, and Python-stdlib-only modules.
Wrappers for external Python libraries and bridges to external Prolog
engines live in their own distributions and are installed separately.

Each package owns its own documentation, doctests, and examples. Use the
`docs` link on each row below to read its reference page. Source for every
package lives at `packages/clausal-<name>/` in the main repository.

## Library wrappers

| Package | Install | Description | Docs |
|---|---|---|---|
| **clausal-acl2** | `pip install clausal-acl2` | The ACL2 theorem prover through its ACL2 Bridge: evaluate forms, submit events, prove theorems; ACL2 terms are Clausal terms | [docs](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-acl2/docs/acl2.md) |
| **clausal-jax** | `pip install clausal-jax` | JAX predicates: array, PRNG, transforms, sharding, `jax.scipy`, optax, equinox, flax | [docs](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-jax/docs/jax.md) |
| **clausal-decide** | `pip install clausal-decide` | Calibrated decisions about a text (choice, yes/no, score) as relations with probabilities, from the laya model or TypeSafe's Jev | [docs](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-decide/docs/decide.md) |
| **clausal-opencv** | `pip install clausal-opencv` | OpenCV (`cv2`) predicates: image I/O, color, imgproc, contours, drawing, features, calib3d, objdetect, video | [docs](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-opencv/docs/opencv.md) |
| **clausal-provenance** | not published | **Disabled pending redesign** (2026-09-25). Provenance-tagged bottom-up Datalog; PyTorch / JAX-differentiable semirings for neurosymbolic AI | [docs](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-provenance/docs/provenance.md) |
| **clausal-scipy** | `pip install clausal-scipy` | SciPy wrappers: `linalg`, `optimize`, `stats`, `integrate`, `interpolate`, `fft`, `ndimage`, `spatial`, `signal`, `sparse`, `cluster`, `special`, `constants`, `differentiate` | [docs](https://github.com/neurosymbolica/clausal-prolog/tree/main/packages/clausal-scipy/docs/) |
| **clausal-sklearn** | `pip install clausal-sklearn` | scikit-learn predicates (estimators, preprocessing, metrics) | [docs](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-sklearn/docs/sklearn.md) |
| **clausal-spacy** | `pip install clausal-spacy` | spaCy NLP predicates (tokens, POS, lemmas, entities) | [docs](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-spacy/docs/spacy.md) |
| **clausal-sympy** | `pip install clausal-sympy` | SymPy symbolic-math wrapper | [docs](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-sympy/docs/sympy.md) |
| **clausal-torch** | `pip install clausal-torch` | PyTorch wrapper: tensors, `torch.nn`, `torch.nn.functional`, `torch.utils.data`, `torch.distributions` | [docs](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-torch/docs/torch.md) |
| **clausal-yaml** | `pip install clausal-yaml` | YAML read/write via PyYAML | [docs](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-yaml/docs/yaml.md) |

## Prolog backend bridges

| Package | Install | Description | Docs |
|---|---|---|---|
| **clausal-gprolog** | `pip install clausal-gprolog` | GNU Prolog backend (C extension; requires the `gprolog` binary) | [docs](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-gprolog/docs/gprolog.md) |
| **clausal-scryer** | `pip install clausal-scryer` | Scryer Prolog backend (Rust/PyO3 extension) | [docs](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-scryer/docs/scryer.md) |
| **clausal-trealla** | `pip install clausal-trealla` | Trealla Prolog backend (pure Python via ctypes) | [docs](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-trealla/docs/trealla.md) |

## Status

The library wrappers (jax, opencv, scipy, sklearn, spacy, sympy, torch, yaml)
are on PyPI. Each can also be installed as an extra of `clausal`, e.g.
`pip install "clausal[scipy]"`. Their sources live in the main repository
under `packages/`.

`clausal-acl2` and `clausal-decide` are new and not on PyPI yet; until they are,
install one from the repository:

```bash
pip install "clausal-decide @ git+https://github.com/neurosymbolica/clausal-prolog#subdirectory=packages/clausal-decide"
```

The Prolog backends and `clausal-provenance` are not published yet. The `docs` links currently
point at the package sources on GitHub; they'll switch to per-package documentation sites
when each package gains its own published site (see
[`implementation_plans/package_extraction/docs_migration.md`](https://gitlab.com/MikeAmy/clausal/-/blob/main/implementation_plans/package_extraction/docs_migration.md)
for the migration plan).
