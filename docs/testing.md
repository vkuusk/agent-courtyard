# Testing

## How testing works

| Layer | What it is | Run |
|---|---|---|
| Functional tests | `tests/test_*.py`, real postgres, real app, a dedicated `courtyard_test` database | `make check` |
| End to end | a round trip through a live Claude Code session | `make test-comms` |
| Manual procedures | a script in `scripts/runbook/` that prints what the operator would see, plus steps done by hand on the WebUI | this document |

Automated tests assert. The procedures show: the operator reads the real envelope, the
real refusal, the real listing. The standard for writing a procedure is in
[development.md](development.md).

## Running a procedure

Every script registers throwaway agents with unique names, prints numbered checkpoints,
removes what it made and exits 0.

A script marked **own hub** starts a hub on a scratch database and removes both. It needs
only postgres: `make db-up`.

The other scripts talk to a running hub. They read its address from `COURTYARD_HUB_URL`
and default to `http://127.0.0.1:2626`. To keep them away from a hub your team works on,
give them a throwaway one:

```sh
uv run python .claude/skills/courtyard-testing/scripts/scratch_hub.py start --name check
export COURTYARD_HUB_URL=<the printed url>
# ... run procedures ...
uv run python .claude/skills/courtyard-testing/scripts/scratch_hub.py stop --name check
```

Do the manual parts that register agents, select teams or change courtyard-wide settings
on a throwaway hub too: agent names are permanent on a hub.

## Messages

### The envelope and peer discovery

The hub renders the envelope an agent receives; the WebUI reads the raw body;
`courtyard_peers` is ranked and worded by the hub; a body cannot forge an envelope.
Design: architecture §7.5.

```sh
uv run python scripts/runbook/envelope_and_peers.py
```

Expected, four blocks:

1. The envelope: `authority="domain-owner"`, a first line naming what each side owns, the
   expert-judgement preamble, the body between two dividers, then the reply footer naming
   `courtyard_send`.
2. The same message on the board: `body` is the plain text, `rendered : None`.
3. The peers listing: reachable agents first, then by name, each with type, status, what
   it owns and its description.
4. The break-out attempt: the forged tags arrive escaped as `&lt;...`, and the verdict
   line reads `exactly one real closing tag (True), forged operator tag present? False`.

Manual: with an agent on shift, ask it a question without saying how to reply. The answer
arrives on the WebUI, not only in the agent's terminal.

### Tool results worded by the hub

What a courtyard tool returns to a model is written by the hub and forwarded by the
adapter. A refusal reads "The courtyard hub refused: [code] message" in both adapters.
Design: communication-protocols sections 3.3 and 8.

```sh
uv run python scripts/runbook/tool_results.py
```

Expected, six blocks: held at the gate; accepted for a recipient that is not connected; a
refusal as the model reads it; the close; delivered to the operator; an acknowledgement
no check is waiting for. The wording is in `src/courtyard/texts/results.yml`, every
variant in `tests/texts/golden/tool_results_*.txt`.

Manual:

1. Ask a Claude Code agent and a pi agent to message a peer on a supervised line. Both
   terminals show the same "Held at the gate" sentence.
2. Ask one to send again before the answer. The refusal starts with "The courtyard hub
   refused: [turn_violation]" and carries no ids.

### Adapters fetch their texts from the hub

At session start an adapter asks the hub for its tool definitions, instructions and own
texts (`GET /api/agents/{name}/texts`) and falls back to its packaged copy. The pi skill
is a file on disk and changes when the agent is saved (edit, save) or at the hub's
start after an upgrade. Design: communication-protocols section 8.

```sh
uv run python scripts/runbook/adapter_texts.py
```

Expected, four blocks: the Claude Code bundle; the pi bundle, without instructions; the
declared differences and nothing else; the packaged copy with the same wording when no
hub answers.

Manual:

1. Start a pi agent with the hub up: `.courtyard/adapter.log` says
   `tools registered (hub wording)`.
2. Stop the hub, start the session again: `tools registered (packaged wording)`, and the
   tools are still listed.
3. A Claude Code agent started with the hub down still lists the tools (`/mcp`).

### An answer says where its result belongs

The hub cannot see a terminal. It knows on which lines an agent is still awaited, and the
footer of every delivered answer ends with that: whom the recipient still owes a reply on
the board, or that nobody is waiting, so a request typed in its terminal is answered
there. Design: communication-protocols sections 3.3 and 6.3.

```sh
uv run python scripts/runbook/owed_reply.py
```

Expected, three blocks: the footer when the request was typed in the terminal (nobody on
the board is waiting); the same ask from the board (the operator is named); the send
result of the ask and of the answer.

Manual:

1. Two agents on an auto-pass line. Type in one terminal: "ask <the other agent> whether
   it has any CSV files". The agent asks through the hub, closes the thread and answers in
   the terminal. Your line with that agent shows nothing.
2. Ask the same from the WebUI. The agent sends you the answer on the board.
3. Admin, Message envelope: both answer variants show the statement. The membership block
   and the instructions name "the user" and "the operator" apart.
4. A pi agent's card shows the message body and "(ctrl+o shows the full envelope ...)";
   ctrl+o shows the preamble and the footer.
