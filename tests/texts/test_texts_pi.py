"""Golden: what the pi extension shows a model (tool definitions, and the texts it words
on its own side of the connection), from the exact file install writes, run under Node."""

from __future__ import annotations

import json
import shutil

import pytest
from texts_golden import blocks, check

from courtyard.common.client import HubClient
from courtyard.hub.core import install as install_core
from test_pi_adapter import Harness

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not on PATH")

TOOLS = (
    "courtyard_send",
    "courtyard_close_thread",
    "courtyard_inbox",
    "courtyard_peers",
    "courtyard_recall",
    "courtyard_note",
    "courtyard_ack",
)


def test_pi_tool_definitions_and_local_texts(live_hub, tmp_path):
    hub = live_hub()
    admin = HubClient(hub)
    _, token = admin.register_agent("pibot", "pi", "the pi twin", None, str(tmp_path))
    ext = tmp_path / "courtyard.mjs"
    ext.write_text(install_core.pi_extension(hub, "pibot", token))
    harness = Harness(ext)
    try:
        events = harness.collect_until(lambda e: e["event"] == "started", what="session_start")
        registered = {e["name"]: e["definition"] for e in events if e["event"] == "tool_registered"}
        assert tuple(registered) == TOOLS
        definitions = [registered[name] for name in TOOLS]
        check("pi_tools", json.dumps(definitions, indent=2, ensure_ascii=False) + "\n")

        entries = []
        for title, tool, params in (
            ("send: missing arguments", "courtyard_send", {"to": "bob"}),
            ("close: missing peer", "courtyard_close_thread", {}),
            ("inbox: empty", "courtyard_inbox", {}),
            ("ack: missing token", "courtyard_ack", {}),
            ("note: missing body", "courtyard_note", {}),
        ):
            result = harness.call(tool, **params)
            flag = " (error)" if result["event"] == "tool_error" else ""
            entries.append((title + flag, result["text"]))
        check("tool_results_pi_adapter", blocks(entries))
    finally:
        harness.stop()
        admin.close()
