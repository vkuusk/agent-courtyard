"""Hub memory (design hub-memory.md): the case file, notes, and recall.

The hub remembers collaboration, not craft. When a thread closes, the hub assembles
its story — the participants as they were, the opening ask, the resolution, every
verdict with its comment, the ordered messages — into one case file. The write-time
work is assembly, not summarization: no model call; the reader summarizes at read time.

A note (slice 2) is the other kind of record: an agent deposits a lesson on purpose,
or the operator writes standing guidance. A note is not a message — no recipient, no
turn, no answer owed — but it passes the gate like one: an agent's note on a supervised
line, or for the whole team, waits for the operator's approve / return / drop.

Recall is the pull path back into an agent's context: a bounded number of trimmed
records matching a question, ranked with the participants' declared domains (the ask,
a note's body and the domains weigh most), filtered by what the asking agent may see.
The hub renders the model-facing text (D14), so both adapters forward it as-is.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

from courtyard import texts
from courtyard.common.models import (
    Agent,
    Line,
    MemoryRecord,
    RecallView,
    Settings,
    Thread,
)
from courtyard.hub.core.deliver import Deliverer
from courtyard.hub.core.encoder import Encoder, EncoderError, NoEncoder
from courtyard.hub.core.errors import (
    LineNotFound,
    MemoryNotFound,
    NotAllowed,
    NoteNotPending,
    NoteScopeUnclear,
)
from courtyard.hub.core.events import EventBus
from courtyard.hub.core.registry import OPERATOR_NAME, Registry
from courtyard.hub.storage.repo import Storage, UnitOfWork

logger = logging.getLogger("courtyard.hub")

RECALL_MAX = 20  # the hard ceiling on one recall, whatever the setting says
EMBED_BATCH = 32  # records embedded per sweep pass
SEARCH_MODES = ("exact", "vector", "hybrid")
NOTE_MAX_CHARS = 2000


def case_file_in(uow: UnitOfWork, thread: Thread, line: Line, closed_by: Agent) -> MemoryRecord:
    """Inside the caller's transaction, right after the thread was ended `closed`: build the
    case file from the thread's messages and the line's two participants."""
    messages = uow.messages.list_thread(thread.id)
    participants = _participants_of(uow, line)
    spoken = [m for m in messages if m.kind == "message"]
    # the resolution is the last message that actually got through, not a dropped or
    # returned draft; with nothing through, the last thing said stands in
    landed = [m for m in spoken if m.status in ("delivered", "queued")]
    ask = spoken[0].body if spoken else ""
    resolution = (landed or spoken)[-1].body if spoken else ""
    verdicts = [
        f"{m.gate_verdict}: {m.gate_note.strip()}"
        for m in messages
        if m.gate_verdict and m.gate_note and m.gate_note.strip()
    ]
    counts = {"approve": 0, "return": 0, "drop": 0}
    for m in messages:
        if m.gate_verdict in counts:
            counts[m.gate_verdict] += 1
    return uow.memory.insert(
        record_id=uuid4(),
        kind="case",
        thread_id=thread.id,
        line_id=line.id,
        participants=participants,
        opened_by=thread.opened_by,
        opened_by_name=thread.opened_by_name,
        opened_at=thread.opened_at,
        closed_at=thread.ended_at,
        message_count=len(spoken),
        approved=counts["approve"],
        returned=counts["return"],
        dropped=counts["drop"],
        ask=ask,
        resolution=resolution,
        verdicts=verdicts,
        document={
            "messages": [m.model_dump(mode="json") for m in messages],
            "closed_by": closed_by.name,
        },
    )


def _participants_of(uow: UnitOfWork, line: Line) -> list[dict]:
    out = []
    for agent_id in (line.agent_a, line.agent_b):
        agent = uow.agents.get(agent_id)
        out.append({"id": str(agent.id), "name": agent.name, "sme_domain": agent.sme_domain})
    return out


def _cut(text: str, limit: int) -> tuple[str, bool]:
    text = text.strip()
    if len(text) <= limit:
        return text, False
    return text[: max(limit - 1, 1)].rstrip() + "…", True


def trim(record: MemoryRecord, chars: int) -> MemoryRecord:
    """The trimmed view: the ask, the resolution and a note's body cut to the recall length."""
    ask, cut_a = _cut(record.ask, chars)
    resolution, cut_r = _cut(record.resolution, chars)
    body, cut_b = _cut(record.body, chars)
    return record.model_copy(
        update={
            "ask": ask,
            "resolution": resolution,
            "body": body,
            "trimmed": cut_a or cut_r or cut_b,
            "document": None,
        }
    )