5. Ask an agent to message a peer by a wrong name, such as `inventory` for
   `inventory-agent`. The refusal names the closest agents, and the agent retries without
   a `courtyard_peers` call.

### Message transfer control

A new agent line starts on auto-pass. An agent's own message to the operator awaits no
reply and its thread ends at once. A release ends the open thread as `locked` and tells
both agents. `serves` names the participant whose open thread an ask serves. The brake
switches every agent line to supervised and back. Design: communication-protocols
section 7.

Its hub must be a throwaway one: the script flips the brake.

```sh
uv run python .claude/skills/courtyard-testing/scripts/scratch_hub.py start --name flow
COURTYARD_HUB_URL=<printed url> uv run python scripts/runbook/flow_control.py
uv run python .claude/skills/courtyard-testing/scripts/scratch_hub.py stop --name flow
```

Expected, five blocks: the default and a first message going through; the report's
result, the idle line and the closed thread; the locked thread and both notices after a
release; the served-thread statement and the `no_served_thread` refusal; the brake on, off,
and the settings flag.

Manual:

1. Courtyard page: click **Brake** beside the shift pill. It turns red and reads "Brake
   on", every agent line reads supervised, the next agent message waits at the gate.
   Click again: the lines read auto-pass.
2. Ask an agent to report something to the operator. Its terminal shows "no answer is to
   be expected", and your line gains one closed thread. Write back: your message opens a
   thread of yours, which stays open until you close it.
3. Release a line an agent is waiting on: both agents' sessions show the notice.
4. End the shift with a line mid-conversation: at the next shift both sessions show the
   shift-end notice first.

### The round trip through a live Claude Code session

The whole delivery path with a real session: install, attach, channel push into a live
turn, the `courtyard_send` reply. Run it first when messages stop arriving, and after any
Claude Code update.

```sh
make test-comms
```

It needs a registered claude-code agent with a project directory and spends a few tokens
on a cheap model. Defaults are in `tests/communications/communication-test-config.yml`;
flags on `tests/communications/oper-agent1-oper.py` override them. Never aim it at an
agent a live session uses: the test attaches under that name and takes its channel.

Expected: blocks 0 to 3, `test message status: delivered`, a reply `ACK <nonce>`, then
`PASS`.

On FAIL read three things: the message status (`queued` means the push failed), the
channel verdict in Claude Code's MCP log (`registered` is healthy, `skipped` names the
reason), and the last lines of the agent's terminal.

### The channel flag and the delivery check

Two ways to find a session that cannot hear the hub. The adapter reports whether its
session was launched with the channel flag. The delivery check pushes a token the model
must return with `courtyard_ack`. Design: architecture §6.3, D29, D30.

```sh
uv run python scripts/runbook/delivery_check.py      # own hub
```

Expected, four blocks: the flag report on attach; the check envelope and the ack; the
timeout verdict; the automatic check on a session that begins during a shift.

Manual:

1. With a shift on, start a plain `claude` in an agent's directory. The WebUI raises
   "<agent> cannot hear the hub" with the remedy, and the card foot reads *started without
   the channel* in red.
2. Close it, End shift, Start shift. Each fresh session gets a check: *checking
   delivery...*, then a green **✓** as the model calls `courtyard_ack`.
3. Click the **✓?** chip on a connected agent's card: the same cycle. Hovering the green ✓
   shows when delivery was last verified.
4. Repeat step 1 and click that card's **✓?**. After 60 s the foot reads *delivery check
   failed*. The flag warning outranks it when both apply.
5. A rejected token: make `COURTYARD_TOKEN` in one agent's `.mcp.json` wrong and start its
   session. The hub log shows a 401 on attach every two seconds, the card foot reads
   `token rejected, rewrite the agent's files`, and `GET /api/agents` shows
   `token_rejected_at` on that agent. Write the files again and restart: green, and the
   field is null. Scripted:
   `uv run pytest tests/test_channels_api.py -k rejected tests/test_claude_adapter.py -k attach_failures`.

A check never appears in a line's history or in an archive.

## Agents

### The files registration writes

For a claude-code agent the hub writes `.mcp.json` (merged with an existing one, a backup
kept, the token inline, mode 600), `.claude/settings.local.json` (the courtyard allow
rule, the declared model, a status line, the session-start hook) and
`start-with-courtyard.sh`. Uninstall takes out exactly what install added. Design:
architecture D8, D21, D39, D40.

```sh
uv run python scripts/runbook/install_mcp_json.py
```

Expected, three blocks:

1. Install: `servers now: ['my-linter', 'courtyard']`, `file mode : 0o600`, the backup
   holds the original, and the files notice says what holds the token and that
   `.gitignore` gained those names.
2. Settings: `allow : ['mcp__courtyard']`, `model : sonnet`, the status line, the
   `SessionStart` hook, and the context the hook prints. Against a dead hub URL it still
   answers: `fallback (hub down) : True`.
3. Disconnect: `restored from backup: True`, `still registered    : True`, `servers now :
   ['my-linter']`, the settings hold only `{'model': 'sonnet'}`, `gitignore cleaned: True`.

Manual:

