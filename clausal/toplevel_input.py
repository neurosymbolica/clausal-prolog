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
    """

    POLL = 0.05

    def __init__(self, fd: int):
        self.fd = fd
        self.typeahead = bytearray()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self) -> "KeyWatcher":
        if threading.current_thread() is not threading.main_thread():
            return self                     # nothing to interrupt from here
        self._stop.clear()
        self._thread = threading.Thread(target=self._watch, daemon=True,
                                        name="clausal-key-watcher")
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join()
            self._thread = None

    def _more(self) -> bool:
        try:
            return bool(select.select([self.fd], [], [], 0.02)[0])
        except (OSError, ValueError):
            return False

    def _watch(self) -> None:
        while not self._stop.is_set():
            try:
                ready, _, _ = select.select([self.fd], [], [], self.POLL)
            except (OSError, ValueError):
                return
            if not ready:
                continue
            try:
                data = os.read(self.fd, 1)
                if data and data[0] == ESC and self._more():
                    data += os.read(self.fd, 16)      # an escape sequence
            except OSError:
                return
            if not data:
                return
            if data == bytes([ESC]) and not self._stop.is_set():
                os.kill(os.getpid(), signal.SIGINT)
                return
            self.typeahead += data
