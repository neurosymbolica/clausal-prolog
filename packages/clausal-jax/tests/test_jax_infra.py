"""Tests for clausal.modules.py.jax — JAX array predicates (Phase 1).

Integration tests run .clausal fixture files.
Unit tests cover infrastructure (lazy import, opts handling, __getattr__).
"""

import os
import pytest

from clausal.logic.solve import call
from clausal.import_hook import _load_module
from clausal._suffixes import SEAM_SUFFIX

_FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _load_fixture(name):
    path = os.path.join(_FIXTURE_DIR, f"{name}{SEAM_SUFFIX}")
    mod = _load_module(name, path)
    return mod.__dict__["$module"]


def _succeeds(functor, *args, module):
    for _ in call(functor, *args, module=module):
        return True
    return False


# ════════════════════════════════════════════════════════════════════════════
# .clausal integration tests
# ════════════════════════════════════════════════════════════════════════════


class TestJaxArrayFixture:
    """Run Test predicates from tests/fixtures/jax_array_tests.seam."""

    @pytest.fixture(autouse=True, scope="class")
    def _setup(self, request):
        request.cls.mod = _load_fixture("jax_array_tests")

    @pytest.mark.parametrize("name", [
        # Creation
        "array from list",
        "array from nested list",
        "zeros default",
        "zeros with dtype option",
        "ones default",
        "ones with options",
        "full",
        "arange end only",
        "arange start end",
        "arange start end step",
        "linspace",
        "eye square",
        "eye rectangular",
        # Properties — query
        "shape query",
        "dtype query",
        "device query",
        "dim query",
        "element count",
        # Properties — check
        "shape check succeeds",
        "shape check fails",
        "dtype check succeeds",
        "dtype check fails",
        # Math
        "matmul shapes",
        "dot product",
        "add element-wise",
        "mul element-wise",
        "sum full reduction",
        "sum along axis",
        "mean full reduction",
        "mean along axis",
        "max full reduction",
        "max along axis",
        "min full reduction",
        "clip values",
        "abs values",
        # Shape operations
        "reshape",
        "squeeze all",
        "squeeze specific axis",
        "expand_dims",
        "squeeze expand_dims roundtrip",
        "transpose default",
        "transpose is self-inverse",
        "transpose with axes",
        "swapaxes",
        "moveaxis",
        "concatenate along axis",
        "concatenate along axis 1",
        "stacked forward",
        "stacked backward recovers slices",
        "stacked roundtrip",
        "broadcast_to",
        "astype",
        # Conversions (bijective)
        "array_list forward",
        "array_list backward",
        "array_list nested",
        "jax_numpy forward",
        "jax_numpy roundtrip",
        "jax_numpy backward",
        # Edge cases
        "shape with bound vars",
        "scalar array",
        "empty array",
        # Phase 3 — Functional updates (.at)
        "at_set scalar index",
        "at_set tuple index",
        "at_set does not mutate input",
        "at_add scalar",
        "at_add does not mutate input",
        "at_mul scalar",
        "at_min sets lower value",
        "at_min keeps existing when lower",
        "at_max sets higher value",
        "at_max keeps existing when higher",
        "at_get scalar index",
        "at_get tuple index",
        "fancy index via jnp.array",
        "at_set at first and last index",
        "at_set out-of-bounds is silently dropped",
        "at_set with tuple containing bound variable",
        "at_set with python list index fails (not a jnp.array)",
    ])
    def test_fixture(self, name):
        # nv
        assert _succeeds("test", name, module=self.mod), f"Test({name!r}) failed"


# ════════════════════════════════════════════════════════════════════════════
# Phase 5 — FFT .clausal integration tests
# ════════════════════════════════════════════════════════════════════════════


class TestJaxFftFixture:
    """Run Test predicates from tests/fixtures/jax_fft_tests.seam."""

    @pytest.fixture(autouse=True, scope="class")
    def _setup(self, request):
        request.cls.mod = _load_fixture("jax_fft_tests")

    @pytest.mark.parametrize("name", [
        # fft_transform
        "fft_transform forward shape",
        "fft_transform of impulse is all ones",
        "fft_transform roundtrip recovers real part",
        "fft_transform with axis on 2d array",
        # real_fft
        "real_fft forward shape on even-length signal",
        "real_fft roundtrip for even N recovers signal",
        "real_fft with axis",
        # fft_transform_2d
        "fft_transform_2d shape",
        "fft_transform_2d roundtrip shape",
        # fft_transform_nd
        "fft_transform_nd on 3-d array",
        # fft_shift
        "fft_shift swaps halves for even N",
        "fft_shift roundtrip",
        "fft_shift on 2d",
        # fftfreq / rfftfreq
        "fft_frequencies default sample spacing",
        "fft_frequencies with sample spacing",
        "real_fft_frequencies default",
        "real_fft_frequencies with sample spacing",
        # Backfill: axis round-trip + value correctness + odd-N
        "fft_transform/3 roundtrip along axis 1 recovers real parts",
        "fft_transform_2d of impulse is all ones",
        "fft_transform_nd of impulse is all ones",
        "fft_frequencies odd N layout",
        "real_fft roundtrip for odd N is lossy",
        # Backfill: axes parameter variants
        "fft_transform_2d with explicit axes",
        "fft_transform_nd with axes=[0] on 3d",
        "fft_shift with axes=[1]",
        # Backfill: _bidir_2 check-mode fix
        "fft_shift check mode succeeds on equal JAX arrays",
        "fft_shift check mode fails on unequal JAX arrays",
    ])
    def test_fixture(self, name):
        # nv
        assert _succeeds("test", name, module=self.mod), f"Test({name!r}) failed"


