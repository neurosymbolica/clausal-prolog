#!/usr/bin/env python3
"""
Build per-file reference docs for the TitleCase → snake_case rename.

For each file in /workspace/clausal/implementation_plans/big_rename/results/
(which contains grep-output of TitleCase matches in the original codebase),
compare with the corresponding file in /workspace/clausal-bigrename/ and
produce a .md reference file under
/workspace/clausal-bigrename/implementation_plans/big_rename/
that mirrors the tree structure.

Each .md file lists:
  - Every distinct TitleCase identifier found in the original
  - Whether it was renamed (and to what) or kept (and why)
"""

import re
import sys
from pathlib import Path
from collections import defaultdict

RESULTS_ROOT = Path("/workspace/clausal/implementation_plans/big_rename/results")
ORIG_ROOT    = Path("/workspace/clausal")
RENAMED_ROOT = Path("/workspace/clausal-bigrename")
OUT_ROOT     = Path("/workspace/clausal-bigrename/implementation_plans/big_rename")

# ── Definitive old predicate name set ──────────────────────────────────────────
# All TitleCase names that were builtin predicates in the original workspace.
# Source: clausal.logic.builtins._BUILTIN_CLASSES + prolog_dialect.BUILTIN_NAME_MAP
OLD_PREDICATE_NAMES = {
    'Abs', 'AllDifferent', 'Append', 'Arg', 'Assert', 'AssertA', 'AssertFirst',
    'AssertZ', 'Atom', 'AtomChars', 'AtomCodes', 'AtomConcat', 'AtomLength',
    'BagOf', 'Between', 'BoolLabeling',
    'Call', 'CallCleanup', 'CallGoal', 'CallNth', 'CanBe',
    'CharCode', 'CharType', 'Circuit', 'ClearAllTables', 'ClearTable',
    'Compound', 'CopyTerm', 'CountAll', 'CurrentTime',
    'DelAttr', 'DictGet', 'DictKeys', 'DictMerge', 'DictPairs', 'DictPut',
    'DictPutPairs', 'DictRemove', 'DictSize', 'DictValues', 'Dif', 'DifT',
    'DivMod', 'DowncaseAtom', 'Drop', 'DropWhile',
    'Element', 'Eq', 'Equivalent', 'Exclude', 'ExpMod', 'Extend',
    'Filter', 'FilterMap', 'FindAll', 'Flatten', 'Float', 'FoldLeft',
    'ForAll', 'Freeze', 'Functor',
    'Gcd', 'GenDict', 'GenSet', 'GenSym', 'GetAttr', 'GetAttrs', 'GetItem',
    'GroupBy', 'GroupPairsByKey',
    'HasUnits',
    'In', 'InCheck', 'InDomain', 'InReal', 'Integer', 'Intersection',
    'IsAtom', 'IsAtomic', 'IsAttVar', 'IsBound', 'IsCallable', 'IsChars',
    'IsCompound', 'IsDict', 'IsFloat', 'IsGround', 'IsInt', 'IsList',
    'IsNumber', 'IsSet', 'IsStr', 'IsVar',
    'Label', 'LabelReal', 'Labeling', 'Last', 'Lcm', 'Length', 'Listing', 'Lsb',
    'MapList', 'Max', 'MaxBy', 'MaxList', 'Member', 'MergeSort', 'Min',
    'MinBy', 'MinList', 'Msb', 'MustBe',
    'Nl', 'NonVar', 'Number', 'NumberChars', 'NumberCodes', 'NumberVars', 'Numlist',
    'PairKeys', 'PairValues', 'Partition', 'Permutation', 'Phrase', 'Plus',
    'Popcount', 'PortrayClause', 'PrintTerm', 'PutAttr', 'PutAttrs',
    'Replicate', 'Retract', 'Reverse',
    'SameLength', 'Sat', 'SatCount', 'ScalarProduct', 'Select', 'Sequence',
    'SetAdd', 'SetDisjoint', 'SetIntersection', 'SetList', 'SetOf',
    'SetRemove', 'SetSize', 'SetSubset', 'SetSubtract', 'SetSymDiff', 'SetUnion',
    'SetupCallCleanup', 'Sign', 'Signature', 'Sort', 'SortBy', 'Span',
    'SplitAt', 'SplitWith', 'Statistics', 'SubAtom', 'SubDict', 'Subtract',
    'Succ', 'Sum', 'SumList',
    'TFilter', 'TPartition', 'Tab', 'Take', 'TakeWhile', 'Taut',
    'TermAttributedVariables', 'TermToString', 'TermVariables', 'TimeGoal',
    'ToSet', 'Translate', 'Transpose',
    'UnboundKeys', 'Union', 'Unpack', 'UpcaseAtom',
    'Var', 'Vary',
    'When', 'Write', 'WriteToString', 'Writeln',
    'Zip',
}

