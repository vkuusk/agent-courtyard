"""The replies an agent owes on the board (design communication-protocols.md section 6).

The hub never sees a terminal, so it cannot tell where a request came from; it does know
on which lines an agent is awaited. The footer of a delivered answer states that fact, so
the agent can tell an answer it has to pass on through the hub from one that belongs to
the user in its terminal."""

from __future__ import annotations

from uuid import UUID

from courtyard.hub.storage.repo import UnitOfWork


def owed_replies(uow: UnitOfWork, agent_id: UUID) -> list[str]:
    """The names of the participants waiting for this agent's reply, in name order."""
    names = []
    for line in uow.lines.list_for_agent(agent_id):
        if line.state == "awaiting_reply" and line.awaiting_from == agent_id:
            other = line.agent_a if line.agent_b == agent_id else line.agent_b
            names.append(uow.agents.get(other).name)
    return sorted(names)


def served_thread(uow: UnitOfWork, message) -> tuple[str, str] | None:
    """When the answered ask declared the thread it serves: the name of that thread's
    other participant (the one the result is for) and the thread's state."""
    if message.thread_id is None:
        return None
    thread = uow.threads.get(message.thread_id)
    if thread is None or thread.serves is None:
        return None
    served = uow.threads.get(thread.serves)
    if served is None:
        return None
    line = uow.lines.get(served.line_id)
    other = line.agent_a if line.agent_b == message.recipient else line.agent_b
    return uow.agents.get(other).name, served.state


def needs_owed(message) -> bool:
    """Only an answer carries the statement: that is when a result may have to travel on."""
    return message.kind == "message" and message.reply_to is not None
