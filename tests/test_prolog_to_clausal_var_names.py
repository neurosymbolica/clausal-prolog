"""An inbound Prolog variable must land on a Clausal VARIABLE, or be refused.

The file used to have one subject: ``prolog_var_to_clausal`` lowercased, so
Prolog ``_PI_`` arrived as ``_pi_`` -- Clausal's module-constant class, not a
variable -- and trailing underscores were stripped to escape it. Import is
the identity now, so the stripping is gone and the rename cases have no
subject left; injectivity and round-trip fidelity replaced them in
tests/test_prolog_var_identity.py.

The CONSEQUENCE did not go away, and is what this file is now about. Most
ISO Prolog variable spellings are Clausal variable spellings, but not all:

    __Foo    dunder                     (excluded from the variable class)

``_PI_`` was the second such case until 2026-09-11, when the module-constant
class was retired: constants are spelled like atoms now, so one leading and
one trailing underscore is an ordinary variable and crosses untouched. It is
kept below as a positive control, because it is the spelling this file was
originally written about.

A dunder is a legal ISO variable. Translated verbatim it produces Clausal
that fails to load, from a `.pl` file that was perfectly well-formed.

The translator already holds the invariant that it never EMITS a name the
loader reads as something other than what was meant; that is why a quoted
functor like ``'Foo'`` is refused rather than translated. These names are
the variable-position instance of it, so they are refused the same way, and
the message names the PROLOG variable rather than the symptom its
translation would eventually cause.

**Refusing is not renaming.** The injectivity that identity buys is intact:
no two Prolog variables are mapped together. A name that cannot cross is
reported, not repaired.

The outbound direction keeps its own subject: a Clausal source file carrying
``-constants`` must refuse to translate, because Prolog has no constants.
"""
import re

import pytest

from clausal.templating.term_rewriting import _is_logic_var_name
from clausal.tools.prolog_dialect import prolog_var_to_clausal
from clausal.tools.clausal_to_prolog import clausal_source_to_prolog
from clausal.tools.prolog_to_clausal import (
    prolog_to_clausal, PrologTranslationError,
)


# ── The mapping itself stays identity ─────────────────────────────────

def test_the_mapping_does_not_rename_these_either():
    """The refusal lives at the call site, not in the mapping function.

    Putting it in ``prolog_var_to_clausal`` would make the function partial
    and tempt a future caller into a "safe" rename, which is how
    non-injectivity got in the first time.
    """
    assert prolog_var_to_clausal("_PI_") == "_PI_"
    assert prolog_var_to_clausal("__Foo") == "__Foo"


# ── Names that cannot cross are refused, naming the Prolog variable ───

@pytest.mark.parametrize("name,why", [
    ("__Foo", "dunder"),
    ("__Bar", "dunder"),
    ("__", "dunder"),
])
def test_variable_that_is_not_a_clausal_variable_is_refused(name, why):
    # The premise the refusal rests on, asserted rather than assumed.
    assert not _is_logic_var_name(name)

    with pytest.raises(PrologTranslationError) as excinfo:
        prolog_to_clausal(f"p({name}) :- q({name}).\n")
    message = str(excinfo.value)
    # The message must name the PROLOG variable, not the symptom.
    assert name in message, message
    assert "variable" in message.lower(), message

    # Every spelling the message OFFERS must itself be a Clausal variable.
    # A remedy that does not work is worse than no remedy: it sends the
    # reader round the loop a second time. Some names have no shorter
    # spelling to offer -- ``__`` would reduce to the anonymous ``_``, which
    # would change what the clause means -- so those get prose instead, and
    # the rule is "whatever you offer must work", not "always offer".
    for suggestion in [q for q in re.findall(r"'([^']+)'", message)
                       if q != name]:
        assert _is_logic_var_name(suggestion), (suggestion, message)


def test_the_offered_remedy_is_a_real_one():
    """Positive control for the rule above, which is vacuous on its own.

    "Every offered spelling works" passes trivially on a message that offers
    none, so at least one case must actually offer one -- and taking the
    remedy must produce a file that translates.
    """
    with pytest.raises(PrologTranslationError) as excinfo:
        prolog_to_clausal("p(__Foo) :- q(__Foo).\n")
    offered = [q for q in re.findall(r"'([^']+)'", str(excinfo.value))
               if q != "__Foo"]
    assert offered, str(excinfo.value)
    for suggestion in offered:
        assert prolog_to_clausal(
            f"p({suggestion}) :- q({suggestion}).\n").strip() == \
            f"p({suggestion}) <- (q({suggestion}))"


def test_the_refusal_fires_in_arithmetic_position_too():
    """``_emit_expr`` is a second call site and had to be guarded separately."""
    with pytest.raises(PrologTranslationError, match="__Foo"):
        prolog_to_clausal("p(X) :- X is __Foo + 1.\n")


# ── Everything else still crosses ─────────────────────────────────────

@pytest.mark.parametrize(
    "name", ["X", "Foo", "FOO", "N0", "_x", "_X", "_Ignored", "X_", "_1_",
             "_PI_", "_MAX_RETRIES_"])
def test_ordinary_variable_spellings_are_untouched(name):
    """Positive control: the guard must not swallow the normal case.

    A refusal test alone would pass on a translator that refused everything.
    ``X_`` and ``_1_`` are here on purpose -- both were near the retired
    constant class without being in it. ``_PI_`` and ``_MAX_RETRIES_`` were
    IN it, and are here because they are the spellings this file was written
    about: since 2026-09-11 they cross like any other variable.
    """
    assert _is_logic_var_name(name)
    assert prolog_to_clausal(f"p({name}) :- q({name}).\n").strip() == \
        f"p({name}) <- (q({name}))"


def test_anonymous_is_not_caught_by_the_guard():
    """``_`` fails ``_is_logic_var_name`` too, but is the wildcard."""
    assert not _is_logic_var_name("_")
    assert prolog_to_clausal("p(_, _) :- q(_).\n").strip() == "p(_, _) <- (q(_))"


# ── Outbound ──────────────────────────────────────────────────────────

def test_outbound_constants_directive_raises_not_implemented():
    source = "-constant_value(pi, 3.14159)\n\nfact(pi),\n"
    with pytest.raises(NotImplementedError, match="constant_value"):
        clausal_source_to_prolog(source)