# Mapping from old TitleCase predicate name to new snake_case name
OLD_TO_NEW = {
    'Abs': 'abs_',
    'AllDifferent': 'all_different',
    'Append': 'append',
    'Arg': 'arg',
    'Assert': 'assert_',
    'AssertA': 'asserta',
    'AssertFirst': 'asserta',
    'AssertZ': 'assertz',
    'Atom': 'atom',
    'AtomChars': 'atom_chars',
    'AtomCodes': 'atom_codes',
    'AtomConcat': 'atom_concat',
    'AtomLength': 'atom_length',
    'BagOf': 'bagof',
    'Between': 'between',
    'BoolLabeling': 'bool_labeling',
    'Call': 'call',
    'CallCleanup': 'call_cleanup',
    'CallGoal': 'call_goal',
    'CallNth': 'call_nth',
    'CanBe': 'can_be',
    'CharCode': 'char_code',
    'CharType': 'char_type',
    'Circuit': 'circuit',
    'ClearAllTables': 'abolish_all_tables',
    'ClearTable': 'abolish_table',
    'Compound': 'compound',
    'CopyTerm': 'copy_term',
    'CountAll': 'count_all',
    'CurrentTime': 'current_time',
    'DelAttr': 'del_attr',
    'DictGet': 'dict_get',
    'DictKeys': 'dict_keys',
    'DictMerge': 'dict_merge',
    'DictPairs': 'dict_pairs',
    'DictPut': 'dict_put',
    'DictPutPairs': 'dict_put_pairs',
    'DictRemove': 'dict_remove',
    'DictSize': 'dict_size',
    'DictValues': 'dict_values',
    'Dif': 'dif',
    'DifT': 'dif_t',
    'DivMod': 'divmod_',
    'DowncaseAtom': 'downcase_atom',
    'Drop': 'drop',
    'DropWhile': 'drop_while',
    'Element': 'element',
    'Eq': 'eq',
    'Equivalent': 'equivalent',
    'Exclude': 'exclude',
    'ExpMod': 'exp_mod',
    'Extend': 'extend',
    'Filter': 'include',
    'FilterMap': 'filter_map',
    'FindAll': 'findall',
    'Flatten': 'flatten',
    'Float': 'float_',
    'FoldLeft': 'foldl',
    'ForAll': 'forall',
    'Freeze': 'freeze',
    'Functor': 'functor',
    'Gcd': 'gcd',
    'GenDict': 'gen_dict',
    'GenSet': 'gen_set',
    'GenSym': 'gensym',
    'GetAttr': 'get_attr',
    'GetAttrs': 'get_attrs',
    'GetItem': 'get_item',
    'GroupBy': 'group_by',
    'GroupPairsByKey': 'group_pairs_by_key',
    'HasUnits': 'has_units',
    'In': 'in_',
    'InCheck': 'in_check',
    'InDomain': 'in_domain',
    'InReal': 'in_real',
    'Integer': 'integer',
    'Intersection': 'intersection',
    'IsAtom': 'is_atom',
    'IsAtomic': 'is_atomic',
    'IsAttVar': 'attvar',
    'IsBound': 'is_bound',
    'IsCallable': 'callable_',
    'IsChars': 'is_chars',
    'IsCompound': 'compound',
    'IsDict': 'is_dict',
    'IsFloat': 'float_',
    'IsGround': 'ground',
    'IsInt': 'integer',
    'IsList': 'is_list',
    'IsNumber': 'number',
    'IsSet': 'is_set',
    'IsStr': 'is_str',
    'IsVar': 'var',
    'Label': 'label',
    'LabelReal': 'label_real',
    'Labeling': 'labeling',
    'Last': 'last',
    'Lcm': 'lcm',
    'Length': 'length',
    'Listing': 'listing',
    'Lsb': 'lsb',
    'MapList': 'maplist',
    'Max': 'max_',
    'MaxBy': 'max_by',
    'MaxList': 'max_list',
    'Member': 'member',
    'MergeSort': 'msort',
    'Min': 'min_',
    'MinBy': 'min_by',
    'MinList': 'min_list',
    'Msb': 'msb',
    'MustBe': 'must_be',
    'Nl': 'nl',
    'NonVar': 'nonvar',
    'Number': 'number',
    'NumberChars': 'number_chars',
    'NumberCodes': 'number_codes',
    'NumberVars': 'numbervars',
    'Numlist': 'numlist',
    'PairKeys': 'pairs_keys',
    'PairValues': 'pairs_values',
    'Partition': 'partition',
    'Permutation': 'permutation',
    'Phrase': 'phrase',
    'Plus': 'plus',
    'Popcount': 'popcount',
    'PortrayClause': 'portray_clause',
    'PrintTerm': 'print_term',
    'PutAttr': 'put_attr',
    'PutAttrs': 'put_attrs',
    'Replicate': 'replicate',
    'Retract': 'retract',
    'Reverse': 'reverse',
    'SameLength': 'same_length',
    'Sat': 'sat',
    'SatCount': 'sat_count',
    'ScalarProduct': 'scalar_product',
    'Select': 'select',
    'Sequence': 'sequence',
    'SetAdd': 'set_add',
    'SetDisjoint': 'set_disjoint',
    'SetIntersection': 'set_intersection',
    'SetList': 'set_list',
    'SetOf': 'setof',
    'SetRemove': 'set_remove',
    'SetSize': 'set_size',
    'SetSubset': 'set_subset',
    'SetSubtract': 'set_subtract',
    'SetSymDiff': 'set_sym_diff',
    'SetUnion': 'set_union',
    'SetupCallCleanup': 'setup_call_cleanup',
    'Sign': 'sign',
    'Signature': 'signature',
    'Sort': 'sort',
    'SortBy': 'sort_by',
    'Span': 'span',
    'SplitAt': 'split_at',
    'SplitWith': 'split_with',
    'Statistics': 'statistics',
    'SubAtom': 'sub_atom',
    'SubDict': 'sub_dict',
    'Subtract': 'subtract',
    'Succ': 'succ',
    'Sum': 'sum_',
    'SumList': 'sum_list',
    'TFilter': 'tfilter',
    'TPartition': 'tpartition',
    'Tab': 'tab',
    'Take': 'take',
    'TakeWhile': 'take_while',
    'Taut': 'taut',
    'TermAttributedVariables': 'term_attvars',
    'TermToString': 'term_to_string',
    'TermVariables': 'term_variables',
    'TimeGoal': 'time_goal',
    'ToSet': 'list_to_set',
    'Translate': 'translate',
    'Transpose': 'transpose',
    'UnboundKeys': 'unbound_keys',
    'Union': 'union',
    'Unpack': 'unpack',
    'UpcaseAtom': 'upcase_atom',
    'Var': 'var',
    'Vary': 'vary',
    'When': 'when',
    'Write': 'write',
    'WriteToString': 'write_to_string',
    'Writeln': 'writeln',
    'Zip': 'zip_',
}

