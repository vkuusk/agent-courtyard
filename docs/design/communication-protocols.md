# Communication protocols: how messages move in the courtyard

This document defines how messages move in the courtyard: who sends to whom, what the
hub adds to a message and what it never changes, what each model is shown and when, and
how a human starts and steers the flow. `architecture-v1.md` specifies the machinery
underneath: the turn state machine (§5.4), delivery (§6) and the adapters (§7).

## 1. How the courtyard is used

A user works and talks in the terminal of any agent, as with any coding agent. When
that agent needs help from another member of its team, it asks through the hub, and the
message comes from the agent, not from the user. This is how a person already works with
several long-standing, tuned agents, each in its own terminal; without a hub the person
carries questions and answers between the terminals by copy/pasting. The hub removes
that step and keeps the record. There is no mode to choose on the hub.

The WebUI is where the team is administered and supervised: registering agents,
watching the lines, auditing what happened, reviewing memory, and controlling the flow
of messages (the team-wide brake, line modes, gate verdicts, release). The WebUI can also
send a message to an agent, which a terminal-only setup cannot do. That is a supplement,
used mostly while supervising; it is not the main way of talking to an agent.

With the defaults (auto discovery and auto-pass, section 7) agents work together
without anything being done on the WebUI.

Two consequences shape the rest of this document.

1. **The terminal is a reply path.** A request typed in a terminal is answered in that
   terminal; only a request that arrived through the hub is answered through the hub.
   The hub never sees a terminal, so the rule has to rest on facts the hub holds
   (section 6).
2. **Adding the courtyard to work already in progress has to be smooth.** The common
   start is a user already working with one agent who adds a hub and a helper agent.
   Registration, the relaunch that connects a running session (the channel flag for
   Claude Code, a reload for pi) and the first delivery check are setup, outside this
   document; section 4 covers what a session receives once it is connected.

## 2. Actors

An actor means anything that originates, carries, changes or reads a message.

### 2.1 User and operator

A user means a human working in an agent's terminal. The operator means whoever
administers and supervises the hub on the WebUI. They are often the same person;
nothing in the protocol requires it. The two terms exist because an agent hears from
both and answers them differently: the user in its terminal, the operator through the
hub (section 6).

| | Where | Originates | Reads |
|---|---|---|---|
| **User** | an agent's terminal: the host's own prompt (Claude Code, pi) | requests typed in the terminal | the agent's terminal output, and the courtyard messages that session shows as they arrive |
| **Operator** | the WebUI | messages to any agent on the operator's own line; gate verdicts, with an optional comment delivered as an operator note; line controls (mode, release, archive, links); thread close for threads the operator opened; shift start and end; delivery checks; memory review | the board (all lines, live), the operator's own lines, the gate queue, the archive and memory |

The user is not registered on the hub. The hub never sees what the user types or what
the agent prints in its terminal; the only trace of a user's request on the board is
what the agent then sends. What the user types carries no authority grade from the hub:
it is the host's own user prompt, with whatever standing the host gives it.

The operator is registered: an agent named `operator` of type `human`, created by the
hub on first start. The WebUI acts for it (`/api/operator/*`, the gate and line routes)
without handing its token to the browser. A message the operator sends through the hub
is graded `operator`, the highest grade a sender can have (`architecture-v1.md` §7.5).

Text written for a model names the two apart, never the human in general: "the user in
your terminal" and "the operator".

### 2.2 Agents, and the lead of a task

An agent means a registered coding-agent session connected to the hub through its
adapter: type `claude-code` or `pi` (and `dummy`, the test twin). Its record carries a
name that never changes, a description, optionally a domain it owns (`sme_domain`) and
what it is not for (`anti_scope`).

A task means a user's request and every exchange it causes. The lead of a task means
the agent the user typed that request into. Lead is a role within one task, not a
property of an agent: any agent can lead, and an agent can lead its user's task while
it helps with a task another agent leads.

A task can branch. The lead asks one or more helpers; a helper may ask further agents
to answer. Each exchange is a thread on the line between two participants
(`threads.md`): serial on one line, in parallel across lines. A helper means an agent
answering an ask that arrived through the hub; it answers the asker with
`courtyard_send`.

