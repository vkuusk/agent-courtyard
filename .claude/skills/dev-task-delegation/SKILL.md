---
name: dev-task-delegation
description: Hands a courtyard development task to a second agent. Says which tasks may be delegated, what the second agent needs, the exact prompt to give it, and what to do with what comes back. Use when the operator names another agent (another model, a second terminal, a subagent) and asks to delegate, hand off, or have that agent run a task; today the one such task is a verification run of docs/testing.md.
---

# Delegating development tasks

Some work on courtyard is better done by a second agent than by the one that wrote
the code. A verification run on another model finds what the author's blind spots
hide, and it costs the lead nothing while it runs. This skill says which tasks may be
handed off, what the second agent needs, and what to do with what comes back.

## When this applies

Both conditions, always:

1. The task is one of the scopes below. Anything else stays with the lead.
2. The operator has named the second agent: which model, where it runs. Never assume
   one exists, and never start one unasked.

## How the hand-off works

The lead fills the scope's prompt from `assets/`, replaces every `<placeholder>`, and
gives the filled text to the operator, who starts the second agent and pastes it. The
operator chooses the agent on purpose: a different model is the point, and a subagent
spawned by the lead runs on the lead's own model.

When the operator says to spawn it instead, use the Agent tool with the same filled
prompt, and treat what comes back the same way.

Either way the second agent works in this checkout, on throwaway hubs, and never on
the operator's live hub (port 2626). The lead does not run the same task in parallel;
it waits for the result.

## Scopes

| Scope | The second agent needs | Prompt | Comes back as | Judged with |
|---|---|---|---|---|
| A verification run of `docs/testing.md` | this checkout, `uv`, Docker, a browser tool, bash | [assets/verification-run-prompt.md](assets/verification-run-prompt.md) | `temp/test-reports/<date>-<sha>/report.md` and `logs/` | `.claude/skills/courtyard-testing/references/judging-a-report.md` |

### A verification run

1. The prompt works as it stands: all sections, 90 minutes, no live sessions. The
   asset marks the three places to edit when the operator wants less, or wants live
   sessions, which cost terminal windows on this screen and model tokens.
2. Hand it over. While it runs, do not touch the hubs it starts, the agents it
   registers or `temp/test-reports/`.
3. When the report is in, judge it before believing it, with the checklist named
   above. A section that stopped at its first failure or an entry with no row is a
   fault of the run, and the section is rerun.
4. Findings that survive judging go to the operator as defects, with the report's own
   evidence lines. The lead decides what to fix; the second agent fixes nothing.

## Gotchas

- Told to stop when blocked, a second agent stops at the first blocked entry and ends
  the whole run. The prompt says to carry on, section by section, for that reason. Do
  not shorten that part when adapting the prompt.
- Every setup fact the second agent needs has to be in the skill it is told to read or
  in the prompt. It has no memory of this project: the first run was blocked by a
  postgres container name that only the lead's own habits knew.
- A model used to zsh writes `${pipestatus[1]}` in bash and gets exit 255 for every
  failure. The prompt names bash; the judging checklist knows the symptom.
- Keep the prompt identical between agents and change only the marked places, so a
  weaker report is the agent's doing and not the prompt's.
- The second agent's own harness may refuse `kill` and `rm` as irreversible, and the
  agent then cannot clean up at all. Every fixture and hub therefore has its own
  `--stop`, and the prompt sends cleanup through those scripts, not through raw
  commands. Whatever is still listed under "Left behind" is the lead's to remove.
- A second agent asked to quote log lines shortens them with `...` where a value was
  interpolated. Those are elisions, not fabrications; the judging checklist says how
  to tell them apart.