# Predicate names verified to still be TitleCase in bigrename (confirmed missed/kept)
# Call, CallGoal, Translate still appear in _BUILTIN_CLASSES as TitleCase
STILL_TITLECASE_BUILTINS = {'Call', 'CallGoal', 'Translate'}

# Python types/classes that happen to share a name with old predicates but are
# legitimately kept TitleCase.  The predicate was renamed; the type kept its name.
# E.g. `Var` is a C-extension type for logical variables; `var/1` is the predicate.
PYTHON_TYPE_ALIASES = {
    'Var',       # C extension type (AttVar); predicate renamed to `var`
    'Compound',  # data structure class; predicate `compound/1` renamed to `compound`
    'Atom',      # atom type; predicate `atom/1` renamed to `atom`
    'Integer',   # int type; predicate `integer/1` renamed to `integer`
    'Float',     # float type; predicate `float_/1`
    'Number',    # number type; predicate `number/1`
    'Functor',   # Functor class; predicate `functor/3` renamed
    'Member',    # might appear in compiler as a structural class reference
    # Python AST comparison operators (from `import ast`):
    'Eq',        # ast.Eq — Python AST comparison node, not clausal Eq/3 predicate
    'Lt', 'LtE', 'Gt', 'GtE', 'NotEq',  # other AST comparison operators
    # Python typing module (from `from typing import ...`):
    'Union',     # typing.Union — type annotation, not clausal Union predicate
    'Optional', 'Sequence', 'Iterator', 'Generator', 'Iterable',
    'Callable', 'Mapping', 'MutableMapping', 'MutableSequence',
    'Awaitable', 'Coroutine', 'AsyncIterator', 'AsyncGenerator',
    'Literal', 'ClassVar', 'Final', 'TypeVar', 'Generic', 'Protocol',
    'NamedTuple', 'TypedDict',
    # Python builtins / stdlib:
    'None',      # NoneType references
    'True', 'False',
    'Exception', 'BaseException', 'SystemExit', 'KeyboardInterrupt',
    'GeneratorExit', 'StopIteration', 'StopAsyncIteration',
    'ArithmeticError', 'LookupError', 'EnvironmentError',
    'ConnectionError', 'BlockingIOError', 'BrokenPipeError',
    'BufferError', 'EOFError', 'FileExistsError', 'FileNotFoundError',
    'InterruptedError', 'IsADirectoryError', 'NotADirectoryError',
    'PermissionError', 'ProcessLookupError', 'TimeoutError',
    'NotImplementedError', 'RecursionError', 'RuntimeError',
    'SyntaxError', 'IndentationError', 'TabError', 'SystemError',
    'UnicodeError', 'UnicodeDecodeError', 'UnicodeEncodeError', 'UnicodeTranslateError',
    'ValueError', 'UnicodeWarning', 'DeprecationWarning', 'FutureWarning',
    'ImportWarning', 'PendingDeprecationWarning', 'ResourceWarning',
    'RuntimeWarning', 'SyntaxWarning', 'UserWarning', 'BytesWarning',
}