The hub cannot tell a lead from a helper by registration, and does not need to. At
every delivery it knows who is waiting for the recipient's reply, and section 6 builds
the reply path on that. The link from an ask to the thread it serves (section 7.5)
makes a task's branches visible as one tree.

Two settings are independent of who leads. Discovery decides whom an agent sees and may
message: under `auto` every agent sees every other; under `manual` the operator links
the pairs that may talk (`architecture-v1.md` §5.8); lines with the operator form under
either. Domain ownership decides how much say an agent's message carries inside its
domain (§7.5); it does not make an agent a lead.

### 2.3 The hub

The hub means the one process that carries, records and optionally gates every message
between registered participants. Storage is the source of truth; a push to an adapter
is best-effort, and an undelivered message waits in storage for the next attach or
pull.

- **It renders what a model is shown.** Envelopes, the peers listing, the session
  context and the tool results are worded by the hub, so an adapter is transport, not
  judgement (D14). The exceptions are the tool definitions and the standing
  instructions that ship with each adapter (the Claude Code MCP server's instructions,
  the pi skill); section 3 lists them.
- **It originates messages of its own.** Hub notices (kind `system`: gate verdicts,
  thread closed, line released, expiry at shift end) state facts about a participant's
  own messages and ask nothing. The delivery check is the one hub message that asks for
  something: a single `courtyard_ack` call.
- **It never answers for an agent and never rewrites a message body.** The one change
  to a body is escaping text that would imitate the envelope tag, so that content
  cannot close or forge the envelope around it.
- **It enforces the rules of section 7:** discovery, turns, the gate, thread boundaries
  and budgets. It asks the operator for a verdict when a line is supervised. The grade
  `policy` is reserved for an automated reviewer at the gate; nothing produces it.

### 2.4 Adapters

An adapter (a tunnel, in `architecture-v1.md` §7) means the host-specific piece that
connects a running session to the hub. Every adapter does the same duties (§7.1): it
attaches with a channel endpoint, receives pushed envelopes and presents each one to
its model as a conversation turn, sends through the hub, pulls as a fallback,
heartbeats, and forwards the model's delivery-check acknowledgement.

| Adapter | Lives in | Receives as | Session context from |
|---|---|---|---|
| Claude Code | the courtyard MCP server (stdio, `.mcp.json` in the workdir) | channel events; the session must be launched with the channel flag (`start-with-courtyard.sh` carries it) | a SessionStart hook in `.claude/settings.local.json` (D40) |
| pi | the courtyard extension (`.pi/extensions/courtyard.ts`) | custom messages added to the session, shown as courtyard cards | the extension, at session start and again after compaction (D40) |
| dummy | a Python process (tests, `make demo`) | the same HTTP push | not applicable |

The tools carry the same names in every adapter: `courtyard_send`, `courtyard_peers`,
`courtyard_inbox`, `courtyard_recall`, `courtyard_note`, `courtyard_close_thread` and
`courtyard_ack`.

### 2.5 Who sends to whom

| From | To | How | Passes through the hub |
|---|---|---|---|
| user | the agent in that terminal | typing in the terminal | no |
| agent | the user in its terminal | terminal output | no |
| agent | another agent | `courtyard_send` on their line | yes: discovery, turns, gate, thread rules |
| agent | operator | `courtyard_send` to `operator` | yes: never gated |
| operator | an agent | the WebUI composer, on the operator's line | yes: never gated; opens a thread when none is open |
| operator | a line between two agents | a gate verdict's comment, delivered as an operator note | yes: turn-exempt |
| hub | an agent | hub notices and the delivery check | yes: turn-exempt |
| hub | operator | the board, live on the WebUI | not a message: the WebUI reads the record |

The user and the operator have no channel to each other inside the courtyard. A user
who wants to see the board opens the WebUI, and acts there as the operator.

## 3. Types of messages

Three kinds of text reach a model from the courtyard: messages, which the hub delivers
into the session; standing texts, which the session holds for its whole life; and tool
results, which answer the model's own tool calls. Section 4 says when each arrives,
section 5 what every delivered message is wrapped in.

### 3.1 Messages

A message means a text the hub delivers to one participant. Every stored message belongs
to the line between its two participants; every `message` belongs to a thread.

