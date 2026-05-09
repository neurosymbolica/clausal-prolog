"""In-source provenance.* builtins (solve/4, recover/3, ...).

These are the `.clausal`-side surface of the engine. The Python-side
``query()`` helper in ``clausal.modules.provenance`` is the primary API.
"""

from clausal.modules.provenance.builtins.solver import solve, recover, aggregate

__all__ = ["solve", "recover", "aggregate"]
