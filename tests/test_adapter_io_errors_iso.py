"""py.* adapters: a file-system or network failure RAISES an ISO error.

RULED 2026-10-02.  Each case below failed the goal (or escaped as a raw
Python error term) before:

- a missing file or directory -> ``existence_error(source_sink, Path)``
  (ISO 8.11.5.3 j);
- a path that exists but may not be used -- no permission, a directory
  where a file is needed, a file where a directory is needed, a name that
  is already taken, a directory that is not empty ->
  ``permission_error(Action, source_sink, Path)`` (8.11.5.3 k), Action
  ``open`` (read, write, list), ``modify`` (delete, rename) or ``create``;
- a program that cannot be started -> ``existence_error(source_sink, P)``
  or ``permission_error(create, process, P)`` (Scryer's process_create/3);
- a network failure -> ``existence_error(source_sink, Host)`` for a host
  that does not resolve, ``system_error(connection_refused)`` and kin,
  ``resource_error(timeout)``; an HTTP error status in a body-only
  predicate -> existence_error (404/410), permission_error (401/403/407),
  ``system_error(http_status(S))`` otherwise.

The TESTS keep failing -- ``file_exists/1``, ``directory_exists/1``,
``path_exists/1`` -- and a VALUE stays a value: an exit status, an HTTP
status from ``request/3``, a ``process_create/4`` timeout.

No test needs the internet: refusal is a local socket that is bound but
not listening, DNS is the reserved ``.invalid`` TLD (RFC 6761), statuses
come from a local ``http.server``.  A sandbox that forbids sockets skips
the network tests (``_needs_sockets``).
"""

from __future__ import annotations

import errno
import http.server
import os
import socket
import stat
import textwrap
import threading

import pytest

from clausal.logic.atoms import mint
from clausal.logic.cells import chars
from clausal.logic.exceptions import LogicException
from clausal.logic.variables import Trail, Var, deref
from clausal.modules.py import os_error_term
from clausal.modules.py import csv as pcsv
from clausal.modules.py import files as pfiles
from clausal.modules.py import http as phttp
from clausal.modules.py import json as pjson
from clausal.modules.py import logging as plogging
from clausal.modules.py import os as pos
from clausal.modules.py import process as pprocess
from clausal.modules.py import sqlite as psqlite
from clausal.modules.py import tcp as ptcp
from clausal.terms import DictTerm


def raised(fn, *args):
    with pytest.raises(LogicException) as info:
        list(fn(*args, Trail(), None))
    return info.value.term


def solutions(fn, *args):
    return list(fn(*args, Trail(), None))


def _err(formal, name, arity):
    return ("error", formal, ("/", name, arity))


def _exists(culprit):
    return ("existence_error", "source_sink", culprit)


def _perm(action, culprit, obj="source_sink"):
    return ("permission_error", action, obj, culprit)


_root = pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0,
    reason="root ignores file permissions")


def _sockets_allowed() -> bool:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("127.0.0.1", 0))
        s.close()
        return True
    except OSError:
        return False


_needs_sockets = pytest.mark.skipif(
    not _sockets_allowed(), reason="the sandbox forbids sockets")


@pytest.fixture
def unreadable(tmp_path):
    """A file and a directory with every permission bit cleared."""
    f = tmp_path / "secret.txt"
    f.write_text("x")
    d = tmp_path / "locked"
    d.mkdir()
    (d / "inner.txt").write_text("y")
    os.chmod(f, 0)
    os.chmod(d, 0)
    yield f, d
    os.chmod(d, stat.S_IRWXU)
    os.chmod(f, stat.S_IRUSR | stat.S_IWUSR)


# ── the shared mapping ───────────────────────────────────────────────────