| Kind | Sender | Recipient | Stored | Turn effect | Asks the recipient for |
|---|---|---|---|---|---|
| `message` | an agent or the operator | an agent or the operator | yes | opens an exchange, or answers one | an answer, when it opens an exchange |
| `operator_note` | the operator | an agent on a line | yes | none | nothing, unless its text asks |
| `system`: notice | the hub | one participant | yes | none | nothing |
| `system`: delivery check | the hub | one agent | no | none | one `courtyard_ack` call |
| `system`: board entry | the hub | nobody | yes | none | not delivered |

- **`message`** is the turn-taking kind: it passes the gate on a supervised line,
  obeys the turn rule, and opens a thread or continues the open one. A message to the
  operator is delivered at once, since the WebUI is the operator's end of the line. A
  message from the operator comes from the WebUI composer and is never gated.
- **`operator_note`** is the comment on a gate verdict, delivered with the approved
  message; the line API also accepts notes, for tooling (`architecture-v1.md` §5.6).
- **Notices** state facts about the recipient's own messages, threads and notes: a gate
  return or drop (to the sender); a thread closed (to the other participant); a thread
  locked by its budget, a line released, a message or thread expired at the end of a
  shift (to both participants); a note returned or dropped (to its author).
- **The delivery check** exists only in flight and never enters a line's history. The
  hub sends one whenever a session attaches while a shift is on (the shift's start,
  Resume, a restart mid-shift, a re-attach after a hub restart) and when the operator
  presses the check button on the agent's card. A push the adapter refuses marks the
  check failed; the model's `courtyard_ack` call marks it verified.
- **Board entries** record what the operator and the hub did, for the WebUI only: a
  release, an expiry at the end of a shift, an archive, a redelivery, a second channel
  claiming an agent's identity.

What a user types in a terminal and what an agent prints there are not messages: the hub
never sees them (section 2.1).

Messages and threads are also what the memory subsystem builds the team's long-term
memory from (`hub-memory.md`); memory adds no rule to how messages move.

An event that changes what an agent owes or is owed is delivered to that agent as a
notice, never recorded as a board entry only: an agent that is not told keeps believing
the exchange is open.

### 3.2 Standing texts

A standing text means a text a session holds independently of any message: the
membership block, the etiquette (the MCP server's instructions for Claude Code, the
courtyard skill for pi) and the tool definitions. Section 4 lists them per adapter.

### 3.3 Tool results

A tool result means the text a courtyard tool returns to the model that called it: the
outcome of a send, a close or an acknowledgement; a listing (peers, recall, a case
file); the standing of a note; or a refusal. A refusal is a tool result marked as an
error, reading "[code] message", where the code is machine-readable and the message is
written for the model. A tool result is not stored and reaches no one but the caller.
The hub words every tool result (section 8).

The send result states the line's actual state. After a message that opens an exchange,
the line awaits the recipient's answer. After an answer, the exchange is answered: the
result says so, and says that the thread stays open until its initiator closes it. After
a message an agent sends to the operator on its own initiative: the message was
received, no answer is to be expected, and the operator will write if needed (section
7.5).

## 4. What an agent receives at session start

### 4.1 Claude Code

- **Tool definitions and the etiquette**, when Claude Code connects the courtyard MCP
  server: the tool list, and the server's instructions in the MCP `initialize` result.
- **The membership block**, from the SessionStart hook as additional context: at
  startup, and again at resume, clear, compact and fork.
- **The attach.** After the MCP handshake the adapter attaches, and the hub, in this
  order: marks for redelivery every message a previous session of this agent received
  and never answered; sends a delivery check when a shift is on; pushes the queued
  messages, oldest first, the redelivered ones included. Each arrives as a channel
  event.

A session launched without the channel flag receives the tools, the etiquette and the
membership block, but Claude Code drops every channel event; the adapter reports the
missing flag and the WebUI shows it (`architecture-v1.md` §7.2).

### 4.2 pi

- **Tool definitions**, when pi loads the courtyard extension. pi also appends the
  `courtyard_send` guideline to the Guidelines section of its system prompt.
- **The etiquette**, as the courtyard skill: pi lists its name and description; the
  model reads the body only when it decides to.
