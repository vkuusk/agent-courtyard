"""Endings the participants did not make are told to them (design
communication-protocols.md section 3.1, threads.md section 4): a release ends the open
thread as `locked` and both agents get a notice; the end of a shift tells the agents on
every line it touched, when they next pull or attach."""

from __future__ import annotations

from conftest import auth


def send(client, token, to, body):
    resp = client.post("/api/lines/send", json={"to": to, "body": body}, headers=auth(token))
    assert resp.status_code == 201, resp.text
    return resp.json()


def inbox(client, name, token):
    return client.get(f"/api/agents/{name}/inbox", headers=auth(token)).json()


def auto_pass_pair(client, make_agent):
    _, alice = make_agent("alice")
    _, bob = make_agent("bob")
    line = client.post("/api/lines", json={"a": "alice", "b": "bob"}).json()
    client.post(f"/api/lines/{line['id']}/mode", json={"mode": "auto_pass"})
    return alice, bob, line["id"]


def test_release_ends_the_thread_as_locked_and_tells_both(client, make_agent):
    alice, bob, line_id = auto_pass_pair(client, make_agent)
    ask = send(client, alice, "bob", "a question nobody will answer")
    inbox(client, "bob", bob)
    assert client.post(f"/api/lines/{line_id}/release").status_code == 200
    line = client.get(f"/api/lines/{line_id}").json()
    assert line["state"] == "idle" and line["open_thread"] is None
    (thread,) = client.get(f"/api/lines/{line_id}/threads").json()
    assert thread["id"] == ask["thread_id"] and thread["state"] == "locked"
    for name, token, peer in (("alice", alice, "bob"), ("bob", bob, "alice")):
        (notice,) = inbox(client, name, token)
        assert notice["kind"] == "system"
        assert f"The operator released your line with {peer}" in notice["body"]
        assert "the next ask opens a new thread" in notice["body"]
    # a locked thread is no case file, and the next ask opens a new thread
    assert client.get("/api/memory").json() == []
    again = send(client, alice, "bob", "a fresh ask")
    assert again["thread_id"] != ask["thread_id"]


def test_end_of_shift_tells_the_agents_on_every_line_it_touched(client, make_agent):
    alice, bob, _ = auto_pass_pair(client, make_agent)
    _, carol = make_agent("carol")
    # alice <-> bob: a message awaiting bob's reply; alice <-> carol: a thread left open
    send(client, alice, "bob", "unanswered")
    ask = send(client, alice, "carol", "held at the gate")
    client.post(f"/api/gate/{ask['id']}", json={"verdict": "approve"})
    inbox(client, "carol", carol)
    answer = send(client, carol, "alice", "answered, thread still open")
    client.post(f"/api/gate/{answer['id']}", json={"verdict": "approve"})  # the line is idle
    assert client.post("/api/shift/start").status_code == 200
    assert client.post("/api/shift/end", json={"force": True}).status_code == 200
    told = {
        name: [m["body"] for m in inbox(client, name, token) if m["kind"] == "system"]
        for name, token in (("alice", alice), ("bob", bob), ("carol", carol))
    }
    assert any("your line with bob unfinished" in b for b in told["alice"])
    assert any("your line with alice unfinished" in b for b in told["bob"])
    assert any("the open thread on your line with carol expired" in b for b in told["alice"])
    assert any("the open thread on your line with alice expired" in b for b in told["carol"])
    assert len(told["alice"]) == 2  # one notice per touched line, not one per entry