@pytest.mark.parametrize("exc, formal", [
    (FileNotFoundError(errno.ENOENT, "x"), _exists("P")),
    (PermissionError(errno.EACCES, "x"), _perm("open", "P")),
    (IsADirectoryError(errno.EISDIR, "x"), _perm("open", "P")),
    (FileExistsError(errno.EEXIST, "x"), _perm("open", "P")),
    (OSError(errno.ENOTEMPTY, "x"), _perm("open", "P")),
    (OSError(errno.EROFS, "x"), _perm("open", "P")),
    (OSError(errno.EMFILE, "x"), ("resource_error", "file_descriptors")),
    (OSError(errno.ENOSPC, "x"), ("resource_error", "disk_space")),
    (TimeoutError("timed out"), ("resource_error", "timeout")),
    (socket.timeout("timed out"), ("resource_error", "timeout")),
    (ConnectionRefusedError(errno.ECONNREFUSED, "x"),
     ("system_error", "connection_refused")),
    (ConnectionResetError(errno.ECONNRESET, "x"),
     ("system_error", "connection_reset")),
    (BrokenPipeError(errno.EPIPE, "x"), ("system_error", "broken_pipe")),
    (OSError(errno.EHOSTUNREACH, "x"), ("system_error", "host_unreachable")),
    (OSError(errno.EADDRINUSE, "x"), ("system_error", "address_in_use")),
    (socket.gaierror(socket.EAI_NONAME, "x"), _exists("P")),
    (socket.gaierror(socket.EAI_AGAIN, "x"),
     ("system_error", "host_lookup_failed")),
    (OSError(errno.EXDEV, "x"), ("system_error", "exdev")),
    (OSError("no errno"), ("system_error", "io_error")),
])
def test_os_error_term_mapping(exc, formal):
    assert os_error_term(exc, "P", "p/1") == _err(formal, "p", 1)


def test_os_error_term_action_is_the_callers():
    exc = PermissionError(errno.EACCES, "x")
    assert os_error_term(exc, "P", "p/1", action="modify") == _err(
        _perm("modify", "P"), "p", 1)


def test_enotdir_through_a_file_is_existence_but_naming_a_file_is_permission(
        tmp_path):
    f = tmp_path / "f.txt"
    f.write_text("x")
    exc = NotADirectoryError(errno.ENOTDIR, "x")
    through = str(f / "below")
    assert os_error_term(exc, "P", "p/1", path=through)[1] == _exists("P")
    assert os_error_term(exc, "P", "p/1", path=str(f))[1] == _perm("open", "P")


# ── the TESTS still fail ─────────────────────────────────────────────────


@pytest.mark.parametrize("fn", [
    pfiles._file_exists_1, pfiles._directory_exists_1, pfiles._path_exists_1,
])
def test_existence_tests_still_fail(fn, tmp_path):
    assert solutions(fn, chars(str(tmp_path / "missing"))) == []


@_root
def test_existence_tests_fail_behind_an_unreadable_directory(unreadable):
    _f, d = unreadable
    assert solutions(pfiles._file_exists_1, chars(str(d / "inner.txt"))) == []


# ── py.files actions ─────────────────────────────────────────────────────


def test_directory_files_on_a_file_is_a_permission_error(tmp_path):
    f = tmp_path / "f.txt"
    f.write_text("x")
    p = chars(str(f))
    assert raised(pfiles._directory_files_2, p, Var()) == _err(
        _perm("open", p), "directory_files", 2)


def test_directory_entries_missing_is_an_existence_error(tmp_path):
    p = chars(str(tmp_path / "nope"))
    assert raised(pfiles._directory_entries_2, p, Var()) == _err(
        _exists(p), "directory_entries", 2)


@_root
def test_directory_files_unreadable_is_a_permission_error(unreadable):
    _f, d = unreadable
    p = chars(str(d))
    assert raised(pfiles._directory_files_2, p, Var()) == _err(
        _perm("open", p), "directory_files", 2)


@_root
def test_read_file_to_string_unreadable_is_a_permission_error(unreadable):
    f, _d = unreadable
    p = chars(str(f))
    assert raised(pfiles._read_file_to_string_2, p, Var()) == _err(
        _perm("open", p), "read_file_to_string", 2)


def test_read_file_to_string_of_a_directory_is_a_permission_error(tmp_path):
    p = chars(str(tmp_path))
    assert raised(pfiles._read_file_to_string_2, p, Var()) == _err(
        _perm("open", p), "read_file_to_string", 2)