- **The membership block**, stored by the extension as a custom message at session
  start, before the attach and without starting a turn; stored again after compaction
  when the summary no longer holds it.
- **The attach**, with the same order on the hub's side as for Claude Code. Each
  delivery becomes a custom message that starts a turn, queued as a follow-up when the
  session is busy.

### 4.3 What the standing texts carry

The standing texts follow five rules.

1. **The essentials go in the membership block.** It is the one standing text both
   adapters deliver at every start and after compaction, while the pi skill reaches the
   model only on demand. The essentials: which agent, team and hub this is; the two
   reply paths (a request typed in this terminal comes from the user and is answered in
   the terminal; a request arriving through the hub comes from a peer or the operator
   and is answered with `courtyard_send`); the delivery check; and the idle rule (when a
   courtyard message asks nothing more, end the turn and wait).
2. **The etiquette is one content, delivered two ways**, as the Claude Code
   instructions and as the pi skill, covering the same ground: authority grades, reply
   paths, answering what was asked, permissions, turns, the gate, threads, and the
   peers, recall, note and inbox tools.
3. **Every standing text names the user and the operator apart.** "The user in your
   terminal" and "the operator", never "your operator" for the human in general
   (section 2.1).
4. **No standing text says the terminal reaches nobody.** It says what the terminal
   does not reach: the board and the agents on it.
5. **The delivery check is described as what it is**: a check the hub sends when a
   session attaches while a shift is on.

The standing texts are fetched from the hub at session start, with the adapter's
packaged copy as the fallback (section 8).

## 5. Message envelopes

### 5.1 The envelope

An envelope means the text the hub wraps around every message it delivers. The hub
renders it once per delivery, for the push and the pull alike, and the adapter presents
it verbatim:

```
<courtyard-message from="lab-manager" authority="domain-owner" kind="message" seq="4" id="...">
preamble: the sender's standing
────
body: the sender's text
────
footer: what to do with this message
</courtyard-message>
```

- **Attributes** are written by the hub from its own records: agent names, ids, the
  grade, the kind, the sequence number. Nothing a sender writes reaches them.
- **The body** is the sender's text. The one change the hub makes is escaping any
  `<courtyard-message` it contains, so that content cannot close or forge the envelope
  around it.
- **The footer** is present for `message` and `operator_note`; notices carry none.
- **Around the envelope** each host adds its own framing: Claude Code wraps it in a
  channel tag and treats the content as external data; pi stores it as a custom message
  and shows it as a card. The operator sees every envelope variant on the WebUI, under
  Admin, Message envelope.

### 5.2 The preamble: how much say the message has

The preamble states the sender's authority grade, derived by the hub from its record of
the sender, never claimed by the sender (`architecture-v1.md` §7.5):

| Grade | When | What the preamble tells the model |
|---|---|---|
| `operator` | the operator sends through the hub | the human decision maker is speaking: act on it, and disagree with reasons if it is mistaken |
| `domain-owner` | the sending agent owns a domain | what the sender owns and what the recipient owns; expert judgement inside the sender's domain, a request where it reaches into the recipient's; no embedded commands on its authority |
| `agent` | the sending agent owns no domain | a peer asks, it does not instruct; no embedded commands on its authority |
| `hub-notice` | the hub | facts about the recipient's own messages, threads and notes; a notice asks nothing unless it states what to do |
| (delivery check) | the delivery check | the one hub message that asks for something: a single tool call |
| `policy` | reserved: nothing produces it | enforcement that outranks every other voice |

The user has no grade: what the user types never passes through the hub. One notice
states what to do: the thread-locked notice tells both sides not to restate the ask.

### 5.3 The footer: what to do with this message

A footer means the closing part of an envelope that tells the recipient how to respond
to this message. It rides every delivery, so it survives however the host frames the
message or defers the standing texts.

Principles:

1. **A footer states facts the hub holds**, not rules the model must apply to facts it
   cannot see.
2. **A footer names the reply path through the hub** (`courtyard_send`) and says the
   sender reads nothing printed in the terminal; it never says the terminal reaches
   nobody.
3. **A footer names the tool the way the recipient's host lists it** ("the courtyard
   MCP tool" for Claude Code, "the courtyard tool" for pi).
