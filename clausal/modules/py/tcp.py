"""clausal.modules.py.tcp — TCP socket predicates for Clausal.

Provides relational predicates for TCP client/server connections.
Import via::

    -import_from(py.tcp, [connect, listen, accept, send, receive, close, set_timeout])

Wraps Python's ``socket`` module. Socket handles are opaque Python objects.
"""

from __future__ import annotations

from clausal.modules.py import (
    ModulePredicate,
    _import_stdlib,
    expect_type,
    require_text,
    simple_to_trampoline,
    to_bytes,
)
_socket = _import_stdlib("socket")

from clausal.logic.variables import deref, is_var, unify


# ── Internal helpers ─────────────────────────────────────────────────────


# ── Predicate implementations ────────────────────────────────────────────


def _connect_3(host, port, sock_out, trail, k):
    """connect/3: connect(Host, Port, Socket) — connect to TCP server."""
    host_d = require_text(deref(host), "connect/3")
    port_d = deref(port)
    if host_d is None:
        return
    if not expect_type(port_d, int, "connect/3", arg=2):
        return
    try:
        s = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
        s.connect((host_d, port_d))
    except (OSError, _socket.error):
        return
    if unify(sock_out, s, trail):
        yield None


def _listen_3(host, port, server_out, trail, k):
    """listen/3: listen(Host, Port, ServerSocket) — create listening socket."""
    host_d = require_text(deref(host), "listen/3")
    port_d = deref(port)
    if host_d is None:
        return
    if not expect_type(port_d, int, "listen/3", arg=2):
        return
    try:
        s = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
        s.setsockopt(_socket.SOL_SOCKET, _socket.SO_REUSEADDR, 1)
        s.bind((host_d, port_d))
        s.listen(5)
    except (OSError, _socket.error):
        return
    if unify(server_out, s, trail):
        yield None


def _accept_2(server_sock, client_out, trail, k):
    """accept/2: accept(ServerSocket, ClientSocket) — accept incoming connection."""
    server_d = deref(server_sock)
    if not expect_type(server_d, _socket.socket, "accept/2", arg=1):
        return
    try:
        client, addr = server_d.accept()
    except (OSError, _socket.error):
        return
    if unify(client_out, client, trail):
        yield None


def _send_2(sock, data, trail, k):
    """send/2: send(Socket, Data) — send text (UTF-8) or bytes via sendall.

    Spec §9.4: the payload is TEXT, so a string or an ATOM both cross as the
    same ``str`` — ``to_bytes`` is the funnel for exactly that (it answers
    ``None`` for a term that is neither text nor bytes).
    """
    sock_d = deref(sock)
    data_d = deref(data)
    if not expect_type(sock_d, _socket.socket, "send/2", arg=1):
        return
    if is_var(data_d):
        return
    data_bytes = to_bytes(data_d)
    if data_bytes is None:
        expect_type(data_d, (str, bytes), "send/2",
                    expected="str or bytes", arg=2)
        return
    try:
        sock_d.sendall(data_bytes)
    except (OSError, _socket.error):
        return
    yield None


def _receive_3(sock, bufsize, data_out, trail, k):
    """receive/3: receive(Socket, BufferSize, Data) — receive with custom buffer."""
    sock_d = deref(sock)
    bufsize_d = deref(bufsize)
    if not expect_type(sock_d, _socket.socket, "receive/3", arg=1):
        return
    if not expect_type(bufsize_d, int, "receive/3", arg=2):
        return
    try:
        raw = sock_d.recv(bufsize_d)
    except (OSError, _socket.error):
        return
    if not raw:
        return  # connection closed
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        if unify(data_out, raw, trail):
            yield None
        return
    if unify(data_out, text, trail):
        yield None


def _receive_2(sock, data_out, trail, k):
    """receive/2: receive(Socket, Data) — receive up to 4096 bytes."""
    yield from _receive_3(sock, 4096, data_out, trail, k)


def _close_1(sock, trail, k):
    """close/1: close(Socket) — close socket. Always succeeds."""
    sock_d = deref(sock)
    if not expect_type(sock_d, _socket.socket, "close/1", arg=1):
        return
    try:
        sock_d.close()
    except (OSError, _socket.error):
        pass
    yield None


def _set_timeout_2(sock, seconds, trail, k):
    """set_timeout/2: set_timeout(Socket, Seconds) — set socket timeout."""
    sock_d = deref(sock)
    sec_d = deref(seconds)
    if not expect_type(sock_d, _socket.socket, "set_timeout/2", arg=1):
        return
    if is_var(sec_d):
        return
    timeout = None if sec_d is None else float(sec_d)
    sock_d.settimeout(timeout)
    yield None


# ── Build and export predicate objects ───────────────────────────────────

connect = ModulePredicate("connect")
connect._register(3, simple_to_trampoline(_connect_3))

listen = ModulePredicate("listen")
listen._register(3, simple_to_trampoline(_listen_3))

accept = ModulePredicate("accept")
accept._register(2, simple_to_trampoline(_accept_2))

send = ModulePredicate("send")
send._register(2, simple_to_trampoline(_send_2))

receive = ModulePredicate("receive")
receive._register(2, simple_to_trampoline(_receive_2))
receive._register(3, simple_to_trampoline(_receive_3))

close = ModulePredicate("close")
close._register(1, simple_to_trampoline(_close_1))

set_timeout = ModulePredicate("set_timeout")
set_timeout._register(2, simple_to_trampoline(_set_timeout_2))
