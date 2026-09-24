---
name: courtyard-testing
description: Testing workflow for the agent-courtyard repository. How to run the existing checks (pytest suite, lint, verification procedures, live round-trip, WebUI checks), which tests a change must add, and how to judge the report of a verification run done by another agent. Use when verifying or testing a change, adding tests for new code, writing a testing entry in docs/testing.md, judging a test report, or when a check needs a safe throwaway hub.
compatibility: Requires uv and Docker with compose. Live-session checks additionally need Claude Code on PATH (macOS).
---

# Testing courtyard

## The layers, and when each runs

1. **`make check`**: the automated bar for every change: the full pytest suite
   plus lint (`make fmt` fixes formatting). The suite runs against a dedicated
   `courtyard_test` database in the compose postgres (brought up
   automatically), so dev data is never touched. Pytest discovers every
   `tests/test_*.py` file by itself; there is no suite list to maintain. Must
   pass before a change is done.
2. **Verification procedures** in `scripts/verify/<area>/`: scripts that print
   what the operator would see. The area is the section of `docs/testing.md`
   the entry sits in. Run the one covering what you changed; read its header
   first, some need their own throwaway hub.
3. **`make test-comms`**: proves the operator to live-Claude-Code-session round
   trip. Run it only when the adapter, envelope, or delivery path changed, or
   after a Claude Code auto-update; it launches a real session (needs `claude`
   on PATH and model access).
4. **WebUI browser check**: drive the changed pages against a scratch hub,
   filled by `scripts/verify/webui/seed_board.py`. The bar is the flow working
   with zero browser console errors.

## What a change must add

- **Hub logic or API**: tests in `tests/test_<area>.py` using the fixtures in
  `tests/conftest.py` (real postgres, real app). Follow the neighbouring tests'
  style.
- **A new migration**: a test that exercises it. If it rewrites rows, verify it
  against a database seeded with pre-migration data, not only against a fresh
  schema.
- **A text a model reads** (envelope, notice, refusal, tool result, instructions):
  the wording lives in `src/courtyard/texts/*.yml`, never in the code. After an
  edit, regenerate the golden files with
  `COURTYARD_UPDATE_GOLDEN=1 uv run pytest tests/texts -q` and review their diff;
  a golden that differs without a YAML edit is a bug to explain, not to regenerate.
- **WebUI change**: drive the changed flow in a browser, checking rendered
  state and console errors.
- **Every completed feature**: an entry in `docs/testing.md` plus a durable
  script (next section). This is part of "done", not a follow-up.

## The verification standard

The standard is defined in `docs/development.md`; the entries live in
`docs/testing.md`; the scripts live in `scripts/verify/<area>/`.

- Before changing an existing feature, read its entry in `testing.md`: it states the
  feature's observable behaviour and how to verify it.
- A verification script prints its checkpoints rather than just asserting them; the
  point is that the operator reads real output (the envelope text, the peers
  listing) with their own eyes. Use the real client (`courtyard.common.client`)
  so what prints is what a real agent would receive.
- Entries are terse: checkpoints, not prose. Copy the format of an existing
  entry.
- Run your new procedure yourself before handing it to the operator.

## When another agent ran the procedures

Handing a run to a second agent is the `dev-task-delegation` skill's job. What comes
back is a report in the shape of [assets/report-template.md](assets/report-template.md).
Before acting on any row of it, check it against
[references/judging-a-report.md](references/judging-a-report.md): quoted lines that no
script prints, exit codes that do not match the logs, and sections that stopped at
their first failure are faults of the run, not findings about the product.

## When a check needs its own hub

Any check that flips courtyard-wide settings (discovery, defaults, team mode)
or does destructive data work must run on a throwaway hub, never the dev hub.
Do not improvise a hub launch; run exactly:

```sh
uv run python .claude/skills/courtyard-testing/scripts/scratch_hub.py start --name <check-name>
# ... run the check against the printed URL (pass it as COURTYARD_HUB_URL or --hub) ...
uv run python .claude/skills/courtyard-testing/scripts/scratch_hub.py stop --name <check-name>
```

It creates a scratch database, starts a hub on a free port, and `stop` removes
both. No environment variables need setting: it reads the checkout's `.env`
(compose project, postgres port) the way `make` does. The hub comes with a
current team already set (D33 requires one before
agents can register); pass `--bare` to start without it when the check targets
the pre-team state itself. `scripts/verify/lines/discovery_links.py` and
`stale_shift.py` show the full pattern in use.

## Gotchas

- **Run every command from the repo root, under bash, not zsh.** `pipestatus`
  is zsh's; bash spells it `${PIPESTATUS[0]}`, and the zsh form silently
  reports the wrong exit code for the command it wrapped.
- **Port 2626 is the operator's live hub.** Never kill it, restart it, or flip
  its courtyard-wide settings; live agents are attached and a settings flip
  refuses their sends mid-run. Never `pkill -f courtyard-hub`; stop only pids
  you recorded (the scratch hub script and `make run-stop` do this correctly).
- **Live-session tests steal channels.** An attach for an agent name takes over
  that agent's channel (last attach wins), so tests that launch sessions must
  use throwaway agent names on a throwaway hub, never a real agent's name or
  token.
- **Agent names are permanent identities** on a hub. Test registrations need
  unique throwaway names and must clean up after themselves
  (`scripts/verify/webui/seed_board.py` shows the cast-cleanup pattern).
- **Driving the WebUI.** Playwright is deliberately not a project dependency:
  install it in a venv outside the repo, or drive the page with whatever browser
  tooling the session has. The clickable line row is `button.line` (`.wire` is
  only the middle span), `agent_a` of a pair is not registration order, and a
  dialog the page raises with `confirm()` freezes a browser driven by tools.
- **Do not wrap streaming responses in generic HTTP middleware**; it makes SSE
  tests flaky. Static-file headers are handled in `RevalidatingStaticFiles`.
- **If live messages stop after a Claude Code auto-update**, run
  `make test-comms` before blaming the hub; the channels research preview's
  flag contract has drifted before, and the test prints whether the channel
  was registered or skipped.