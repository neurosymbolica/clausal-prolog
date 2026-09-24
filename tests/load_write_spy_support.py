"""Count load writes at the mutation gate's one door, ``Database.mutate``.

Shared by the "a refused load writes nothing" pins
(``tests/test_mutation_gate.py``, ``tests/test_vocabulary_implements_refused.py``).
Every load that writes a clause opens a ``load-clauses`` transaction there, so
a load refused in the step-3d dry run opens none -- and the same recorder
seeing a permitted load's writes is the positive control.
"""

from __future__ import annotations

from clausal.logic.database import Database, WRITE_LOAD_CLAUSES


class LoadWrites:
    """The ``load-clauses`` transactions opened while installed, as
    ``(author, functor, arity)``."""

    def __init__(self) -> None:
        self.opened: list[tuple[str, str, int]] = []

    def by(self, marker: str) -> list[tuple[str, int]]:
        """The keys written by loads whose author (the source path) contains
        *marker*."""
        return [(functor, arity) for author, functor, arity in self.opened
                if marker in author]


def record_load_writes(monkeypatch) -> LoadWrites:
    """Install the recorder for the rest of the test; *monkeypatch* undoes it
    at teardown.  Install ONCE per test and filter with ``LoadWrites.by``."""
    writes = LoadWrites()
    real = Database.mutate

    def mutate(self, functor, arity, *, author, kind, **kw):
        if kind == WRITE_LOAD_CLAUSES:
            writes.opened.append((str(author), functor, arity))
        return real(self, functor, arity, author=author, kind=kind, **kw)

    monkeypatch.setattr(Database, "mutate", mutate)
    return writes
