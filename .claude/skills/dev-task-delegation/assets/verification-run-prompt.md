# Prompt: a verification run of docs/testing.md

Give the second agent the block below. It works as it stands: all sections, 90
minutes, no live sessions. To change that, edit the three places marked in the block
before pasting:

- **all sections** (step 3): replace with a list of `##` section names from
  `docs/testing.md` to narrow the run (`the sections Agents and Memory`).
- **90 minutes** (step 5): the time limit; a narrowed run needs less.
- **step 9**: present only when the operator has allowed real terminal windows on this
  screen and model tokens spent. Delete it otherwise; every entry and step whose *Needs*
  line says a live session is then reported as skipped.

The same prompt for every agent tried, so their reports stay comparable; the report's
Run table names the agent and its model.

```
You are testing the agent-courtyard repository in this directory.

1. Read .claude/skills/courtyard-testing/SKILL.md first and follow it. It says which
   checks exist, how to start a throwaway hub, and what you must never touch (port 2626
   is the operator's live hub). Run every command from the repository root, under bash.
2. Run `make check` first: it is the automated bar, the whole test suite and lint.
   Record its result and carry on whatever it says.
3. Run all sections of docs/testing.md, in the order they appear. A section is a "##"
   heading; its entries are the "###" headings under it. For each section:
   a. give it a hub of its own and point the procedures at it:
      uv run python .claude/skills/courtyard-testing/scripts/scratch_hub.py start --name <section>
      export COURTYARD_HUB_URL=<the url it prints>
      No environment variable needs setting for this; the script reads the checkout's
      .env by itself.
   b. run every entry of the section: the entry's command first, then the manual steps
      its "Needs" line says you can do. Compare what you see with the Expected text.
   c. clean up in the order the entries show: first the `--stop` of every fixture the
      section started (seed_board.py --stop, before its hub is gone), then the section's
      hub. Cleanup goes through those scripts, never through kill or rm on your own.
      Record what the section left behind.
4. What you may not do, you report, you do not attempt. Entries whose "Needs" line says
   a live session, or this machine, are SKIPPED with that reason, and so is every single
   manual step that needs one.
5. Carry on. Nothing inside a section ends the run:
   - an entry whose output does not match Expected is FAIL; the next entry still runs;
   - an entry that cannot run at all is BLOCKED, with what was missing named;
   - skip an entry only when what it needs was made by an entry that failed in the same
     section, and name that entry;
   - if a section's hub does not start, that whole section is BLOCKED and the next
     section starts with its own fresh hub;
   - stop the whole run only when every section is done, or 90 minutes have passed.
6. Do not fix anything you find, in code or docs; report it under Findings.
7. Write the report exactly as .claude/skills/courtyard-testing/assets/report-template.md
   specifies, at temp/test-reports/<YYYY-MM-DD>-<short git sha>/report.md (the local
   date), with the full output of every command saved under logs/ beside it. Keep every
   working file under that directory too. Write the report even when the run ends
   early, with a row for every entry of every section.
8. Leave nothing behind: every scratch hub stopped, every fixture stopped, every agent
   you registered removed, every directory you made under temp/ deleted. List what you
   could not remove.
9. You may also run entries and steps whose "Needs" line says a live session. They open
   terminal windows on this screen and spend model tokens; End shift when you are done.
```
