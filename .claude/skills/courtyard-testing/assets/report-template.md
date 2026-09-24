# Verification report: template

The report is read by a model, so it has to be checkable, not persuasive.

Location: `temp/test-reports/<YYYY-MM-DD>-<short git sha>/report.md`, with the complete
stdout and stderr of every command saved as `logs/<NN>-<name>.log` in the same directory
(`command 2>&1 | tee logs/...`). The report references those files; a checkpoint without
a log line behind it counts as not run.

Rules:

1. Quote output, never paraphrase it. "Observed" cells hold lines copied from the log.
   The judge greps the verification scripts for the strings they print; a quoted line
   that no script can print is fabrication.
2. Every command verbatim, with its exit code, as it was typed, including the environment
   variables in front of it.
3. Say what was NOT done, and why. SKIPPED (a decision) and BLOCKED (could not) are
   results, not omissions.
4. Do not fix anything. A failing checkpoint is reported; the product and the docs are
   not edited by the testing agent.
5. Never port 2626, never 26432, never `pkill`. State how every hub was started.

---

# Courtyard verification report

## Run

| field | value |
|---|---|
| started / ended | 2026-MM-DD HH:MM / HH:MM (local) |
| machine | hostname, macOS version |
| repository | `git rev-parse HEAD`, branch, `git status --short \| wc -l` (dirty files) |
| testing agent | the agent and model that produced this report |
| skill read | yes / no; path of the SKILL.md read, and the one instruction that changed a decision during the run |
| sections | the sections run, and the sections not run with the reason |
| hubs | one row per section: the scratch hub's name and URL, the exact `scratch_hub.py start` command and its printed output, the `stop` line |
| postgres | the compose project and postgres port the scratch hub reported using |
| versions | `uv --version`, `docker --version`, `claude --version` and `pi --version` when a live check ran |

## Summary

| # | section | procedure (heading exactly as in docs/testing.md) | kind | result | duration | log |
|---|---|---|---|---|---|---|
| 1 | | The automated bar (`make check`) | pytest + lint | PASS / FAIL | | `logs/01-make-check.log` |
| 2 | Messages | ... | script / manual / live | PASS / FAIL / SKIPPED / BLOCKED | | |

kind: `script` = a `scripts/verify/<area>/*.py` run; `manual` = the entry's Manual steps
done by hand or in a browser; `live` = needs a real Claude Code or pi session.

Every entry of every section named in the prompt has a row, including the ones that did
not run: a missing row is a gap in the report, not a skipped test.

## The automated bar

- command: `...` (verbatim)
- exit code:
- last lines of output (copied): `N passed in ...`, the lint line
- tests that failed, with the failure's first traceback line each; a rerun of a single
  failed test and its result (some timing tests flake; say so only with the rerun shown)

## Procedures

One block per row of the summary, in the same order.

### <heading exactly as in docs/testing.md>

- command: `...` (verbatim, environment variables included)
- exit code:
- log: `logs/NN-name.log`

| checkpoint (quoted from the entry's Expected) | observed (line copied from the log) | match |
|---|---|---|
| `restored from backup: True` | `restored from backup: True` | yes |
| ... | ... | no: ... |

- unexpected in the output: warnings, tracebacks, lines the entry does not mention
  (copied), or "none"
- manual steps: one line per step, what was done and what was seen; a screenshot per
  screen as `shots/NN-step.png`; for WebUI steps, how console errors were checked and
  the count
- result: PASS / FAIL / SKIPPED (reason) / BLOCKED (what was missing)

## Skill compliance

| rule from SKILL.md | followed | evidence |
|---|---|---|
| a check that flips settings or does destructive work runs on a scratch hub | yes / no | the `scratch_hub.py start` line from the log |
| port 2626 never touched, no `pkill` | yes / no | `grep -c 2626 logs/*` = 0 |
| throwaway agent names, cleaned up | yes / no | the names, and the final `GET /api/agents/<name>` showing `removed_at` set, or the script's own cleanup line |
| `COURTYARD_HUB_URL` or `--hub` pointed at the scratch hub | yes / no | the command lines |
| every scratch hub stopped, its database dropped | yes / no | the `stopped, database ... dropped` line per section |

## Left behind

Anything the run created and did not remove: files outside `temp/`, containers, volumes,
`sandbox/` directories, agents still registered on any hub, open terminal windows.
"nothing" when clean.

## Findings

Problems in the product or the docs seen during the run, each as: what happened, where
(`file:line` or the WebUI screen), how to reproduce, and whether it looks like a code
defect or a doc defect (the Expected text does not match what the code prints). Not fixed.

## Not verifiable by the testing agent

What the judge or the operator has to look at: real terminal windows opened, a Dock
icon, a menu bar item, a live model's behaviour.
