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
| **clausal-jax** | `pip install clausal-jax` | JAX predicates: array, PRNG, transforms, sharding, `jax.scipy`, optax, equinox, flax | [docs](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-jax/docs/jax.md) |
| **clausal-opencv** | `pip install clausal-opencv` | OpenCV (`cv2`) predicates: image I/O, color, imgproc, contours, drawing, features, calib3d, objdetect, video | [docs](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-opencv/docs/opencv.md) |
| **clausal-provenance** | `pip install clausal-provenance` | **Disabled pending redesign** (2026-09-25). Provenance-tagged bottom-up Datalog; PyTorch / JAX-differentiable semirings for neurosymbolic AI | [docs](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-provenance/docs/provenance.md) |
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

Today these packages live in the main repository under `packages/` and are
installed from the source tree. Once published to PyPI, the `pip install`
commands above will pull from there directly. The `docs` links currently
point at the package sources on GitHub; they'll switch to per-package documentation sites
when each package gains its own published site (see
[`implementation_plans/package_extraction/docs_migration.md`](https://gitlab.com/MikeAmy/clausal/-/blob/main/implementation_plans/package_extraction/docs_migration.md)
for the migration plan).