TC_IDENT  = re.compile(r'\b([A-Z][a-zA-Z0-9_]*[a-z][a-zA-Z0-9_]*)\b')
CLASS_DEF = re.compile(r'^\s*class\s+([A-Z][A-Za-z0-9_]+)\b')
COMMENT_OR_STR = re.compile(r'^\s*#|^\s*"""')


EXCLUDE_DIRS = {'venv', '.venv', 'build', 'dist', '__pycache__',
                '.git', '.tox', 'node_modules', '.mypy_cache'}


def build_class_set(*roots: Path) -> set:
    """Scan .py files under each root (excluding venv/build/etc) for class names."""
    classes = set()
    for root in roots:
        for py in root.rglob('*.py'):
            # Skip excluded directories anywhere in the path
            if any(part in EXCLUDE_DIRS for part in py.parts):
                continue
            if '.egg-info' in str(py):
                continue
            try:
                for line in py.read_text(errors='replace').splitlines():
                    m = CLASS_DEF.match(line)
                    if m:
                        classes.add(m.group(1))
            except Exception:
                pass
    return classes


def get_result_lines(result_file: Path):
    """Return list of (linenum_str, content_str) from a grep output file."""
    pairs = []
    for line in result_file.read_text(errors='replace').splitlines():
        m = re.match(r'^(\d+):(.*)', line)
        pairs.append((m.group(1), m.group(2)) if m else ('?', line))
    return pairs