def _who(record: MemoryRecord) -> str:
    return " ↔ ".join(p.name for p in record.participants)


def _when(record: MemoryRecord) -> str:
    stamp = record.closed_at or record.created_at
    return stamp.strftime("%Y-%m-%d")


def _plural(count: int) -> str:
    return "s" if count != 1 else ""


def _note_scope(record: MemoryRecord) -> str:
    if record.scope == "team":
        return texts.render("listings.scope.team")
    return texts.render("listings.scope.line", who=_who(record))


def render_listing(question: str, records: list[MemoryRecord], searchable: bool = True) -> str:
    """The recall tool's text: bounded, trimmed, each record with its handle."""
    unknown = texts.render("listings.recall.unknown")
    none = texts.render("listings.recall.none")
    if not searchable:
        # not "nothing settled": the question could not be searched at all
        return texts.render("listings.recall.unsearchable", question=question)
    if not records:
        return texts.render("listings.recall.nothing", question=question)
    order = "best_match" if question.strip() else "newest"
    lines = [
        texts.render(
            "listings.recall.header",
            count=len(records),
            plural=_plural(len(records)),
            order=texts.render(f"listings.recall.order.{order}"),
        ),
        "",
    ]
    for n, r in enumerate(records, 1):
        if r.kind == "note":
            lines.append(
                texts.render(
                    "listings.recall.note_head",
                    n=n,
                    id=r.id,
                    author=r.author_name or unknown,
                    scope=_note_scope(r),
                    when=_when(r),
                )
            )
            lines.append(texts.render("listings.recall.note_body", body=r.body))
            lines.append("")
            continue
        counts = []
        if r.returned:
            counts.append(texts.render("listings.recall.case_returned", count=r.returned))
        if r.dropped:
            counts.append(texts.render("listings.recall.case_dropped", count=r.dropped))
        lines.append(
            texts.render(
                "listings.recall.case_head",
                n=n,
                id=r.id,
                who=_who(r),
                when=_when(r),
                count=r.message_count,
                plural=_plural(r.message_count),
                tail=f", {', '.join(counts)}" if counts else "",
            )
        )
        lines.append(
            texts.render(
                "listings.recall.case_ask", opener=r.opened_by_name or unknown, ask=r.ask or none
            )
        )
        lines.append(
            texts.render("listings.recall.case_resolution", resolution=r.resolution or none)
        )
        for v in r.verdicts:
            lines.append(texts.render("listings.recall.case_verdict", verdict=v))
        lines.append("")
    return "\n".join(lines).rstrip()


def render_case(record: MemoryRecord) -> str:
    """The full record as text: a case file's header and every message in order, or a
    note with its author, scope and standing."""
    unknown = texts.render("listings.recall.unknown")
    if record.kind == "note":
        head = texts.render(
            "listings.record.note_head",
            id=record.id,
            author=record.author_name or unknown,
            scope=_note_scope(record),
            when=_when(record),
            status=record.status,
        )
        tail = ""
        if record.gate_note:
            tail = "\n\n" + texts.render("listings.record.note_comment", comment=record.gate_note)
        return f"{head}\n\n{record.body}{tail}"
    doc = record.document or {}
    lines = [
        texts.render(
            "listings.record.case_head",
            id=record.id,
            who=_who(record),
            opener=record.opened_by_name or unknown,
            when=_when(record),
            closer=doc.get("closed_by") or unknown,
            count=record.message_count,
            plural=_plural(record.message_count),
            approved=record.approved,
            returned=record.returned,
            dropped=record.dropped,
        ),
        "",
    ]
    for m in doc.get("messages", []):
        who = m.get("sender_name") or texts.render(
            "listings.record.sender_hub"
            if m.get("kind") == "system"
            else "listings.record.sender_operator"
        )
        head = texts.render("listings.record.message_head", seq=m.get("seq", unknown), who=who)
        if m.get("recipient_name"):
            head += texts.render("listings.record.message_to", to=m["recipient_name"])
        if m.get("gate_verdict") and m.get("gate_note"):
            head += texts.render(
                "listings.record.message_verdict_comment",
                verdict=m["gate_verdict"],
                comment=m["gate_note"],
            )
        elif m.get("gate_verdict"):
            head += texts.render("listings.record.message_verdict", verdict=m["gate_verdict"])
        lines.append(head)
        body = (m.get("body") or "").replace("\n", "\n   ")
        lines.append(texts.render("listings.record.message_body", body=body))
    return "\n".join(lines).rstrip()


