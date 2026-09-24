# Judging a verification report

A report from a delegated run (shape: `assets/report-template.md`) is evidence, not a
verdict. Check it before acting on any row. The checks are cheap and each one catches
a failure mode seen in real reports.

## The evidence

- [ ] Open `logs/`. Every command in the report has a log file, and the file holds the
      command's full output, not a summary.
- [ ] For every quoted "observed" line, grep the log first, then `scripts/verify/*/*.py`
      for the fixed part the script prints (the text before the first interpolated
      value). A line in neither is fabrication, and the whole report is then suspect.
      A line with `...` where the log has an id or a name is an elision: check the log
      line it stands for, and note that rule 1 was bent, not broken.
- [ ] Exit codes match the logs. A wrapper that misreports them (zsh's `pipestatus`
      under bash prints `exit: : numeric argument required` and exit 255) means the
      real code is in the log, not the report.
- [ ] Every Expected vs Observed row is compared against the entry's own Expected text
      in `docs/testing.md`, not against the report's paraphrase of it.
- [ ] `grep -c 2626 logs/*` is 0 in every file.
- [ ] The Skill compliance table carries evidence lines, not yes/no alone.

## The run itself

- [ ] Every section named in the prompt has a scratch hub start line and a stop line.
- [ ] Every entry of every named section has a row in the Summary, including SKIPPED
      and BLOCKED ones.
- [ ] A section that stopped at its first failure, or an entry with no row, is a fault
      of the run, not a finding about the product. Say so, and rerun that section.
- [ ] "Left behind" is either "nothing" or a list you then clean up yourself:
      `scratch_hub.py list`, `docker ps`, `sandbox/`, agents still registered on any hub.

## What to do with findings

A FAIL whose observed line is real and whose Expected text is quoted correctly is a
defect to look at: either the code or the entry's Expected text is wrong, and the report
should say which it looks like. A BLOCKED entry with a named missing piece is usually a
gap in the skill or the docs, since the testing agent had only those to go on. Fix the
gap before rerunning, so the next agent does not hit it again.