1. Register an agent in a new directory and start it with `./start-with-courtyard.sh`
   during a shift. Its first lines show the membership context, it answers the delivery
   check without asking you, and it answers a peer through `courtyard_send`.
2. `courtyard-invite --register --name coding --type claude-code --workdir <dir>`
   registers and connects. `courtyard-invite --name coding --unregister` takes the files
   out and ends with `removed coding from the hub`; `--disconnect` ends with
   `coding stays registered on the hub`. Scripted: `uv run pytest tests/test_invite.py`.
3. Agents page, **remove ▾**, **disconnect**: a message at the bottom of the window says
   `<name> disconnected: the courtyard files left <dir>` and fades; the table does not
   move. The directory holds no `.mcp.json` entry and no `start-with-courtyard.sh`, the
   agent is still in the list and in the charter. A second disconnect says
   `<name>: nothing to take out of <dir>`. **edit**, **save** writes them again:
   `saved; files written into ‹dir›`. No console errors.
4. **remove ▾**, **unregister**: the dialog names the token, the Archive, the charter and
   the files; after it the directory is clean and the agent is gone from the list and
   from the charter.
5. Restart the hub after changing `.env`'s `COURTYARD_PORT` (or after an upgrade): the log
   has one `connect on start: <name>: courtyard files written into <dir>` line per agent,
   and `.mcp.json` carries the new URL. A restart without a change logs nothing.

### Stored tokens

The hub keeps each agent's token: it can be read again, install needs none passed in, and
rotation revokes the old one at once. Design: architecture D19.

```sh
uv run python scripts/runbook/token_rotation.py
```

Expected, four blocks: `same as at registration? True`; `equals the stored one? True`;
after rotation `status after : gone`, the old token refused with `invalid_token`, the new
one reads the inbox; the re-install carries the new token.

Manual: **launch config** on the row shows the token and the three files, read-only, the
same content every time. In **edit**, **rotate token** asks first, then says `Token
rotated; the old one no longer works. Files written into ‹dir›; restart the agent`; the
launch config shows the new token, and the agent's dot stays grey until it is restarted.

### The Agents page and the Defaults setting

The add form, the edit view over `PATCH /api/agents/{id}` whose save also connects the
directory, unregister (disconnect first, then delete), and `New lines start` under
Admin, Defaults.

```sh
uv run python scripts/runbook/agents_edit.py
```

Expected, three blocks: the edit, `null clears`, and two refusals (the name, the
operator); `cleaned+gone : entry left = False; removed = True`; a first message under the
auto-pass default has `status = queued`, and the default is restored.

Manual:

1. Agents page: no message box. The add form is behind **+ Add an agent**. Every row
   carries **edit**, **launch config** and **remove ▾**, nothing else.
2. **edit**: change the description and colour, save. The row and the card update live,
   and the line under the buttons says `saved; files written into ‹dir›` (a dummy: `saved`).
   Name and type are shown as permanent. Change the project directory and save: the old
   directory is clean, the new one holds the files, the line names both.
3. **remove ▾**, **unregister**: the dialog says the files leave the directory first.
   Confirm: the agent leaves the list, its lines go to the Archive, the courtyard entries
   leave its files and other content stays.
4. Admin: Status first, Settings below, every setting a pulldown, `Always on` disabled.
5. Admin, Defaults: set `New lines start` to supervised. A first message between two
   agents that never talked is held; an existing auto-pass line still flows. Set it back.
6. Admin, Terminal application, **+ add an application**, for example `kitty` with
   `kitty --directory {dir} sh -c {command}`. It appears in the pulldown. A custom
   application only opens windows; End shift cannot close them. **remove app** falls back
   to Terminal.
7. **+ Add an agent** with a project directory: the launch config opens with
   `Registered; files written into ‹dir›` and the directory holds the files at once.

### A removed name is registered again

Registering a removed agent's name revives its row: same id, new token, status `invited`.
The old token stays dead, the archives still name the agent, no line comes back, and a
live name is still refused. Design: architecture §5.1, D36.

```sh
uv run python scripts/runbook/name_reuse.py
```

Expected, four blocks: `status : gone, removed_at set: True`; `same id : True` with a
different token; the old token `still refused`, the live name `refused (name_taken)`;
`archive still names ...: True`, `lines on the revived agent: 0`.

Manual: remove an agent, add one with the same name. It appears with the new fields, its
card is back in the charter directory, its launch config shows a new token.

### The pi adapter

One extension file, `.pi/extensions/courtyard.ts`, written by install and speaking the
same hub contract as the Claude Code adapter. Design: architecture §7.3, D32.

```sh
uv run pytest tests/test_pi_adapter.py -q
```

It runs the install-written file under Node with a stub `pi` object against a real hub:
attach, a pushed message, the reply, a turn violation, the delivery check, detach, and
the membership context at session start and after a compaction.

Manual, with pi installed (`npm i -g @earendil-works/pi-coding-agent`):

1. Register an agent of type `pi` with a directory and run `./start-with-courtyard.sh`
   there. The card turns green, and with a shift on the ✓ turns green.
2. Before the footer reads connected, the session shows the membership context naming the
   agent and its team (`.courtyard/adapter.log`: `membership context added`). The model
   answers the check with one `courtyard_ack` and then waits. `pi -c` adds no second
   block. After `/compact` the session still holds it.
