"""The thread an ask serves (design threads.md section 3, communication-protocols.md
sections 6.3 and 7.5): `serves` on a send names the participant whose open thread with
the sender the ask serves; the hub keeps the link on the thread the ask opens and uses it
to tell the asker whom the answer is for."""

from __future__ import annotations

from conftest import auth


def send(client, token, to, body, **extra):
    resp = client.post(
        "/api/lines/send", json={"to": to, "body": body, **extra}, headers=auth(token)
    )
    return resp


def sent(client, token, to, body, **extra):
    resp = send(client, token, to, body, **extra)
    assert resp.status_code == 201, resp.text
    return resp.json()


def inbox(client, name, token):
    return client.get(f"/api/agents/{name}/inbox", headers=auth(token)).json()


def setup(client, make_agent):
    _, alice = make_agent("alice")
    _, bob = make_agent("bob")
    line = client.post("/api/lines", json={"a": "alice", "b": "bob"}).json()
    client.post(f"/api/lines/{line['id']}/mode", json={"mode": "auto_pass"})
    ask = client.post("/api/operator/send", json={"to": "alice", "body": "which port?"}).json()
    inbox(client, "alice", alice)
    return alice, bob, ask


def test_the_link_is_kept_and_the_answer_names_whom_the_result_is_for(client, make_agent):
    alice, bob, operator_ask = setup(client, make_agent)
    helper_ask = sent(client, alice, "bob", "which port is staging on?", serves="operator")
    (thread,) = client.get(f"/api/lines/{helper_ask['line_id']}/threads").json()
    assert thread["serves"] == operator_ask["thread_id"]
    inbox(client, "bob", bob)
    sent(client, bob, "alice", "5433")
    (answer,) = inbox(client, "alice", alice)
    assert "Your ask served your thread with operator: answer operator" in answer["rendered"]
    assert "owe a reply on the board" not in answer["rendered"]  # case 1 replaces case 2


def test_a_declaration_with_no_such_open_thread_is_refused(client, make_agent):
    _, alice = make_agent("alice")
    make_agent("bob")
    make_agent("carol")
    resp = send(client, alice, "bob", "a question", serves="carol")
    assert resp.status_code == 409 and resp.json()["error"]["code"] == "no_served_thread"
    assert "no open thread with 'carol'" in resp.json()["error"]["message"]
    assert (
        send(client, alice, "bob", "x", serves="nobody").json()["error"]["code"] == "unknown_agent"
    )
    assert client.get("/api/lines").json() == []  # nothing was sent


def test_continuing_a_thread_leaves_the_link_alone(client, make_agent):
    alice, bob, _ = setup(client, make_agent)
    first = sent(client, alice, "bob", "which port?")  # opened without a link
    inbox(client, "bob", bob)
    sent(client, bob, "alice", "which environment?")
    inbox(client, "alice", alice)
    follow_up = sent(client, alice, "bob", "staging", serves="operator")  # continues, no refusal
    assert follow_up["thread_id"] == first["thread_id"]
    (thread,) = client.get(f"/api/lines/{first['line_id']}/threads").json()
    assert thread["serves"] is None


def test_an_answer_says_when_the_served_thread_has_ended(client, make_agent):
    alice, bob, _ = setup(client, make_agent)
    sent(client, alice, "bob", "which port?", serves="operator")
    client.post("/api/operator/close-thread", json={"peer": "alice"})  # the operator moved on
    inbox(client, "bob", bob)
    sent(client, bob, "alice", "5433")
    (answer,) = [m for m in inbox(client, "alice", alice) if m["kind"] == "message"]
    assert "served your thread with operator, which has ended since (closed)" in answer["rendered"]
    assert "answer it there" in answer["rendered"]