def test_write_into_a_missing_directory_is_an_existence_error(tmp_path):
    p = chars(str(tmp_path / "no" / "f.txt"))
    for fn, name in ((pfiles._write_string_to_file_2, "write_string_to_file"),
                     (pfiles._append_string_to_file_2,
                      "append_string_to_file")):
        assert raised(fn, p, chars("x")) == _err(_exists(p), name, 2)


def test_write_through_a_file_is_an_existence_error(tmp_path):
    f = tmp_path / "f.txt"
    f.write_text("x")
    p = chars(str(f / "g.txt"))
    assert raised(pfiles._write_string_to_file_2, p, chars("x")) == _err(
        _exists(p), "write_string_to_file", 2)


@_root
def test_write_into_a_read_only_directory_is_a_permission_error(tmp_path):
    d = tmp_path / "ro"
    d.mkdir()
    os.chmod(d, stat.S_IRUSR | stat.S_IXUSR)
    try:
        p = chars(str(d / "f.txt"))
        assert raised(pfiles._write_string_to_file_2, p, chars("x")) == _err(
            _perm("open", p), "write_string_to_file", 2)
    finally:
        os.chmod(d, stat.S_IRWXU)


def test_delete_file_of_a_directory_is_a_permission_error(tmp_path):
    p = chars(str(tmp_path))
    assert raised(pfiles._delete_file_1, p) == _err(
        _perm("modify", p), "delete_file", 1)


def test_delete_directory_of_a_file_is_a_permission_error(tmp_path):
    f = tmp_path / "f.txt"
    f.write_text("x")
    p = chars(str(f))
    assert raised(pfiles._delete_directory_1, p) == _err(
        _perm("modify", p), "delete_directory", 1)


def test_delete_directory_missing_is_an_existence_error(tmp_path):
    p = chars(str(tmp_path / "nope"))
    assert raised(pfiles._delete_directory_1, p) == _err(
        _exists(p), "delete_directory", 1)


@_root
def test_delete_file_in_a_read_only_directory_is_a_permission_error(tmp_path):
    d = tmp_path / "ro"
    d.mkdir()
    (d / "f.txt").write_text("x")
    os.chmod(d, stat.S_IRUSR | stat.S_IXUSR)
    try:
        p = chars(str(d / "f.txt"))
        assert raised(pfiles._delete_file_1, p) == _err(
            _perm("modify", p), "delete_file", 1)
    finally:
        os.chmod(d, stat.S_IRWXU)


def test_rename_into_a_missing_directory_blames_the_new_name(tmp_path):
    old = tmp_path / "a.txt"
    old.write_text("x")
    new = chars(str(tmp_path / "no" / "b.txt"))
    assert raised(pfiles._rename_file_2, chars(str(old)), new) == _err(
        _exists(new), "rename_file", 2)


def test_rename_a_file_onto_a_directory_is_a_permission_error(tmp_path):
    old = tmp_path / "a.txt"
    old.write_text("x")
    d = tmp_path / "d"
    d.mkdir()
    (d / "keep").write_text("y")
    new = chars(str(d))
    assert raised(pfiles._rename_file_2, chars(str(old)), new) == _err(
        _perm("modify", new), "rename_file", 2)


def test_copy_into_a_missing_directory_blames_the_destination(tmp_path):
    src = tmp_path / "a.txt"
    src.write_text("x")
    dst = chars(str(tmp_path / "no" / "b.txt"))
    assert raised(pfiles._copy_file_2, chars(str(src)), dst) == _err(
        _exists(dst), "copy_file", 2)


def test_copy_of_a_directory_is_a_permission_error(tmp_path):
    src = chars(str(tmp_path))
    dst = chars(str(tmp_path / "copy"))
    assert raised(pfiles._copy_file_2, src, dst) == _err(
        _perm("open", src), "copy_file", 2)


