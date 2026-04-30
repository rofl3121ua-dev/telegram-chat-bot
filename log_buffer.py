"""Кольцевой буфер строк логов в памяти — для команды /logs владельцем в личке."""

from __future__ import annotations

import logging
from collections import deque
from threading import Lock

_MAX_LINES = 1200
_lines: deque[str] = deque(maxlen=_MAX_LINES)
_lock = Lock()


class RingBufferHandler(logging.Handler):
    """Сохраняет последние N строк форматированного вывода логов."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            with _lock:
                _lines.append(msg)
        except Exception:
            self.handleError(record)


def get_recent_lines(count: int = 100) -> list[str]:
    if count <= 0:
        count = 100
    count = min(count, _MAX_LINES)
    with _lock:
        snap = list(_lines)
    return snap[-count:] if len(snap) > count else snap
