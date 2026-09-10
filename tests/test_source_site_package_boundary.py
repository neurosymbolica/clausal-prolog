"""``_source_site`` must not mistake a SIBLING directory for the engine package.

The helper walks the stack for the nearest frame outside the ``clausal``
package, so a diagnostic is attributed to the user's code rather than to
engine internals.  The boundary test was a bare prefix compare against the
package directory, and a bare prefix compare counts any sibling whose name
merely STARTS with that one.

Not hypothetical: the extension distributions install alongside the package,
so ``…/site-packages/clausal_jax/x.py`` starts with ``…/site-packages/clausal``
and a frame from one of them was treated as engine-internal.  The effect is a
diagnostic that names whatever lies further up the stack instead of the line
the user wrote.

Same shape another lane hit the same day in a measurement probe, where
``/workspace/clausal-prepivot-84`` string-started-with ``/workspace/clausal``
and a known-negative control failed to fail.  In a workspace of sibling trees
sharing a name prefix that is the normal case, not the edge one.
"""
from __future__ import annotations

import os

from clausal.logic.predicate import _CLAUSAL_PKG_DIR, _source_site


def _call_from(filename: str):
    """Run ``_source_site`` from a frame whose file is *filename*.

    ``compile`` lets the frame carry any ``co_filename``, which is what the
    helper reads — no file has to exist on disk.
    """
    src = "def probe(site):\n    return site(1)\n"
    namespace: dict = {}
    exec(compile(src, filename, "exec"), namespace)  # noqa: S102
    return namespace["probe"](_source_site)


def test_the_package_dir_carries_a_trailing_separator():
    """The property the boundary rests on, asserted directly so a future
    refactor that drops it fails here rather than in a diagnostic."""
    assert _CLAUSAL_PKG_DIR.endswith(os.sep)


def test_a_sibling_sharing_the_prefix_is_a_user_frame():
    """The regression: a directory whose name merely starts with the package
    directory's is NOT inside the package."""
    sibling = _CLAUSAL_PKG_DIR.rstrip(os.sep) + "_jax" + os.sep + "arrays.py"
    site = _call_from(sibling)
    assert site is not None
    assert site[0] == sibling, (
        "a sibling package was treated as engine-internal and skipped")


def test_a_real_member_of_the_package_is_still_skipped():
    """The negative half, so the fix cannot be 'stop skipping anything'.

    Without this, deleting the boundary check entirely would pass the test
    above.
    """
    inside = os.path.join(_CLAUSAL_PKG_DIR, "logic", "made_up_module.py")
    site = _call_from(inside)
    # The engine frame is skipped, so the site walks up to THIS test file.
    assert site is not None
    assert site[0] != inside
    assert site[0].endswith("test_source_site_package_boundary.py")


def test_a_clausal_source_frame_wins_even_inside_the_package():
    """A ``.clausal`` frame is preferred outright — the first arm of the
    condition, pinned so the separator change did not disturb it."""
    seam = os.path.join(_CLAUSAL_PKG_DIR, "stdlib", "somewhere.clausal")
    site = _call_from(seam)
    assert site is not None
    assert site[0] == seam
