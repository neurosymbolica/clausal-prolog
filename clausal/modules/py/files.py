"""clausal.modules.py.files — File system predicates for Clausal.

Provides relational predicates for file and directory operations:
existence checks, listing, metadata, CRUD, path manipulation, and
temporary files.  Import via::

    -import_from(py.files, [file_exists, directory_files, read_file_to_string,
                            write_string_to_file, join_path])

Or via module import::

    -import_module(py.files)
    # then use py.files.file_exists("data.csv"), py.files.join_path(A_, B_, P_), etc.
"""

from __future__ import annotations

from clausal.modules.py import (
    ModulePredicate,
    _import_stdlib,
    expect_type,
    simple_to_trampoline,
    to_text,
)
_os = _import_stdlib("os")
_shutil = _import_stdlib("shutil")
_tempfile = _import_stdlib("tempfile")

import pathlib

from clausal.logic.variables import Var, deref, is_var, unify


# ── Helper ──────────────────────────────────────────────────────────────


def _require_ground_str(val, pred, arg):
    """Deref and validate a ground TEXT argument. Returns str or None.

    Spec §9.4: a wrapper that takes text accepts a string or an ATOM, and
    both convert to the same ``str`` -- so a path written ``'/tmp/x'`` in a
    ``.clausal`` file works exactly as ``"/tmp/x"`` does under
    ``-double_quotes(chars)``.  Routed through ``to_text``, never ``str()``
    (which would hand the library an atom's tuple repr).

    Used for PATHS and for the CONTENTS a file is written from: text is text
    on both sides of the call, and a source-written ``"hello"`` is an atom in
    the default mode just as a source-written path is.

    *pred* is the registered predicate name/arity (e.g. ``"file_exists/1"``)
    and *arg* the 1-based argument position, used to record a type-mismatch
    note when the value is bound but not text.
    """
    val = deref(val)
    text = to_text(val)
    if text is not None:
        return text
    expect_type(val, str, pred, arg=arg)   # records the note; always False here
    return None


# ── Existence predicates ────────────────────────────────────────────────


def _file_exists_1(path, trail, k):
    """file_exists/1: succeeds if Path is a regular file."""
    path = _require_ground_str(path, "file_exists/1", 1)
    if path is None:
        return
    if pathlib.Path(path).is_file():
        yield None


def _directory_exists_1(path, trail, k):
    """directory_exists/1: succeeds if Path is a directory."""
    path = _require_ground_str(path, "directory_exists/1", 1)
    if path is None:
        return
    if pathlib.Path(path).is_dir():
        yield None


def _path_exists_1(path, trail, k):
    """path_exists/1: succeeds if Path exists (file, directory, or other)."""
    path = _require_ground_str(path, "path_exists/1", 1)
    if path is None:
        return
    if pathlib.Path(path).exists():
        yield None


# ── Directory listing ───────────────────────────────────────────────────


def _directory_files_2(dir_path, files, trail, k):
    """directory_files/2: unify Files with list of filenames in Dir."""
    dir_path = _require_ground_str(dir_path, "directory_files/2", 1)
    if dir_path is None:
        return
    p = pathlib.Path(dir_path)
    if not p.is_dir():
        return
    try:
        entries = sorted(e.name for e in p.iterdir())
    except OSError:
        return
    if unify(files, entries, trail):
        yield None


def _directory_entries_2(dir_path, entry, trail, k):
    """directory_entries/2: enumerate directory entries via backtracking."""
    dir_path = _require_ground_str(dir_path, "directory_entries/2", 1)
    if dir_path is None:
        return
    p = pathlib.Path(dir_path)
    if not p.is_dir():
        return
    try:
        entries = sorted(e.name for e in p.iterdir())
    except OSError:
        return
    for name in entries:
        mark = trail.mark()
        if unify(entry, name, trail):
            yield None
        trail.undo(mark)


# ── File metadata ──────────────────────────────────────────────────────


def _file_size_2(path, size, trail, k):
    """file_size/2: unify Size with file size in bytes."""
    path = _require_ground_str(path, "file_size/2", 1)
    if path is None:
        return
    try:
        st = pathlib.Path(path).stat()
    except OSError:
        return
    if unify(size, st.st_size, trail):
        yield None