3. Message it from the WebUI: the envelope arrives as a courtyard card, not as user input,
   and the reply lands on the board.
4. The footer shows `⏺ <agent> · courtyard · connected`; `/courtyard` answers without a
   model turn; `.courtyard/adapter.log` logs every delivery.
5. A mixed team: a claude-code agent and a pi agent on one supervised line, both
   directions.

## Lines

### The archive

A line's history becomes one immutable document: on request (the line continues empty and
idle) and by itself when an agent is removed. Design: architecture §5.7, D20.

```sh
uv run python scripts/runbook/archive_line.py
```

Expected, three blocks: `reason : operator   messages: 3` and `line state : idle`; the
transcript, `gate note kept: 'fine by me'`, `export : HTTP 200`, `same document: True`;
after the removal `line still on the board: False` and two archives,
`[('agent_removed', 2), ('operator', 3)]`.

Manual: **archive** in the pane header asks first. Afterwards the pane shows one system
entry and the Archive page lists the conversation: read it, **export JSON**, **delete**
after a confirm. Removing an agent moves its lines from the Courtyard page to the Archive.

### Discovery: auto and manual

Under `auto` every agent sees every other and a line forms on the first message. Under
`manual` agents see and reach only whom the operator linked; a link is an idle line.
Unlink archives the history and removes the line. The operator is exempt. Design:
architecture §5.8, D22.

```sh
uv run python scripts/runbook/discovery_links.py     # own hub
```

Expected, six blocks: a line forms under auto; `not_linked` under manual while the
operator still reaches everyone; peers follow the lines; a link, then talk; unlink
mid-conversation archives and refuses; back to auto.

Manual, with two or three agents:

1. Admin, Team: Discovery reads `auto`. The Lines panel has no link control.
2. Set **manual**. The Lines panel gains a small **+** in its corner. An agent asked to
   message an unlinked peer is told it has no line with that peer; nothing reaches the
   board.
3. That agent's `courtyard_peers` lists linked peers and you, and ends "the operator
   manages the links".
4. **+**, pick two agents: an idle line appears on the Defaults mode. The same ask now
   goes through.
5. With that line selected the header shows **unlink**. Unlink mid-conversation: the line
   disappears, the transcript is in the Archive with reason `unlinked`, the pair is
   refused again. **archive** on another line clears history and keeps the link.
6. Back to **auto**: the control disappears, lines form freely, linked lines remain.
7. Three agents, A-B and B-C linked: A and C cannot see or reach each other.

## The shift

### Start and end

The shift state machine, the Team mode and terminal settings, and the real terminal
windows. Design: architecture §8.1, D23, D28.

```sh
uv run python scripts/runbook/shift_and_settings.py
```

Expected, two blocks: the settings round trip, `always_on` refused, a custom terminal
application added, validated and removed; a full shift cycle. The script spawns nothing,
and skips the cycle when real agents are down or other lines are mid-conversation.

Manual, which opens real windows:

1. With one agent's terminal closed, press **▶ Start shift**. The countdown runs
   (`Waiting for the team · N`, agents show "checking..."), then one window opens in that
   agent's directory. The pill reads `Starting · x/y`, then `● y/y on shift`. An agent
   that sends a heartbeat during the countdown gets no window.
2. **■ End shift**, confirm: every window the shift opened closes, even mid-conversation.
   Terminals you opened stay. With a line mid-conversation a second confirm comes first.
3. End the shift and press Start at once, while the cards are still green: the dots turn
   to "checking..." and fresh windows open.
4. Admin, Team: `Always on` is disabled. The terminal application survives a hub restart.
5. Quit Terminal.app, Start shift with N agents down: exactly N windows, no empty one.

Nothing the shift did not open is ever closed, and a running agent is never started twice.

### End shift closes the books

Ending the shift releases every busy line and marks unfinished messages `expired`; nothing
is deleted. A message delivered to an earlier session and never answered is delivered
again at the agent's next attach. Design: architecture §8.1, §6.4, D24.

```sh
uv run python scripts/runbook/expire_and_rearm.py
```

Expected, two blocks: the redelivery on attach; the expiry. The second block skips itself
when other lines are busy or real agents are down.

Manual:

1. Ask an agent something and do not let it reply: its card shows **owes you a reply**
   and the header names it. When the line waits on you the header reads "waiting for your
   reply" and the card shows no badge.
2. **■ End shift** while the question is open, accept the second confirm. The badge is
   gone, the line is idle, the message is struck through with `· expired`, and a system
   entry says it expired at end of shift. A message held at the gate expires the same way.
3. Next shift, message the same agent: the expired question is not delivered again.
4. With a shift on, close the terminal of an agent that owes you a reply and start it
   again: the message arrives in the fresh session and the history gains "redelivered".

### The stale shift

A shift left open, by closing the terminals by hand or by a reboot, is detected, and the
Courtyard page asks what to do. Design: architecture §8.1, D25, D26.

```sh
uv run python scripts/runbook/stale_shift.py         # own hub
```

