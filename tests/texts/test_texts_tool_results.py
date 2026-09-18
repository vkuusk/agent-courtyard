"""Golden: what a courtyard tool returns to the model. The hub words the outcome of a
send, a close, an acknowledgement and a refusal; an adapter words only what happens on
its own side of the connection."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

import httpx
from texts_golden import blocks, check

from courtyard.adapters.claude_code.mcp_server import AdapterConfig, CourtyardAdapter
from courtyard.common.client import HubError
from courtyard.common.models import Message
from courtyard.hub.core import results

NO_HUB = "http://127.0.0.1:9"  # nothing listens: the adapter uses its packaged texts


def message(status: str, **kw) -> Message:
    return Message(
        id=UUID(int=0),
        line_id=UUID(int=0),
        seq=7,
        sender=UUID(int=1),
        recipient=UUID(int=2),
        kind="message",
        body="(body)",
        status=status,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        **kw,
    )


def test_tool_results_worded_by_the_hub():
    check(
        "tool_results_hub",
        blocks(
            [
                ("send: delivered", results.send(message("delivered"), "bob")),
                ("send: held at the gate", results.send(message("pending_gate"), "bob")),
                ("send: recipient not connected", results.send(message("queued"), "bob")),
                (
                    "send: an answer, delivered",
                    results.send(message("delivered", reply_to=UUID(int=3)), "bob"),
                ),
                (
                    "send: an answer, recipient not connected",
                    results.send(message("queued", reply_to=UUID(int=3)), "bob"),
                ),
                (
                    "send: an answer, held at the gate",
                    results.send(message("pending_gate", reply_to=UUID(int=3)), "bob"),
                ),
                ("close", results.close("bob")),
                ("ack: confirmed", results.ack(True)),
                ("ack: check no longer open", results.ack(False)),
                ("a refusal", results.refusal("turn_violation", "(the refusal's message)")),
            ]
        ),
    )


class StubClient:
    """The hub client's surface, answering from a script."""

    def __init__(self):
        self.send_result: Message | Exception = message("delivered", result="(the hub's wording)")
        self.inbox_result: list[Message] = []

    def send(self, to, body, new_thread=False, serves=None):
        if isinstance(self.send_result, Exception):
            raise self.send_result
        return self.send_result

    def close_thread(self, peer):
        return SimpleNamespace(result="(the hub's wording)", state="closed")

    def inbox(self):
        return self.inbox_result

    def ack_delivery(self, token):
        return True, "(the hub's wording)"

    def note(self, body, peer=None, team_wide=False):
        return SimpleNamespace(rendered=None, id=UUID(int=11))


def test_claude_code_adapter_forwards_and_words_its_own_side():
    adapter = CourtyardAdapter(AdapterConfig(NO_HUB, "agent-x", "t", 5.0))
    stub = adapter._client = StubClient()
    entries = []

    def call(title, tool, **arguments):
        result = adapter._call_tool(tool, arguments)
        flag = " (error)" if result["isError"] else ""
        entries.append((title + flag, result["content"][0]["text"]))

    call("send: forwarded", "courtyard_send", to="bob", message="hi")
    call("close: forwarded", "courtyard_close_thread", peer="bob")
    call("ack: forwarded", "courtyard_ack", token="T")
    stub.send_result = HubError(409, "turn_violation", "(message)", {}, "(the hub's wording)")
    call("a refusal: forwarded", "courtyard_send", to="bob", message="hi")
    stub.send_result = HubError(422, "http_error", "(a body the hub did not word)")
    call("an error the hub did not word", "courtyard_send", to="bob", message="hi")
    stub.send_result = httpx.ConnectError("connection refused")
    call("hub unreachable", "courtyard_send", to="bob", message="hi")
    call("send: missing arguments", "courtyard_send", to="bob")
    call("close: missing peer", "courtyard_close_thread")
    call("inbox: empty", "courtyard_inbox")
    stub.inbox_result = [
        message("delivered", rendered="(envelope one)"),
        message("delivered", rendered="(envelope two)"),
    ]
    call("inbox: two messages", "courtyard_inbox")
    call("ack: missing token", "courtyard_ack")
    call("note: no rendered text from the hub", "courtyard_note", body="a lesson")
    call("note: missing body", "courtyard_note")
    call("recall: bad limit", "courtyard_recall", question="x", limit="many")
    call("unknown tool", "courtyard_nothing")
    check("tool_results_claude_code_adapter", blocks(entries))