def _file_modification_time_2(path, time, trail, k):
    """file_modification_time/2: unify Time with modification timestamp."""
    path = _require_ground_str(path, "file_modification_time/2", 1)
    if path is None:
        return
    try:
        st = pathlib.Path(path).stat()
    except OSError:
        return
    if unify(time, st.st_mtime, trail):
        yield None


# ── Destructive operations ─────────────────────────────────────────────


def _delete_file_1(path, trail, k):
    """delete_file/1: delete a file."""
    path = _require_ground_str(path, "delete_file/1", 1)
    if path is None:
        return
    try:
        pathlib.Path(path).unlink()
    except OSError:
        return
    yield None


def _delete_directory_1(path, trail, k):
    """delete_directory/1: delete an empty directory."""
    path = _require_ground_str(path, "delete_directory/1", 1)
    if path is None:
        return
    try:
        pathlib.Path(path).rmdir()
    except OSError:
        return
    yield None


def _rename_file_2(old, new, trail, k):
    """rename_file/2: rename/move a file or directory."""
    old = _require_ground_str(old, "rename_file/2", 1)
    new = _require_ground_str(new, "rename_file/2", 2)
    if old is None or new is None:
        return
    try:
        pathlib.Path(old).rename(new)
    except OSError:
        return
    yield None


def _copy_file_2(source, destination, trail, k):
    """copy_file/2: copy a file (not directory)."""
    source = _require_ground_str(source, "copy_file/2", 1)
    destination = _require_ground_str(destination, "copy_file/2", 2)
    if source is None or destination is None:
        return
    try:
        _shutil.copy2(source, destination)
    except OSError:
        return
    yield None


# ── Directory creation ─────────────────────────────────────────────────


def _make_directory_1(path, trail, k):
    """make_directory/1: create a directory. Fails if it already exists."""
    path = _require_ground_str(path, "make_directory/1", 1)
    if path is None:
        return
    try:
        pathlib.Path(path).mkdir()
    except OSError:
        return
    yield None


def _make_directory_path_1(path, trail, k):
    """make_directory_path/1: create a directory and all parents (mkdir -p)."""
    path = _require_ground_str(path, "make_directory_path/1", 1)
    if path is None:
        return
    try:
        pathlib.Path(path).mkdir(parents=True, exist_ok=True)
    except OSError:
        return
    yield None


# ── File I/O ───────────────────────────────────────────────────────────


def _read_file_to_string_2(path, contents, trail, k):
    """read_file_to_string/2: read entire file as a string."""
    path = _require_ground_str(path, "read_file_to_string/2", 1)
    if path is None:
        return
    try:
        text = pathlib.Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return
    if unify(contents, text, trail):
        yield None


def _write_string_to_file_2(path, contents, trail, k):
    """write_string_to_file/2: write a string to a file (overwrite)."""
    path = _require_ground_str(path, "write_string_to_file/2", 1)
    if path is None:
        return
    contents = _require_ground_str(contents, "write_string_to_file/2", 2)
    if contents is None:
        return
    try:
        pathlib.Path(path).write_text(contents, encoding="utf-8")
    except OSError:
        return
    yield None


def _append_string_to_file_2(path, contents, trail, k):
    """append_string_to_file/2: append a string to a file."""
    path = _require_ground_str(path, "append_string_to_file/2", 1)
    if path is None:
        return
    contents = _require_ground_str(contents, "append_string_to_file/2", 2)
    if contents is None:
        return
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(contents)
    except OSError:
        return
    yield None


# ── Path manipulation ──────────────────────────────────────────────────


def _absolute_path_2(relative, absolute, trail, k):
    """absolute_path/2: resolve relative path to absolute."""
    relative = _require_ground_str(relative, "absolute_path/2", 1)
    if relative is None:
        return
    resolved = str(pathlib.Path(relative).resolve())
    if unify(absolute, resolved, trail):
        yield None


def _join_path_3(base, relative, joined, trail, k):
    """join_path/3: join two path components."""
    base = _require_ground_str(base, "join_path/3", 1)
    relative = _require_ground_str(relative, "join_path/3", 2)
    if base is None or relative is None:
        return
    result = str(pathlib.Path(base) / relative)
    if unify(joined, result, trail):
        yield None