Expected, four blocks: the agent reads `unknown` with `checking_until` set and stale
`False`, then one transition to `gone` and stale `True`; a connected agent means not
stale; End shift resolves it; resume with nothing open is refused with `no_shift`.

Manual, which opens real windows:

1. With a shift on, close every agent terminal and stop the hub. Start it and open the
   Courtyard page: grey pulsing dots, the Team panel dimmed, `Checking the team · 10`, no
   green and no question. Then, in one step, the agents read offline and "The last shift
   was never ended" appears with **■ End shift** focused. "Not now" leaves the *shift left
   open* tag, which reopens the question.
2. With a shift on, close one agent's terminal. The pill reads `1/2 on shift` and
   **▶ Resume shift** appears. Press it: one window opens for that agent, the shift keeps
   its start time, and what the agent owed arrives in the fresh session.
3. Repeat step 1 and choose **Start new shift**: the old unfinished messages read
   `· expired` and a new shift starts.
4. Restart the hub mid-shift with the agents running: no question. Cards show
   "checking..." for at most one heartbeat, then green, never a false green first.

### Terminal applications

Terminal, iTerm2 and Ghostty are driven the same way: spawn opens a window and records
its id and tty; alive sees the process on that tty; close ends the process, then the
window, with no dialog and no orphan. Design: architecture §8.1, D35.

No hub needed. It opens a real window.

```sh
uv run python scripts/runbook/terminal_spawners.py Ghostty     # or Terminal, iTerm2
```

Expected: a window appears at step 1 and is gone after step 3. `tty : /dev/ttysNNN`,
`alive() : True`, `close() : True`, then `alive() : False` and `orphans : none`. A
`tty : NOT REPORTED` line is a degraded reference, not a dead one: alive then follows the
window alone, and close still closes it.

Manual: Admin, Terminal application lists the three and your own. Select Ghostty, Start
shift: one Ghostty window per agent. End shift closes exactly those.

## Threads

### Open, continue, close, expire

Every message belongs to a thread, one bounded exchange about one ask, at most one open
per line. A declared new ask while one is open is refused. Close is a tool call by the
initiator only; the peer reads "thread closed by X". End shift marks open threads
`expired`. Design: threads.md, D34.

```sh
uv run python scripts/runbook/threads.py
```

Expected, four blocks: the same thread id on ask and answer; the `thread_open` refusal;
the close-tool pointer in the answer, the `not_thread_initiator` refusal, the closed
state and the peer's notice; `expired` after a forced end of shift. The last block skips
itself like the shift scripts do.

Manual, with a live agent:

1. Ask the agent something. `GET /api/lines/<id>/threads` shows one open thread opened by
   `operator`.
2. Close it with **close thread** in the pane header. The pane gains "thread closed by
   operator", and the agent's session receives it.
3. Have the agent ask you something and answer it: a well-behaved session closes its
   thread after your answer.

### Thread budgets

An agent-to-agent thread carries a budget of messages, `thread_budget`, 12 by default, 0
for none. A reply always passes. A fresh ask on a spent thread locks it, tells both
agents, and is refused with `thread_locked`; the next ask opens a new thread. Returned and
dropped messages do not count. Threads with the operator are never locked. Design:
threads.md section 5.

```sh
uv run python scripts/runbook/thread_budget.py       # own hub
```

Expected, seven blocks: the setting; the lock and both refusal texts; a fresh thread
after it; a reply passing a spent budget; a returned message not counting; the operator
exempt; 0 means no budget.

Manual: Admin, Defaults shows "Thread budget" 12; a negative value is refused by the
field. On a throwaway hub set it to 2, let two agents exchange two messages and send a
follow-up: the pane shows two "thread locked" system lines and the sender reads the
refusal.

### Threads on the WebUI

The pane groups messages by thread, with a chip at each thread's first message naming its
number, opener and state. The line's row counts them: "supervised · 3 threads, 1 open ·
2m ago". The header of your own line shows **close thread** when the open thread is yours.

Manual, on `make demo` or any hub where two agents have talked:

1. A line whose pair has talked reads "N threads", with ", 1 open" while an ask is open.
2. Select it: chips split the conversation by ask, and "thread closed by X" sits at each
   ending. No close button: those threads are not yours.
3. Message an agent. A blue "thread N · you · open" chip appears with **close thread**.
   Click and confirm: the chip turns closed without a reload and the agent is told.
4. Have the agent message you first: the chip names it, and there is no close button.

## The team charter

All five entries use one script with its own hub:

```sh
uv run python scripts/runbook/team_charter.py        # own hub
```

Do the manual parts on a throwaway hub with a copy of a charter directory. Selecting a
team registers its agents under permanent names, and the forms write into the directory.
Design: team-charter.md, D33.

### A current team is required

Registration without a current team is refused with `no_team`. The empty Courtyard page
asks for the team's directory. The selection can move but never clear, and the current
team cannot be removed. Script checkpoints 0 and 11.

Manual, on a fresh hub:

1. The Team panel offers the directory choice, not an add-agent tile. The Agents page's
   add form is disabled with the same message.
2. Pick an empty directory and name the team: `team-definition.yml` exists, and each
   agent you add lands there as card files.
3. Admin, Teams: the current team's remove button is disabled, and the pulldown has no
   empty choice.
