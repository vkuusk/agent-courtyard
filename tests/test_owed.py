"""The owed-reply statement and the truthful send result (design
communication-protocols.md sections 3.3 and 6.3; feedback item 45).

The hub cannot see where a request came from, so an answer's footer states what the hub
does know: on which lines the recipient is still awaited."""

from __future__ import annotations

from conftest import auth


def send(client, token, to, body):
    resp = client.post("/api/lines/send", json={"to": to, "body": body}, headers=auth(token))
    assert resp.status_code == 201, resp.text
    return resp.json()


def inbox(client, name, token):
    return client.get(f"/api/agents/{name}/inbox", headers=auth(token)).json()


def linked(client, make_agent):
    _, alice = make_agent("alice")
    _, bob = make_agent("bob")
    line = client.post("/api/lines", json={"a": "alice", "b": "bob"}).json()
    client.post(f"/api/lines/{line['id']}/mode", json={"mode": "auto_pass"})
    return alice, bob


def test_an_answer_names_whom_the_recipient_still_owes(client, make_agent):
    alice, bob = linked(client, make_agent)
    # the operator asks alice on the board; alice asks bob to be able to answer
    client.post("/api/operator/send", json={"to": "alice", "body": "which port is staging on?"})
    inbox(client, "alice", alice)
    send(client, alice, "bob", "which port is the staging db on?")
    inbox(client, "bob", bob)
    send(client, bob, "alice", "5433")
    (answer,) = inbox(client, "alice", alice)
    assert "You still owe a reply on the board to: operator." in answer["rendered"]
    assert "Nobody on the board is waiting" not in answer["rendered"]


def test_an_answer_to_a_terminal_request_says_nobody_is_waiting(client, make_agent):
    """The 2026-09-13 session: the user typed the question in alice's terminal, so the
    board holds no ask for alice; the answer belongs in the terminal."""
    alice, bob = linked(client, make_agent)
    send(client, alice, "bob", "do you have any CSV files?")
    inbox(client, "bob", bob)
    send(client, bob, "alice", "no CSV files")
    (answer,) = inbox(client, "alice", alice)
    assert "Nobody on the board is waiting on you" in answer["rendered"]
    assert "answer it there" in answer["rendered"]
    assert "owe a reply" not in answer["rendered"]


def test_a_question_carries_no_owed_statement(client, make_agent):
    alice, bob = linked(client, make_agent)
    client.post("/api/operator/send", json={"to": "bob", "body": "status?"})
    send(client, alice, "bob", "a question")
    rendered = [m["rendered"] for m in inbox(client, "bob", bob)]
    assert len(rendered) == 2 and not any("on the board" in r for r in rendered)


def test_the_send_result_states_the_lines_state(client, make_agent):
    alice, bob = linked(client, make_agent)
    ask = send(client, alice, "bob", "a question")
    assert "The line awaits their reply" in ask["result"]  # bob is not connected: accepted
    inbox(client, "bob", bob)
    answer = send(client, bob, "alice", "an answer")
    assert "That answers their message: nobody owes a reply on this line now" in answer["result"]
    assert "awaits their reply" not in answer["result"]
    line = client.get(f"/api/lines/{ask['line_id']}").json()
    assert line["state"] == "idle"  # what the result said is what the hub holds
