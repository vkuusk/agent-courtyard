"""Every text a model reads, as named templates (design communication-protocols.md
section 8).

The wording lives in the YAML files beside this module, one file per family: the file's
name and the nesting of its keys make a text's key (`envelope.footer.reply`), and named
variables (`{sender}`) mark what the caller fills in. Which text applies is decided by
the caller: this package holds wording only. Changing a text means editing the YAML and
regenerating the golden files under `tests/texts/golden`, where the change shows as a
diff.
"""

from __future__ import annotations

from functools import cache
from importlib import resources
from string import Formatter
from typing import Any

import yaml


class TextError(Exception):
    """A text was asked for by an unknown key, or rendered with the wrong variables."""


def _flatten(prefix: str, node: Any, out: dict[str, Any]) -> None:
    if isinstance(node, dict):
        for name, child in node.items():
            _flatten(f"{prefix}.{name}", child, out)
    else:
        out[prefix] = node


@cache
def catalog() -> dict[str, Any]:
    """Every entry by key. A string is a template; anything else (the tool definitions)
    is structured data read with `get`."""
    out: dict[str, Any] = {}
    for entry in sorted(resources.files(__package__).iterdir(), key=lambda e: e.name):
        if entry.name.endswith(".yml"):
            _flatten(entry.name[: -len(".yml")], yaml.safe_load(entry.read_text()), out)
    return out


def get(key: str, /) -> Any:
    try:
        return catalog()[key]
    except KeyError:
        raise TextError(f"no text named {key!r}") from None


def section(prefix: str, /) -> dict[str, Any]:
    """The entries directly under `prefix`, by their last name: `section("tools.adapter.pi")`
    is that adapter's declared variables."""
    start = prefix + "."
    found = {k[len(start) :]: v for k, v in catalog().items() if k.startswith(start)}
    if not found:
        raise TextError(f"no texts under {prefix!r}")
    return found


def variables(template: str) -> set[str]:
    """The named variables a template takes (`{peer.name!r}` counts as `peer`)."""
    names = set()
    for _, field, _, _ in Formatter().parse(template):
        if field is None:
            continue
        name = field.split(".")[0].split("[")[0]
        if not name or name.isdigit():
            raise TextError(f"positional variable in template: {template[:60]!r}")
        names.add(name)
    return names


def render(key: str, /, **values: Any) -> str:
    """The text named `key` with its variables filled in. A missing variable and a
    variable the template does not use are both errors: either one means the caller and
    the wording have drifted apart."""
    template = get(key)
    if not isinstance(template, str):
        raise TextError(f"{key!r} is structured data, not a template: read it with get()")
    wanted = variables(template)
    if wanted != set(values):
        missing, unused = sorted(wanted - set(values)), sorted(set(values) - wanted)
        raise TextError(f"{key!r}: missing variables {missing}, unused variables {unused}")
    return template.format(**values)