# ════════════════════════════════════════════════════════════════════════════
# Phase 4 — Linear algebra .clausal integration tests
# ════════════════════════════════════════════════════════════════════════════


class TestJaxLinalgFixture:
    """Run Test predicates from tests/fixtures/jax_linalg_tests.seam."""

    @pytest.fixture(autouse=True, scope="class")
    def _setup(self, request):
        request.cls.mod = _load_fixture("jax_linalg_tests")

    @pytest.mark.parametrize("name", [
        # det, slogdet
        "det of 2x2",
        "det of identity is 1",
        "slogdet of identity",
        # inv
        "inv shape matches input",
        "A @ inv(A) is approximately identity",
        "inv of inv recovers original",
        # solve
        "solve with identity returns B",
        "solve diagonal system",
        # svd
        "svd returns U, S, Vh with correct shapes",
        "svd on tall matrix (full_matrices=True default)",
        # eig / eigh
        "eigh on 2x2 symmetric returns real values and vectors",
        "eigh eigenvalues of [[2,1],[1,2]] are 1 and 3",
        "eigvalsh returns shape-only array of eigenvalues",
        "eig returns shape-correct tuple",
        "eigvals returns shape-correct array",
        # cholesky
        "cholesky of positive-definite matrix",
        "cholesky diagonal entry is sqrt of input diag",
        # qr
        "qr on 3x2 matrix (reduced)",
        "qr on square matrix",
        # lstsq
        "lstsq returns 4-tuple",
        # norm
        "norm default (frobenius) on [[3,4]]",
        "norm of vector [3,4] is 5",
        "norm with ord=1 on vector",
        "norm with ord=2 on vector",
        # rank
        "matrix_rank of identity is 3",
        "matrix_rank of singular matrix",
        # pinv
        "pinv shape for rectangular",
        "pinv of square invertible matches inv",
        # matrix_power
        "matrix_power 0 is identity",
        "matrix_power 1 is A",
        "matrix_power 2 squares diagonal",
        # cross
        "cross product of x and y is z",
        "cross product antisymmetry: a x b = -(b x a)",
        # singular matrix
        "inv of singular matrix succeeds with non-finite values",
        # complex-dtype eigenvalue verification
        "eigvals of diagonal matrix has correct real parts",
        # norm with non-integer ord
        "norm with ord='fro' on [[3,4]]",
        "norm with ord=inf on vector [1,-7,3]",
        # matrix_power negative N
        "matrix_power -1 is inv",
    ])
    def test_fixture(self, name):
        # nv
        assert _succeeds("test", name, module=self.mod), f"Test({name!r}) failed"


# ════════════════════════════════════════════════════════════════════════════
# Phase 6 — Comparisons, logic, selection .clausal integration tests
# ════════════════════════════════════════════════════════════════════════════


class TestJaxComparisonFixture:
    """Run Test predicates from tests/fixtures/jax_comparison_tests.seam."""

    @pytest.fixture(autouse=True, scope="class")
    def _setup(self, request):
        request.cls.mod = _load_fixture("jax_comparison_tests")

    @pytest.mark.parametrize("name", [
        # Element-wise comparisons
        "eq element-wise",
        "ne element-wise",
        "gt element-wise",
        "lt element-wise",
        "ge element-wise",
        "le element-wise",
        # Check predicates
        "equal check succeeds",
        "equal check fails",
        "equal check fails on different shapes",
        "array_equal succeeds",
        "array_equal fails",
        "allclose within tolerance",
        "allclose fails outside tolerance",
        "allclose with explicit tolerances succeeds",
        "allclose with explicit tolerances fails",
        # Logical
        "logical_and",
        "logical_or",
        "logical_not",
        "logical_xor",
        # any / all
        "any true",
        "any fails when all false",
        "all true",
        "all fails with false",
        "any with axis",
        "all with axis",
        # Selection
        "where selects",
        "where broadcasts scalar branches",
        "masked_select",
        "masked_select non-contiguous mask",
        "take along axis 0",
        "take along axis 1",
        "put_along_axis scatter",
    ])
    def test_fixture(self, name):
        # nv
        assert _succeeds("test", name, module=self.mod), f"Test({name!r}) failed"


# ════════════════════════════════════════════════════════════════════════════
# Phase 7 — Einsum + advanced math .clausal integration tests
# ════════════════════════════════════════════════════════════════════════════


class TestJaxMathFixture:
    """Run Test predicates from tests/fixtures/jax_math_tests.seam."""

    @pytest.fixture(autouse=True, scope="class")
    def _setup(self, request):
        request.cls.mod = _load_fixture("jax_math_tests")

    @pytest.mark.parametrize("name", [
        # einsum
        "einsum matmul",
        "einsum trace",
        "einsum diag extract",
        "einsum dot product",
        # Bijective logarithm
        "logarithm forward",
        "logarithm backward",
        "logarithm backward recovers e from Y=1",
        # Bijective trig
        "sine forward at 0",
        "sine backward at 0",
        "sine roundtrip",
        "cosine forward at 0 is 1",
        "cosine backward at 1 is 0",
        "tangent forward at 0 is 0",
        "tangent backward at 0 is 0",
        # Non-bijective math
        "sqrt of 4 is 2",
        "pow element-wise",
        "atan2 of (1,1) is pi/4",
        "sinh at 0 is 0",
        "cosh at 0 is 1",
        "tanh at 0 is 0",
        "sigmoid at 0 is 0.5",
        "softmax sums to 1 along axis",
        "softmax on 2d along axis 1",
        "log_softmax on 1d",
        "logsumexp of [0,0,0] is log(3)",
        # Rounding / sign
        "floor truncates down",
        "ceil rounds up",
        "round to nearest",
        "sign extracts sign",
        # Cumulative
        "cumsum along axis 0",
        "cumsum along axis 1",
        "cumprod along axis 0",
        # Partial-bijection NaN silence (locks in Caveat doc entry)
        "logarithm of -1 is NaN (not a raise)",
        "sine backward on 2.0 is NaN (out of [-1, 1])",
        "cosine backward on 2.0 is NaN (out of [-1, 1])",
        "tangent backward on any real succeeds (arctan has no domain gap)",
    ])
    def test_fixture(self, name):
        # nv
        assert _succeeds("test", name, module=self.mod), f"Test({name!r}) failed"