4. Add a directory that holds a charter, such as a copy of
   `examples/team-charters/aws-devops`, and select it: its agents appear, and an agent of
   no other team is adopted into it.

### Registering, reloading, selecting

The hub loads what the files say, reloads only when told, and reports a broken charter
instead of failing. Script checkpoints 1 to 5.

Manual:

1. Admin, Teams, "add a team", browse: the macOS folder dialog opens
   (`COURTYARD_NATIVE_PICKER=0` forces the in-page one). Pick `tests/team-charter`: the
   team appears as `demo-devops` with 3 agents and no problems.
2. Pick a directory without `team-definition.yml`: the panel offers to initialize it.
   Naming it writes the file and touches nothing else. Cancel writes nothing.
3. Change the name in the file and reload the page: the old name. Press "⟳ reload from
   disk": the new name.
4. Break the file and reload from disk: a readable problem report; the row survives.
5. Remove a team that is not current: the row goes, the files stay.

### Projection: cards become the team

Selecting a team, or reloading the current one, turns cards into registrations and
declared links into lines with their modes. It only adds. Script checkpoints 6 to 8
and 10.

Manual:

1. Select `tests/team-charter` as current: three agents appear, and the Lines panel shows
   infra and tf-dev on auto-pass as declared, infra and scribe on the default. Discovery
   reads manual because the charter declares it, and a hand change is reasserted at the
   next reload.
2. In the team view each agent has a "directory on this machine" cell. Browse for infra:
   `workdirs.local.yml` appears in the charter directory and infra's registration carries
   the directory.
3. Edit `infra/description.md` and reload from disk: the new text is on the card. Change
   the declared line's mode and reload: it returns. A change on the undeclared line stays.
4. Register an agent by hand and reload: it is untouched.
5. The agent's edit view shows the "not for" text from `anti-scope.md`.
6. Start a shift and reload the current team: refused, "a shift is running". End the
   shift: it works.

### Write-back: the forms write the files

While a team is current, adding, editing and removing an agent through the hub also
changes the charter files. Agents outside the charter stay in the database only. Script
checkpoint 9.

Manual:

1. "+ Add an agent" says the agent is also written into the charter directory. Register
   one with every field and a directory: `<name>/` holds `card.yml`, `description.md`,
   `owns.md`, `anti-scope.md`, the yml gains the entry, `workdirs.local.yml` the directory.
2. Edit it: change the model, clear the anti-scope. `card.yml` shows the model and
   `anti-scope.md` is gone.
3. Edit an agent that is not in the charter: no note, no file change.
4. Remove the charter agent: the yml entry, its links and its directory are gone, and a
   reload does not bring it back.
5. Break `team-definition.yml`, reload, add an agent: refused with `charter_not_loaded`,
   nothing registered.

### A load writes the agents' files

A load that registers an agent writes that agent's courtyard files into its directory.
Agents already registered are never rewritten by a reload. Script checkpoints 6 to 8.

Manual, on a fresh hub:

1. Copy `examples/team-charters/aws-devops`. Make two empty directories and write
   `workdirs.local.yml` beside the copy's `team-definition.yml`, mapping `infra-agent` and
   `tf-developer` to them. Leave `argocd-agent` out.
2. Courtyard page, **browse**, pick the copy. Three agents appear. Both directories hold
   `.mcp.json` (`-rw-------`), `.claude/settings.local.json` and
   `start-with-courtyard.sh`, with the token of the agent's launch config.
3. Admin, Teams, the team view names the files written and says `argocd-agent` has no
   directory yet.
4. Choose `argocd-agent`'s directory: its files appear.
5. **Start shift**: every terminal opens and connects with no further step.
6. End the shift, delete one `.mcp.json`, reload from disk: it is not recreated.

## Memory

### The case file and recall

A thread that closes becomes one case file: participants with their domains, the ask, the
resolution, every verdict with its comment, the counts, the messages. Expired and locked
threads leave nothing. `courtyard_recall` returns trimmed records, best match first; the
handle fetches the full case file. Design: hub-memory.md.

```sh
uv run python scripts/runbook/memory_recall.py
```

Expected, four blocks: `case files written by the close: 1` with the approved answer as
the resolution and both verdicts; the recall listing with `our case first : True`; the
full case file, every message numbered with its verdict; nothing found for `kubernetes
ingress`, and an open thread adds no case file.

Manual:

1. Memory page: case files newest first. Click one: who opened and closed it, the id for
   `courtyard_recall(case=...)`, the verdicts, every message.
2. Search `ipv6`: found. Search `kubernetes`: "Nothing matches". The participant pulldown
   narrows the list.
3. Admin, Defaults: `Recall returns` and `Recall trims to`. Set the trim to 80 and recall
   from a live agent: the ask ends in an ellipsis.
4. Under Discovery `manual` an agent recalls only case files it took part in; the Memory
   page shows all.

### Notes

`courtyard_note` deposits a lesson. It is not a message: nobody is addressed and nothing
is owed. On a supervised line, or team-wide, it waits for the operator's verdict on the
Memory page. Only accepted notes are recalled: a line's note by that line's two agents, a
team-wide note by everyone. The operator's own notes are accepted at once.