def render_note_result(record: MemoryRecord) -> str:
    """What the `courtyard_note` tool tells the author right after writing."""
    outcome = "held" if record.status == "pending" else "accepted"
    return texts.render(f"listings.note_result.{outcome}", id=record.id, scope=_note_scope(record))


QUESTION_EMBED_SECONDS = 5.0


def embedding_text(record: MemoryRecord) -> str:
    """What a record's vector is computed from: the trimmed view a future question would
    resemble (hub-memory.md section 7). Cases: ask, resolution, verdict comments, the
    participants' domains. Notes: the body."""
    if record.kind == "note":
        return record.body
    domains = " ".join(p.sme_domain or "" for p in record.participants).strip()
    parts = [record.ask, record.resolution, *record.verdicts, domains]
    return "\n".join(part for part in parts if part)


def sample_records() -> list[MemoryRecord]:
    """Deterministic records for the Admin page's envelope preview (item 29): what a recall
    listing costs, built through the same render as a real one."""
    when = datetime(2026, 1, 1, tzinfo=UTC)
    infra = {"id": str(UUID(int=1)), "name": "infra-agent", "sme_domain": "the AWS estate"}
    tf = {"id": str(UUID(int=2)), "name": "tf-agent", "sme_domain": "terraform modules"}
    case = MemoryRecord(
        id=UUID(int=10),
        kind="case",
        participants=[infra, tf],
        opened_by=UUID(int=1),
        opened_by_name="infra-agent",
        opened_at=when,
        closed_at=when,
        created_at=when,
        message_count=3,
        approved=2,
        returned=1,
        ask="(the opening ask of the thread, cut to the recall length)",
        resolution="(the last message that got through, cut to the recall length)",
        verdicts=["return: (the operator's comment on a returned draft)"],
    )
    note = MemoryRecord(
        id=UUID(int=11),
        kind="note",
        participants=[infra, tf],
        created_at=when,
        ask="",
        resolution="",
        body="(a note an agent or the operator left for this line, cut to the recall length)",
        scope="line",
        status="accepted",
        author=UUID(int=2),
        author_name="tf-agent",
    )
    return [case, note]


