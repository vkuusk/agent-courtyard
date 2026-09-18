"""Golden: the notices, board entries and refusals one scripted session produces.

These texts are written where the event happens (board, turns, registry, memory), so
they are collected by making the events happen on a real hub."""

from __future__ import annotations

from texts_golden import blocks, check

from conftest import auth


class Session:
    def __init__(self, client, make_agent):
        self.client = client
        self.tokens = {name: make_agent(name)[1] for name in ("alice", "bob", "carol", "dave")}
        self.refusals: list[tuple[str, str]] = []

    def call(self, method, path, who=None, **json):
        headers = auth(self.tokens[who]) if who else None
        return self.client.request(method, path, json=json or None, headers=headers)

    def ok(self, *args, **kw):
        resp = self.call(*args, **kw)
        assert resp.status_code < 300, resp.text
        return resp.json() if resp.content else None

    def refused(self, title, *args, **kw):
        resp = self.call(*args, **kw)
        assert resp.status_code >= 400, f"{title}: expected a refusal, got {resp.text}"
        self.refusals.append((title, resp.json()["error"]["rendered"]))

    def send(self, who, to, body, **kw):
        return self.ok("POST", "/api/lines/send", who, to=to, body=body, **kw)

    def hub_texts(self, line_id) -> str:
        rows = self.ok("GET", f"/api/lines/{line_id}/messages")
        return "\n".join(
            f"to {m['recipient_name'] or 'the board'}: {m['body']}"
            for m in rows
            if m["kind"] == "system"
        )


def test_notices_board_entries_and_refusals(client, make_agent):
    s = Session(client, make_agent)
    s.ok("DELETE", "/api/agents/dave")

    s.refused("unknown recipient", "POST", "/api/lines/send", "alice", to="nobody", body="x")
    s.refused("send to yourself", "POST", "/api/lines/send", "alice", to="alice", body="x")
    s.refused("removed recipient", "POST", "/api/lines/send", "alice", to="dave", body="x")

    # the gate: held, returned with a comment, dropped
    q1 = s.send("alice", "bob", "q1")
    line = q1["line_id"]
    assert q1["result"].startswith("Held at the gate")  # the send answers with its result
    s.refused(
        "send while a message is held", "POST", "/api/lines/send", "alice", to="bob", body="x"
    )
    s.refused(
        "close while a message is held", "POST", "/api/lines/close-thread", "alice", peer="bob"
    )
    s.ok("POST", f"/api/gate/{q1['id']}", verdict="return", note="too vague")
    q2 = s.send("alice", "bob", "q2")
    s.ok("POST", f"/api/gate/{q2['id']}", verdict="drop", note="not now")

    # turns and threads on an auto-pass line
    s.ok("POST", f"/api/lines/{line}/mode", mode="auto_pass")
    s.send("alice", "bob", "q3")
    s.refused("send before the answer", "POST", "/api/lines/send", "alice", to="bob", body="x")
    s.send("bob", "alice", "a3")
    s.refused(
        "new ask on an open thread",
        "POST",
        "/api/lines/send",
        "alice",
        to="bob",
        body="x",
        new_thread=True,
    )
    s.refused("close by the other side", "POST", "/api/lines/close-thread", "bob", peer="alice")
    closed = s.ok("POST", "/api/lines/close-thread", "alice", peer="bob")
    assert closed["result"].startswith("Thread closed")
    s.refused("close with no open thread", "POST", "/api/lines/close-thread", "alice", peer="bob")
    s.refused("close on your own line", "POST", "/api/lines/close-thread", "alice", peer="alice")
    s.refused(
        "an ask serving a thread that is not open",
        "POST",
        "/api/lines/send",
        "alice",
        to="bob",
        body="x",
        serves="carol",
    )
    # a report to the operator: delivered, and nothing is waited for (section 7.5)
    report = s.send("alice", "operator", "a report")
    s.results = [("send: a report to the operator", report["result"])]

    # the budget
    s.ok("PATCH", "/api/settings", thread_budget=2)
    s.send("alice", "bob", "b1")
    s.send("bob", "alice", "b2")
    s.refused("budget spent", "POST", "/api/lines/send", "alice", to="bob", body="b3")
    s.ok("PATCH", "/api/settings", thread_budget=12)

    # release, body size
    s.send("alice", "bob", "r1")
    s.ok("POST", f"/api/lines/{line}/release")
    s.refused("body too large", "POST", "/api/lines/send", "alice", to="bob", body="x" * 17000)

    # notes
    s.refused("note with no line", "POST", "/api/agents/carol/notes", "carol", body="a lesson")
    s.refused("empty note", "POST", "/api/agents/alice/notes", "alice", body="  ")
    held = s.send("alice", "carol", "held at the gate")
    s.refused("note with two lines", "POST", "/api/agents/alice/notes", "alice", body="a lesson")
    for verdict, comment in (("return", "say which module"), ("drop", None)):
        note = s.ok("POST", "/api/agents/alice/notes", "alice", body="a lesson", team_wide=True)
        s.ok("POST", f"/api/memory/{note['id']}/decide", verdict=verdict, note=comment)

    # manual discovery
    s.ok("PATCH", "/api/settings", discovery="manual")
    s.refused(
        "no line under manual discovery", "POST", "/api/lines/send", "bob", to="carol", body="x"
    )
    case = next(r for r in s.ok("GET", "/api/memory") if r["kind"] == "case")
    s.refused(
        "a case file of someone else's line",
        "GET",
        f"/api/agents/carol/recall/{case['id']}",
        "carol",
    )
    s.ok("PATCH", "/api/settings", discovery="auto")

    # the end of a shift: one message awaiting a reply, one held at the gate
    s.send("alice", "bob", "e1")
    s.ok("POST", "/api/shift/start")
    s.ok("POST", "/api/shift/end", force=True)

    operator_line = next(
        ln["id"] for ln in s.ok("GET", "/api/lines") if ln["id"] not in (line, held["line_id"])
    )
    entries = [
        ("alice and bob", s.hub_texts(line)),
        ("alice and carol", s.hub_texts(held["line_id"])),
        ("alice and the operator", s.hub_texts(operator_line)),
    ]
    s.ok("POST", f"/api/lines/{line}/archive")
    entries.append(("alice and bob, after an archive", s.hub_texts(line)))
    check("notices_and_board_entries", blocks(entries))
    check("refusals", blocks(s.refusals))
    check("tool_results_flow", blocks(s.results))