```sh
uv run python scripts/runbook/memory_notes.py
```

Expected, four blocks: the note `pending` and not yet recalled; a return reaching the
author with the comment, then an approved note recalled by both agents of the line and
not by a third; a team-wide note pending even on an auto-pass line, then recalled by a
third agent; the operator's note `status: accepted, scope: team`.

Manual:

1. An agent calls `courtyard_note`. Memory page: "Notes waiting for you (1)" with a
   comment field and approve, return to sender, drop. Return with a comment: the agent's
   terminal shows the notice.
2. "+ write a note": a team-wide note lists as `note by operator · team-wide`, a scoped
   one as `for a ↔ b`.
3. Search finds notes by their words. A line's note is absent from a third agent's recall.
4. Admin, Message envelope: "A recall listing" shows a case file and a note as an agent
   reads them.

### Similarity search

With `COURTYARD_EMBEDDINGS_URL` set to a local OpenAI-compatible endpoint, records get a
vector in the background and recall fuses full text with cosine similarity. Without an
encoder recall stays full text and says so. Design: hub-memory.md section 7.

```sh
ollama pull nomic-embed-text
COURTYARD_EMBEDDINGS_URL=http://127.0.0.1:11434/v1/embeddings make run
uv run python scripts/runbook/memory_vectors.py      # exits 2 with instructions otherwise
```

Expected, four blocks: `encoder : http`, `default_mode : hybrid`;
`embedding pass : 2 record(s) got a vector`; a paraphrase with no word in common is found
by similarity and hybrid, not by full text; `argocd first? : True` where the words agree.

Manual:

1. The Memory page footer says similarity is on and how many records have a vector. The
   pulldown offers hybrid, full text only, similarity only.
2. Unset the variable and restart: the footer says it is off, the pulldown is gone, and
   the hub's ready line says `recall is full-text only`.
3. A non-local address: the hub refuses to start unless
   `COURTYARD_EMBEDDINGS_ALLOW_REMOTE=1`.
4. Give one record a vector of another width in psql:
   `UPDATE memory SET embedding = '[1,0,0]'::vector WHERE id = '<id>'`. Recall still
   answers, that record is not a similarity hit, and the next pass repairs it.

### Export and retention

`GET /api/memory/export` streams every record in full, one JSON document per line, oldest
first; `participant`, `line` and `since` narrow it. A case file goes with the archive it
came from. Notes are never deleted. Design: hub-memory.md sections 6 and 8.

```sh
uv run python scripts/runbook/memory_export.py
```

Expected, four blocks: `case files of this run: 3`; `oldest first? : True`,
`full documents? : True`, the note included, the filters; `case_files : 2` on the archive;
after the delete one case file left and `the note stayed : True`. One team-wide note,
marked as the script's, stays behind.

Manual:

1. Memory page, **export JSON Lines**: downloads `courtyard-memory-<stamp>.jsonl`. With a
   participant selected the file holds only that agent's records.
2. Archive page: a row reads `· N case files`. Delete it: the confirm names them, and the
   Memory page no longer lists them.
3. `curl -s 'http://127.0.0.1:2626/api/memory/export?since=2026-01-01T00:00:00Z' | wc -l`.

## The WebUI

### The Courtyard page

The side bar, the team as rectangles, lines as two names and a coloured wire, the
conversation pane, one input box for direct chats. Design: architecture §10, D18.

```sh
make demo          # open http://127.0.0.1:2626/ when it says so
make demo-stop
```

Expected:

1. Team: one rectangle per dummy, each its own colour, a green dot when connected. The
   first is selected and the box reads `Message <name>...`. Team and Lines scroll apart;
   their grips resize them, double-click resets, the height survives a reload.
2. Lines: `dev ↔ ops` amber, *held at the gate*, first; `alice ↔ bob` blue, *new since you
   looked*.
3. The gate: click the amber line. The pane shows the **supervised | auto-pass** switch
   and the held message with a comment field and **approve / return to sender / drop**.
   No input box while a line is selected. Approve with a comment: it appears as a note to
   ops. Return: struck through with `returned to sender: <comment>`. Drop: struck through
   with `dropped: <comment>`, and the hub's notice to the sender carries no comment.
4. Your own line: message `concierge-...`, the echo arrives within a second. Message
   `alice-...`, who does not reply: the box greys out and **release** appears in the
   header. Drafts are kept per selection.
5. Unread: a reply while another agent is selected shows `N new` on the rectangle and
   `(N) Agent Courtyard` in the tab title.
6. The icon at the top collapses the side bar, remembered across reloads. No errors in
   the browser console.
7. Themes: the page follows macOS; the sun and moon item switches and is remembered;
   Admin, Appearance, "follow the system" returns.

### The envelope on the Admin page

Admin, **Message envelope**: one collapsible block per text an agent can receive, served
by `GET /api/envelope` from the code that wraps real deliveries.

Manual: expand "A question from a peer" and "The delivery check". Send a real agent a
message and compare: identical apart from names, ids and the body.

## The hub

### Log level

