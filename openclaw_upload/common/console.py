# -*- coding: utf-8 -*-
"""Console helpers that avoid UnicodeEncodeError on Windows terminals."""
from __future__ import annotations

import sys
from typing import TextIO


def ensure_console_ready() -> None:
    """Configure stdout/stderr to escape unsupported characters instead of crashing."""
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        if stream is None or not hasattr(stream, "reconfigure"):
            continue
        try:
            stream.reconfigure(errors="backslashreplace", line_buffering=True)
        except Exception:
            continue


def safe_print(*args, sep: str = " ", end: str = "\n", file: TextIO | None = None, flush: bool = False) -> None:
    """Print text without crashing when the active console encoding cannot represent it."""
    stream = sys.stdout if file is None else file
    text = sep.join(str(arg) for arg in args)
    try:
        print(text, end=end, file=stream, flush=flush)
    except UnicodeEncodeError:
        encoding = getattr(stream, "encoding", None) or "utf-8"
        stream.write(text.encode(encoding, errors="backslashreplace").decode(encoding, errors="ignore"))
        stream.write(end)
        if flush:
            stream.flush()