def test_copy_onto_itself_is_a_permission_error(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("x")
    p = chars(str(f))
    assert raised(pfiles._copy_file_2, p, p) == _err(
        _perm("open", p), "copy_file", 2)


def test_make_directory_missing_parent_is_an_existence_error(tmp_path):
    p = chars(str(tmp_path / "no" / "d"))
    assert raised(pfiles._make_directory_1, p) == _err(
        _exists(p), "make_directory", 1)


def test_make_directory_path_over_a_file_is_a_permission_error(tmp_path):
    f = tmp_path / "f.txt"
    f.write_text("x")
    p = chars(str(f))
    assert raised(pfiles._make_directory_path_1, p) == _err(
        _perm("create", p), "make_directory_path", 1)


def test_temp_file_with_no_usable_tmpdir_raises(tmp_path, monkeypatch):
    import tempfile
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "gone"))
    term = raised(pfiles._temp_file_1, Var())
    assert term[1][0] == "existence_error"
    assert term[2] == ("/", "temp_file", 1)


# ── py.os ────────────────────────────────────────────────────────────────


def test_change_directory_to_a_file_is_a_permission_error(tmp_path):
    f = tmp_path / "f.txt"
    f.write_text("x")
    p = chars(str(f))
    assert raised(pos._change_directory_1, p) == _err(
        _perm("open", p), "change_directory", 1)


@_root
def test_change_directory_unenterable_is_a_permission_error(unreadable):
    _f, d = unreadable
    p = chars(str(d))
    here = os.getcwd()
    try:
        assert raised(pos._change_directory_1, p) == _err(
            _perm("open", p), "change_directory", 1)
    finally:
        os.chdir(here)


# ── py.csv / py.json file I/O ────────────────────────────────────────────


@pytest.mark.parametrize("fn, name", [
    (pcsv._read_file_2, "read_file"), (pcsv._read_records_2, "read_records"),
    (pjson._read_file_2, "read_file"),
])
def test_reading_a_directory_is_a_permission_error(fn, name, tmp_path):
    p = chars(str(tmp_path))
    assert raised(fn, p, Var()) == _err(_perm("open", p), name, 2)


@_root
@pytest.mark.parametrize("fn", [pcsv._read_file_2, pjson._read_file_2])
def test_reading_an_unreadable_file_is_a_permission_error(fn, unreadable):
    f, _d = unreadable
    p = chars(str(f))
    assert raised(fn, p, Var()) == _err(_perm("open", p), "read_file", 2)


@pytest.mark.parametrize("fn, data", [
    (pcsv._write_file_2, [[chars("a")]]),
    (pjson._write_file_2, DictTerm({mint("a"): 1})),
])
def test_writing_into_a_missing_directory_is_an_existence_error(
        fn, data, tmp_path):
    p = chars(str(tmp_path / "no" / "out"))
    assert raised(fn, p, data) == _err(_exists(p), "write_file", 2)


# ── py.logging, py.sqlite, reflection ────────────────────────────────────


def test_file_handler_in_a_missing_directory_is_an_existence_error(tmp_path):
    p = chars(str(tmp_path / "no" / "app.log"))
    assert raised(plogging._file_handler_2, p, Var()) == _err(
        _exists(p), "file_handler", 2)


def test_sqlite_connect_in_a_missing_directory_is_an_existence_error(
        tmp_path):
    p = chars(str(tmp_path / "no" / "db.sqlite"))
    alias = chars("ioerr_missing_dir")
    assert raised(psqlite._sqlite_connect_2, p, alias) == _err(
        _exists(p), "connect", 2)


def test_sqlite_connect_to_a_directory_is_a_permission_error(tmp_path):
    p = chars(str(tmp_path))
    alias = chars("ioerr_dir")
    assert raised(psqlite._sqlite_connect_2, p, alias) == _err(
        _perm("open", p), "connect", 2)


def _reified_file_item(path):
    from clausal.modules.reflection import _reified_file_item_2
    gen = _reified_file_item_2(None, "proceed", "fail", None, path, Var(),
                               Trail())
    with pytest.raises(LogicException) as info:
        list(gen)
    return info.value.term


