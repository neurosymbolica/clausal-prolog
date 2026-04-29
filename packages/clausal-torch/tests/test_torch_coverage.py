"""Coverage tracking: compare wrapped predicates against PyTorch API.

This test does NOT fail on missing coverage — it reports what's covered
and what isn't, so new PyTorch additions or renames are visible in CI output.

Run with: pytest tests/test_torch_coverage.py -v
"""

import pytest
import warnings


def _get_wrapped_names():
    """Collect all predicate names from torch wrapper modules."""
    names = set()
    import clausal.modules.torch as t
    names.update(t.__all__)
    import clausal.modules.torch_nn as tnn
    names.update(tnn.__all__)
    try:
        import clausal.modules.torch_functional as tf
        names.update(tf.__all__)
    except ImportError:
        pass
    try:
        import clausal.modules.torch_distributions as td
        names.update(td.__all__)
    except ImportError:
        pass
    try:
        import clausal.modules.torch_data as tdata
        names.update(tdata.__all__)
    except ImportError:
        pass
    return names


# Common PyTorch functions/classes that are candidates for wrapping.
# Grouped by category. Each entry is (pytorch_name, wrapper_name_or_None).
# wrapper_name_or_None is the expected predicate name if different from
# the PyTorch name, or None if we just check by pytorch_name.

_TENSOR_CREATION = [
    "tensor", "zeros", "ones", "randn", "arange", "linspace", "full", "eye",
    "zeros_like", "ones_like", "full_like", "rand", "randint", "logspace",
    "diag", "empty",
]

_TENSOR_PROPERTIES = [
    "shape", "dtype", "device", "dim", "element_count", "requires_gradient",
    "is_contiguous",
]

_TENSOR_MATH = [
    "add", "mul", "matmul", "sum", "mean", "max", "min", "clamp", "abs",
    "sub", "div", "pow", "sqrt", "neg",
    "median", "std", "var",
    "argmin", "argmax",
    "cumsum", "cumprod",
    "einsum",
    "sign", "floor", "ceil", "round",
]

_TENSOR_COMPARISON = [
    "eq", "ne", "gt", "lt", "ge", "le", "equal", "allclose",
    "isnan", "isinf", "isfinite",
    "has_nan", "has_inf", "all_finite",
]

_TENSOR_LOGIC = [
    "logical_and", "logical_or", "logical_not", "logical_xor",
    "any", "all",
]

_TENSOR_SHAPE = [
    "reshape", "squeeze", "unsqueeze", "flatten", "unflatten",
    "transpose", "permute", "contiguous",
    "cat", "stack", "split", "chunk", "unbind",
    "narrow", "expand", "repeat", "tile", "flip", "roll",
]

_TENSOR_SELECTION = [
    "where", "masked_select", "index_select", "gather", "scatter",
    "nonzero", "sort", "argsort", "topk", "unique",
]

_TENSOR_CONVERSION = [
    "tensor_numpy", "tensor_list",
]

_LINALG = [
    "det", "inv", "solve", "svd", "eig", "cholesky", "qr",
    "norm", "matrix_rank", "pinv", "cross", "dot",
    "diag", "triu", "tril", "trace",
]

_FFT = [
    "fft_transform", "real_fft", "fft_transform_2d", "fft_transform_nd",
    "fft_shift", "fft_frequencies", "real_fft_frequencies",
]

_ACTIVATIONS = [
    "relu", "softmax", "sigmoid", "tanh",
    "leaky_relu", "elu", "selu", "gelu", "silu", "mish",
    "hardswish", "hardsigmoid",
    "log_softmax",
]

_TRIG_BIJECTIVE = [
    "logarithm", "sine", "cosine", "tangent",
    "atan2",
]

_HYPERBOLIC = ["sinh", "cosh", "tanh"]

_CONV_POOL = [
    "conv1d", "conv2d", "conv3d",
    "max_pool1d", "max_pool2d", "avg_pool1d", "avg_pool2d",
    "adaptive_avg_pool1d", "adaptive_avg_pool2d",
    "pad",
]

