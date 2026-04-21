"""Tests for clausal.modules.py.jax — JAX array predicates (Phase 1).

Integration tests run .clausal fixture files.
Unit tests cover infrastructure (lazy import, opts handling, __getattr__).
"""

import os
import pytest

from clausal.logic.solve import call
from clausal.import_hook import _load_module

_FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _load_fixture(name):
    path = os.path.join(_FIXTURE_DIR, f"{name}.clausal")
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
    """Run Test predicates from tests/fixtures/jax_array_tests.clausal."""

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
        "stack along axis",
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
        assert _succeeds("Test", name, module=self.mod), f"Test({name!r}) failed"


# ════════════════════════════════════════════════════════════════════════════
# Phase 5 — FFT .clausal integration tests
# ════════════════════════════════════════════════════════════════════════════


class TestJaxFftFixture:
    """Run Test predicates from tests/fixtures/jax_fft_tests.clausal."""

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
        assert _succeeds("Test", name, module=self.mod), f"Test({name!r}) failed"


# ════════════════════════════════════════════════════════════════════════════
# Phase 4 — Linear algebra .clausal integration tests
# ════════════════════════════════════════════════════════════════════════════


class TestJaxLinalgFixture:
    """Run Test predicates from tests/fixtures/jax_linalg_tests.clausal."""

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
        assert _succeeds("Test", name, module=self.mod), f"Test({name!r}) failed"


# ════════════════════════════════════════════════════════════════════════════
# Phase 2 — PRNG .clausal integration tests
# ════════════════════════════════════════════════════════════════════════════


class TestJaxRandomFixture:
    """Run Test predicates from tests/fixtures/jax_random_tests.clausal."""

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
        assert _succeeds("Test", name, module=self.mod), f"Test({name!r}) failed"


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
        for name in impl.__all__:
            # newaxis is legitimately None (jnp.newaxis == None), so accept it
            if name == "newaxis":
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
