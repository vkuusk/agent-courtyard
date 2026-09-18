# Hub memory: the team remembers collaboration, not craft

## 1. The problem

Courtyard deliberately leaves craft memory to the agents. Each specialist grows
its own experience in its own project directory: memories, skills, conventions,
and that experience survives any team it takes part in. The hub stays out of it.

What nobody keeps is the other half. A team of standing agents still loses three
things every day:

- **The exchange itself.** An agent remembers its own view of a conversation, not
  the conversation. When infra asks terraform whether a module supports a flag,
  infra remembers the answer it acted on, terraform remembers that it was asked,
  and neither remembers that the operator returned the first draft with a
  comment. A week later a third agent asks the same question and spends a
  peer's turn on it.
- **The operator's verdicts.** A return to sender with a comment is the highest
  signal event the hub records: this message, on this line, was wrong, and here
  is why. Without memory it lands in the archive and is never read again, and
  supervision teaches nobody.
- **The record as material.** The complete inter-agent history is the one thing
  in the system that no agent can see and the operator sees only live. It is
  exactly what an audit, a post-mortem, a training set or a runbook would be
  written from, and without memory the only way to it is the Archive page, one
  line at a time.

The wider field describes the same gap. Disposable agent teams (a lead spawns
teammates for one task and dissolves them) re-establish context on every spawn:
the teammates share no memory, the lead's history does not carry over, and a
three-agent team costs about four times the tokens of a single session, much of
it re-explaining. Courtyard's standing team already removes the re-spawning half
of that cost. Hub memory removes the other half: what the team learned about
working together does not evaporate at End shift.

## 2. The rule

**The hub remembers collaboration, not craft.**

Agents own what they learned doing the work. The hub owns what happened between
them and what the operator ruled. Every feature in this document has to pass that
test, and two fall on the wrong side of it by design:

- The hub never reads an agent's transcript, session files or memory directory.
  It sees only what passes through it. Reading a session would duplicate the
  agent's own memory and break the segregation of duties the README promises:
  each agent holds only its own access, and the hub is not a back door into it.
- The hub never writes into an agent's memory. Memory reaches an agent through
  the two paths the hub already owns, the envelope and the hub tools, and
  through nothing else.

A second principle: **a memory layer is only real once there is a path that
delivers it back into an agent's context.**
Extraction into storage that nothing reads back is a dashboard feature. So the
retrieval hop is designed first, and extraction is shaped to serve it.

## 3. The case file

The unit of memory is the closed thread (`threads.md`): one ask, its resolution,
done. Only threads that closed become case files. Threads that expired or were
locked never got their answer, and recording them would skew every later
judgement toward asks that failed. Threads the operator opened with an agent count
too. An agent's report to the operator does not: the hub ends that thread at once
(`threads.md` section 3), and it holds no ask and no resolution, so it stays in the
line's history only. At close the
hub assembles the thread's story, which is spread over the messages, threads,
lines and agents tables and the gate columns, into one **case file**. The
write-time work is assembly, not summarization: the hub makes no model call, and
the reader summarizes at read time, which is what a model does well. A digest
written by a model would be shorter, at the price of an API key, a cost and a new
failure mode inside the hub.

One record, two parts:

- **Typed columns**, for filtering and for the WebUI: id, kind (`case` or
  `note`), the thread and line it came from, participants (ids and names as they
  were at the time), who opened it, opened and closed timestamps, message count,
  verdict counts (approved, returned, dropped), and the thread this one served,
  when its opening ask declared one (`threads.md` section 3). Plus `superseded_by`, the
  encoder name and the embedding column of section 7, and a full-text index over
  the searchable text.
- **A JSON document**: the ordered messages with sender, body, the gate verdict,
  the verdict comment and who decided; the operator's notes on the line during
  the thread; the closing line. This is the same technique the archive uses per
  line (D20), one level down and indexed.

Two views of a record serve the two kinds of reader:

- **The trimmed view**, what recall returns: the opening ask, the resolution
  (the last message before close), every verdict with its comment, and a handle.
  Bounded, so it fits an agent's context the way a delivery does.
