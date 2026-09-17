# Threads: the quant of conversation

## 1. Why threads exist

A line lives as long as its pair of participants and is unbounded; a message and
its turn are too fine to carry a task. A thread is the tier between them: the
unit that an ask opens, a budget bounds, an acceptance closes, the end of a shift
expires, and the team's memory records.

## 2. What a thread means

A thread means one bounded exchange about one ask: it starts with an
independent question or request, and it ends when its initiator accepts the
answer, or when someone other than its participants ends it. Every message
belongs to exactly one thread. A conversation on a line consists of threads, one
after another.

The initiator of most threads is an agent acting on a request its user typed in
its terminal (`communication-protocols.md` section 2.2). One such request can
cause several threads: the agent asks a helper, and the helper asks a further
agent to be able to answer. Threads are serial on one line and run in parallel
across lines.

Vocabulary is kept rigid: **line** owns the outer tier (the standing pairing),
**thread** owns the quant. Neither word is ever used for the other tier, in
docs, schema or telemetry. (Some ecosystems use "thread" for the outer
container; here it never leaks upward.)

## 3. Thread features

**One open thread per line.** A new independent ask begins only when the
previous thread has ended. Reason: courtyard agents change infrastructure, and
parallel threads on one line would need proof that the two exchanges do not
touch the same piece of infrastructure. Turn-taking stays a per-line rule; the
thread adds lifecycle and bookkeeping on top of it.

**The sender declares; the hub never infers.** The sender knows its own intent,
and reading intent out of message text is guesswork the hub avoids everywhere.
A sender can declare two things, both as parameters of `courtyard_send`.

- **`new_thread`: this message starts a new independent ask.** A message on a
  line with no open thread opens one whether declared or not; any other message
  continues the open thread. The declaration has one job: a declared new ask
  while a thread is still open is refused, the way a turn violation is, instead
  of being filed silently into the open thread.
- **`serves`: the thread this ask serves.** Optional. Its value is the name of
  the participant whose open thread with the sender the ask serves. A line holds
  one open thread, so a name identifies it, and the model never handles an id.
  Example: lab-manager asks inventory-agent for an address list;
  inventory-agent needs a fact from a third agent to answer, and sends to it
  with `serves: "lab-manager"`. When the sender has no open thread with the named
  participant the send is refused: a declaration is never dropped silently, and
  the hub never guesses which thread was meant.

**Served threads form a tree.** The link belongs to the thread the ask opens; a
message that continues an open thread leaves it as it is.

- A tree starts at a thread that serves nothing: an agent's ask on behalf of its
  user, or an ask from the operator. A user's request never reaches the hub, so
  an agent that asks two helpers for one request starts two trees, and the hub
  cannot join them.
- The link is used three ways. When the answer arrives, the hub tells the asker
  whom the result is for, or that the served thread has ended
  (`communication-protocols.md` section 6.3). On the WebUI a thread's divider
  names the thread it serves and the threads serving it, each a jump to that
  line. A case file names the thread its thread served (`hub-memory.md`).
- Ending a thread ends no other thread: threads serving it stay open. A tree
  carries no budget of its own; every thread has its budget, and the turn rule
  refuses an ask that comes back around to a line that is already waiting. The
  operator's team-wide brake is the control for a tree that grows the wrong way.

**Close is a bare tool call.** `courtyard_close_thread` takes the peer's name
and nothing else: no message and no note. An acceptance often carries no
content, so the close costs no message, and the hub gets a deterministic
protocol event instead of parsing text. There is no note field because an
initiator with something left to say has the whole message channel until it
closes (send, then close), because lessons worth keeping belong to the team's
memory, and because an optional text field invites the closing pleasantries the
tool call removes. Only the initiator closes. The peer learns of the close from a
fixed line rendered by the hub, "thread closed by X". A close resolves the
line's reply obligation, so a closed thread never leaves a line waiting.

**Threads with the operator carry no budget.** The operator's lines are never
gated, and the budget never locks a thread the operator takes part in: a human
in the exchange is its natural stopper. One open thread per line still applies
and costs the operator nothing: a send on a line with no open thread opens one,
so the operator declares nothing, and starting a new ask is close, then send.

**Only a message from the operator keeps a thread open on the operator's
line.** A message an agent sends to the operator on its own initiative awaits no
reply, and the thread it opens ends at once, as `closed`: a report is a whole
exchange. The send result tells the agent that the message was received, that no
answer is to be expected, and that the operator will write if needed. When the
operator writes, that message opens a thread of the operator's own, which awaits
the agent's answer and which the operator closes. An agent's message inside a
thread the operator opened (its answer, or a later addition) stays in that
thread. Reason: the operator reads reports and rarely answers them on the board;
a thread waiting for that answer could be closed by nobody, and every later
report would land in it.

**The operator closes through a control in the conversation pane.** The control
sits in the pane header and invokes the same hub operation as the agents' close
tool. It shows when the selected line has an open thread the operator opened,
which is every thread that stays open on the operator's lines. It is not a typed
command: the composer carries message text only, parsing "/done" out of it
would be the text inference this design rejects, and every other protocol action
of the operator is a click (verdicts, release, archive).

**Messages older than threads belong to none.** Rebuilding threads from old
messages would mean inferring boundaries from text.

## 4. Lifecycle

| State | Meaning | Moved by |
|---|---|---|
| `open` | an ask is in flight or under clarification | the first message of a new exchange |
| `closed` | the initiator accepted the answer | the initiator; the hub, at once, for an agent's report to the operator |
| `expired` | the shift ended with the thread still open | end shift |
| `locked` | someone other than the participants ended it | the hub, when the budget is spent; the operator, by releasing the line |

`closed` is the healthy ending. `expired` and `locked` delete nothing: history
keeps the thread with its state. `locked` is distinct from both because it
records that an authority other than the participants ended the exchange; that
difference matters when reading history later. A release is such an ending: the
operator abandons the exchange, and leaving its thread open would file every
later message on the line into it.

The participants are told of every ending they did not make: the peer of a
close, both sides of a budget lock, a release and an expiry, each as a hub
notice.

## 5. What the hub enforces

1. **Closure as protocol, not prose.** The initiator closes the thread through
   a real signal; the closing wording of the envelope renders a state instead of
   making a request.
2. **Per-thread budgets.** A thread between two agents holds at most a set
   number of messages (an Admin setting, default 12, 0 for none). A send that
   would grow the thread past it is refused, the thread is locked and both sides
   are told. An answer always passes, so a line never jams on an obligation it
   cannot discharge. Turn-taking is backpressure per message; the budget is
   backpressure per task.
3. **The end of a shift expires open threads**, together with the unanswered
   and gate-held messages on their lines.
4. **Visible boundaries.** The conversation pane groups messages by thread,
   with a divider per thread; the board shows each line's thread count and
   whether one is open.

## 6. Relations to other designs

- **Communication protocols** (`communication-protocols.md`): how messages
  move around threads: the footer that carries the close instruction, the
  owed-reply statement, the send results, turns and the gate.
- **Team charter** (`team-charter.md`): thread policies (budget, who may
  close) are rules of engagement and belong in the charter; the construct
  itself is defined here.
- **Team memory** (`hub-memory.md`): a closed thread is the unit a case file
  records: one ask, its resolution, done.
- **Turn machine** (`architecture-v1.md` §5.4): turn-taking is per line; threads
  sit above it.
