"""KeyWatcher (``clausal.toplevel_input``): latency, and the Esc race."""

from __future__ import annotations

import os
import signal
import time

import pytest

from clausal.toplevel_input import ESC, KeyWatcher


def test_watching_a_search_adds_almost_no_latency():
    r, w = os.pipe()
    try:
        n = 60
        t = time.perf_counter()
        for _ in range(n):
            with KeyWatcher(r):
                pass
        per = (time.perf_counter() - t) / n
    finally:
        os.close(r)
        os.close(w)
    assert per < 0.01, f"{per * 1000:.1f} ms per watched search"


def test_esc_keeps_no_stray_interrupt_when_the_search_ends_with_it():
    # Esc lands as the "search" completes: either it interrupts inside the
    # with, or it is typeahead; never an interrupt after the block.
    def boom(signum, frame):
        raise KeyboardInterrupt

    old = signal.signal(signal.SIGINT, boom)
    r, w = os.pipe()
    try:
        for i in range(150):
            os.write(w, bytes([ESC]))
            try:
                with KeyWatcher(r) as watcher:
                    time.sleep(0.0005 * (i % 5))
            except KeyboardInterrupt:
                pass
            else:
                # not interrupted: the Esc is typeahead, or still unread
                if watcher.typeahead != bytearray([ESC]):
                    # unread: drain so the next round starts clean
                    try:
                        os.read(r, 1)
                    except OSError:
                        pass
            time.sleep(0.003)          # a stray interrupt would land here
    finally:
        signal.signal(signal.SIGINT, old)
        os.close(r)
        os.close(w)
