"""What an inbound Prolog variable name can land on, now that import is identity.

The file used to have one subject: ``prolog_var_to_clausal`` lowercased, so
Prolog ``_PI_`` arrived as ``_pi_`` — Clausal's *module constant* lexical
class, not a variable — and trailing underscores were stripped to escape it.
Import is now the identity, so the stripping is gone and those cases have no
subject left; injectivity and round-trip fidelity replaced them in
tests/test_prolog_var_identity.py.

What survives here is the consequence, which did NOT go away: a Prolog
variable spelled ``_PI_`` still arrives constant-shaped.  It is now a LOUD
failure at load rather than a quiet rename, and that is the thing worth
pinning — a future guard that silently renames it again would be a
regression against injectivity, so it has to be a deliberate change to this
test rather than an accident.

The outbound direction keeps its own subject: a Clausal source file carrying
``-constants`` must refuse to translate, because Prolog has no constants.
"""
import os

import pytest

from clausal.import_hook import _load_module
from clausal.templating.term_rewriting import (
    _is_constant_name, _is_logic_var_name,
)
from clausal.tools.prolog_dialect import prolog_var_to_clausal
from clausal.tools.clausal_to_prolog import clausal_source_to_prolog
from clausal.tools.prolog_to_clausal import prolog_to_clausal


def _load(tmp_path, source: str, name: str):
    path = os.path.join(str(tmp_path), f"{name}.clausal")
    with open(path, "w") as f:
        f.write(source)
    return _load_module(name, path)


def test_constant_shaped_prolog_var_crosses_unchanged():
    """``_PI_`` is a legal Prolog VARIABLE and imports verbatim.

    It is not renamed to dodge Clausal's constant class: renaming is what
    made the old rule non-injective in the first place.
    """
    assert prolog_var_to_clausal("_PI_") == "_PI_"
    assert prolog_to_clausal("p(_PI_) :- q(_PI_).\n").strip() == "p(_PI_) <- (q(_PI_))"


def test_constant_shaped_prolog_var_fails_loudly_at_load(tmp_path):
    """The consequence, observed rather than asserted about.

    ``_PI_`` is constant-shaped and therefore NOT a logic variable in
    Clausal, so the imported module does not load.  The old rule hid this by
    renaming; the trade is a rename that could merge two variables against a
    diagnostic that names the file, the line and the remedy.
    """
    assert _is_constant_name("_PI_")
    assert not _is_logic_var_name("_PI_")

    source = prolog_to_clausal("p(_PI_) :- q(_PI_).\n")
    with pytest.raises(SyntaxError, match="constant name"):
        _load(tmp_path, source + "\n", "var_names_constant_shaped")


def test_outbound_constants_directive_raises_not_implemented():
    source = "-constants(_PI_ = 3.14159)\n\nfact(_PI_),\n"
    with pytest.raises(NotImplementedError, match="constants"):
        clausal_source_to_prolog(source)