# ════════════════════════════════════════════════════════════════════════════
# Phase 8 — Shape extras .clausal integration tests
# ════════════════════════════════════════════════════════════════════════════


class TestJaxShapeExtrasFixture:
    """Run Test predicates from tests/fixtures/jax_shape_extras_tests.seam."""

    @pytest.fixture(autouse=True, scope="class")
    def _setup(self, request):
        request.cls.mod = _load_fixture("jax_shape_extras_tests")

    @pytest.mark.parametrize("name", [
        # partition (bidirectional split + concatenate)
        "partition forward into 3 equal parts",
        "partition forward produces correct pieces",
        "partition forward into 1 returns list of 1",
        "partition forward by indices",
        "partition backward concatenates pieces",
        "partition backward along axis 1",
        "partition roundtrip",
        "partition forward along axis 1",
        # array_split
        "array_split uneven",
        "array_split even matches split",
        "array_split along axis",
        # hsplit / vsplit / dsplit
        "hsplit 2x4 into 2",
        "hsplit on 2x4 matrix splits columns",
        "vsplit on 4x2 matrix splits rows",
        "dsplit on 2x3x4 into 2",
        # tile
        "tile 1d",
        "tile by 1 is identity",
        "tile with int reps",
        "tile 2d with 2-tuple reps",
        # repeat
        "repeat each element twice",
        "repeat along axis 0 of 2d",
        "repeat along axis 1 of 2d",
        # flip
        "flip along axis 0",
        "flip along axis 1",
        "flip 1d reverses",
        "flip multiple axes via tuple",
        "flip no axis reverses all dims",
        "flip no axis on 1d",
        # roll
        "roll 1d by 1",
        "roll 1d by 2",
        "roll by 0 is identity",
        "roll with axis",
        "roll no axis on 2d flattens and reshapes",
        "roll along axis 1",
        # stacked backward (subsumes the old unstack)
        "stacked backward along axis 0",
        "stacked backward produces correct slices",
        "stacked backward along axis 1",
        # pad
        "pad 1d constant default",
        "pad 1d constant explicit mode",
        "pad 1d edge mode",
        "pad 2d with per-axis widths",
        "pad reflects",
    ])
    def test_fixture(self, name):
        # nv
        assert _succeeds("test", name, module=self.mod), f"Test({name!r}) failed"


# ════════════════════════════════════════════════════════════════════════════
# Phase 14 — Creation variants + arithmetic gaps .clausal integration tests
# ════════════════════════════════════════════════════════════════════════════


class TestJaxCreation2Fixture:
    """Run Test predicates from tests/fixtures/jax_creation2_tests.seam."""

    @pytest.fixture(autouse=True, scope="class")
    def _setup(self, request):
        request.cls.mod = _load_fixture("jax_creation2_tests")

    @pytest.mark.parametrize("name", [
        # *_like
        "zeros_like preserves shape",
        "zeros_like preserves dtype",
        "ones_like preserves shape",
        "full_like fills with value",
        "zeros_like opts overrides dtype",
        "ones_like opts overrides dtype",
        "full_like opts overrides dtype",
        # empty
        "empty shape",
        "empty with dtype option",
        # logspace / geomspace
        "logspace default base 10",
        "logspace with base option",
        "geomspace endpoints",
        # meshgrid
        "meshgrid default xy indexing",
        "meshgrid ij indexing",
        # diag
        "diag from 1d creates square matrix",
        "diag extracts from 2d",
        "diag with k offset extracts super-diagonal",
        "diag with k offset extracts sub-diagonal",
        # identity
        "identity 3x3",
        "identity with dtype option",
        # Arithmetic gaps
        "sub element-wise",
        "sub broadcasts scalar",
        "div true divides",
        "div of ints produces floats",
        "floor_div truncates",
        "mod remainder",
        "neg negates values",
        "neg twice recovers",
        "reciprocal inverts",
    ])
    def test_fixture(self, name):
        # nv
        assert _succeeds("test", name, module=self.mod), f"Test({name!r}) failed"


# ════════════════════════════════════════════════════════════════════════════
# Phase 15 — Statistics + selection .clausal integration tests
# ════════════════════════════════════════════════════════════════════════════


class TestJaxStatsFixture:
    """Run Test predicates from tests/fixtures/jax_stats_tests.seam."""

    @pytest.fixture(autouse=True, scope="class")
    def _setup(self, request):
        request.cls.mod = _load_fixture("jax_stats_tests")

    @pytest.mark.parametrize("name", [
        # median
        "median odd length",
        "median even length averages middle",
        "median along axis",
        # std / var
        "std of [2,4,4,4,5,5,7,9] is 2.0",
        "var of [2,4,4,4,5,5,7,9] is 4.0",
        "std along axis 0",
        # percentile / quantile
        "percentile 50 is median",
        "quantile 0.5 is median",
        "percentile along axis",
        # cov / corrcoef
        "cov shape on 3-variable matrix",
        "corrcoef diagonal is ones",
        # argmin / argmax
        "argmin returns index of smallest",
        "argmax returns index of largest",
        "argmin along axis 0 on 2d",
        "argmax along axis 1 on 2d",
        # sort / argsort
        "sort 1d ascending",
        "argsort 1d gives permutation",
        "sort along axis 1 of 2d",
        "sort and argsort consistent via take",
        # topk
        "topk returns (values, indices) tuple",
        "topk k=1 is argmax+value",
        # nonzero
        "nonzero 1d returns 1-tuple of indices",
        "nonzero of all zeros returns empty indices",
        "nonzero on 2d returns per-dim indices",
        # unique
        "unique sorts and dedupes",
        "unique of single repeated value",
        # argpartition
        "argpartition pivot value matches sorted position",
    ])
    def test_fixture(self, name):
        # nv
        assert _succeeds("test", name, module=self.mod), f"Test({name!r}) failed"