- **The full case file**, fetched by the handle: the whole document above.

Both views follow the served-thread link. A record names the participants of the
thread it served and, once that thread has closed, the handle of its case file;
the full case file also lists the case files of the threads that served it. A
helper's thread usually closes before the thread it served, so the link is kept
as the thread and resolved to a case file at read time. A handle is shown only to
a reader who may open it (section 8).

The second kind of record is the **note**: a memory record with an author, a body
and a scope, no thread. Its scope is one line unless the author says team-wide.
Where it comes from is section 4; why it is not a message is section 5.

## 4. Where records come from

1. **Thread close.** The initiator's close call (D34) is the natural moment: the
   ask is settled and the record is complete. The hub writes the case file in the
   same transaction that closes the thread.
2. **Notes.** An agent deposits a lesson on purpose through a hub tool
   (section 5), or the operator writes one on the WebUI. The operator's notes
   are standing team guidance; the agents' notes are what a specialist wants the
   rest of the team to know without anyone having asked.

Nothing else writes memory. End shift writes none: the threads it expires (D24)
and the threads a budget or a release locked stay in the archive only. The hub does not mine
messages in the background looking for lessons; that would be summarization the
hub cannot do without a model, and it would produce records with no event behind
them.

## 5. Delivery paths

Two paths, both riding what the hub already owns, and both pull: the envelope's
token overhead is measured and watched, and every push is a standing cost on
every message. Verdicts in particular need no delivery of their own: a
return already goes back to its sender with the comment, and an approval already
goes on to its recipient with the note (D7, D27), inside the thread, at the moment
they apply. Memory keeps them for later recall; it does not deliver them twice.

1. **Recall (pull).** A hub tool, `courtyard_recall(question, ...)`, beside the
   existing `courtyard_send`, `courtyard_peers`, `courtyard_inbox`,
   `courtyard_ack` and `courtyard_close_thread`. It returns a bounded number of
   trimmed records matching the question, filtered by what the asking agent may
   see (section 8), each with a handle; a second call with the handle returns the
   full case file. An agent asks "has the team discussed X before" and gets the
   answer without opening a line and spending a peer's turn. Zero standing token
   cost.
2. **Notes (write).** A hub tool, `courtyard_note(body, peer?, team_wide?)`, by
   which an agent deposits a lesson into team memory. A note is not a message: it
   has no recipient, takes no turn and expects no answer. It is scoped to the line
   the author names (or its only line) unless the author says team-wide. It shares
   two things with a message: it shows on the WebUI, and it passes the gate
   (section 8). The same record kind lets the operator write notes from the
   Memory page; the operator's notes are team-wide unless scoped.

Recall ranks with the team's declared domains: a record's participants carry their
`sme_domain` at the time, so a question about terraform finds the threads terraform
took part in first, before any vector exists. The existing `courtyard_peers`
roster is unchanged: the roster says who owns what, memory says what happened.

## 6. Beyond the agents

The store is the same; the readers differ. One read endpoint serves them all,
`GET /api/memory?q=...&mode=...&participant=...&line=...&since=...`, returning
trimmed records, plus `GET /api/memory/{id}` for the full case file and an export
in JSON Lines. Admin surface, unauthenticated on localhost like the rest (D3).

- **Audit.** Who told whom what, with the operator's verdicts inline. The Archive
  page is the raw read-back per line; memory is the indexed layer above it, and
  every record points at the archive entries it was built from.
- **Training and evaluation.** The export is a labeled set: messages with
  verdicts and comments are examples of what the operator accepts and rejects.
  What is done with it is outside the hub.
- **Skills and runbooks.** The established pattern in conversational AI is to
  mine historical transcripts into question and answer pairs, cluster them, and
  promote representatives into a knowledge base that a human reviews. Case files
  are that material with provenance attached, so a distilled runbook can be
  checked against its source.
- **Precedent.** The case file keeps every verdict, its comment and who decided,
  so whoever rules at the gate can read past verdicts as precedent.

The operator reads memory on a dedicated **Memory** page: search in each of the
modes of section 7, filters by participant, line and date, the trimmed and full
views of a record, the note form, and the export. It is its own page rather than a
section of the Archive page because its searches and controls are its own; the two
pages link to each other by record and archive.