def name_in_code_lines(name: str, lines: list[str]) -> bool:
    """Return True if `name` appears in a non-comment, non-docstring line.

    Tracks multi-line docstrings so interior lines aren't flagged as code.
    """
    pattern = re.compile(r'\b' + re.escape(name) + r'\b')
    in_docstring = False
    docstring_delim = None

    for line in lines:
        stripped = line.lstrip()

        # Toggle docstring state
        if not in_docstring:
            for delim in ('"""', "'''"):
                if stripped.startswith(delim):
                    count = stripped.count(delim)
                    if count == 1:
                        # Opening docstring on this line, not closed
                        in_docstring = True
                        docstring_delim = delim
                    # If count >= 2, it's a one-liner docstring — stays False
                    break
            # Comment or docstring line — skip even if pattern matches
            if stripped.startswith('#') or stripped.startswith('"""') or stripped.startswith("'''"):
                continue
            if in_docstring:
                continue
        else:
            # Inside multi-line docstring — check for closing delimiter
            if docstring_delim and docstring_delim in line:
                in_docstring = False
            continue

        # We're in code — check if name appears here
        if pattern.search(line):
            return True

    return False


def classify(name, orig_lines, renamed_lines, file_ext, bigrename_classes):
    """
    Classify a TitleCase name.
    Returns (status, new_name, reason):
      'renamed'        - was a predicate; correctly renamed in bigrename
      'missed'         - was a predicate; still TitleCase in bigrename
      'kept_class'     - Python class / stdlib type (legitimately TitleCase)
      'kept_user_pred' - user-defined predicate in .clausal/.pl (not a builtin)
      'kept_other'     - natural language, comment, or other non-predicate
    """
    renamed_text = '\n'.join(renamed_lines)
    tc_in_renamed = bool(re.search(r'\b' + re.escape(name) + r'\b', renamed_text))

    # For .clausal/.pl files: non-predicate TitleCase names are user predicates
    # (Python class names don't appear in .clausal source)
    if file_ext in ('.clausal', '.pl') and name not in OLD_PREDICATE_NAMES:
        return ('kept_user_pred', name,
                'User-defined predicate or variable — not a builtin')

    # Is it a known Python type alias (C extension etc.) with the same name as a predicate?
    if name in PYTHON_TYPE_ALIASES:
        new_name = OLD_TO_NEW.get(name, name.lower())
        return ('kept_class', name,
                f'Python type/alias kept TitleCase; predicate aspect renamed to `{new_name}`')

    # Is it a known Python class defined in bigrename?
    if name in bigrename_classes:
        # Even if it was also an old predicate name, the class takes priority
        # The predicate aspect would have been renamed separately
        if name in OLD_PREDICATE_NAMES:
            new_name = OLD_TO_NEW.get(name, name.lower())
            snake_in_renamed = bool(re.search(r'\b' + re.escape(new_name) + r'\b', renamed_text))
            if snake_in_renamed:
                return ('kept_class',
                        name,
                        f'Python class (kept TitleCase); predicate aspect renamed to `{new_name}`')
            else:
                return ('kept_class',
                        name,
                        'Python class — TitleCase is for the class, not the predicate')
        return ('kept_class', name, 'Python class defined in bigrename — intentionally TitleCase')

    # Is it a known old predicate name?
    if name in OLD_PREDICATE_NAMES:
        new_name = OLD_TO_NEW.get(name, name.lower())
        if name in STILL_TITLECASE_BUILTINS:
            # Confirmed still TitleCase in _BUILTIN_CLASSES, but check if THIS file
            # has the name in actual code (registration/call) vs just comments/docstrings
            if name_in_code_lines(name, renamed_lines):
                return ('missed', name,
                        f'Predicate still registered/called as TitleCase in bigrename '
                        f'— should be renamed to `{new_name}`')
            else:
                return ('kept_other', name,
                        f'Old name appears only in comments/docstrings in this file '
                        f'(registered as TitleCase in translations_builtin.py/higher_order.py)')
        if tc_in_renamed:
            # TitleCase still present — check if it's in actual code or just comments/docstrings
            tc_in_code = name_in_code_lines(name, renamed_lines)
            snake_in_renamed = bool(re.search(r'\b' + re.escape(new_name) + r'\b', renamed_text))
            if snake_in_renamed:
                # Both present: TitleCase is likely in comments/strings, snake_case is the predicate
                return ('renamed', new_name,
                        f'Renamed to `{new_name}`; old name may still appear in comments/strings')
            elif not tc_in_code:
                # TitleCase only in comments/docstrings — not a missed rename
                return ('kept_other', name,
                        f'Old name appears only in comments/docstrings in renamed file '
                        f'(predicate renamed to `{new_name}` elsewhere)')
            else:
                return ('missed', name,
                        f'Predicate may not have been renamed — TitleCase still in code '
                        f'(expected `{new_name}`)')
        else:
            return ('renamed', new_name,
                    f'Renamed from `{name}` to `{new_name}` (TitleCase no longer present)')

    # Not a predicate, not a bigrename class — check file type
    if file_ext in ('.clausal', '.pl'):
        return ('kept_user_pred', name,
                'User-defined predicate or variable in .clausal/.pl — not a builtin')

    # Everything else: natural language in comments/docs, stdlib types, etc.
    return ('kept_other', name,
            'Natural language, comment word, stdlib type, or non-predicate identifier')


