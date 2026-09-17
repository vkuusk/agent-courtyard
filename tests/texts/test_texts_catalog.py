"""The catalog itself: every template parses, render() refuses drifted variables, and the
keys the code asks for are the keys the catalog holds."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from courtyard import texts

SRC = Path(__file__).parents[2] / "src" / "courtyard"
CALL = re.compile(r"""texts\.(?:render|get|section)\(\s*(f?)["']([^"']+)["']""")
LITERAL = re.compile(r"""["']([a-z_]+(?:\.[a-z_]+)+)["']""")


def test_every_template_parses():
    for value in texts.catalog().values():
        if isinstance(value, str):
            texts.variables(value)  # raises on a positional or malformed field


def test_render_refuses_missing_and_unused_variables():
    assert texts.render("notices.thread.closed", closer="alice") == "thread closed by alice"
    with pytest.raises(texts.TextError, match="missing variables"):
        texts.render("notices.thread.closed")
    with pytest.raises(texts.TextError, match="unused variables"):
        texts.render("notices.thread.closed", closer="alice", extra=1)
    with pytest.raises(texts.TextError, match="no text named"):
        texts.render("notices.thread.no_such_text")
    with pytest.raises(texts.TextError, match="structured data"):
        texts.render("tools.definitions")


def test_code_and_catalog_name_the_same_keys():
    asked, prefixes, mentioned = set(), set(), set()
    for path in SRC.rglob("*.py"):
        source = path.read_text()
        mentioned |= set(LITERAL.findall(source))  # also the keys chosen by a condition
        for is_fstring, key in CALL.findall(source):
            if is_fstring:
                prefixes.add(key.split("{")[0])  # f"results.send.{outcome}" -> "results.send."
            else:
                asked.add(key)
    catalog = set(texts.catalog())
    assert asked <= catalog, f"the code asks for texts that do not exist: {sorted(asked - catalog)}"
    for prefix in prefixes:
        assert any(k.startswith(prefix) for k in catalog), f"no text under {prefix!r}"
    unused = {
        k for k in catalog if k not in mentioned and not any(k.startswith(p) for p in prefixes)
    }
    assert not unused, f"texts nothing renders: {sorted(unused)}"
