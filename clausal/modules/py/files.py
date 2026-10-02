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
    text_result,   # stage 1: a str result is the chars carrier
    ModulePredicate,
    _import_stdlib,
    raise_os_error,
    require_text,
    simple_to_trampoline,
)
_os = _import_stdlib("os")
_shutil = _import_stdlib("shutil")
_tempfile = _import_stdlib("tempfile")

import pathlib

from clausal.logic.variables import Var, deref, is_var, unify


# ── Helper ──────────────────────────────────────────────────────────────
#
# RULED 2026-10-02: a file-system failure in an ACTION raises the ISO term
# (``raise_os_error``): a missing path is existence_error(source_sink, P), a
# path that exists but may not be used permission_error(Action,
# source_sink, P).  The three TESTS (file_exists/1, directory_exists/1,
# path_exists/1) still fail: their failure is the answer.


# ── Existence predicates ────────────────────────────────────────────────


def _file_exists_1(path, trail, k):
    """file_exists/1: succeeds if Path is a regular file.

    A TEST: its failure is the answer, including for a path the process may
    not look at (``os.path.isfile`` answers False on any OSError, as Scryer's
    ``file_exists/1`` does; ``pathlib``'s ``is_file`` raised on EACCES)."""
    path = require_text(path, "file_exists/1", 1)
    if path is None:
        return
    if _os.path.isfile(path):
        yield None


def _directory_exists_1(path, trail, k):
    """directory_exists/1: succeeds if Path is a directory."""
    path = require_text(path, "directory_exists/1", 1)
    if path is None:
        return
    if _os.path.isdir(path):
        yield None


def _path_exists_1(path, trail, k):
    """path_exists/1: succeeds if Path exists (file, directory, or other)."""
    path = require_text(path, "path_exists/1", 1)
    if path is None:
        return
    if _os.path.exists(path):
        yield None


# ── Directory listing ───────────────────────────────────────────────────


def _list_directory(dir_path, dir_term, pred):
    """The sorted entry names of *dir_path*; raises the ISO error when it
    cannot be listed (missing -> existence_error, a file or unreadable ->
    permission_error(open, source_sink, Dir))."""
    try:
        return sorted(e.name for e in pathlib.Path(dir_path).iterdir())
    except OSError as exc:
        raise_os_error(exc, dir_term, pred, path=dir_path)


def _directory_files_2(dir_path, files, trail, k):
    """directory_files/2: unify Files with list of filenames in Dir."""
    dir_term = deref(dir_path)
    dir_path = require_text(dir_path, "directory_files/2", 1)
    entries = _list_directory(dir_path, dir_term, "directory_files/2")
    if unify(files, text_result(entries), trail):
        yield None


def _directory_entries_2(dir_path, entry, trail, k):
    """directory_entries/2: enumerate directory entries via backtracking."""
    dir_term = deref(dir_path)
    dir_path = require_text(dir_path, "directory_entries/2", 1)
    entries = _list_directory(dir_path, dir_term, "directory_entries/2")
    for name in entries:
        mark = trail.mark()
        if unify(entry, text_result(name), trail):
            yield None
        trail.undo(mark)


# ── File metadata ──────────────────────────────────────────────────────


def _file_size_2(path, size, trail, k):
    """file_size/2: unify Size with file size in bytes."""
    path_term = deref(path)
    path = require_text(path, "file_size/2", 1)
    try:
        st = pathlib.Path(path).stat()
    except OSError as exc:
        raise_os_error(exc, path_term, "file_size/2", action="open", path=path)
    if unify(size, st.st_size, trail):
        yield None


def _file_modification_time_2(path, time, trail, k):
    """file_modification_time/2: unify Time with modification timestamp."""
    path_term = deref(path)
    path = require_text(path, "file_modification_time/2", 1)
    try:
        st = pathlib.Path(path).stat()
    except OSError as exc:
        raise_os_error(exc, path_term, "file_modification_time/2", action="open", path=path)
    if unify(time, st.st_mtime, trail):
        yield None


# ── Destructive operations ─────────────────────────────────────────────


