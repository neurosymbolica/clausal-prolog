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
