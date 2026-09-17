# Next features

Postponed features, kept as a list without assigning them a version. Each entry
points at the document that records the reasoning. Ideas that are not decided yet
live in `ideas-to-review.md`.

- **Switching the current team.** The hub registers several team charter
  directories and selects one as current; what switching does to a running hub
  (agents, lines, history) is not designed: today selecting a team loads it and
  removes nothing of the team that was current before. See
  `../design/team-charter.md` section 3.
- **Parallel threads on one line.** Threads are serial in v1; concurrency needs
  proof that two exchanges do not touch the same infrastructure. See
  `../design/threads.md` section 3.
- **"Verifiably done" thread close.** The v1 close is initiator-accepted;
  verifiable completion needs typed artifacts (see
  `../design/team-charter.md` section 4).
- **Gate policy per thread.** Supervise thread openings, auto-pass inside one.
- **Always on team mode.** The team runs without shifts; today the option is
  visible but disabled in Admin. See `../design/architecture-v1.md` D23.
- **Remote hub deployment.** Hub on a server, agents local and remote. See
  feedback item 27 in `feedback-items.md`.
- **Delivery without channels: a queue the agent pulls from.** Today the only thing
  that wakes an idle session is the adapter's channel notification, a Claude Code
  research preview whose flag contract has drifted before; `courtyard_inbox` is pull,
  but a model pulls only when it already has a turn. The question is a fallback
  delivery path when channels are unavailable, and with it whether queue handling
  should move to a small pub-sub queue (its own container, or postgres-backed) rather
  than the hub's own tables. A design of its own, touching the delivery model
  (`../design/architecture-v1.md` section 6) and the wake-at-turn-end question. See
  feedback item 32 in `feedback-items.md`.
- **Automatic use of memory by the hub.** The envelope hint: when an incoming ask
  closely matches existing records, the delivery carries their handles only, one
  line such as "the team has discussed this before: cases 41, 57", and the agent
  fetches what it wants through recall. Handles cost a few tokens, but it is a push
  all the same, as is anything else that hands memory to an agent unasked. Waits on
  evidence of how memory is used, gathered from the WebUI and the export. See
  `../design/hub-memory.md` section 5.
- **Memory curation.** The operator's supersede control (the column and the reads
  exist), a note's scope change and deletion. In the first weeks of live use no agent
  wrote a note, and the operator addressed agents through the charter; notes are
  collected but not improved until collected notes show a use. See
  `../design/hub-memory.md` section 8.
- **A model-written digest per case file.** Shorter recall results, at the price of
  an API key, a cost and a heavy subsystem inside the hub. Only if recall proves
  used. See `../design/hub-memory.md` section 3.
- **The judge.** An agent that sits on a supervised line and gives verdicts in the
  operator's place, with the hub's memory as its precedent. Its own design.
- **Memory encoders beyond the HTTP one.** An in-process ONNX encoder (small
  models, no torch) if the extra service proves a burden; a vector index (HNSW)
  once the table reaches tens of thousands of rows.