# ════════════════════════════════════════════════════════════════════════════
# Phase 9 — Pytrees .clausal integration tests
# ════════════════════════════════════════════════════════════════════════════


class TestJaxTreeFixture:
    """Run Test predicates from tests/fixtures/jax_tree_tests.seam."""

    @pytest.fixture(autouse=True, scope="class")
    def _setup(self, request):
        request.cls.mod = _load_fixture("jax_tree_tests")

    @pytest.mark.parametrize("name", [
        # Leaf enumeration
        "leaf enumerates flat list",
        "leaf enumerates nested dict",
        "leaf on a single value",
        "leaf on empty list has no leaves",
        "leaf on empty dict has no leaves",
        # leaf_with_path
        "leaf_with_path on flat list yields index paths",
        "leaf_with_path exposes dict key",
        "leaf_with_path on nested dict yields correct depth",
        "leaf_with_path dict path then list index",
        # Bijective flatten
        "tree_flatten forward count",
        "tree_flatten roundtrip dict",
        "tree_flatten roundtrip list",
        "unflatten with modified leaves",
        "tree_flatten on single value",
        # Structure queries
        "tree_structure returns PyTreeDef",
        "tree_leaves_list flat list",
        "tree_leaves_list nested",
        "all_leaves accepts flat list of leaves",
        "all_leaves rejects nested list",
        "treedef_is_leaf on scalar flatten",
        "treedef_is_leaf false on list flatten",
        # Mapping
        "tree_map doubles leaves",
        "tree_map preserves structure",
        "tree_map_n adds leaves of two trees",
        # Reducing
        "tree_reduce sums leaves",
        "tree_reduce with max and init",
        "tree_reduce counts leaves",
        # Key-path rendering
        "keystr renders dict + index path",
        "keystr on empty path",
        # Showcase
        "findall scalar leaves greater than 2",
    ])
    def test_fixture(self, name):
        # nv
        assert _succeeds("test", name, module=self.mod), f"Test({name!r}) failed"


# ════════════════════════════════════════════════════════════════════════════
# Phase 13 — Sharding and Devices .clausal integration tests
# ════════════════════════════════════════════════════════════════════════════


class TestJaxShardingFixture:
    """Run Test predicates from tests/fixtures/jax_sharding_tests.seam."""

    @pytest.fixture(autouse=True, scope="class")
    def _setup(self, request):
        request.cls.mod = _load_fixture("jax_sharding_tests")

    @pytest.mark.parametrize("name", [
        # Device enumeration
        "jax_device finds at least one",
        "device_count matches enumeration",
        "local_device finds at least one",
        "local_device_count matches",
        "jax_device check mode",
        "device_id forward",
        "device_id reverse",
        "device_id enumerates all pairs when unbound",
        "device_platform is cpu on CI",
        # device_of
        "device_of returns a Device",
        # Mesh
        "make_mesh creates 1x mesh",
        "mesh_shape check mode with dict literal",
        "mesh_shape reach-through by key",
        "mesh_devices has length matching mesh size",
        "mesh_devices list pattern match",
        # PartitionSpec / shardings
        "partition_spec single axis",
        "partition_spec with None unsharded",
        "named_sharding construction succeeds",
        "named_sharding equal when built from equal mesh/spec",
        "single_device_sharding construction",
        # sharding/2 query
        "sharding query on fresh array",
        # device_put
        "device_put to specific device",
        "device_put preserves values",
        "device_put with named sharding",
        "device_put with single-device sharding",
        # Check predicates
        "is_fully_addressable on fresh array",
        "is_committed after device_put",
        "is_deleted false on live array",
    ])
    def test_fixture(self, name):
        # nv
        assert _succeeds("test", name, module=self.mod), f"Test({name!r}) failed"


# ════════════════════════════════════════════════════════════════════════════
# Phase 12 — Function Transforms .clausal integration tests
# ════════════════════════════════════════════════════════════════════════════


class TestJaxTransformsFixture:
    """Run Test predicates from tests/fixtures/jax_transforms_tests.seam."""

    @pytest.fixture(autouse=True, scope="class")
    def _setup(self, request):
        request.cls.mod = _load_fixture("jax_transforms_tests")

    @pytest.mark.parametrize("name", [
        # grad_value
        "grad of x^2 at 3 is 6",
        "grad of sum(x^2) gives 2x",
        "grad of sin at 0 is 1",
        # value_and_grad
        "value_and_grad of x^3 at 2",
        "value_and_grad on vector sum(x^2)",
        # jvp
        "jvp of x^2 at 3 with tangent 1 gives 6",
        "jvp sum(x^2) along [1,0,0] gives 2",
        # vjp
        "vjp value matches forward eval",
        "vjp_fn applied gives gradient",
        # Jacobian / Hessian
        "jacobian of elementwise square",
        "jacfwd matches jacrev for pointwise fn",
        "hessian of sum(x^2) is 2I",
        # vmap
        "vmap doubles each element",
        "vmap preserves shape",
        "vmap with explicit in_axes=0",
        # jit
        "jit_compile returns callable that produces correct output",
        "jit_compile of grad gives same value as grad_value",
        # make_jaxpr
        "make_jaxpr returns a Jaxpr",
        # eval_shape
        "eval_shape of matmul",
        "eval_shape cheap — doesn't allocate the huge result",
        # pytree grad
        "grad with dict input",
        # scalar-only grad
        "grad of vector output fails (not scalar)",
    ])
    def test_fixture(self, name):
        # nv
        assert _succeeds("test", name, module=self.mod), f"Test({name!r}) failed"


