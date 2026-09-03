"""Codepoint interval sets and alphabet partitioning for toklex."""
from __future__ import annotations
import bisect
import unicodedata
from dataclasses import dataclass

_MAX = 0x10FFFF
_CATEGORY_CACHE: dict[str, "CharSet"] = {}


def _normalize(ivs):
    """Sort, merge overlapping/adjacent inclusive intervals."""
    out = []
    for lo, hi in sorted(ivs):
        if out and lo <= out[-1][1] + 1:
            out[-1] = (out[-1][0], max(out[-1][1], hi))
        else:
            out.append((lo, hi))
    return tuple(out)


@dataclass(frozen=True)
class CharSet:
    ivs: tuple[tuple[int, int], ...]

    @classmethod
    def from_chars(cls, chars):
        return cls(_normalize([(ord(c), ord(c)) for c in chars]))

    @classmethod
    def from_ranges(cls, ranges):
        return cls(_normalize([(ord(a), ord(b)) for a, b in ranges]))

    @classmethod
    def from_unicode_category(cls, cat):
        if cat not in _CATEGORY_CACHE:
            ivs, run = [], None
            for cp in range(_MAX + 1):
                if unicodedata.category(chr(cp)) == cat:
                    if run and cp == run[1] + 1:
                        run = (run[0], cp)
                    else:
                        if run:
                            ivs.append(run)
                        run = (cp, cp)
            if run:
                ivs.append(run)
            _CATEGORY_CACHE[cat] = cls(tuple(ivs))
        return _CATEGORY_CACHE[cat]

    @classmethod
    def full(cls):
        return cls(((0, _MAX),))

    @classmethod
    def empty(cls):
        return cls(())

    def contains(self, ch):
        cp = ord(ch)
        i = bisect.bisect_right(self.ivs, (cp, _MAX)) - 1
        return i >= 0 and self.ivs[i][0] <= cp <= self.ivs[i][1]

    def is_empty(self):
        return not self.ivs

    def __or__(self, other):
        return CharSet(_normalize(list(self.ivs) + list(other.ivs)))

    def __and__(self, other):
        out, j = [], 0
        for lo, hi in self.ivs:
            for olo, ohi in other.ivs:
                s, e = max(lo, olo), min(hi, ohi)
                if s <= e:
                    out.append((s, e))
        return CharSet(_normalize(out))

    def __sub__(self, other):
        comp, prev = [], 0
        for lo, hi in other.ivs:
            if prev <= lo - 1:
                comp.append((prev, lo - 1))
            prev = hi + 1
        if prev <= _MAX:
            comp.append((prev, _MAX))
        return self & CharSet(tuple(comp))


@dataclass(frozen=True)
class Partition:
    """Exact alphabet partition over CharSet list.

    Cells partition U+0000..U+10FFFF such that each input set is
    a union of complete cells (no cell straddles a set boundary).
    """
    starts: tuple[int, ...]  # codepoint where each cell starts

    @classmethod
    def build(cls, sets: list[CharSet]) -> Partition:
        """Build partition from a list of CharSets.

        Collects all interval boundaries and creates cells between them,
        ensuring no cell straddles a set boundary.
        """
        # Collect all cut points: interval boundaries plus universe boundaries
        cuts = set()
        cuts.add(0)
        cuts.add(_MAX + 1)

        for cs in sets:
            for lo, hi in cs.ivs:
                cuts.add(lo)
                cuts.add(hi + 1)

        # Sort cut points
        sorted_cuts = sorted(cuts)

        # Each adjacent pair defines a cell; store the start codepoint of each
        starts = tuple(sorted_cuts[:-1])

        return cls(starts)

    @property
    def n(self) -> int:
        """Number of cells (symbols)."""
        return len(self.starts)

    def symbol_of(self, ch: str) -> int:
        """Get the symbol (cell id) for a codepoint."""
        cp = ord(ch)
        # bisect_right finds the insertion point; subtract 1 to get the cell
        idx = bisect.bisect_right(self.starts, cp) - 1
        return idx

    def symbols_of(self, cs: CharSet) -> frozenset[int]:
        """Get all symbols whose start codepoint is in the CharSet."""
        syms = set()
        for sym in range(self.n):
            if cs.contains(chr(self.starts[sym])):
                syms.add(sym)
        return frozenset(syms)

    def sample(self, sym: int) -> str:
        """Get a representative character for a symbol."""
        return chr(self.starts[sym])

    def cells(self) -> tuple[tuple[int, int], ...]:
        """Read-only view of each symbol's inclusive (lo, hi) codepoint bounds.

        ``cells()[sym] == (lo, hi)`` where ``lo`` is ``self.starts[sym]`` and
        ``hi`` is one less than the next cell's start (or ``_MAX`` for the
        last cell). Additive accessor for interchange dumps that need cell
        bounds without reaching into ``starts`` directly.
        """
        out = []
        n = len(self.starts)
        for i, lo in enumerate(self.starts):
            hi = self.starts[i + 1] - 1 if i + 1 < n else _MAX
            out.append((lo, hi))
        return tuple(out)
