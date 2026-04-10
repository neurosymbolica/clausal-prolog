"""Tests for clausal.modules.py.torch — PyTorch tensor predicates.

Integration tests run .clausal fixture files.
Unit tests cover infrastructure (lazy import, opts handling).
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


class TestTorchTensorFixture:
    """Run Test predicates from tests/fixtures/torch_tensor_tests.clausal."""

    @pytest.fixture(autouse=True, scope="class")
    def _setup(self, request):
        request.cls.mod = _load_fixture("torch_tensor_tests")

    @pytest.mark.parametrize("name", [
        # Creation
        "tensor from list",
        "tensor from nested list",
        "zeros default",
        "zeros with dtype option",
        "ones default",
        "ones with options",
        "randn shape",
        "arange end only",
        "arange start end",
        "arange start end step",
        "linspace",
        "full",
        "eye square",
        "eye rectangular",
        # Properties — query
        "shape query",
        "dtype query",
        "device query",
        "dim query",
        "element count",
        "requires gradient default false",
        # Properties — check
        "shape check succeeds",
        "shape check fails",
        "dtype check succeeds",
        "dtype check fails",
        # Math
        "matmul shapes",
        "add element-wise",
        "mul element-wise",
        "cat along dim 0",
        "cat along dim 1",
        "stack along dim 0",
        "sum full reduction",
        "sum along dim",
        "mean full reduction",
        "mean along dim",
        "max full reduction",
        "max along dim",
        "min full reduction",
        "clamp values",
        "abs values",
        "softmax sums to one",
        "relu zeroes negatives",
        # Shape operations
        "reshape",
        "squeeze all",
        "squeeze specific dim",
        "unsqueeze",
        "squeeze unsqueeze roundtrip",
        "flatten all",
        "flatten partial",
        "unflatten",
        "flatten unflatten roundtrip",
        "transpose",
        "transpose is self-inverse",
        "permute",
        "contiguous",
        # Conversions
        "tensor_list forward",
        "tensor_list backward",
        "tensor_list nested",
        "tensor_numpy forward",
        "tensor_numpy roundtrip",
        "tensor_numpy backward",
        # Edge cases
        "shape with bound vars",
        "scalar tensor",
        "empty tensor",
    ])
    def test_fixture(self, name):
        assert _succeeds("Test", name, module=self.mod), f"Test({name!r}) failed"


# ════════════════════════════════════════════════════════════════════════════
# torch_nn .clausal integration tests
# ════════════════════════════════════════════════════════════════════════════


class TestTorchNnFixture:
    """Run Test predicates from tests/fixtures/torch_nn_tests.clausal."""

    @pytest.fixture(autouse=True, scope="class")
    def _setup(self, request):
        request.cls.mod = _load_fixture("torch_nn_tests")

    @pytest.mark.parametrize("name", [
        "named_parameter enumerates weight and bias",
        "parameter count for Linear",
        "parameter count for no-param module",
        "named_module includes self and children",
        "module count for Sequential",
        "child count for Sequential",
        "named_child names",
        "child of leaf module is empty",
        "named_module recurses into nested Sequential",
        "named_parameter recurses into nested model",
    ])
    def test_fixture(self, name):
        assert _succeeds("Test", name, module=self.mod), f"Test({name!r}) failed"


# ════════════════════════════════════════════════════════════════════════════
# Registry .clausal integration tests
# ════════════════════════════════════════════════════════════════════════════


class TestTorchRegistryFixture:
    """Run Test predicates from tests/fixtures/torch_registry_tests.clausal."""

    @pytest.fixture(autouse=True, scope="class")
    def _setup(self, request):
        request.cls.mod = _load_fixture("torch_registry_tests")

    @pytest.mark.parametrize("name", [
        "layer enumerates Linear",
        "layer enumerates Conv2d",
        "layer enumerates LSTM",
        "layer lookup by name returns usable class",
        "layer lookup is deterministic",
        "activation enumerates ReLU",
        "activation enumerates Sigmoid and Tanh",
        "activation enumerates Softmax",
        "loss_fn enumerates CrossEntropyLoss",
        "loss_fn enumerates MSELoss",
        "loss_fn lookup by name",
        "optimizer_type enumerates Adam",
        "optimizer_type enumerates SGD",
        "optimizer_type lookup by name",
        "dtype_info bits for float32",
        "dtype_info bits for float64",
        "dtype_info is_floating_point for float32",
        "dtype_info is_floating_point for int64",
        "dtype_info enumerate keys",
    ])
    def test_fixture(self, name):
        assert _succeeds("Test", name, module=self.mod), f"Test({name!r}) failed"


# ════════════════════════════════════════════════════════════════════════════
# IO .clausal integration tests
# ════════════════════════════════════════════════════════════════════════════


class TestTorchIoFixture:
    """Run Test predicates from tests/fixtures/torch_io_tests.clausal."""

    @pytest.fixture(autouse=True, scope="class")
    def _setup(self, request):
        request.cls.mod = _load_fixture("torch_io_tests")

    @pytest.mark.parametrize("name", [
        "save and load tensor roundtrip",
        "save and load preserves values",
        "load nonexistent file fails",
    ])
    def test_fixture(self, name):
        assert _succeeds("Test", name, module=self.mod), f"Test({name!r}) failed"


# ════════════════════════════════════════════════════════════════════════════
# Linear algebra .clausal integration tests
# ════════════════════════════════════════════════════════════════════════════


class TestTorchLinalgFixture:
    """Run Test predicates from tests/fixtures/torch_linalg_tests.clausal."""

    @pytest.fixture(autouse=True, scope="class")
    def _setup(self, request):
        request.cls.mod = _load_fixture("torch_linalg_tests")

    @pytest.mark.parametrize("name", [
        # Determinant
        "det of identity",
        "det of 2x2",
        # Inverse
        "inv of identity",
        "inv roundtrip",
        "inv of singular fails",
        # Solve
        "solve identity system",
        "solve 2x2 system",
        # SVD
        "svd shapes",
        "svd rectangular",
        # Eigendecomposition
        "eig shapes",
        # Cholesky
        "cholesky of identity",
        "cholesky reconstruct",
        "cholesky of non-positive-definite fails",
        # QR
        "qr shapes",
        "qr square",
        # Norm
        "norm of vector",
        "norm with ord",
        "norm of matrix",
        # Matrix rank
        "matrix_rank of identity",
        "matrix_rank of rank-1",
        # Pseudoinverse
        "pinv shapes",
        "pinv of square invertible",
        # Cross product
        "cross product",
        # Dot product
        "dot product",
        "dot product orthogonal",
    ])
    def test_fixture(self, name):
        assert _succeeds("Test", name, module=self.mod), f"Test({name!r}) failed"


# ════════════════════════════════════════════════════════════════════════════
# FFT .clausal integration tests
# ════════════════════════════════════════════════════════════════════════════


class TestTorchFFTFixture:
    """Run Test predicates from tests/fixtures/torch_fft_tests.clausal."""

    @pytest.fixture(autouse=True, scope="class")
    def _setup(self, request):
        request.cls.mod = _load_fixture("torch_fft_tests")

    @pytest.mark.parametrize("name", [
        # fft_transform (bijective complex FFT)
        "fft_transform forward and inverse",
        "fft_transform with dim forward",
        "fft_transform with dim inverse",
        # real_fft (bijective real FFT)
        "real_fft forward shape",
        "real_fft roundtrip",
        "real_fft with dim",
        # fft_transform_2d
        "fft_transform_2d forward",
        "fft_transform_2d roundtrip",
        # fft_transform_nd
        "fft_transform_nd forward",
        "fft_transform_nd roundtrip",
        # fft_shift (bijective)
        "fft_shift roundtrip",
        "fft_shift changes order",
        # fft_frequencies / real_fft_frequencies
        "fft_frequencies shape",
        "fft_frequencies with spacing",
        "real_fft_frequencies shape",
        "real_fft_frequencies with spacing",
    ])
    def test_fixture(self, name):
        assert _succeeds("Test", name, module=self.mod), f"Test({name!r}) failed"


# ════════════════════════════════════════════════════════════════════════════
# Comparisons, logic, selection .clausal integration tests
# ════════════════════════════════════════════════════════════════════════════


class TestTorchComparisonFixture:
    """Run Test predicates from tests/fixtures/torch_comparison_tests.clausal."""

    @pytest.fixture(autouse=True, scope="class")
    def _setup(self, request):
        request.cls.mod = _load_fixture("torch_comparison_tests")

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
        "allclose check succeeds",
        "allclose check with tolerance",
        "allclose check fails",
        # Logical operations
        "logical_and",
        "logical_or",
        "logical_not",
        "logical_xor",
        # any / all
        "any succeeds when some True",
        "any fails when all False",
        "all succeeds when all True",
        "all fails when some False",
        "any with dim",
        "all with dim",
        # Selection
        "where selects conditionally",
        "masked_select",
        "index_select",
        "gather along dim",
        "scatter into zeros",
    ])
    def test_fixture(self, name):
        assert _succeeds("Test", name, module=self.mod), f"Test({name!r}) failed"


# ════════════════════════════════════════════════════════════════════════════
# Einsum and advanced math .clausal integration tests
# ════════════════════════════════════════════════════════════════════════════


class TestTorchMathFixture:
    """Run Test predicates from tests/fixtures/torch_math_tests.clausal."""

    @pytest.fixture(autouse=True, scope="class")
    def _setup(self, request):
        request.cls.mod = _load_fixture("torch_math_tests")

    @pytest.mark.parametrize("name", [
        # Einsum
        "einsum matmul",
        "einsum trace",
        "einsum outer product",
        "einsum batch matmul",
        # Logarithm (bijective)
        "logarithm forward (exp)",
        "logarithm backward (log)",
        "logarithm roundtrip",
        # Sine (bijective)
        "sine forward",
        "sine roundtrip",
        # Cosine (bijective)
        "cosine forward",
        "cosine roundtrip",
        # Tangent (bijective)
        "tangent forward",
        "tangent roundtrip",
        # sqrt, pow
        "sqrt known values",
        "pow squares",
        "pow cubes",
        # atan2
        "atan2 known values",
        # Hyperbolic
        "sinh shape",
        "cosh shape",
        "tanh range",
        "tanh at zero",
        # Sigmoid
        "sigmoid range",
        "sigmoid at zero",
        # Log-softmax
        "log_softmax shape",
        # Rounding
        "floor values",
        "ceil values",
        "round values",
        # Sign
        "sign values",
        # Cumulative
        "cumsum known sequence",
        "cumsum 2d along dim 1",
        "cumprod known sequence",
    ])
    def test_fixture(self, name):
        assert _succeeds("Test", name, module=self.mod), f"Test({name!r}) failed"


# ════════════════════════════════════════════════════════════════════════════
# Additional shape operations .clausal integration tests
# ════════════════════════════════════════════════════════════════════════════


class TestTorchShape2Fixture:
    """Run Test predicates from tests/fixtures/torch_shape2_tests.clausal."""

    @pytest.fixture(autouse=True, scope="class")
    def _setup(self, request):
        request.cls.mod = _load_fixture("torch_shape2_tests")

    @pytest.mark.parametrize("name", [
        # split
        "split into equal chunks",
        "split with dim",
        "split then cat roundtrip",
        "split uneven",
        # chunk
        "chunk into n parts",
        "chunk with dim",
        "chunk then cat roundtrip",
        "chunk non-divisible",
        # unbind
        "unbind along dim 0",
        "unbind along dim 1",
        "unbind then stack roundtrip",
        # narrow
        "narrow along dim 0",
        "narrow along dim 1",
        "narrow shape",
        # expand
        "expand broadcasts",
        "expand with -1",
        # repeat
        "repeat tiles",
        "repeat 2d",
        # tile
        "tile 1d",
        "tile 2d",
        # flip
        "flip 1d",
        "flip self-inverse",
        "flip 2d along dim 1",
        # roll
        "roll shifts elements",
        "roll roundtrip",
        "roll with dim",
    ])
    def test_fixture(self, name):
        assert _succeeds("Test", name, module=self.mod), f"Test({name!r}) failed"


# ════════════════════════════════════════════════════════════════════════════
# Distributions .clausal integration tests
# ════════════════════════════════════════════════════════════════════════════


class TestTorchDistributionsFixture:
    """Run Test predicates from tests/fixtures/torch_distributions_tests.clausal."""

    @pytest.fixture(autouse=True, scope="class")
    def _setup(self, request):
        request.cls.mod = _load_fixture("torch_distributions_tests")

    @pytest.mark.parametrize("name", [
        # Registry
        "enumerate distributions",
        "distribution lookup by name",
        # Construction
        "make normal distribution",
        "make bernoulli distribution",
        "make uniform distribution",
        "make poisson distribution",
        "make categorical distribution",
        # Properties
        "normal mean",
        "normal variance",
        "normal stddev",
        "uniform mean",
        # Entropy
        "normal entropy",
        # Sampling
        "sample scalar",
        "sample with shape",
        "sample 2d shape",
        "sample bernoulli",
        # Log probability
        "log_prob normal at mean",
        "log_prob bernoulli",
        # CDF / Inverse CDF
        "cdf normal at mean",
        "icdf normal median",
        "cdf icdf roundtrip",
        "cdf uniform",
    ])
    def test_fixture(self, name):
        assert _succeeds("Test", name, module=self.mod), f"Test({name!r}) failed"


# ════════════════════════════════════════════════════════════════════════════
# nn.functional .clausal integration tests
# ════════════════════════════════════════════════════════════════════════════


class TestTorchFunctionalFixture:
    """Run Test predicates from tests/fixtures/torch_functional_tests.clausal."""

    @pytest.fixture(autouse=True, scope="class")
    def _setup(self, request):
        request.cls.mod = _load_fixture("torch_functional_tests")

    @pytest.mark.parametrize("name", [
        # Activations
        "leaky_relu default",
        "leaky_relu custom slope",
        "elu default",
        "elu custom alpha",
        "selu",
        "gelu",
        "silu",
        "mish",
        "hardswish",
        "hardsigmoid",
        "gelu positive passthrough",
        # Convolutions
        "conv1d shape",
        "conv2d shape",
        "conv2d with padding",
        "conv2d with stride",
        "conv3d shape",
        # Pooling
        "max_pool1d",
        "max_pool2d",
        "max_pool2d with stride",
        "avg_pool1d",
        "avg_pool2d",
        "adaptive_avg_pool1d",
        "adaptive_avg_pool2d",
        # Normalization
        "batch_norm shape preserved",
        "layer_norm shape preserved",
        "layer_norm multi-dim",
        "normalize default",
        "normalize with dim",
        # Loss functions
        "cross_entropy",
        "cross_entropy with reduction",
        "mse_loss",
        "mse_loss nonzero",
        "l1_loss",
        "nll_loss",
        "binary_cross_entropy",
        # Dropout
        "dropout eval mode",
        "dropout with opts",
    ])
    def test_fixture(self, name):
        assert _succeeds("Test", name, module=self.mod), f"Test({name!r}) failed"


# ════════════════════════════════════════════════════════════════════════════
# Schedulers and gradient utilities .clausal integration tests
# ════════════════════════════════════════════════════════════════════════════


class TestTorchSchedulersFixture:
    """Run Test predicates from tests/fixtures/torch_schedulers_tests.clausal."""

    @pytest.fixture(autouse=True, scope="class")
    def _setup(self, request):
        request.cls.mod = _load_fixture("torch_schedulers_tests")

    @pytest.mark.parametrize("name", [
        "enumerate schedulers",
        "scheduler lookup StepLR",
        "scheduler lookup MultiStepLR",
        "scheduler lookup CyclicLR",
        "scheduler lookup OneCycleLR",
        "scheduler lookup ReduceLROnPlateau",
        "scheduler lookup LambdaLR",
        "scheduler lookup LinearLR",
        "scheduler lookup ConstantLR",
        "scheduler lookup PolynomialLR",
    ])
    def test_fixture(self, name):
        assert _succeeds("Test", name, module=self.mod), f"Test({name!r}) failed"


# ════════════════════════════════════════════════════════════════════════════
# Scheduler and gradient utility unit tests
# ════════════════════════════════════════════════════════════════════════════


class TestSchedulerGradUtils:
    """Unit tests for current_lr, clip_grad_norm, clip_grad_value.

    These predicates need objects (schedulers, parameter lists with grads)
    that are hard to construct in .clausal, so they are tested via Python.
    """

    def _nn_module(self):
        """Load torch_nn as a Clausal Module for call()."""
        import clausal.modules.py.torch_nn as nn_mod
        from clausal.logic.database import Module
        return Module("torch_nn", module_dict=vars(nn_mod))

    def test_current_lr(self):
        import torch
        from clausal.logic.variables import Var, deref
        model = torch.nn.Linear(2, 2)
        opt = torch.optim.SGD(model.parameters(), lr=0.1)
        sched = torch.optim.lr_scheduler.StepLR(opt, step_size=1)
        result_var = Var()
        mod = self._nn_module()
        for _ in call("current_lr", sched, result_var, module=mod):
            assert deref(result_var) == [0.1]
            break

    def test_clip_grad_norm(self):
        import torch
        from clausal.logic.variables import Var, deref
        model = torch.nn.Linear(2, 2)
        x = torch.randn(1, 2)
        loss = model(x).sum()
        loss.backward()
        params = list(model.parameters())
        result_var = Var()
        mod = self._nn_module()
        for _ in call("clip_grad_norm", params, 1.0, result_var, module=mod):
            assert isinstance(deref(result_var), torch.Tensor)
            break

    def test_clip_grad_value(self):
        import torch
        model = torch.nn.Linear(2, 2)
        x = torch.randn(1, 2)
        loss = model(x).sum()
        loss.backward()
        params = list(model.parameters())
        mod = self._nn_module()
        succeeded = False
        for _ in call("clip_grad_value", params, 0.5, module=mod):
            succeeded = True
            break
        assert succeeded
        # Verify gradients are clipped
        for p in params:
            if p.grad is not None:
                assert p.grad.abs().max() <= 0.5 + 1e-6


# ════════════════════════════════════════════════════════════════════════════
# Infrastructure unit tests
# ════════════════════════════════════════════════════════════════════════════


class TestTorchInfra:
    """Unit tests for torch.py infrastructure."""

    def test_lazy_import_loads_torch(self):
        import clausal.modules.py.torch as impl
        impl._ensure_torch()
        assert impl._torch is not None

    def test_exports_exist(self):
        import clausal.modules.py.torch as impl
        for name in impl.__all__:
            obj = getattr(impl, name)
            assert obj is not None, f"{name} is None"

    def test_pred_arities(self):
        """Verify key predicates have the expected arity variants."""
        import clausal.modules.py.torch as impl
        # zeros should have arity 2 and 3
        assert 2 in impl.zeros._dispatch_fns
        assert 3 in impl.zeros._dispatch_fns
        # shape should have arity 2 only
        assert 2 in impl.shape._dispatch_fns
        # squeeze should have arity 2 and 3
        assert 2 in impl.squeeze._dispatch_fns
        assert 3 in impl.squeeze._dispatch_fns