The export is the interface for other parties: `GET /api/memory/export` streams
every record as JSON Lines, one full record per line, with the same filters as the
search (participant, line, since) so an external system can pull incrementally by
date. Superseded records and returned or dropped notes are included with their
status: the export is the labeled set, and those labels are part of it. The hub
curates nothing: what is done with the raw memory happens outside it.

## 7. Similarity: full text first, vectors behind the same door

Recall's question is natural language, and "a similar situation" means semantic
similarity, which needs embeddings. The design adds them without changing the
API or the tool:

- **Storage.** pgvector, a Postgres extension, so vectors live in the same
  transaction domain as everything else (the reason Postgres was chosen over a
  dedicated graph or vector store). Changes: the compose image moves from
  `postgres:17-alpine` to the pgvector image, a migration creates the extension
  and adds an `embedding` column, and each record stores `embedding_model`. The
  column has no fixed dimension (the encoder decides it), and every vector search
  filters on the current model name, so a model change is a re-embed, never a
  schema change; the stored model name is what makes that safe. There is no vector
  index: a sequential scan is fast at the table sizes a team produces.
- **What is encoded.** One vector per record, computed from the ask, the
  resolution and the verdict comments (untrimmed), because that is the text a
  future question resembles. Notes are encoded from their body.
- **When.** By a background sweep, never in the write transaction: a record is
  stored with a null embedding and the sweep (every `COURTYARD_EMBED_SWEEP_SECONDS`,
  or `POST /api/memory/embed` at once) fills it, the same shape as the liveness
  sweep, tolerant of the encoder being down. First enablement and model changes are
  that same sweep over every record. A question is embedded at recall time with a
  timeout of seconds, not the sweep's minute, and falls back to full text.
