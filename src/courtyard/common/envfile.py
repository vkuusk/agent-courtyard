"""Read a checkout's `.env` the way the Makefile does.

`make` exports `.env` into everything it starts, and docker compose reads the file by
itself. A script or a pytest run started directly gets neither: it would address the
default compose project on the default port while compose uses whatever `.env` names,
which is a container that does not exist, or worse, somebody else's postgres. Anything
runnable without `make` calls this first.

A value already in the environment wins, as it does with `make`.
"""

from __future__ import annotations

import os
from pathlib import Path


def load_env_file(start: Path | None = None) -> Path | None:
    """Load the nearest `.env` at or above `start` (default: the working directory).

    Returns the file that was read, or None when there is none.
    """
    here = (start or Path.cwd()).resolve()
    for directory in [here, *here.parents]:
        env_file = directory / ".env"
        if not env_file.is_file():
            continue
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())
        return env_file
    return None