`COURTYARD_LOG_LEVEL` (INFO by default, WARNING, ERROR, DEBUG) sets the hub's own loggers,
uvicorn's and the request lines. A request logs at its real severity: below 400 INFO, 4xx
WARNING, 5xx ERROR. The hub always prints one ready line.

```sh
uv run python scripts/runbook/log_level.py           # own hub
```

Expected, two blocks: at INFO every line prints and the 422 is a WARNING; at WARNING the
200 line is gone and the 422 stays.

Manual: `COURTYARD_LOG_LEVEL=WARNING make run` prints the ready line and then nothing
while the WebUI loads. A refusal, such as adding a team from a directory without a
charter and cancelling, prints its 422 as WARNING.

### The database's identity

At startup the hub stamps the database with an identity or adopts the one there, and
every pooled connection and health ping compares it. When another database answers on the
port the hub logs it once, `/api/health` reports it, every request answers
`503 foreign_database`, and only a restart adopts the new database. Design: architecture
D38.

```sh
uv run pytest tests/test_identity.py -q
```

Manual, with two checkouts on one machine:

1. Hub A is running. In checkout B, whose `.env` sets only `COURTYARD_COMPOSE_PROJECT`,
   stop A's postgres and `make run`: B's postgres takes the port and B's hub fails on A's.
2. A's log shows one `ERROR ... not the one this hub started with`;
   `curl -s localhost:2626/api/health` reports it under `db`; the WebUI's calls answer 503.
3. Give B its own `COURTYARD_PG_PORT` and `COURTYARD_PORT`, restart A's postgres and hub:
   A serves its own database again.

### The hub as a macOS app

`make install` builds `.venv`, creates `.env`, brings postgres up, writes and loads two
LaunchAgents (`com.courtyard.hub`, `com.courtyard.tray`) and `~/Applications/Courtyard
Admin.app`. `scripts/hub-launch.sh` loads `.env`, waits for Docker, brings postgres up and
starts the hub. `make hub-start|stop|restart|status|open` drive it; `make uninstall`
reverses it. `install.sh` checks the prerequisites, downloads the newest release into the
current empty directory and runs `make install`.

```sh
uv run pytest tests/test_install_app.py tests/test_tray.py tests/test_health.py -q
```

Manual. This changes your login items.

1. **The one command.** In an empty directory, the `curl ... install.sh | sh` line prints
   `downloading Agent Courtyard v...`, `unpacked into ...`, then six install steps. A
   non-empty directory stops it with `is not empty`; one holding only `.env` is taken.
   Without Docker running it names the fix. Settings on the command,
   `... | COURTYARD_COMPOSE_PROJECT=courtyard-2 COURTYARD_PG_PORT=26433 COURTYARD_PORT=2627 sh`,
   are written into the new `.env`, and the machine's usual instance is untouched. With
   an existing `.env` step 2 warns that they were not applied.
2. **The database.** Step 3 names the compose project and port and says `fresh courtyard
   database` or `EXISTING courtyard database found and used: N agent(s), ...`. A database
   holding other tables makes the hub refuse to start.
3. **make install.** Stop any `make run` hub first. Six numbered steps, then a `Summary`
   with one row per step, `- OK` or `- WARNING:` with the warning repeated in full, closed
   by `no warnings` or `N warning(s), see above`. `make hub-status` says `loaded` and `up`.
4. **Take-over.** `make install` from a second directory: step 4 says the LaunchAgents ran
   the hub from the first directory and the summary shows a WARNING. The plist names the
   second directory; the first directory's files are untouched.
5. **Restart.** Admin, Status: `supervisor: launchd` with **restart hub**. Press it: the
   page reloads by itself and the cards turn green at their next heartbeat.
6. **The Dock.** The install opens the WebUI with "Keep the courtyard in your Dock?". In
   Chrome **Add to Dock** opens the install dialog; Safari names File, Add to Dock; "not
   now" hides the banner in that browser. A message held at the gate shows as a badge on
   the Dock icon.
7. **Keep alive.** `kill -9 $(pgrep -f .venv/bin/courtyard-hub)`: `make hub-status` says
   `up` again within about five seconds. `make hub-stop`: `down`. Log out and in: the hub
   is up.
8. **The menu bar.** A Courtyard icon and no Dock tile. Its first line reads
   `hub: up (db ok) · no shift · 0 at the gate`; a held message shows `1` beside the icon.
   **Stop hub**, **Start hub**, **Start shift**, **End shift** (asks when a conversation
   is open), **Open WebUI**, **Show hub log** do what they say. **Quit Courtyard Admin**
   removes the icon and leaves the hub; opening `Courtyard Admin` from Spotlight brings it
   back; `pkill -f courtyard-tray` brings it back by itself.
9. **make uninstall.** Step 1 prints one line per registered agent, `<name>: files taken
   out of <dir>`; the directory holds no courtyard entry in `.mcp.json` and no
   `start-with-courtyard.sh`, and the charter directory is untouched. Both plists, the
   menu bar icon and the launcher are gone, the containers are down, `.venv` is gone.
   `.env` and the data volume stay; `make run` still works from the directory and the
   agents are still on the Agents page, where **edit**, **save** connects a directory again.
   With the hub stopped first, step 1 says the hub is not answering and names the
   `courtyard-invite ... --disconnect` command instead.