def _delete_file_1(path, trail, k):
    """delete_file/1: delete a file."""
    path_term = deref(path)
    path = require_text(path, "delete_file/1", 1)
    try:
        pathlib.Path(path).unlink()
    except OSError as exc:
        raise_os_error(exc, path_term, "delete_file/1", action="modify", path=path)
    yield None


def _delete_directory_1(path, trail, k):
    """delete_directory/1: delete an empty directory."""
    path_term = deref(path)
    path = require_text(path, "delete_directory/1", 1)
    try:
        pathlib.Path(path).rmdir()
    except OSError as exc:
        raise_os_error(exc, path_term, "delete_directory/1", action="modify", path=path)
    yield None


def _culprit_for(exc, *candidates):
    """The (term, text) pair among *candidates* that the OS error names:
    the one whose text is ``exc.filename`` (or ``filename2``), else the
    first."""
    named = {getattr(exc, "filename", None), getattr(exc, "filename2", None)}
    for term, text in candidates:
        if text in named:
            return term, text
    return candidates[0]


def _rename_file_2(old, new, trail, k):
    """rename_file/2: rename/move a file or directory.

    A missing Old is ``existence_error(source_sink, Old)``; a missing
    directory on New's side ``existence_error(source_sink, New)``; a New
    the OS refuses to replace (a directory, a non-empty directory) or a
    place that may not be written ``permission_error(modify, source_sink,
    _)``.  ``os.rename`` names both paths in every error, so the culprit is
    decided by looking: Old when Old is not there or its directory may not
    be written, New otherwise.  Known limit: a refusal that is Old's yet
    leaves its directory writable (EPERM on another user's file in a
    sticky directory, an immutable file) blames New."""
    old_term, new_term = deref(old), deref(new)
    old = require_text(old, "rename_file/2", 1)
    new = require_text(new, "rename_file/2", 2)
    try:
        pathlib.Path(old).rename(new)
    except OSError as exc:
        import errno as _errno  # noqa: PLC0415
        old_dir = _os.path.dirname(_os.path.abspath(old))
        if not _os.path.lexists(old) or (
                exc.errno in (_errno.EACCES, _errno.EPERM)
                and not _os.access(old_dir, _os.W_OK | _os.X_OK)):
            raise_os_error(exc, old_term, "rename_file/2", action="modify",
                           arg=1, path=old)
        raise_os_error(exc, new_term, "rename_file/2", action="modify",
                       arg=2, path=new)
    yield None


def _copy_file_2(source, destination, trail, k):
    """copy_file/2: copy a file (not directory).

    The culprit is the path the OS error names: Source when it is missing,
    a directory or unreadable (``open``), Destination when its directory is
    missing or it may not be written."""
    src_term, dst_term = deref(source), deref(destination)
    source = require_text(source, "copy_file/2", 1)
    destination = require_text(destination, "copy_file/2", 2)
    try:
        _shutil.copy2(source, destination)
    except _shutil.SameFileError as exc:
        # Copying a file onto itself: the destination cannot be opened for
        # output while it is the source.
        from clausal.logic.exceptions import (  # noqa: PLC0415
            LogicException, permission_error,
        )
        raise LogicException(permission_error(
            "open", "source_sink", dst_term,
            f"copy_file/2: argument 2: {exc}")) from exc
    except OSError as exc:
        term, text = _culprit_for(exc, (src_term, source),
                                  (dst_term, destination))
        raise_os_error(exc, term, "copy_file/2",
                       arg=1 if term is src_term else 2, path=text)
    yield None


# ── Directory creation ─────────────────────────────────────────────────


def _make_directory_1(path, trail, k):
    """make_directory/1: create a directory.

    A path that already exists raises ``permission_error(create,
    source_sink, P)`` (it failed before 2026-10-02); a missing parent
    ``existence_error(source_sink, P)``."""
    path_term = deref(path)
    path = require_text(path, "make_directory/1", 1)
    try:
        pathlib.Path(path).mkdir()
    except OSError as exc:
        raise_os_error(exc, path_term, "make_directory/1", action="create", path=path)
    yield None


def _make_directory_path_1(path, trail, k):
    """make_directory_path/1: create a directory and all parents (mkdir -p)."""
    path_term = deref(path)
    path = require_text(path, "make_directory_path/1", 1)
    try:
        pathlib.Path(path).mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise_os_error(exc, path_term, "make_directory_path/1", action="create", path=path)
    yield None


