# tools/clpq_reference/rename.py
"""Rename atoms in a Prolog file per rename_map.tsv (the reading copy).

Usage: rename.py MAP SRC DST [OTHER_SOURCE ...]

Rewrites unquoted atoms only, leaving variables, numbers, quoted atoms,
strings and comments as they are.  Before writing anything it checks the
map against the atoms of SRC and of every OTHER_SOURCE:

- no two old atoms map to the same new atom;
- no new atom is an atom already in the sources (or already a key of the
  map), unless it is that atom's own identity row.

Either failure exits with status 2 and a message naming the atoms.
"""
import re
import sys

TOKEN = re.compile(
    r"(%[^\n]*)"                        # 1 line comment
    r"|(/\*.*?\*/)"                     # 2 block comment
    r"|('(?:[^'\\]|\\.|'')*')"          # 3 quoted atom
    r"|(\"(?:[^\"\\]|\\.|\"\")*\")"     # 4 string
    r"|(0'(?:''|\\.|.))"                # 5 character code
    r"|([0-9][A-Za-z0-9_]*)"            # 6 number (0b00, 0x1f, 1e10, 12)
    r"|([A-Z_][A-Za-z0-9_]*)"           # 7 variable
    r"|([a-z][A-Za-z0-9_]*)"            # 8 unquoted atom: the only thing renamed
    r"|(.)", re.S)

ATOM_GROUP = 8


class MapError(Exception):
    pass


def load_map(path):
    pairs = {}
    with open(path) as handle:
        for number, line in enumerate(handle, 1):
            if not line.strip() or line.startswith("#"):
                continue
            fields = line.rstrip("\n").split("\t")
            if len(fields) != 2 or not all(fields):
                raise MapError(f"{path}:{number}: expected 'old<TAB>new', got {line!r}")
            old, new = fields
            if old in pairs:
                raise MapError(f"{path}:{number}: {old!r} has two rows")
            pairs[old] = new
    return pairs


def atoms_in(text):
    """Every unquoted atom in *text*, outside comments, strings and quotes."""
    return {m.group(ATOM_GROUP) for m in TOKEN.finditer(text)
            if m.group(ATOM_GROUP) is not None}


def check_map(pairs, source_atoms):
    """Raise MapError unless *pairs* is injective and renames onto no
    atom that already exists (in *source_atoms* or as a key of *pairs*)."""
    problems = []
    owner = {}
    for old, new in sorted(pairs.items()):
        if new in owner:
            problems.append(f"{owner[new]!r} and {old!r} both map to {new!r}")
        else:
            owner[new] = old
    existing = set(source_atoms) | set(pairs)
    for old, new in sorted(pairs.items()):
        if new != old and new in existing:
            problems.append(f"{old!r} -> {new!r}: {new!r} is already an atom "
                            f"in the sources")
    if problems:
        raise MapError("rename map refused:\n  " + "\n  ".join(problems))


def rename(text, pairs):
    out = []
    for m in TOKEN.finditer(text):
        atom = m.group(ATOM_GROUP)
        out.append(pairs.get(atom, atom) if atom is not None else m.group(0))
    return "".join(out)


def main(argv):
    if len(argv) < 3:
        sys.exit(__doc__)
    map_path, source, destination, *others = argv
    pairs = load_map(map_path)
    with open(source) as handle:
        text = handle.read()
    atoms = atoms_in(text)
    for other in others:
        with open(other) as handle:
            atoms |= atoms_in(handle.read())
    check_map(pairs, atoms)
    with open(destination, "w") as handle:
        handle.write(rename(text, pairs))


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except MapError as error:
        print(f"rename.py: {error}", file=sys.stderr)
        sys.exit(2)