# ════════════════════════════════════════════════════════════════════════════
# Phase 11 — jax.scipy Special + Stats .clausal integration tests
# ════════════════════════════════════════════════════════════════════════════


class TestJaxScipyFixture:
    """Run Test predicates from tests/fixtures/jax_scipy_tests.seam."""

    @pytest.fixture(autouse=True, scope="class")
    def _setup(self, request):
        request.cls.mod = _load_fixture("jax_scipy_tests")

    @pytest.mark.parametrize("name", [
        # Special functions
        "gamma_fn at 1 is 1",
        "gamma_fn at 5 is 24",
        "gammaln at 1 is 0",
        "gammaln at 2 is 0",
        "digamma at 1 is -euler_mascheroni",
        "erf at 0 is 0",
        "erf approaches 1 at large x",
        "erfc at 0 is 1",
        "erfinv roundtrips erf",
        "expit at 0 is 0.5",
        "logit at 0.5 is 0",
        "logit is inverse of expit",
        "i0 at 0 is 1",
        "i1 at 0 is 0",
        "logsumexp of [0, 0, 0] is log(3)",
        "logsumexp along axis",
        "beta_fn at (1,1) is 1",
        "betainc at x=1 is 1",
        "polygamma order 1 at 1 is pi^2/6",
        "rel_entr with identical args is 0",
        "xlogy at x=0 is 0",
        "zeta at (2,1) is pi^2/6",
        "factorial of 5 is 120",
        "spence at 1 is 0",
        # Distribution registry
        "distribution lookup by name",
        "distribution registry includes common names",
        "distribution findall enumerates registry",
        "distribution reverse lookup",
        # Distribution methods
        "normal pdf at mean",
        "normal logpdf at mean",
        "normal cdf at mean is 0.5",
        "normal sf at mean is 0.5",
        "normal ppf at 0.5 is mean",
        "normal logsf at mean is log(0.5)",
        "normal logcdf at mean is log(0.5)",
        "exp of logpdf equals pdf for normal",
        "beta pdf at 0.5 with a=b=2 is 1.5",
        "gamma cdf at 0 is 0",
        "uniform pdf in range",
        "uniform pdf outside range is 0",
        "bernoulli pmf at 1",
        "bernoulli pmf at 0",
        "poisson pmf at 0 for lam=1",
        # Missing-method failure paths
        "bernoulli has no pdf — failure",
        "t has no cdf in this JAX — failure",
    ])
    def test_fixture(self, name):
        # nv
        assert _succeeds("test", name, module=self.mod), f"Test({name!r}) failed"


# ════════════════════════════════════════════════════════════════════════════
# Phase 10 — Activations and Initializers .clausal integration tests
# ════════════════════════════════════════════════════════════════════════════


class TestJaxNnFixture:
    """Run Test predicates from tests/fixtures/jax_nn_tests.seam."""

    @pytest.fixture(autouse=True, scope="class")
    def _setup(self, request):
        request.cls.mod = _load_fixture("jax_nn_tests")

    @pytest.mark.parametrize("name", [
        # Activation registry
        "activation lookup by name",
        "activation registry contains common names",
        "activation registry contains leaky_relu and selu",
        "activation findall enumerates full registry",
        "activation reverse lookup",
        # Applied activations
        "relu zeroes negatives",
        "relu leaves positives unchanged",
        "sigmoid at 0 is 0.5",
        "tanh at 0 is 0",
        "softmax sums to 1",
        "softmax on 2d along axis 1",
        "log_softmax shape preserved",
        "gelu at 0 is 0",
        "gelu with approximate flag",
        "elu negative gets smooth",
        "leaky_relu default slope",
        "leaky_relu custom slope",
        "selu shape",
        "softplus positive",
        "silu at 0 is 0",
        # One-hot
        "one_hot basic",
        "one_hot single index",
        # Initializer registry
        "initializer lookup by name",
        "initializer registry contains common names",
        "initializer findall enumerates full registry",
        "initializer reverse lookup",
        # init_array
        "init_array with glorot_uniform produces correct shape",
        "init_array with he_normal",
        "init_array with zeros (direct initializer)",
        "init_array with ones (direct initializer)",
        "init_array accepts scalar shape",
        "init_array determinism — same key, same sample",
        "init_array different keys differ",
        "configured initializer via ++()",
    ])
    def test_fixture(self, name):
        # nv
        assert _succeeds("test", name, module=self.mod), f"Test({name!r}) failed"


# ════════════════════════════════════════════════════════════════════════════
# Phase 9 + 10 — jax_tree × jax_nn composition .clausal integration tests
# ════════════════════════════════════════════════════════════════════════════


class TestJaxNnTreeIntegrationFixture:
    """Run Test predicates from tests/fixtures/jax_nn_tree_integration.seam."""

    @pytest.fixture(autouse=True, scope="class")
    def _setup(self, request):
        request.cls.mod = _load_fixture("jax_nn_tree_integration")

    @pytest.mark.parametrize("name", [
        "init a two-layer param pytree",
        "tree_map preserves structure over an init'd param pytree",
        "tree_reduce sums element counts across param leaves",
        "tree_leaves_list preserves leaf order by dict key",
    ])
    def test_fixture(self, name):
        # nv
        assert _succeeds("test", name, module=self.mod), f"Test({name!r}) failed"