# ── File I/O ───────────────────────────────────────────────────────────


def _read_file_to_string_2(path, contents, trail, k):
    """read_file_to_string/2: read entire file as a string."""
    path_term = deref(path)
    path = require_text(path, "read_file_to_string/2", 1)
    try:
        text = pathlib.Path(path).read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return          # not UTF-8 text: unchanged by the file-system ruling
    except OSError as exc:
        raise_os_error(exc, path_term, "read_file_to_string/2", arg=1,
                       path=path)
    if unify(contents, text_result(text), trail):
        yield None


def _write_string_to_file_2(path, contents, trail, k):
    """write_string_to_file/2: write a string to a file (overwrite)."""
    path_term = deref(path)
    path = require_text(path, "write_string_to_file/2", 1)
    contents = require_text(contents, "write_string_to_file/2", 2)
    try:
        pathlib.Path(path).write_text(contents, encoding="utf-8")
    except OSError as exc:
        raise_os_error(exc, path_term, "write_string_to_file/2", arg=1, path=path)
    yield None


def _append_string_to_file_2(path, contents, trail, k):
    """append_string_to_file/2: append a string to a file."""
    path_term = deref(path)
    path = require_text(path, "append_string_to_file/2", 1)
    contents = require_text(contents, "append_string_to_file/2", 2)
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(contents)
    except OSError as exc:
        raise_os_error(exc, path_term, "append_string_to_file/2", arg=1, path=path)
    yield None


# ── Path manipulation ──────────────────────────────────────────────────


def _absolute_path_2(relative, absolute, trail, k):
    """absolute_path/2: resolve relative path to absolute."""
    relative = require_text(relative, "absolute_path/2", 1)
    if relative is None:
        return
    resolved = str(pathlib.Path(relative).resolve())
    if unify(absolute, text_result(resolved), trail):
        yield None


def _join_path_3(base, relative, joined, trail, k):
    """join_path/3: join two path components."""
    base = require_text(base, "join_path/3", 1)
    relative = require_text(relative, "join_path/3", 2)
    if base is None or relative is None:
        return
    result = str(pathlib.Path(base) / relative)
    if unify(joined, text_result(result), trail):
        yield None


def _split_path_3(path, directory, filename, trail, k):
    """split_path/3: split path into directory and filename."""
    path = require_text(path, "split_path/3", 1)
    if path is None:
        return
    p = pathlib.Path(path)
    dir_part = str(p.parent)
    name_part = p.name
    if unify(directory, text_result(dir_part), trail) and unify(filename, text_result(name_part), trail):
        yield None


def _file_extension_2(path, extension, trail, k):
    """file_extension/2: unify Extension with the file extension (including dot)."""
    path = require_text(path, "file_extension/2", 1)
    if path is None:
        return
    ext = pathlib.Path(path).suffix
    if unify(extension, text_result(ext), trail):
        yield None


# ── Temporary files ────────────────────────────────────────────────────


def _raise_temp_error(exc, pred):
    """A temporary file or directory could not be created: the culprit is
    the path the OS names, else the temporary directory itself."""
    where = getattr(exc, "filename", None)
    if where is None:
        try:
            where = _tempfile.gettempdir()
        except OSError:            # no usable temporary directory at all
            where = _tempfile.tempdir or _os.environ.get("TMPDIR") or "/tmp"
    raise_os_error(exc, text_result(str(where)), pred, action="create",
                   path=str(where))


def _temp_file_1(path, trail, k):
    """temp_file/1: create a temporary file and unify Path with its path."""
    try:
        fd, tmp_path = _tempfile.mkstemp()
        _os.close(fd)
    except OSError as exc:
        _raise_temp_error(exc, "temp_file/1")
    if unify(path, text_result(tmp_path), trail):
        yield None


def _temp_directory_1(path, trail, k):
    """temp_directory/1: create a temporary directory and unify Path with its path."""
    try:
        tmp_path = _tempfile.mkdtemp()
    except OSError as exc:
        _raise_temp_error(exc, "temp_directory/1")
    if unify(path, text_result(tmp_path), trail):
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