def process_file(result_file: Path, bigrename_classes: set):
    """Process one result file → markdown string (or None if nothing to report)."""
    rel        = result_file.relative_to(RESULTS_ROOT)
    orig_file  = ORIG_ROOT / rel
    renamed_file = RENAMED_ROOT / rel
    file_ext   = orig_file.suffix

    result_lines_raw = get_result_lines(result_file)
    orig_lines    = orig_file.read_text(errors='replace').splitlines() if orig_file.exists() else []
    renamed_lines = renamed_file.read_text(errors='replace').splitlines() if renamed_file.exists() else []

    # Collect TitleCase names + which lines they appear on
    tc_lines: dict[str, list[str]] = defaultdict(list)
    for linenum, content in result_lines_raw:
        for m in TC_IDENT.finditer(content):
            tc_lines[m.group(1)].append(linenum)

    if not tc_lines:
        return None

    # Classify each name
    records = {}
    for name in sorted(tc_lines):
        status, new_name, reason = classify(name, orig_lines, renamed_lines, file_ext, bigrename_classes)
        records[name] = (status, new_name, reason, tc_lines[name])

    # ── Build markdown ──────────────────────────────────────────────────────────
    def fmt_lnums(lnums):
        shown = lnums[:8]
        s = ', '.join(shown)
        if len(lnums) > 8:
            s += f' (+{len(lnums)-8})'
        return s

    def section(title, rows, cols, admonition=None):
        if not rows:
            return []
        out = [f"## {title}", ""]
        if admonition:
            out += [admonition, ""]
        out.append("| " + " | ".join(cols) + " |")
        out.append("|" + "|".join("-" * (len(c) + 2) for c in cols) + "|")
        for row in rows:
            out.append("| " + " | ".join(row) + " |")
        out.append("")
        return out

    md = [f"# {rel}", ""]
    md += [f"**Original:** `{orig_file}`  ",
           f"**Renamed:**  `{renamed_file}` {'(exists)' if renamed_file.exists() else '**NOT FOUND**'}",
           ""]

    groups = defaultdict(list)
    for name, (status, new_name, reason, lnums) in records.items():
        groups[status].append((name, new_name, reason, lnums))

    # Renamed section
    md += section(
        "Renamed — TitleCase predicate → snake_case",
        [( f"`{n}`", f"`{nn}`", fmt_lnums(ln), r)
         for n, nn, r, ln in sorted(groups['renamed'])],
        ["Original", "New Name", "Lines", "Notes"],
    )

    # Missed section
    md += section(
        "POSSIBLY MISSED — predicate still TitleCase",
        [( f"`{n}`", fmt_lnums(ln), r)
         for n, nn, r, ln in sorted(groups['missed'])],
        ["Name", "Lines", "Notes"],
        admonition=("> These were builtin predicate names that may not have been fully renamed "
                    "to snake_case in this file."),
    )

    # Kept class
    md += section(
        "Kept — Python classes / types (intentionally TitleCase)",
        [( f"`{n}`", fmt_lnums(ln), r)
         for n, nn, r, ln in sorted(groups['kept_class'])],
        ["Name", "Lines", "Notes"],
    )

    # User predicates
    md += section(
        "Kept — user-defined predicates / variables (.clausal/.pl)",
        [( f"`{n}`", fmt_lnums(ln), r)
         for n, nn, r, ln in sorted(groups['kept_user_pred'])],
        ["Name", "Lines", "Notes"],
    )

    # Other
    md += section(
        "Kept — natural language / comments / stdlib names",
        [( f"`{n}`", fmt_lnums(ln), r)
         for n, nn, r, ln in sorted(groups['kept_other'])],
        ["Name", "Lines", "Notes"],
    )

    return '\n'.join(md)