# ════════════════════════════════════════════════════════════════════════════
# Phase 2 — PRNG .clausal integration tests
# ════════════════════════════════════════════════════════════════════════════


class TestJaxRandomFixture:
    """Run Test predicates from tests/fixtures/jax_random_tests.seam."""

    @pytest.fixture(autouse=True, scope="class")
    def _setup(self, request):
        request.cls.mod = _load_fixture("jax_random_tests")

    @pytest.mark.parametrize("name", [
        # Key primitives
        "create key",
        "create key with zero seed",
        "create key with large seed",
        "split into 2",
        "split into N=3",
        "split into N=5",
        "split produces distinct keys",
        "fold_in produces different key",
        "key_bytes roundtrip reproduces samples",
        "key_bytes forward shape",
        "determinism — same seed",
        # Samplers
        "normal shape",
        "normal 2d shape",
        "uniform shape",
        "uniform range",
        "bernoulli default shape",
        "bernoulli with shape",
        "categorical picks a class",
        "poisson shape",
        "gamma shape",
        "beta shape",
        "exponential shape",
        "dirichlet sums to one",
        "multivariate_normal shape",
        "permutation of integer range",
        "permutation of array",
        "choice picks from array",
        "randint in range",
        "truncated_normal within bounds",
        # Registry
        "sampler registry lookup",
        "sampler registry includes uniform",
        "sampler registry includes bernoulli",
        "sampler registry enumerate contains expected names",
        # Backtracking safety
        "key is a value — repeated sampling is idempotent",
        "failed sampler branch leaves sibling key untouched",
        # State threading
        "state-threaded initialisation",
    ])
    def test_fixture(self, name):
        # nv
        assert _succeeds("test", name, module=self.mod), f"Test({name!r}) failed"


# ════════════════════════════════════════════════════════════════════════════
# Phase 2 — infrastructure unit tests
# ════════════════════════════════════════════════════════════════════════════


class TestJaxRandomInfra:
    """Unit tests for jax_random.py infrastructure."""

    def test_lazy_import_loads_jax_random(self):
        # nv
        import clausal.modules.py.jax_random as impl
        assert impl._jr() is not None

    def test_exports_exist(self):
        # nv
        import clausal.modules.py.jax_random as impl
        for name in impl.__all__:
            assert getattr(impl, name) is not None, f"{name} is None"

    def test_sampler_facts_non_empty(self):
        # nv
        import clausal.modules.py.jax_random as impl
        facts = impl._build_sampler_facts()
        names = {n for n, _ in facts}
        for expected in ("normal", "uniform", "bernoulli", "categorical"):
            assert expected in names, f"missing sampler {expected}"

    def test_split_returns_python_list(self):
        """Pattern matching [K1, K2] needs a real list, not a KeyArray."""
        # nv
        import clausal.modules.py.jax_random as impl
        jr = impl._jr()
        k0 = jr.key(0)
        assert isinstance(impl._split_2(k0), list)
        assert isinstance(impl._split_3(k0, 3), list)


# ════════════════════════════════════════════════════════════════════════════
# Infrastructure unit tests
# ════════════════════════════════════════════════════════════════════════════


class TestJaxInfra:
    """Unit tests for jax.py infrastructure."""

    def test_lazy_import_loads_jax(self):
        # nv
        import clausal.modules.py.jax as impl
        impl._ensure_jax()
        assert impl._jax is not None
        assert impl._jnp is not None

    def test_exports_exist(self):
        # nv
        import clausal.modules.py.jax as impl
        # newaxis is legitimately None (jnp.newaxis == None) and null is an
        # explicit alias for Python None — accept both.
        _NONE_OK = {"newaxis", "null"}
        for name in impl.__all__:
            if name in _NONE_OK:
                assert getattr(impl, name) is None
                continue
            obj = getattr(impl, name)
            assert obj is not None, f"{name} is None"

    def test_dtype_export(self):
        # nv
        import clausal.modules.py.jax as impl
        import jax.numpy as jnp
        assert impl.float32 is jnp.float32
        assert impl.float64 is jnp.float64
        assert impl.int32 is jnp.int32

    def test_const_export(self):
        # nv
        import clausal.modules.py.jax as impl
        import math
        assert impl.pi == math.pi
        assert impl.newaxis is None  # jnp.newaxis is None

    def test_unknown_attribute_raises(self):
        # nv
        import clausal.modules.py.jax as impl
        with pytest.raises(AttributeError):
            _ = impl.not_a_real_name

    def test_pred_arities(self):
        """Verify key predicates have the expected arity variants."""
        # nv
        import clausal.modules.py.jax as impl
        # zeros should have arity 2 and 3
        assert 2 in impl.zeros._dispatch_fns
        assert 3 in impl.zeros._dispatch_fns
        # shape should have arity 2 only
        assert 2 in impl.shape._dispatch_fns
        # squeeze should have arity 2 and 3
        assert 2 in impl.squeeze._dispatch_fns
        assert 3 in impl.squeeze._dispatch_fns
        # arange should have arity 2, 3, 4, 5
        assert set(impl.arange._dispatch_fns.keys()) >= {2, 3, 4}
        # eye should have arity 2, 3, 4
        assert set(impl.eye._dispatch_fns.keys()) >= {2, 3, 4}

    def test_empty_opts_dict(self):
        """Empty opts dict should behave like default call."""
        # nv
        import clausal.modules.py.jax as impl
        from clausal.logic.variables import Var, deref
        from clausal.logic.database import Module
        mod = Module("jax", module_dict=vars(impl))
        out = Var()
        succeeded = False
        for _ in call("zeros", [2, 3], {}, out, module=mod):
            arr = deref(out)
            assert list(arr.shape) == [2, 3]
            succeeded = True
            break
        assert succeeded