def test_reified_file_item_of_a_directory_is_a_permission_error(tmp_path):
    p = chars(str(tmp_path))
    assert _reified_file_item(p) == _err(_perm("open", p),
                                         "reified_file_item", 2)


@_root
def test_reified_file_item_unreadable_is_a_permission_error(unreadable):
    f, _d = unreadable
    p = chars(str(f))
    assert _reified_file_item(p) == _err(_perm("open", p),
                                         "reified_file_item", 2)


# ── py.process ───────────────────────────────────────────────────────────


def test_process_create_bare_unknown_program_is_an_existence_error():
    p = chars("no_such_program_clausal_xyz")
    assert raised(pprocess._process_create_3, p, [], Var()) == _err(
        _exists(p), "process_create", 3)


def test_process_create_non_executable_is_a_permission_error(tmp_path):
    f = tmp_path / "script.sh"
    f.write_text("#!/bin/sh\necho hi\n")
    os.chmod(f, stat.S_IRUSR | stat.S_IWUSR)
    p = chars(str(f))
    assert raised(pprocess._process_create_3, p, [], Var()) == _err(
        _perm("create", p, "process"), "process_create", 3)


def test_process_create_of_a_directory_is_a_permission_error(tmp_path):
    p = chars(str(tmp_path))
    assert raised(pprocess._process_create_3, p, [], Var()) == _err(
        _perm("create", p, "process"), "process_create", 3)


def test_process_create_missing_cwd_blames_the_cwd(tmp_path):
    cwd = chars(str(tmp_path / "gone"))
    opts = DictTerm({mint("cwd"): cwd})
    assert raised(pprocess._process_create_4, chars("pwd"), [], opts,
                  Var()) == _err(_exists(cwd), "process_create", 4)


def test_process_create_nonzero_exit_is_a_value():
    r = Var()
    assert len(solutions(pprocess._process_create_3, chars("sh"),
                         [chars("-c"), chars("exit 3")], r)) == 1
    assert deref(r).data[mint("exit_code")] == 3


def test_shell_2_nonzero_exit_is_a_value_and_a_missing_command_is_127():
    code = Var()
    assert len(solutions(pprocess._shell_2,
                         chars("no_such_program_clausal_xyz 2>/dev/null"),
                         code)) == 1
    assert deref(code) == 127


def test_shell_1_and_shell_output_still_fail_on_a_nonzero_exit():
    assert solutions(pprocess._shell_1, chars("exit 1")) == []
    assert solutions(pprocess._shell_output_2, chars("exit 1"), Var()) == []


# ── py.tcp (local sockets only) ──────────────────────────────────────────


