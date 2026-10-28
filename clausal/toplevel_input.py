"""Input helpers of the ``?-`` top-level that are not line editing.

:class:`KeyWatcher` -- while a query searches for its next answer, the Esc key
interrupts it (the top-level then prints ``% Execution Aborted`` and prompts
again), as in Shumway; Ctrl-C always did.  Every other key typed meanwhile is
typeahead: the watcher keeps it for the next prompt to read, so a pasted
script of queries is not disturbed.
"""
from __future__ import annotations

import os
import select
import signal
import threading

ESC = 0x1B


class KeyWatcher:
    """Context manager: a thread that watches file descriptor *fd* while the
    body runs.  A lone Esc interrupts the main thread (SIGINT, so a
    ``KeyboardInterrupt`` where the search is); anything else (an escape
    sequence such as an arrow key included) is appended to :attr:`typeahead`.

    The thread sleeps in ``select`` on *fd* and on a private pipe that
    ``__exit__`` writes to, so leaving the block does not wait out a poll
    interval.  An Esc is decided under a lock against the end of the block:
    it either interrupts (and the interrupt is delivered before ``__exit__``
    returns, never after it) or is kept as typeahead for the next prompt.
    """

    def __init__(self, fd: int):
        self.fd = fd
        self.typeahead = bytearray()
        self.interrupted = False
        self._lock = threading.Lock()
        self._stopped = False
        self._wake_r = self._wake_w = -1
        self._thread: threading.Thread | None = None

    def __enter__(self) -> "KeyWatcher":
        if threading.current_thread() is not threading.main_thread():
            return self                     # nothing to interrupt from here
        self._wake_r, self._wake_w = os.pipe()
        self._thread = threading.Thread(target=self._watch, daemon=True,
                                        name="clausal-key-watcher")
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        if self._thread is None:
            return
        with self._lock:
            self._stopped = True
        os.write(self._wake_w, b"x")
        self._thread.join()
        self._thread = None
        os.close(self._wake_r)
        os.close(self._wake_w)
        if self.interrupted:
            # The SIGINT is already pending in this process: let it be
            # delivered here, inside the block's exit, not at some later line.
            for _ in range(1000):
                pass

    def _more(self) -> bool:
        try:
            return bool(select.select([self.fd], [], [], 0.02)[0])
        except (OSError, ValueError):
            return False

    def _watch(self) -> None:
        while True:
            try:
                ready, _, _ = select.select([self.fd, self._wake_r], [], [])
            except (OSError, ValueError):
                return
            if self._wake_r in ready:
                return
            try:
                data = os.read(self.fd, 1)
                if data and data[0] == ESC and self._more():
                    data += os.read(self.fd, 16)      # an escape sequence
            except OSError:
                return
            if not data:
                return
            with self._lock:
                if data == bytes([ESC]) and not self._stopped:
                    self.interrupted = True
                    os.kill(os.getpid(), signal.SIGINT)
                    return
                self.typeahead += data
                if self._stopped:
                    return