# ════════════════════════════════════════════════════════════════════════════
# Phase 16 — Optax .clausal integration tests
# ════════════════════════════════════════════════════════════════════════════


class TestJaxOptaxFixture:
    """Run Test predicates from tests/fixtures/jax_optax_tests.seam."""

    @pytest.fixture(autouse=True, scope="class")
    def _setup(self, request):
        request.cls.mod = _load_fixture("jax_optax_tests")

    @pytest.mark.parametrize("name", [
        # Training-loop trio
        "sgd one step on a flat array",
        "sgd opts: momentum",
        "adam step using value_and_grad",
        "two-step training reduces loss for x^2",
        "apply_updates on pytree of params",
        "init_optimizer on pytree params returns matching state",
        # Composition
        "chain of clip then sgd builds and steps",
        "scale alone",
        "zero_nans replaces nan grads with 0",
        # Schedules
        "constant_schedule returns same value at every step",
        "linear_schedule interpolates",
        "exponential_decay shrinks",
        "cosine_decay_schedule endpoints",
        "warmup_cosine_decay_schedule peaks at end of warmup",
        "piecewise_constant_schedule steps at boundary",
        "polynomial_schedule",
        "scale_by_schedule wired into chain decays effective LR",
        # Losses
        "softmax_cross_entropy on one-hot label",
        "softmax_cross_entropy_with_integer_labels matches one-hot form",
        "sigmoid_binary_cross_entropy on logit 0 with label 1",
        "l2_loss with target",
        "huber_loss small residual ≈ quadratic",
        "huber_loss with custom delta",
        "cosine_similarity of identical vectors is 1",
        "hinge_loss correct margin gives 0",
        "smooth_labels with alpha=0.1 on 3-class one-hot",
        # Registries
        "optimizer registry has known names",
        "optimizer findall returns full list",
        "optimizer lookup by name returns the constructor",
        "schedule registry has known names",
        "loss_function registry has known names",
        # multi_steps
        "multi_steps accumulates K gradients before applying",
    ])
    def test_fixture(self, name):
        # nv
        assert _succeeds("test", name, module=self.mod), f"Test({name!r}) failed"


# ════════════════════════════════════════════════════════════════════════════
# Phase 16 — jax_optax module unit tests
# ════════════════════════════════════════════════════════════════════════════


class TestJaxOptaxInfrastructure:
    """Module-level invariants for jax_optax."""

    def test_lazy_import(self):
        # nv
        # Importing the wrapper module must not eagerly import optax.
        # We can't easily un-import optax in a running process, so just
        # verify the wrapper exposes its lazy hook.
        import clausal.modules.py.jax_optax as impl
        assert hasattr(impl, "_ensure_optax")
        assert callable(impl._ensure_optax)

    def test_all_exports_resolve(self):
        # nv
        import clausal.modules.py.jax_optax as impl
        for name in impl.__all__:
            obj = getattr(impl, name)
            assert obj is not None, f"{name} is None"

    def test_pred_arities(self):
        # nv
        import clausal.modules.py.jax_optax as impl
        # sgd/adam: /2 and /3
        assert {2, 3} <= set(impl.sgd._dispatch_fns.keys())
        assert {2, 3} <= set(impl.adam._dispatch_fns.keys())
        # update_optimizer: /4 and /5
        assert {4, 5} <= set(impl.update_optimizer._dispatch_fns.keys())
        # l2_loss: /2 and /3
        assert {2, 3} <= set(impl.l2_loss._dispatch_fns.keys())
        # huber_loss: /3 and /4
        assert {3, 4} <= set(impl.huber_loss._dispatch_fns.keys())
        # zero_nans: /1
        assert 1 in impl.zero_nans._dispatch_fns


# ════════════════════════════════════════════════════════════════════════════
# Phase 17 — Equinox .clausal integration tests
# ════════════════════════════════════════════════════════════════════════════


class TestJaxEquinoxFixture:
    """Run Test predicates from tests/fixtures/jax_equinox_tests.seam."""

    @pytest.fixture(autouse=True, scope="class")
    def _setup(self, request):
        request.cls.mod = _load_fixture("jax_equinox_tests")

    @pytest.mark.parametrize("name", [
        # Layer construction
        "linear forward shape",
        "linear with use_bias=False opts",
        "mlp forward shape",
        "layer_norm forward preserves shape",
        "sequential of linear, layer_norm, linear",
        "identity is a no-op",
        "lambda_layer wraps a callable",
        "dropout defaults to inference (no-op)",
        "conv2d forward shape",
        "max_pool2d shape with stride=2 opts",
        "avg_pool1d shape with stride=2 opts",
        "adaptive_avg_pool2d shape",
        "embedding lookup shape",
        "lstm_cell single-step shape",
        # Filter transforms
        "filter_grad_value over a Linear loss",
        "filter_value_and_grad tuple decomposition",
        "filter_jit_compile produces equivalent callable",
        # Partition / combine
        "partition splits and combine rebuilds",
        # tree_at
        "tree_at_set replaces a single leaf",
        "tree_at_apply transforms a leaf",
        # Leaf checks
        "is_array succeeds on a JAX array",
        "is_array fails on a Python int",
        "is_inexact_array succeeds on a float array",
        "is_inexact_array fails on an int array",
        "tree_equal on identical models",
        # Serialisation
        "serialise then deserialise round-trip",
        # End-to-end
        "MLP one optax SGD step changes the model",
        # Stateful modules (Phase 17b)
        "batch_norm constructs model and state",
        "batch_norm with mode=batch opts",
        "apply_stateful_module in inference mode preserves shape",
        "apply_stateful_module under vmap preserves batch shape",
        "dropout_train differs from its input under a key",
        "inference_mode flips inference field to True",
        "inference_mode/3 with value=False switches back",
        "is_stateful discriminates BatchNorm vs Linear",
        "make_with_state generic form equals batch_norm/5",
        # Registry
        "layer_class registry exposes Linear, MLP, Conv2d",
        "layer_class findall has at least 40 entries",
    ])
    def test_fixture(self, name):
        # nv
        assert _succeeds("test", name, module=self.mod), f"Test({name!r}) failed"


