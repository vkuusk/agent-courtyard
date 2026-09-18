"""The team-wide brake (design communication-protocols.md section 7.4): one control
switches every agent line to supervised and back; a new line starts supervised while the
brake is on; the operator's lines are never touched."""

from __future__ import annotations

from conftest import auth


def modes(client) -> dict:
    return {
        frozenset((ln["agent_a_name"], ln["agent_b_name"])): ln["mode"]
        for ln in client.get("/api/lines").json()
    }


def test_brake_holds_every_agent_line_and_releases_them_to_the_default(client, make_agent):
    client.patch("/api/settings", json={"default_line_mode": "auto_pass"})
    _, alice = make_agent("alice")
    make_agent("bob")
    make_agent("carol")
    client.post("/api/lines", json={"a": "alice", "b": "bob"})
    client.post("/api/lines", json={"a": "bob", "b": "carol"})
    client.post("/api/operator/send", json={"to": "alice", "body": "hello"})
    assert set(modes(client).values()) == {"auto_pass"}

    resp = client.post("/api/lines/brake", json={"on": True})
    assert resp.status_code == 200 and len(resp.json()["changed"]) == 2
    assert client.get("/api/settings").json()["brake"] is True
    after = modes(client)
    assert after[frozenset(("alice", "bob"))] == "supervised"
    assert after[frozenset(("bob", "carol"))] == "supervised"
    assert after[frozenset(("operator", "alice"))] == "auto_pass"  # never gated
    # the next message on a braked line waits for the operator; a new line starts braked
    held = client.post("/api/lines/send", json={"to": "bob", "body": "x"}, headers=auth(alice))
    assert held.json()["status"] == "pending_gate"
    client.post("/api/lines/send", json={"to": "carol", "body": "x"}, headers=auth(alice))
    assert modes(client)[frozenset(("alice", "carol"))] == "supervised"

    resp = client.post("/api/lines/brake", json={"on": False})
    assert len(resp.json()["changed"]) == 3
    assert client.get("/api/settings").json()["brake"] is False
    assert set(modes(client).values()) == {"auto_pass"}
    # a message held while the brake was on still needs its verdict (mode changes apply
    # to the next send), so the line is still blocked
    again = client.post("/api/lines/send", json={"to": "bob", "body": "y"}, headers=auth(alice))
    assert again.json()["error"]["code"] == "gate_pending"
