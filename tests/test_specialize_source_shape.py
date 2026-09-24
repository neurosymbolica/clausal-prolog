"""``-specialize``'s source program: a predicate is CALLED for its program,
anything else is refused by name -- whatever shape the binding has.

F1 row 34 widened "is it a predicate" to accept the post-flip mangled-atom
binding.  Its first cut tested ``is_mangled``, which a ``-hide`` DATA atom
also passes, so naming one as the source stopped getting this refusal and
was called instead, failing with an unrelated
``existence_error(procedure, hsrc/1)``.
"""

from __future__ import annotations

import sys
import textwrap

import pytest

import clausal.import_hook  # noqa: F401 — installs the meta-path finder
from clausal.import_hook import _load_module


def test_a_hidden_data_atom_as_the_source_is_refused_by_name(tmp_path):
    path = tmp_path / "spsrc_hide.clausal"
    path.write_text(textwrap.dedent("""
        -module(spsrc_hide, [])
        -import_from(clausal.examples.metainterpreters, [solve_count])
        -hide([spsrc_data])

        -specialize(solve_count, spsrc_data, alias=spsrc_spec)
    """).lstrip())
    sys.modules.pop("spsrc_hide", None)
    with pytest.raises(RuntimeError,
                       match="source program 'spsrc_data' must be a "
                             "predicate or list"):
        _load_module("spsrc_hide", str(path))
