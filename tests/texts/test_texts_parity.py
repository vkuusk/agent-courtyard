"""Adapter parity: Claude Code and pi are told the same things about the courtyard tools,
except for the differences declared per adapter in tools.yml."""

from __future__ import annotations

from courtyard import texts
from courtyard.common import adapter_texts


def test_adapters_differ_only_by_the_declared_variables():
    claude, pi = adapter_texts.bundle("claude-code"), adapter_texts.bundle("pi")
    declared = {a: texts.section(f"tools.adapter.{a}") for a in ("claude_code", "pi")}
    assert set(declared["claude_code"]) == set(declared["pi"]), "every variable for every adapter"

    templates = {d["name"]: d["description"] for d in texts.get("tools.definitions")}
    assert [t["name"] for t in claude["tools"]] == [t["name"] for t in pi["tools"]]
    for c, p in zip(claude["tools"], pi["tools"], strict=True):
        assert c["inputSchema"] == p["parameters"], c["name"]
        if c["description"] != p["description"]:
            used = texts.variables(templates[c["name"]])
            assert used, f"{c['name']}: the descriptions differ without a declared variable"
            assert used <= set(declared["pi"])
    assert claude["local"] == pi["local"]
    assert claude["instructions"] and pi["instructions"] is None  # pi's etiquette is a skill


def test_the_etiquette_is_one_content_for_both_adapters():
    """Section 4.3: the Claude Code instructions and the pi skill cover the same ground;
    they differ by the declared variables and by the skill's front matter."""
    from courtyard.hub.core.install import pi_skill

    declared = {a: texts.section(f"etiquette.adapter.{a}") for a in ("claude_code", "pi")}
    assert set(declared["claude_code"]) == set(declared["pi"])
    assert texts.variables(texts.get("etiquette.body")) == set(declared["pi"])
    claude, pi = adapter_texts.etiquette("claude-code"), adapter_texts.etiquette("pi")
    assert adapter_texts.bundle("claude-code")["instructions"] == claude
    assert pi_skill("agent-x").endswith(pi + "\n")  # the skill is the same body under its head
    for value in declared["claude_code"].values():
        claude = claude.replace(value, "") if value else claude
    for value in declared["pi"].values():
        pi = pi.replace(value, "") if value else pi
    assert claude == pi  # nothing differs but the declared variables
    for topic in (
        "courtyard_peers",
        "courtyard_recall",
        "courtyard_note",
        "courtyard_inbox",
        "courtyard_ack",
        "answered the way it came",
        "exchange budget",
    ):
        assert topic in pi, f"the etiquette leaves out {topic!r}"


def test_the_hub_serves_each_agent_the_bundle_of_its_type(client, make_agent):
    make_agent("claude-one", "claude-code")
    make_agent("pi-one", "pi")
    for name, agent_type in (("claude-one", "claude-code"), ("pi-one", "pi")):
        resp = client.get(f"/api/agents/{name}/texts")
        assert resp.status_code == 200, resp.text
        assert resp.json() == adapter_texts.bundle(agent_type)
    assert client.get("/api/agents/nobody/texts").status_code == 404
