# Clausal Prolog — TCP Module (`tcp`)

!!! note "Clausal Prolog examples"

    Examples on this page are [Clausal Prolog](clausal_prolog.md)
    (`.clausal`), which uses ISO Prolog syntax. Clausal Prolog reaches
    Python only through a `.seam` module, so it imports this module through
    its facade `library(tcp)`; the [seam](syntax.md) imports `py.tcp`
    directly (`-import_from(py.tcp, [...])`).

## Overview

The `tcp` module provides predicates for TCP client/server socket operations,
wrapping Python's `socket` module. Socket handles are opaque Python objects —
use them with `send`, `receive`, and `close`.

```clausal
:- use_module(library(tcp), [connect/3, send/2, receive/2, close/1]).

echo_client(HOST, PORT, MESSAGE, RESPONSE) :-
    connect(HOST, PORT, SOCKET),
    send(SOCKET, MESSAGE),
    receive(SOCKET, RESPONSE),
    close(SOCKET).

% Nothing listens on port 1 here: the connection is refused, and that raises.
test("refused") :-
    catch(echo_client("127.0.0.1", 1, "hi", _),
          error(system_error(connection_refused), _),
          true).
```

Or import the whole module and qualify each call with the module name:

```clausal
:- use_module(library(tcp)).

main :-
    tcp:connect("localhost", 8080, S),
    tcp:send(S, "hello"),
    tcp:receive(S, REPLY),
    format("~s~n", [REPLY]),
    tcp:close(S).
```

(The seam prints the reply with a Python escape, `++print(REPLY)`.)

---

## Import

```clausal
:- use_module(library(tcp), [
    connect/3, listen/3, accept/2,
    send/2, receive/2, receive/3, close/1, set_timeout/2
]).

test("listen on an ephemeral port") :-
    listen("127.0.0.1", 0, SERVER),
    close(SERVER).
```

---

## Client predicates

| Predicate | Mode | Description |
|-----------|------|-------------|
| `connect(Host, Port, Socket)` | `+Host, +Port, -Socket` | connect to TCP server, bind opaque socket handle |

```text
--8<-- "tests/fixtures/docs/tcp_sigs.txt:connect_example"
```

A network failure raises (ruled 2026-10-02; it used to fail): a host that
does not resolve is `existence_error(source_sink, Host)` (Scryer's
`socket_client_open/3` term), a refused connection
`system_error(connection_refused)`, an unreachable host
`system_error(host_unreachable)`, a timeout `resource_error(timeout)`, a
permission refusal `permission_error(open, source_sink, Host)`. `listen/3`
on a port in use is `system_error(address_in_use)`; `send/2` on a broken
connection `system_error(broken_pipe)` or `system_error(connection_reset)`.

---

## Server predicates

| Predicate | Mode | Description |
|-----------|------|-------------|
| `listen(Host, Port, ServerSocket)` | `+Host, +Port, -ServerSocket` | Create listening socket with `SO_REUSEADDR`. Port `0` → ephemeral. |
| `accept(ServerSocket, ClientSocket)` | `+Server, -Client` | accept incoming connection. Blocks until a client connects. |

```text
--8<-- "tests/fixtures/docs/tcp_sigs.txt:server_example"
```

---

## Data transfer

| Predicate | Mode | Description |
|-----------|------|-------------|
| `send(Socket, Data)` | `+Socket, +Data` | send string (UTF-8) or bytes via `sendall()` |
| `receive(Socket, Data)` | `+Socket, -Data` | receive up to 4096 bytes, decode UTF-8 |
| `receive(Socket, BufferSize, Data)` | `+Socket, +BufSize, -Data` | receive with custom buffer size |

`receive` returns a string if the data is valid UTF-8, or raw `bytes` if
decoding fails. Fails if the connection is closed (no data received).

```text
--8<-- "tests/fixtures/docs/tcp_sigs.txt:data_transfer_examples"
```

---

## Socket management

| Predicate | Mode | Description |
|-----------|------|-------------|
| `close(Socket)` | `+Socket` | close socket. Always succeeds (even on already-closed sockets). |
| `set_timeout(Socket, Seconds)` | `+Socket, +Seconds` | Set socket timeout (float). A later operation that times out raises `resource_error(timeout)`. |

```text
--8<-- "tests/fixtures/docs/tcp_sigs.txt:socket_management_example"
```

---

??? example "Examples"

    ### Simple TCP client

    ```text
    --8<-- "tests/fixtures/docs/tcp_sigs.txt:tcp_client_example"
    ```

    ### Echo server (single client)

    ```text
    --8<-- "tests/fixtures/docs/tcp_sigs.txt:echo_server_example"
    ```

---

## Gotchas

- **Sockets are impure** — socket operations have side effects and do not
  [backtrack](control.md) cleanly. If a `send` succeeds but a later goal fails, the data
  has already been sent.
- **`accept` blocks** — it waits for a connection. Use `set_timeout` on the
  server socket to limit the wait time.
- **No automatic cleanup** — always `close` sockets explicitly. Python's
  garbage collector will eventually close them, but relying on GC is bad
  practice for network resources.
- **Port 0** in `listen` lets the OS pick an ephemeral port — useful for tests.

---

*See also: [HTTP](http.md) — higher-level HTTP requests (no sockets needed) ·
[Process](process.md) — shell commands and subprocess execution ·
[Python Interop](python_integration.md) — the seam's `++()` for advanced socket operations.*
