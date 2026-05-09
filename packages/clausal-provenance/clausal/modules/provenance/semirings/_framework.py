"""Framework detection for tensor-valued semirings.

Tagged-tensor semirings (``diff_add_mult_prob``, ``diff_min_max_prob``, …)
must work with both PyTorch and JAX *without* either being a hard
dependency of ``clausal-provenance``. This module provides:

- ``detect_framework(tag) -> 'torch' | 'jax' | 'python' | 'mixed'``
- Deferred ``torch_module()`` / ``jax_module()`` accessors (raise a clean
  error if the framework isn't installed when actually needed).
- ``check_homogeneous(tags) -> framework`` — refuses tag-list mixes of
  torch + jax in one ``solve`` call.
"""

from __future__ import annotations

from typing import Any, Iterable


# ── Lazy module accessors ───────────────────────────────────────────────


_torch_mod = None
_torch_loaded = False
_torch_import_error: Exception | None = None


def torch_module():
    """Import torch lazily; cache result. Raises with a clear hint if missing.

    Uses ``clausal.modules.py._import_stdlib`` to bypass the Clausal import
    hook so the *real* PyPI torch package is loaded, not the
    ``clausal-torch`` wrapper.
    """
    global _torch_mod, _torch_loaded, _torch_import_error
    if not _torch_loaded:
        _torch_loaded = True
        try:
            from clausal.modules.py import _import_stdlib
            _torch_mod = _import_stdlib("torch")
        except ImportError as e:
            _torch_import_error = e
    if _torch_mod is None:
        raise ImportError(
            "PyTorch is not installed. Install via `pip install "
            "clausal-provenance[torch]`."
        ) from _torch_import_error
    return _torch_mod


_jax_mod = None
_jnp_mod = None
_jax_loaded = False
_jax_import_error: Exception | None = None


def jax_module():
    """Import jax + jax.numpy lazily, bypassing the Clausal import hook."""
    global _jax_mod, _jnp_mod, _jax_loaded, _jax_import_error
    if not _jax_loaded:
        _jax_loaded = True
        try:
            from clausal.modules.py import _import_stdlib
            _jax_mod = _import_stdlib("jax")
            _jnp_mod = _import_stdlib("jax.numpy")
        except ImportError as e:
            _jax_import_error = e
    if _jax_mod is None:
        raise ImportError(
            "JAX is not installed. Install via `pip install "
            "clausal-provenance[jax]`."
        ) from _jax_import_error
    return _jax_mod, _jnp_mod


# ── Detection ───────────────────────────────────────────────────────────


def _is_torch_tensor(x: Any) -> bool:
    if not _torch_loaded:
        # Lazy-import only on first detection request — but cheaply: try once.
        try:
            torch_module()
        except ImportError:
            return False
    if _torch_mod is None:
        return False
    return isinstance(x, _torch_mod.Tensor)


def _is_jax_array(x: Any) -> bool:
    if not _jax_loaded:
        try:
            jax_module()
        except ImportError:
            return False
    if _jax_mod is None:
        return False
    # ``jax.Array`` covers Tracer, ArrayImpl, etc.
    return isinstance(x, _jax_mod.Array)


def detect_framework(tag: Any) -> str:
    """Return one of ``'torch'``, ``'jax'``, ``'python'``."""
    if _is_torch_tensor(tag):
        return "torch"
    if _is_jax_array(tag):
        return "jax"
    return "python"


def check_homogeneous(tags: Iterable[Any]) -> str:
    """Verify all tags are from the same framework; return that framework name.

    Raises ``ValueError`` if torch and jax tags appear together.
    Returns ``'python'`` when no tensor tags appear.
    """
    seen: set[str] = set()
    for t in tags:
        seen.add(detect_framework(t))
    seen.discard("python")  # plain python tags compose with either
    if len(seen) > 1:
        raise ValueError(
            f"Mixing tag frameworks in one solve is not supported (saw "
            f"{sorted(seen)}). All tagged facts must come from the same "
            "tensor framework."
        )
    return next(iter(seen)) if seen else "python"


__all__ = [
    "detect_framework",
    "check_homogeneous",
    "torch_module",
    "jax_module",
]