def main():
    print("Scanning both workspaces for class definitions...")
    bigrename_classes = build_class_set(RENAMED_ROOT, ORIG_ROOT)
    print(f"  Found {len(bigrename_classes)} class names across both workspaces.")

    result_files = sorted(f for f in RESULTS_ROOT.rglob('*') if f.is_file())
    print(f"Processing {len(result_files)} result files...")

    stats  = defaultdict(int)
    missed_index = []   # (rel_path, name) for all missed predicate names

    for i, rf in enumerate(result_files):
        rel      = rf.relative_to(RESULTS_ROOT)
        out_file = OUT_ROOT / rel.with_suffix(rel.suffix + '.md')

        content = process_file(rf, bigrename_classes)
        if content is None:
            stats['skipped'] += 1
            continue

        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(content + '\n')
        stats['written'] += 1

        if 'POSSIBLY MISSED' in content:
            in_missed_section = False
            for line in content.splitlines():
                if '## POSSIBLY MISSED' in line:
                    in_missed_section = True
                    continue
                if in_missed_section and line.startswith('## '):
                    in_missed_section = False
                if in_missed_section:
                    m = re.match(r'\| `([^`]+)` \|', line)
                    if m:
                        name = m.group(1)
                        if name in OLD_PREDICATE_NAMES:
                            missed_index.append((str(rel), name))

        if (i + 1) % 50 == 0:
            print(f"  {i+1}/{len(result_files)}...")

    # ── Write INDEX.md ──────────────────────────────────────────────────────────
    ix = [
        "# Big Rename Reference Index",
        "",
        "This directory mirrors `/workspace/clausal/implementation_plans/big_rename/results/`.",
        "Each `.md` file documents the TitleCase names found in the corresponding source file,",
        "classified as: renamed, possibly-missed, Python class, user predicate, or other.",
        "",
        f"**Result files processed:** {stats['written'] + stats['skipped']}  ",
        f"**Reference files written:** {stats['written']}  ",
        f"**Skipped (no TitleCase matches):** {stats['skipped']}",
        "",
        "## Classification Legend",
        "",
        "| Category | Meaning |",
        "|----------|---------|",
        "| **Renamed** | Builtin predicate correctly renamed from TitleCase to snake_case |",
        "| **POSSIBLY MISSED** | Builtin predicate still TitleCase in renamed file — verify |",
        "| **Kept — Python class** | Class defined in bigrename — intentionally TitleCase |",
        "| **Kept — user pred** | User-defined predicate in .clausal/.pl — not a builtin |",
        "| **Kept — other** | Natural language, comment, stdlib type, or non-predicate |",
        "",
    ]

    if missed_index:
        unique_missed = sorted(set(missed_index))
        ix += [
            "## Possibly Missed Renames",
            "",
            f"**{len(unique_missed)} (file, name) pairs** where a builtin predicate may not "
            "have been fully renamed:",
            "",
            "| File | Predicate Name |",
            "|------|----------------|",
        ]
        for rel, name in unique_missed:
            ix.append(f"| `{rel}` | `{name}` |")
        ix.append("")
    else:
        ix += ["## Possibly Missed Renames", "", "None detected.", ""]

    ix += [
        "## Directory Structure",
        "",
        "- [`clausal/`](clausal/) — main source and stdlib",
        "- [`tests/`](tests/) — test files",
        "- [`docs/`](docs/) — documentation",
    ]

    (OUT_ROOT / "INDEX.md").write_text('\n'.join(ix) + '\n')

    print(f"\nDone.")
    print(f"  Written: {stats['written']}")
    print(f"  Skipped (no TitleCase): {stats['skipped']}")
    unique_missed = sorted(set(missed_index))
    if unique_missed:
        print(f"\nPOSSIBLY MISSED ({len(unique_missed)} unique file/name pairs):")
        for rel, name in unique_missed[:30]:
            print(f"  {rel}: {name}")
        if len(unique_missed) > 30:
            print(f"  ... see INDEX.md for full list")
    else:
        print("\nNo missed renames detected.")


if __name__ == '__main__':
    main()
