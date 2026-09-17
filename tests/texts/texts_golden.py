"""Golden files for the texts a model reads (design communication-protocols.md section 8).

Every text is rendered with fixed sample values and compared with a checked-in file, so
a wording change shows as a diff in review. To accept a change on purpose:

    COURTYARD_UPDATE_GOLDEN=1 uv run pytest tests/texts -q
"""

from __future__ import annotations

import os
from pathlib import Path

GOLDEN_DIR = Path(__file__).parent / "golden"
UPDATE = os.environ.get("COURTYARD_UPDATE_GOLDEN") == "1"


def blocks(entries: list[tuple[str, str]]) -> str:
    """Several texts in one golden file, each under its title."""
    return "\n".join(f"===== {title} =====\n{text}\n" for title, text in entries)


def check(name: str, text: str) -> None:
    path = GOLDEN_DIR / f"{name}.txt"
    if UPDATE:
        path.write_text(text)
        return
    assert path.exists(), f"no golden file {path.name}: run with COURTYARD_UPDATE_GOLDEN=1"
    assert text == path.read_text(), (
        f"{path.name} differs: a model-facing text changed. If that is intended, "
        "regenerate with COURTYARD_UPDATE_GOLDEN=1 and review the diff."
    )