class TestJaxEquinoxInfrastructure:
    """Module-level invariants for jax_equinox."""

    def test_lazy_import(self):
        # nv
        import clausal.modules.py.jax_equinox as impl
        assert hasattr(impl, "_ensure_equinox")
        assert callable(impl._ensure_equinox)

    def test_all_exports_resolve(self):
        # nv
        import clausal.modules.py.jax_equinox as impl
        for name in impl.__all__:
            obj = getattr(impl, name)
            assert obj is not None, f"{name} is None"

    def test_pred_arities(self):
        # nv
        import clausal.modules.py.jax_equinox as impl
        # linear: /4 (with key) and /5 (with opts + key)
        assert {4, 5} <= set(impl.linear._dispatch_fns.keys())
        # mlp: /6 and /7
        assert {6, 7} <= set(impl.mlp._dispatch_fns.keys())
        # layer_norm: /2 and /3
        assert {2, 3} <= set(impl.layer_norm._dispatch_fns.keys())
        # apply_module: /3 and /4
        assert {3, 4} <= set(impl.apply_module._dispatch_fns.keys())
        # partition: /4
        assert 4 in impl.partition._dispatch_fns
        # is_array: /1
        assert 1 in impl.is_array._dispatch_fns
        # Phase 17b — stateful
        assert {4, 5} <= set(impl.batch_norm._dispatch_fns.keys())
        assert 4 in impl.make_with_state._dispatch_fns
        assert {5, 6} <= set(impl.apply_stateful_module._dispatch_fns.keys())
        assert {2, 3} <= set(impl.dropout_train._dispatch_fns.keys())
        assert {2, 3} <= set(impl.inference_mode._dispatch_fns.keys())
        assert 1 in impl.is_stateful._dispatch_fns

    def test_layer_class_registry_has_known(self):
        # nv
        import clausal.modules.py.jax_equinox as impl
        # The registry uses TitleCase Equinox class names.
        from clausal.logic.variables import Var, deref
        from clausal.logic.database import Module
        mod = Module("eq", module_dict=vars(impl))
        out = Var()
        succeeded = False
        for _ in call("layer_class", "Linear", out, module=mod):
            cls = deref(out)
            assert cls.__name__ == "Linear"
            succeeded = True
            break
        assert succeeded


# ════════════════════════════════════════════════════════════════════════════
# Phase 18 — Flax Linen .clausal integration tests
# ════════════════════════════════════════════════════════════════════════════


class TestJaxFlaxFixture:
    """Run Test predicates from tests/fixtures/jax_flax_tests.seam."""

    @pytest.fixture(autouse=True, scope="class")
    def _setup(self, request):
        request.cls.mod = _load_fixture("jax_flax_tests")

    @pytest.mark.parametrize("name", [
        # Init / apply basics
        "Dense init returns params, apply produces correct shape",
        "Dense with use_bias=False opts",
        "Conv 2-spatial init+apply",
        "LayerNorm preserves shape",
        "Embed lookup shape",
        "Sequential composes Dense + Dense",
        # init_with_output
        "init_with_output gives same result as init then apply",
        # Stochastic / stateful apply
        "Dropout in inference mode (no RNG needed) is identity",
        "Dropout in training mode needs apply_with_rngs",
        "BatchNorm apply_mutable returns (out, new_state)",
        # Pool functions
        "max_pool with stride=2 halves spatial dims",
        "avg_pool default stride=window",
        # End-to-end
        "MLP one optax SGD step changes the variables",
        # Pytree predicates on variables
        "leaf enumerates Dense variable arrays",
        # Registry
        "layer_class exposes Dense, Conv, LayerNorm",
        "layer_class findall has at least 30 entries",
    ])
    def test_fixture(self, name):
        # nv
        assert _succeeds("test", name, module=self.mod), f"Test({name!r}) failed"


class TestJaxFlaxInfrastructure:
    """Module-level invariants for jax_flax."""

    def test_lazy_import(self):
        # nv
        import clausal.modules.py.jax_flax as impl
        assert hasattr(impl, "_ensure_flax")
        assert callable(impl._ensure_flax)

    def test_all_exports_resolve(self):
        # nv
        import clausal.modules.py.jax_flax as impl
        for name in impl.__all__:
            obj = getattr(impl, name)
            assert obj is not None, f"{name} is None"

    def test_pred_arities(self):
        # nv
        import clausal.modules.py.jax_flax as impl
        # dense: /2 and /3
        assert {2, 3} <= set(impl.dense._dispatch_fns.keys())
        # conv: /3 and /4
        assert {3, 4} <= set(impl.conv._dispatch_fns.keys())
        # layer_norm: /1 and /2 (no required positional args)
        assert {1, 2} <= set(impl.layer_norm._dispatch_fns.keys())
        # init / apply: /4
        assert 4 in impl.init._dispatch_fns
        assert 4 in impl.apply._dispatch_fns
        # apply_mutable / apply_with_rngs: /5
        assert 5 in impl.apply_mutable._dispatch_fns
        assert 5 in impl.apply_with_rngs._dispatch_fns
        # max_pool: /3 and /4
        assert {3, 4} <= set(impl.max_pool._dispatch_fns.keys())