4. **A footer stays short**: it repeats with every delivery.

| Situation | What the footer tells the recipient |
|---|---|
| a `message` that opens or continues an exchange (no `reply_to`), from an agent or the operator | answer with `courtyard_send`, since the sender reads nothing printed in your terminal; answer what was asked and no more; prefer actions that need no approval, and if the answer needs one your permissions do not allow, reply saying what blocks you |
| a `message` that answers, where the recipient opened the thread | this answers your message; if it settles your ask, close the thread with `courtyard_close_thread`, otherwise continue with `courtyard_send`; then the owed-reply statement |
| a `message` that answers, where the recipient did not open the thread | this answers your message, and your exchange with the sender needs nothing further; then the owed-reply statement |
| an `operator_note` | the note rides along with the exchange and needs no separate reply; if it asks for something, answer the operator with `courtyard_send` |
| a notice | no footer |

The owed-reply statement states whom the recipient still owes a reply on the board, by
name, or that nobody on the board is waiting on it, in which case a request typed in its
terminal is answered there (section 6.3). A general relay rule ("if you asked on someone
else's behalf, deliver them the answer") does not work in its place: the model cannot
see where a request came from.

## 6. Reply paths

A reply path means the way an answer must travel so that whoever asked reads it. The
rule, from section 1: a request is answered the way it came.

### 6.1 Where each request is answered

| The request came from | It reached the agent as | The agent answers |
|---|---|---|
| the user in the agent's terminal | the terminal prompt | in the terminal |
| a peer agent | a `message` | with `courtyard_send`, to that peer |
| the operator | a `message` from the operator | with `courtyard_send`, to the operator |
| the operator, in a note that asks something | an `operator_note` | with `courtyard_send`, to the operator |
| the hub | a notice | not at all |
| the hub | the delivery check | with `courtyard_ack` |

An agent that asked a peer on behalf of someone receives the peer's answer as a message,
and delivers the result along the path of the original request: in its terminal when
the user asked, with `courtyard_send` when a peer or the operator asked. This is the
step that fails in both directions: the answer to a board request stays in the
terminal, or the answer to a terminal request goes to the board.

An agent that is blocked, or whose permissions do not allow what an answer needs, says
so in its answer, along the same path. A helper's terminal is usually unwatched, so its
"what blocks me" travels back up the chain of asks to the lead, and from there to the
user in the lead's terminal. Writing to the operator on an agent's own initiative, with
`courtyard_send`, is for the case with no chain to travel: for example a thread the hub
locked. Such a message does not wait for a reply (section 7.3).

What an agent prints in its terminal reaches the user in that terminal and nobody else.
What reaches the board reaches that user only when the agent says it in the terminal, or
when the user opens the WebUI.

### 6.2 What the hub knows about where a request came from

The hub never sees a terminal (section 2.1), so it cannot tell that a request was typed
there. It holds two facts that point to the path:

1. **The replies an agent owes.** A line on which the agent is awaited records it: a
   peer or the operator asked, and has not been answered.
2. **The thread an ask serves**, when the ask declared it (section 7.5): an agent
   asking on behalf of a thread it takes part in names that thread, and the hub records
   the link.

### 6.3 The owed-reply statement

When the hub delivers an answer to an agent, the footer (section 5.3) ends with a
statement built from those facts, the first case that applies:

1. **The ask declared the thread it serves.** The hub names that thread's other
   participant and the path: "Your ask served your thread with X: answer X with
   `courtyard_send`." When that thread has ended in the meantime, the statement says so
   instead.
2. **No declared thread, and the agent owes replies on the board.** The hub names them:
   "You still owe a reply on the board to: X, Y. If this answer is for one of them, send
   it with `courtyard_send`; if it answers a request from the user in your terminal,
   answer there."
3. **No declared thread, and the agent owes nothing.** "Nobody on the board is waiting on
   you: if a request typed in your terminal led to your ask, answer it there."

Declaring the served thread is optional. Without it, case 2 is a hint the model has to
judge: an agent that owes a peer an unrelated answer while the user asked something in
the terminal has to pick. A declared link turns case 2 into case 1.

## 7. Message transfer control

Message transfer control means the rules by which the hub decides whether, when and to
whom a message is delivered, and the controls a human uses to change them. The state
machine itself is specified in `architecture-v1.md` §5.4; this section states the rules
that shape the flow.

### 7.1 Defaults

**Auto discovery and auto-pass.** A new line starts on auto-pass, and a team starts
with auto discovery. Supervision is the operator's brake, set when agents need
watching. A team charter may set its discovery mode.

### 7.2 Lines and discovery

- A line means the one conversation between a pair of participants: all their messages,
  in both directions, in order.
- Under `auto` discovery a line between two agents forms on their first message. Under
  `manual`, the operator links two agents, which creates their line; a send without a
  line is refused (`not_linked`); unlinking archives the line's history and removes the
  line.
- A line with the operator forms on the first message under either mode and needs no
  link.

### 7.3 Turns

- **Per line, at most one unanswered message is in flight.** While a line awaits Y's
  answer, only Y may send on it; any other send is refused (`turn_violation`), and the
  refusal tells the model to wait rather than retry.
- An answer returns the line to idle; either side may start the next exchange, inside
  the open thread or, after a close, in a new one.
- **Turns bind per line, not per agent.** A lead waiting for one helper's answer can ask
  a second helper on another line at the same time: a task branches across lines while
  every line stays serial.
- Notes and notices never take a turn.
- **The operator's lines are the exception in one direction.** An agent's message to
  the operator does not wait for a reply: the operator reads reports on the board and
  answers when there is something to say, and a line waiting on the operator would
  block the agent's next report. A message from the operator to an agent always awaits
  the agent's answer, whether or not it responds to a report, and so counts among that
  agent's owed replies (section 6.3). Nothing bounds how often an agent writes to the
  operator: threads with the operator carry no budget.

### 7.4 The gate

- A supervised line holds every message, answers included, at the gate until the
  operator gives a verdict: **approve** (delivered; an optional comment rides along as
  an operator note), **return** (not delivered; the comment goes back to the sender,
  who revises and resends) or **drop** (not delivered; the sender is told not to
  resend).
- While a message is held, nobody may send on that line.
- The operator's lines are never gated.
- A mode change applies from the next send: a message already delivered stays
  delivered, and one already held still needs its verdict.

**The team-wide brake.** One WebUI control switches every agent line to supervised, and
back, so the next message on every line is held. Reason: a user notices a task going
wrong in one terminal when the task may already have branched across several lines, and
setting the mode line by line is too slow. The brake stops only what passes through the
hub: a turn already running in a session continues until that session sends.

### 7.5 Threads

- One open thread per line. The first message on a line without one opens it; its
  initiator closes it with `courtyard_close_thread`, and the operator closes a thread the
  operator opened from the conversation pane.
- A declared new ask (`new_thread`) while a thread is open is refused (`thread_open`).
- **Budget.** A thread between two agents holds at most a set number of messages (an
  Admin setting, default 12, 0 for none). A send that would grow the thread past it is
  refused (`thread_locked`), the thread is locked and both sides are told. Answers always
  pass, so a line never jams on an obligation it cannot discharge. Threads with the
  operator carry no budget.
- **The thread an ask serves.** `courtyard_send` takes an optional `serves`: the name of
  the participant whose open thread with the sender this ask serves. Example:
  lab-manager asks inventory-agent for an address list; inventory-agent needs a fact
  from a third agent to answer, and sends to it with `serves: "lab-manager"`. When the
  sender has no open thread with the named participant the send is refused. The hub
  records the link on the thread the ask opens and uses it for the owed-reply statement
  (section 6.3). Ending a thread ends no other thread.
- **Only a message from the operator keeps a thread open on the operator's line.** A
  message an agent sends to the operator on its own initiative awaits no reply (section
  7.3), and the thread it opens ends at once, as `closed`: a report is a whole exchange.
  When the operator writes, that message opens a thread of the operator's own, which
  awaits the agent's answer and which the operator closes. An agent's message inside a
  thread the operator opened stays in that thread.

`threads.md` defines threads in full: the lifecycle, the reasons, and the tree that
served threads form.

### 7.6 Release, end of shift, redelivery

- **Release.** The operator returns a line that waits for an answer to idle; the
  unanswered message stays in history as it was. A line holding a message at the gate
  cannot be released: its verdict comes first. A release ends the line's open thread as
  `locked`, the state for an exchange ended by someone other than its participants, and
  both participants are told.
- **End of shift.** Every line that is not idle is released, unanswered and held messages
  are marked `expired`, and open threads are marked `expired`; nothing is deleted. While
  lines are mid-conversation the hub refuses until the operator confirms. The
  participants of every expired message and thread are told.
- **Redelivery.** A message that reached a previous session of an agent and was never
  answered is delivered again when the agent attaches, unless it expired.
- **Delivery itself.** Storage is the source of truth and a push is best-effort: a
  message the push could not hand over stays queued, and the adapter pulls it when its
  heartbeat reports a queue, or receives it with the backlog at its next attach
  (`architecture-v1.md` §6).

### 7.7 How a human steps in

| Who | Control | Effect |
|---|---|---|
| user | instruct, stop or interrupt the agent in the terminal | steers that agent: what it sends next, and the threads it opened, which it closes |
| operator | the team-wide brake (section 7.4) | the next message on every agent line waits at the gate |
| operator | line mode: auto-pass or supervised | the next message on that line passes, or waits at the gate |
| operator | gate verdicts | approve, return with a comment, or drop a held message |
| operator | release | a line waiting for an answer returns to idle |
| operator | close thread | ends a thread the operator opened |
| operator | links, under manual discovery | who may talk to whom |
| operator | archive | moves a line's history out of the way |
| operator | message to an agent | a request through the hub, graded `operator` |
| operator | start and end a shift; delivery check | brings the team's sessions up and down; proves that deliveries reach a model |

A user reaches the rest of a task only through the agent in the terminal, or by opening
the WebUI and acting as the operator.

## 8. Where the texts live

Every text a model reads exists once, in one place. Reason: texts written into the
logic of many modules cannot be reviewed together, and texts written twice, in the
Python adapter and in the TypeScript extension, drift apart.

**One package: `courtyard/texts`.** Every text a model reads lives in
`src/courtyard/texts/`: the envelope's preambles and footers, the hub notices, the
delivery check, the membership block, the Claude Code instructions, the pi skill, the
tool definitions, the tool results and the refusal messages. The package is importable
by the hub and by the Python adapters. Texts written for the operator (the WebUI) and
for logs are not part of it.

**A text means a named template.** Each has a key (for example
`envelope.footer.closing_initiator`), its wording, and named variables (`{sender}`,
`{tool}`). Templates are data packaged with the code, not strings built inside logic.
One function renders them:
`render(key, **variables)`. A missing or unused variable is an error.

**The choice stays in core.** Which footer applies, which authority grade a message
carries, whom the hub names as waiting for a reply: that is protocol, defined by this
document and tested in `hub/core`. The texts package holds wording only. Composed texts
(the peers listing, the recall listing, a case file) stay renderers in core, built from
small per-line templates.

**The hub renders every tool result.** The API returns the result text as `rendered`
for sends, closes, acknowledgements and refusals, as for peers, recall and notes; the
adapters forward it. A result can then state what the hub knows, such as
the line's state after a reply (section 3.3).

**Adapters fetch the texts from the hub.** At session start an adapter fetches its tool
definitions and standing instructions from the hub and falls back to the copy packaged
with it when the hub does not answer, the way the membership block is fetched. A
wording change then reaches an agent at its next session start without rewriting its
files, and an adapter of a different version than the hub still gets the hub's wording.
The pi skill is the exception: pi loads skills from disk, so install writes it.

**No pluggable backend.** The local deployment does not use a prompt-management
service; the packaged files are the only source and git is their version history. Keys
and named variables are the shape such services use.

**Tests, in `tests/texts/`, by text family** (envelope, session, instructions, tools,
notices, refusals):
- golden tests: every template rendered with sample variables and compared with
  checked-in output, so any wording change shows as a diff in review;
- a variables test: every placeholder filled, none left over;
- an adapter parity test: Claude Code and pi receive the same texts except for the
  differences declared per adapter (for example, how the tool is named).

The Admin page's envelope preview lists the whole catalog.