def _split_path_3(path, directory, filename, trail, k):
    """split_path/3: split path into directory and filename."""
    path = _require_ground_str(path, "split_path/3", 1)
    if path is None:
        return
    p = pathlib.Path(path)
    dir_part = str(p.parent)
    name_part = p.name
    if unify(directory, dir_part, trail) and unify(filename, name_part, trail):
        yield None


def _file_extension_2(path, extension, trail, k):
    """file_extension/2: unify Extension with the file extension (including dot)."""
    path = _require_ground_str(path, "file_extension/2", 1)
    if path is None:
        return
    ext = pathlib.Path(path).suffix
    if unify(extension, ext, trail):
        yield None


# ── Temporary files ────────────────────────────────────────────────────


def _temp_file_1(path, trail, k):
    """temp_file/1: create a temporary file and unify Path with its path."""
    try:
        fd, tmp_path = _tempfile.mkstemp()
        _os.close(fd)
    except OSError:
        return
    if unify(path, tmp_path, trail):
        yield None


def _temp_directory_1(path, trail, k):
    """temp_directory/1: create a temporary directory and unify Path with its path."""
    try:
        tmp_path = _tempfile.mkdtemp()
    except OSError:
        return
    if unify(path, tmp_path, trail):
        yield None


# ── Build and export predicate objects ──────────────────────────────────

file_exists = ModulePredicate("file_exists")
file_exists._register(1, simple_to_trampoline(_file_exists_1))

directory_exists = ModulePredicate("directory_exists")
directory_exists._register(1, simple_to_trampoline(_directory_exists_1))

path_exists = ModulePredicate("path_exists")
path_exists._register(1, simple_to_trampoline(_path_exists_1))

directory_files = ModulePredicate("directory_files")
directory_files._register(2, simple_to_trampoline(_directory_files_2))

directory_entries = ModulePredicate("directory_entries")
directory_entries._register(2, simple_to_trampoline(_directory_entries_2))

file_size = ModulePredicate("file_size")
file_size._register(2, simple_to_trampoline(_file_size_2))

file_modification_time = ModulePredicate("file_modification_time")
file_modification_time._register(2, simple_to_trampoline(_file_modification_time_2))

delete_file = ModulePredicate("delete_file")
delete_file._register(1, simple_to_trampoline(_delete_file_1))

delete_directory = ModulePredicate("delete_directory")
delete_directory._register(1, simple_to_trampoline(_delete_directory_1))

rename_file = ModulePredicate("rename_file")
rename_file._register(2, simple_to_trampoline(_rename_file_2))

copy_file = ModulePredicate("copy_file")
copy_file._register(2, simple_to_trampoline(_copy_file_2))

make_directory = ModulePredicate("make_directory")
make_directory._register(1, simple_to_trampoline(_make_directory_1))

make_directory_path = ModulePredicate("make_directory_path")
make_directory_path._register(1, simple_to_trampoline(_make_directory_path_1))

read_file_to_string = ModulePredicate("read_file_to_string")
read_file_to_string._register(2, simple_to_trampoline(_read_file_to_string_2))

write_string_to_file = ModulePredicate("write_string_to_file")
write_string_to_file._register(2, simple_to_trampoline(_write_string_to_file_2))

append_string_to_file = ModulePredicate("append_string_to_file")
append_string_to_file._register(2, simple_to_trampoline(_append_string_to_file_2))

absolute_path = ModulePredicate("absolute_path")
absolute_path._register(2, simple_to_trampoline(_absolute_path_2))

join_path = ModulePredicate("join_path")
join_path._register(3, simple_to_trampoline(_join_path_3))

split_path = ModulePredicate("split_path")
split_path._register(3, simple_to_trampoline(_split_path_3))

file_extension = ModulePredicate("file_extension")
file_extension._register(2, simple_to_trampoline(_file_extension_2))

temp_file = ModulePredicate("temp_file")
temp_file._register(1, simple_to_trampoline(_temp_file_1))

temp_directory = ModulePredicate("temp_directory")
temp_directory._register(1, simple_to_trampoline(_temp_directory_1))
