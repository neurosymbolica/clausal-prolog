"""clausal.modules.py.tcp — TCP socket predicates for Clausal.

Provides relational predicates for TCP client/server connections.
Import via::

    -import_from(py.tcp, [connect, listen, accept, send, receive, close, set_timeout])

Wraps Python's ``socket`` module. Socket handles are opaque Python objects.
"""

from __future__ import annotations

from clausal.modules.py import _import_stdlib, ModulePredicate, simple_to_trampoline
_socket = _import_stdlib("socket")

from clausal.logic.variables import deref, is_var, unify


# ── Predicate implementations ────────────────────────────────────────────


def _connect_3(host, port, sock_out, trail, k):
    """connect/3: connect(Host, Port, Socket) — connect to TCP server."""
    host_d = deref(host)
    port_d = deref(port)
    if is_var(host_d) or not isinstance(host_d, str):
        return
    if is_var(port_d) or not isinstance(port_d, int):
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
    host_d = deref(host)
    port_d = deref(port)
    if is_var(host_d) or not isinstance(host_d, str):
        return
    if is_var(port_d) or not isinstance(port_d, int):
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
    if is_var(server_d) or not isinstance(server_d, _socket.socket):
        return
    try:
        client, addr = server_d.accept()
    except (OSError, _socket.error):
        return
    if unify(client_out, client, trail):
        yield None


def _send_2(sock, data, trail, k):
    """send/2: send(Socket, Data) — send string (UTF-8) or bytes via sendall."""
    sock_d = deref(sock)
    data_d = deref(data)
    if is_var(sock_d) or not isinstance(sock_d, _socket.socket):
        return
    if is_var(data_d):
        return
    if isinstance(data_d, str):
        data_bytes = data_d.encode("utf-8")
    elif isinstance(data_d, bytes):
        data_bytes = data_d
    else:
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
    if is_var(sock_d) or not isinstance(sock_d, _socket.socket):
        return
    if is_var(bufsize_d) or not isinstance(bufsize_d, int):
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
    if is_var(sock_d) or not isinstance(sock_d, _socket.socket):
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
    if is_var(sock_d) or not isinstance(sock_d, _socket.socket):
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