class Memory:
    def __init__(
        self,
        storage: Storage,
        registry: Registry,
        settings: Callable[[], Settings],
        events: EventBus,
        deliverer: Deliverer | None = None,
        discovery: Callable[[], str] | None = None,
        encoder: Encoder | None = None,
    ):
        self._storage = storage
        self._registry = registry
        self._settings = settings
        self._events = events
        self._deliverer = deliverer
        self._discovery = discovery or (lambda: "auto")
        self._encoder = encoder or NoEncoder()
        # the encoder's vector width, learned from the first vector it returns: an
        # endpoint that changed models but kept the name (or the same model name at
        # another width) must not leave rows the search cannot compare against
        self._dims: int | None = None

    # -- similarity (hub-memory.md section 7) --------------------------------------------

    @property
    def similarity(self) -> bool:
        return self._encoder.name != "none"

    def default_mode(self) -> str:
        """Hybrid when an encoder is configured, full text otherwise. The recall tool never
        exposes the mode; it always gets the best the hub has."""
        return "hybrid" if self.similarity else "exact"

    def _question_vector(self, question: str) -> list[float] | None:
        if not self.similarity or not question.strip():
            return None
        try:
            # a recall runs inside an agent's turn: a slow or wedged encoder gets seconds,
            # not the sweep's minute, and the search falls back to full text
            return self._learn_dims(
                self._encoder.embed([question.strip()], timeout=QUESTION_EMBED_SECONDS)
            )[0]
        except EncoderError as exc:
            logger.warning("similarity search unavailable, falling back to full text: %s", exc)
            return None

    def embed_pending(self, batch: int = EMBED_BATCH) -> int:
        """Give a vector to records that lack one from the current encoder (never embedded,
        or embedded by another model). Called by the hub's sweep and by the admin endpoint;
        tolerant of the encoder being down: nothing changes, the next pass retries."""
        if not self.similarity:
            return 0
        if self._dims is None:
            # one probe per hub start: without the width, rows embedded at another
            # width under this model name would pass as current and never be redone
            try:
                self._learn_dims(self._encoder.embed(["courtyard"]))
            except EncoderError as exc:
                logger.warning("embedding probe failed: %s", exc)
                return 0
        with self._storage.transaction() as uow:
            records = uow.memory.list_unembedded(self._encoder.model, batch, self._dims)
        if not records:
            return 0
        try:
            vectors = self._learn_dims(self._encoder.embed([embedding_text(r) for r in records]))
        except EncoderError as exc:
            logger.warning("embedding %d memory record(s) failed: %s", len(records), exc)
            return 0
        with self._storage.transaction() as uow:
            for record, vector in zip(records, vectors, strict=True):
                uow.memory.set_embedding(record.id, self._encoder.model, vector)
        return len(records)

    def _learn_dims(self, vectors: list[list[float]]) -> list[list[float]]:
        if vectors and vectors[0]:
            self._dims = len(vectors[0])
        return vectors

    def encoder_status(self) -> dict:
        with self._storage.transaction() as uow:
            stats = uow.memory.embedding_stats(self._encoder.model, self._dims)
        return {
            "encoder": self._encoder.name,
            "model": self._encoder.model,
            "default_mode": self.default_mode(),
            **stats,
            "pending": stats["total"] - stats["embedded"],
        }

    # -- visibility (hub-memory.md section 8) -------------------------------------------

    def _viewer(self, agent: Agent | None) -> tuple[UUID | None, bool]:
        """(the reading agent's id, whether it may see every case file). The operator and
        anonymous admin reads see everything; under `manual` discovery an agent sees
        only the case files it appears in; a line-scoped note is always its line's."""
        if agent is None or agent.type == "human":
            return None, True
        return agent.id, self._discovery() != "manual"

    # -- reads ---------------------------------------------------------------------------

    def search(
        self,
        *,
        question: str | None = None,
        participant: str | None = None,
        line_id: UUID | None = None,
        since: datetime | None = None,
        limit: int | None = None,
        as_agent: Agent | None = None,
        mode: str | None = None,
    ) -> list[MemoryRecord]:
        settings = self._settings()
        limit = min(limit or settings.recall_limit, RECALL_MAX)
        viewer, all_cases = self._viewer(as_agent)
        mode = mode or self.default_mode()
        vector = self._question_vector(question or "") if mode != "exact" else None
        with self._storage.transaction() as uow:
            who = self._registry.resolve(uow, participant).id if participant else None
            records = uow.memory.search(
                question=question,
                participant=who,
                line_id=line_id,
                since=since,
                limit=limit,
                viewer=viewer,
                all_cases=all_cases,
                mode=mode,
                query_vector=vector,
                model=self._encoder.model if vector is not None else None,
            )
        return [trim(r, settings.recall_trim_chars) for r in records]

    def export(
        self,
        *,
        participant: str | None = None,
        line_id: UUID | None = None,
        since: datetime | None = None,
    ) -> Iterator[str]:
        """JSON Lines (hub-memory.md section 6): every record in full, one per line,
        oldest first; superseded records and notes in every gate state included, with
        their status. Nothing trimmed, nothing rendered: the raw memory."""
        with self._storage.transaction() as uow:
            who = self._registry.resolve(uow, participant).id if participant else None
            records = uow.memory.export(participant=who, line_id=line_id, since=since)
        for record in records:
            yield record.model_dump_json(exclude={"trimmed", "rendered"}) + "\n"

    def get(self, record_id: UUID, as_agent: Agent | None = None) -> MemoryRecord:
        with self._storage.transaction() as uow:
            record = uow.memory.get(record_id)
        if record is None:
            raise MemoryNotFound("no such memory record")
        viewer, all_cases = self._viewer(as_agent)
        if viewer is not None:
            mine = any(p.id == viewer for p in record.participants)
            if record.kind == "note":
                if record.status != "accepted" and record.author != viewer:
                    raise NotAllowed(texts.render("refusals.recall.note_not_in_memory"))
                if record.scope == "line" and not mine:
                    raise NotAllowed(texts.render("refusals.recall.note_other_line"))
            elif not all_cases and not mine:
                raise NotAllowed(texts.render("refusals.recall.case_other_line"))
        return record

    def recall(self, agent: Agent, question: str, limit: int | None = None) -> RecallView:
        """The agent-facing read (the `courtyard_recall` tool): trimmed, bounded,
        filtered, and rendered hub-side."""
        if question.strip() and not self.searchable(question):
            return RecallView(records=[], rendered=render_listing(question, [], searchable=False))
        records = self.search(question=question, limit=limit, as_agent=agent)
        return RecallView(records=records, rendered=render_listing(question, records))

    def recall_case(self, agent: Agent, record_id: UUID) -> MemoryRecord:
        record = self.get(record_id, as_agent=agent)
        return record.model_copy(update={"rendered": render_case(record)})

    def count(self) -> int:
        with self._storage.transaction() as uow:
            return uow.memory.count()

    def searchable(self, question: str) -> bool:
        with self._storage.transaction() as uow:
            return uow.memory.searchable(question)

    # -- notes (slice 2) -------------------------------------------------------------------

    def note(
        self,
        author: Agent,
        body: str,
        *,
        peer: str | None = None,
        line_id: UUID | None = None,
        team_wide: bool = False,
    ) -> MemoryRecord:
        """Deposit a note. Scope: the line with `peer` (or `line_id`), or the author's only
        line when neither is given, unless `team_wide`. The operator's notes are team-wide
        by default and never wait; an agent's note waits at the gate when its line is
        supervised, and always when it is team-wide (it would reach everyone)."""
        body = body.strip()
        if not body:
            raise NoteScopeUnclear(texts.render("refusals.note.no_body"))
        if len(body) > NOTE_MAX_CHARS:
            raise NoteScopeUnclear(texts.render("refusals.note.too_long", limit=NOTE_MAX_CHARS))
        with self._storage.transaction() as uow:
            line = None if team_wide else self._scope_line(uow, author, peer, line_id)
            if line is None:
                scope = "team"
                participants = [
                    {"id": str(author.id), "name": author.name, "sme_domain": author.sme_domain}
                ]
                status = "accepted" if author.type == "human" else "pending"
            else:
                scope = "line"
                participants = _participants_of(uow, line)
                gated = author.type != "human" and line.mode == "supervised"
                status = "pending" if gated else "accepted"
            record = uow.memory.insert_note(
                record_id=uuid4(),
                body=body,
                scope=scope,
                status=status,
                author=author.id,
                author_name=author.name,
                line_id=line.id if line else None,
                participants=participants,
            )
        self._events.publish("memory", record)
        return record.model_copy(update={"rendered": render_note_result(record)})

    def _scope_line(
        self, uow: UnitOfWork, author: Agent, peer: str | None, line_id: UUID | None
    ) -> Line | None:
        """The line a note is for. The operator with neither peer nor line means team-wide
        (returns None); an agent must name one or have exactly one line to fall back on."""
        if line_id is not None:
            line = uow.lines.get(line_id)
            if line is None:
                raise LineNotFound("no such line")
            return line
        if peer:
            other = self._registry.resolve(uow, peer)
            line = uow.lines.get_pair_locked(author.id, other.id)
            if line is None:
                raise LineNotFound(f"you have no line with {other.name!r}")
            return line
        if author.type == "human":
            return None
        candidates = []
        for ln in uow.lines.list_for_agent(author.id):
            other_id = ln.agent_a if ln.agent_b == author.id else ln.agent_b
            if uow.agents.get(other_id).type != "human":
                candidates.append(ln)
        if len(candidates) == 1:
            return candidates[0]
        raise NoteScopeUnclear(
            texts.render("refusals.note.which_line" if candidates else "refusals.note.no_line")
        )

    def pending(self) -> list[MemoryRecord]:
        with self._storage.transaction() as uow:
            return uow.memory.list_pending()

    def decide(self, record_id: UUID, verdict: str, note: str | None) -> MemoryRecord:
        """The operator rules on a pending note. A return carries the comment back to the
        author, a drop tells it not to resend; both ride the operator's line with the
        author as a hub notice, the way message verdicts do. Approve is silent: the note
        simply becomes memory."""
        status = {"approve": "accepted", "return": "returned", "drop": "dropped"}[verdict]
        notice = None
        with self._storage.transaction() as uow:
            record = uow.memory.decide_note(record_id, status, note)
            if record is None:
                if uow.memory.get(record_id) is None:
                    raise MemoryNotFound("no such note")
                raise NoteNotPending("this note is not waiting for a verdict")
            if verdict != "approve" and record.author is not None:
                operator = uow.agents.get_by_name(OPERATOR_NAME)
                line = uow.lines.get_or_create_locked(
                    operator.id, record.author, self._settings().default_line_mode
                )
                outcome = "returned" if verdict == "return" else "dropped"
                body = texts.render(f"notices.note.{outcome}", excerpt=record.body[:80])
                if verdict == "return" and note:
                    body += texts.render("notices.note.comment", note=note)
                notice = uow.messages.insert(
                    message_id=uuid4(),
                    line_id=line.id,
                    sender=None,
                    recipient=record.author,
                    kind="system",
                    body=body,
                    reply_to=None,
                    status="queued",
                    thread_id=line.open_thread,
                )
        self._events.publish("memory", record)
        if notice is not None:
            self._events.publish("message", notice)
            if self._deliverer is not None:
                self._deliverer.deliver(notice)
        return record