@pytest.fixture
def closed_port():
    """A port bound but not listening: a connection to it is refused."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    yield s.getsockname()[1]
    s.close()


@_needs_sockets
def test_tcp_connect_refused(closed_port):
    assert raised(ptcp._connect_3, chars("127.0.0.1"), closed_port,
                  Var()) == _err(("system_error", "connection_refused"),
                                 "connect", 3)


@_needs_sockets
def test_tcp_connect_unresolvable_host_is_an_existence_error():
    # RFC 6761: .invalid never resolves.  A resolver that cannot be reached
    # at all answers EAI_AGAIN instead; that is host_lookup_failed.
    h = chars("no-such-host.invalid")
    term = raised(ptcp._connect_3, h, 80, Var())
    assert term in (_err(_exists(h), "connect", 3),
                    _err(("system_error", "host_lookup_failed"), "connect", 3))


@_needs_sockets
def test_tcp_listen_on_a_port_in_use():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    s.listen(1)
    try:
        port = s.getsockname()[1]
        assert raised(ptcp._listen_3, chars("127.0.0.1"), port,
                      Var()) == _err(("system_error", "address_in_use"),
                                     "listen", 3)
    finally:
        s.close()


@_needs_sockets
def test_tcp_receive_timeout_is_a_resource_error():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    c = socket.create_connection(srv.getsockname())
    try:
        c.settimeout(0.05)
        assert raised(ptcp._receive_2, c, Var()) == _err(
            ("resource_error", "timeout"), "receive", 2)
    finally:
        c.close()
        srv.close()


@_needs_sockets
def test_tcp_receive_on_a_closed_connection_still_fails():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    c = socket.create_connection(srv.getsockname())
    peer, _ = srv.accept()
    peer.close()
    try:
        assert solutions(ptcp._receive_2, c, Var()) == []
    finally:
        c.close()
        srv.close()


# ── py.http (a local http.server) ────────────────────────────────────────


class _StatusHandler(http.server.BaseHTTPRequestHandler):
    def _answer(self):
        status = int(self.path.strip("/") or 200)
        body = f"status {status}".encode()
        self.send_response(status)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_GET = do_POST = _answer

    def log_message(self, *args):
        pass


@pytest.fixture
def http_base():
    server = http.server.HTTPServer(("127.0.0.1", 0), _StatusHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


@_needs_sockets
@pytest.mark.parametrize("status, formal", [
    (404, lambda u: _exists(u)),
    (410, lambda u: _exists(u)),
    (401, lambda u: _perm("open", u)),
    (403, lambda u: _perm("open", u)),
    (500, lambda u: ("system_error", ("http_status", 500))),
    (418, lambda u: ("system_error", ("http_status", 418))),
])
def test_http_get_error_status(http_base, status, formal):
    u = chars(f"{http_base}/{status}")
    assert raised(phttp._get_2, u, Var()) == _err(formal(u), "get", 2)


@_needs_sockets
def test_http_body_only_predicates_raise_the_status(http_base):
    u = chars(f"{http_base}/404")
    for fn, args, name, arity in [
        (phttp._get_3, (DictTerm({}), Var()), "get", 3),
        (phttp._post_3, (chars("x"), Var()), "post", 3),
        (phttp._post_4, (chars("x"), DictTerm({}), Var()), "post", 4),
        (phttp._json_get_2, (Var(),), "json_get", 2),
        (phttp._json_post_3, (DictTerm({mint("a"): 1}), Var()),
         "json_post", 3),
    ]:
        assert raised(fn, u, *args) == _err(_exists(u), name, arity)


@_needs_sockets
def test_http_request_3_answers_the_status_as_a_value(http_base):
    status, body = Var(), Var()
    opts = DictTerm({mint("url"): chars(f"{http_base}/404")})
    assert len(solutions(phttp._request_3, opts, status, body)) == 1
    assert deref(status) == 404
    assert deref(body) == chars("status 404")


@_needs_sockets
def test_http_connection_refused(closed_port):
    u = chars(f"http://127.0.0.1:{closed_port}/")
    assert raised(phttp._get_2, u, Var()) == _err(
        ("system_error", "connection_refused"), "get", 2)
    opts = DictTerm({mint("url"): u})
    assert raised(phttp._request_3, opts, Var(), Var()) == _err(
        ("system_error", "connection_refused"), "request", 3)


@_needs_sockets
def test_http_unresolvable_host_is_an_existence_error():
    u = chars("http://no-such-host.invalid/")
    term = raised(phttp._get_2, u, Var())
    assert term in (_err(_exists(u), "get", 2),
                    _err(("system_error", "host_lookup_failed"), "get", 2))


# ── end to end: catch/3 in a program sees the ISO term ───────────────────


def test_existence_error_is_catchable_in_a_program(tmp_path):
    from clausal.import_hook import _load_module
    from clausal.logic.solve import call
    from tests._suffix import SEAM

    p = tmp_path / f"ioerr{SEAM}"
    p.write_text(textwrap.dedent("""
        -import_from(py.files, [read_file_to_string])
        -private([source_sink])

        caught(P, C) <- (
            catch(read_file_to_string(P, _),
                  error(existence_error(source_sink, C), _), true)
        ),
    """).lstrip())
    mod = _load_module("ioerr", str(p)).__dict__["$module"]
    missing = chars(str(tmp_path / "missing.txt"))
    C = Var()
    sols = [deref(C) for _ in call("caught", missing, C, module=mod)]
    assert sols == [missing]