_LOSS = [
    "cross_entropy", "mse_loss", "l1_loss", "nll_loss",
    "binary_cross_entropy",
    "smooth_l1_loss", "huber_loss", "kl_div",
]

_NORM = ["batch_norm", "layer_norm", "normalize", "dropout"]

_NN_STRUCTURE = [
    "parameter", "named_parameter", "module", "named_module",
    "child", "named_child",
]

_REGISTRIES = [
    "layer", "activation", "loss_fn", "optimizer_type",
    "scheduler_type", "distribution",
]

_IO = ["save", "load", "dtype_info"]

_DISTRIBUTIONS = [
    "make_distribution", "sample", "log_prob", "entropy",
    "cdf", "icdf", "mean", "variance", "stddev",
]

_DATA = ["tensor_dataset", "dataset_length", "dataset_item", "dataset_element"]

_GRAD_UTILS = ["clip_grad_norm", "clip_grad_value", "current_lr"]

_ALL_EXPECTED = {
    "Tensor Creation": _TENSOR_CREATION,
    "Tensor Properties": _TENSOR_PROPERTIES,
    "Tensor Math": _TENSOR_MATH,
    "Tensor Comparison": _TENSOR_COMPARISON,
    "Tensor Logic": _TENSOR_LOGIC,
    "Tensor Shape": _TENSOR_SHAPE,
    "Tensor Selection": _TENSOR_SELECTION,
    "Tensor Conversion": _TENSOR_CONVERSION,
    "Linear Algebra": _LINALG,
    "FFT": _FFT,
    "Activations": _ACTIVATIONS,
    "Trig (bijective)": _TRIG_BIJECTIVE,
    "Hyperbolic": _HYPERBOLIC,
    "Conv/Pool": _CONV_POOL,
    "Loss Functions": _LOSS,
    "Normalization": _NORM,
    "NN Structure": _NN_STRUCTURE,
    "Registries": _REGISTRIES,
    "IO": _IO,
    "Distributions": _DISTRIBUTIONS,
    "Data": _DATA,
    "Gradient Utils": _GRAD_UTILS,
}


class TestTorchCoverage:
    """Report coverage of PyTorch API by Clausal wrapper.

    These tests WARN on missing coverage rather than failing, so they
    serve as a living checklist rather than a gate.
    """

    @pytest.fixture(autouse=True, scope="class")
    def _setup(self, request):
        request.cls.wrapped = _get_wrapped_names()

    @pytest.mark.parametrize("category,names", list(_ALL_EXPECTED.items()))
    def test_category_coverage(self, category, names):
        # nv
        missing = [n for n in names if n not in self.wrapped]
        if missing:
            warnings.warn(
                f"[{category}] Not wrapped: {', '.join(missing)}",
                stacklevel=1,
            )

    def test_report_full_coverage(self):
        """Summary: overall coverage percentage."""
        # nv
        all_names = []
        for names in _ALL_EXPECTED.values():
            all_names.extend(names)
        all_names = set(all_names)
        covered = all_names & self.wrapped
        missing = all_names - self.wrapped
        pct = len(covered) / len(all_names) * 100 if all_names else 100
        # Always print the report
        print(f"\n{'='*60}")
        print(f"PyTorch wrapper coverage: {len(covered)}/{len(all_names)} ({pct:.0f}%)")
        print(f"Missing ({len(missing)}): {', '.join(sorted(missing))}")
        print(f"{'='*60}")

    def test_no_unexpected_exports(self):
        """Check for predicates not in any expected category."""
        # nv
        all_expected = set()
        for names in _ALL_EXPECTED.values():
            all_expected.update(names)
        # Constants are expected exports but not predicates
        dtype_names = {
            "float16", "float32", "float64", "bfloat16",
            "int8", "int16", "int32", "int64", "uint8",
            "bool", "complex64", "complex128",
            "nan", "inf", "neg_inf",
        }
        extra = self.wrapped - all_expected - dtype_names
        if extra:
            # Not a failure — just informational
            warnings.warn(
                f"Exports not in coverage checklist: {', '.join(sorted(extra))}",
                stacklevel=1,
            )