- **The encoder.** An `Encoder` interface with a `none` default. With no encoder
  configured, recall is full-text only; the hub's ready line and the Memory page
  say so (the tool's listing does not name its mode). The implementation is an
  HTTP encoder for any OpenAI-compatible embeddings endpoint; Ollama with
  `nomic-embed-text` is the documented default. The endpoint is on localhost unless
  the operator opts in to a remote one with an explicit setting, because a remote
  encoder sends message bodies off the machine and the README promises nothing
  does by default. The opt-in has a precedent: the non-local bind flag. A fake
  encoder serves the tests.
- **Retrieval.** Modes `exact` (Postgres full-text, `websearch_to_tsquery`),
  `vector`, and `hybrid` (both, merged by reciprocal rank fusion). The tool never
  exposes the mode: it uses hybrid when embeddings exist and full-text otherwise.
  The API exposes it for other consumers and for testing. Filters by participant,
  line and date are SQL `WHERE` clauses applied before ranking in every mode (a
  there is no domain filter: domains rank, they do not filter). Results are
  records, never scores alone, so adding vectors changes what comes first, not
  what a result is. A question that holds no searchable lexeme (stop words,
  punctuation) is answered as such, never as "nothing settled".

## 8. Governance

Shared memory fails in ways private memory does not: staleness, conflicts, noise
crowding out signal, and poisoning, where one agent's bad note steers every other
agent. Each rule below answers one of those.

- **Provenance on every record.** Thread, line, participants, dates, and the
  verdicts with who decided. Nothing enters memory without an event behind it.
  Notes carry their author.
- **Supersession, not deletion.** A later decision that reverses an earlier one
  marks the earlier record `superseded_by`. Only the operator supersedes; an agent's
  new note never supersedes anything on its own. Every read honours the column (a
  superseded record is not recalled); nothing is silently rewritten. The WebUI has
  no control for it; the close date carried by every recalled record is what lets
  an agent weigh an older answer against a newer one.
- **The gate applies to writes.** An agent's note is visible on the WebUI the
  moment it is written. A note on a supervised line, and every team-wide note,
  waits for the operator like a message: approve, return with a comment, or drop.
  The team-wide brake (`communication-protocols.md` section 7.4) therefore holds
  notes together with the messages. A line-scoped note on an auto-pass line flows
  like an auto-pass message and is still logged. This is the defense against
  poisoning, and it is the same dial the operator already knows. Case files
  themselves need no gate: every message in them already passed it.
- **Visibility follows discovery and scope.** Under `auto`, every agent recalls
  from the whole team's case files. Under `manual`, an agent recalls from the
  lines it is party to. Notes add their own scope on top: a line-scoped note is
  seen by that line's two agents, a team-wide note by everyone. The operator sees
  everything. Segregation of duties, applied to memory. Visibility is keyed on the
  agent's id, and a removed name registered again keeps its id (D36): the revived
  agent inherits the case files and line notes of its previous life. Accepted: the
  name is the identity the team knows, and the record of what that name was told and
  ruled on is exactly what a re-registered specialist should find again.
- **Retention is explicit.** A case file lives until the archive it was built from
  is deleted. Deleting an archive deletes what was distilled from it: the archive is
  the single source, memory is derived. An archive is one stretch of one line's
  history (an operator archive keeps the line, so a later archive of the same line
  follows), and the case files that go with it are those of that line whose thread
  closed inside the archive's stretch, from its first message to its last. The
  Archive page's delete confirmation names how many case files go with it. A
  deleted case file that had superseded another leaves that record in place,
  unsuperseded. Notes are not tied to an archive and are kept; there is no delete
  for them.
- **Recall is bounded and visible.** A recall result enters an agent's context.
  The tool returns at most five trimmed records (an Admin setting), each capped in
  length (a second setting), and the Admin page's envelope preview shows a recall
  payload the way it shows the envelope, so the token cost stays measured.

## 9. Relations to other designs

- **Threads** (`threads.md`, D34): the closed thread is the unit, the close is
  the write moment, and a case file carries the link to the thread it served.
- **Communication protocols** (`communication-protocols.md`): memory adds no rule
  to how messages move. Recall and notes are tool calls; notes pass the gate.
- **Archive** (`architecture-v1.md` section 5.7, D20): the archive stays the raw,
  immutable record per line; memory is derived from it and deleted with it.
- **The envelope** (`architecture-v1.md` section 7.5): memory adds nothing to it;
  both delivery paths are tool calls.
- **Discovery** (`architecture-v1.md` section 5.8, D22): visibility of memory
  follows the same setting.
- **Team charter** (`team-charter.md`, D33): whether notes are allowed, who may
  write them, and the recall limit are rules of engagement; the mechanism is
  defined here.

## Appendix: further reading

Reference only; none of these is a dependency of the design.

- Claude Code documentation, agent teams: the limitations section (no shared
  memory, no history carry-over, one team per session).
  <https://code.claude.com/docs/en/agent-teams>
- A practitioner's account of agent teams cost and coordination.
  <https://alexop.dev/posts/from-tasks-to-swarms-agent-teams-in-claude-code/>
- Memory in LLM-based multi-agent systems: mechanisms, challenges, collective
  intelligence (TechRxiv).
  <https://www.techrxiv.org/users/1007269/articles/1367390-memory-in-llm-based-multi-agent-systems-mechanisms-challenges-and-collective-intelligence>
- Managing procedural memory in LLM agents: control, adaptation, evaluation
  (the episodic versus procedural split; Reflexion-style verbal lessons).
  <https://arxiv.org/html/2606.23127v1>
- From storage to experience: a survey of LLM agent memory mechanisms.
  <https://arxiv.org/pdf/2605.06716>
- Always-on agents: persistent memory, state and governance in LLM agents.
  <https://arxiv.org/pdf/2606.30306>
- AI Knowledge Assist: automated knowledge bases from conversation transcripts
  (the QA-pair clustering pattern behind section 6).
  <https://arxiv.org/html/2510.08149>
- Why multi-agent systems need memory engineering (MongoDB engineering blog).
  <https://www.mongodb.com/company/blog/technical/why-multi-agent-systems-need-memory-engineering>
- Designing multi-agent memory systems for production (mem0).
  <https://mem0.ai/blog/multi-agent-memory-systems>
- pgvector. <https://github.com/pgvector/pgvector>
