"""The operator's lines take turns in one direction (design communication-protocols.md
section 7.3, threads.md section 3): an agent's own message to the operator awaits no
reply and the thread it opens ends at once; the operator's messages take turns."""

from __future__ import annotations

from conftest import auth


def send(client, token, to, body):
    resp = client.post("/api/lines/send", json={"to": to, "body": body}, headers=auth(token))
    assert resp.status_code == 201, resp.text
    return resp.json()


def line_of(client, message):
    return client.get(f"/api/lines/{message['line_id']}").json()


def threads_of(client, message):
    return client.get(f"/api/lines/{message['line_id']}/threads").json()


def test_a_report_to_the_operator_awaits_nothing_and_its_thread_ends_at_once(client, make_agent):
    _, alice = make_agent("alice")
    report = send(client, alice, "operator", "staging db is on 5433")
    assert report["status"] == "delivered"  # the WebUI is the operator's end of the line
    assert "no answer is to be expected" in report["result"]
    line = line_of(client, report)
    assert line["state"] == "idle" and line["open_thread"] is None
    (thread,) = threads_of(client, report)
    assert thread["state"] == "closed" and thread["ended_at"]
    # the next report is not a turn violation, and opens and closes a thread of its own
    second = send(client, alice, "operator", "and the app server is on 8080")
    assert second["status"] == "delivered"
    assert [t["state"] for t in threads_of(client, second)] == ["closed", "closed"]
    # a report is no case file: it holds no ask and no resolution (hub-memory.md section 3)
    assert client.get("/api/memory").json() == []


def test_the_operators_message_takes_a_turn_and_keeps_its_thread(client, make_agent):
    _, alice = make_agent("alice")
    ask = client.post("/api/operator/send", json={"to": "alice", "body": "which port?"}).json()
    line = line_of(client, ask)
    assert line["state"] == "awaiting_reply"
    answer = send(client, alice, "operator", "5433")
    assert answer["reply_to"] == ask["id"]
    assert "nobody owes a reply on this line now" in answer["result"]
    line = line_of(client, answer)
    assert (
        line["state"] == "idle" and line["open_thread"] == ask["thread_id"]
    )  # the operator closes
    # a later addition from the agent stays in the operator's thread and waits for nothing
    more = send(client, alice, "operator", "the app server is on 8080, by the way")
    assert more["thread_id"] == ask["thread_id"] and "no answer is to be expected" in more["result"]
    assert line_of(client, more)["state"] == "idle"
    assert [t["state"] for t in threads_of(client, more)] == ["open"]


def test_agents_between_themselves_still_take_turns(client, make_agent):
    _, alice = make_agent("alice")
    make_agent("bob")
    first = send(client, alice, "bob", "a question")
    client.post(f"/api/gate/{first['id']}", json={"verdict": "approve"})
    assert line_of(client, first)["state"] == "awaiting_reply"
    refused = client.post(
        "/api/lines/send", json={"to": "bob", "body": "again"}, headers=auth(alice)
    )
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "turn_violation"
