# Development

## Setup

Requirements: macOS, [uv](https://docs.astral.sh/uv/), Docker with compose.

```sh
git clone https://github.com/vkuusk/agent-courtyard.git
cd agent-courtyard
cp .env.default .env   # local settings; the defaults work unless a port is taken
uv sync                # the venv, everything included
make run               # postgres + the hub on http://127.0.0.1:2626, in the foreground
```

| Command | What it does |
|---|---|
| `make run` | the hub from the working tree; Ctrl+C ends it |
| `make run-chrome`, `make run-stop` | the hub in the background (log in `sandbox/`), the WebUI in its own Chrome window |
| `make check` | the test suite and lint; brings postgres up itself |
| `make fmt` | fixes formatting |
| `make test-comms` | a round trip through a live Claude Code session; needs `claude` on PATH |
| `make demo`, `make demo-stop` | two scripted dummy agents talking through the hub; stop removes them and what they produced |
| `make db-nuke` | stops the containers and deletes the database volume |
| `make zip-package` | the install zip of the committed tree |

`sandbox/` is the gitignored scratch area.

A hub installed with `make install` runs from its own directory under launchd. Only one
hub can hold a port: `make run` refuses to bind while an installed hub is up on the same
one. A second instance needs its own compose project, postgres port and hub port in
`.env`.

### Python and the venv

- `.python-version` pins `3.14`, minor only, so homebrew patch upgrades keep matching.
- `.venv` holds no Python of its own; it links to brew's. After a brew Python upgrade,
  recreate it: `rm -rf .venv && uv sync`.
- `uv sync` makes the venv match `uv.lock` exactly, so it removes packages installed by
  hand with pip. `uv sync --inexact` installs what the lock requires and leaves the rest.
  `uv add <pkg>` makes a package permanent.
- pip works on the same venv: `source .venv/bin/activate`, then `pip install <pkg>`. For
  a venv without uv: `python3.14 -m venv .venv`, then `pip install -e . --group dev`
  (pip 25.1 or newer). Keep `-e`: without it a copy of the code shadows edits to `src/`.
- `uv lock` re-resolves the lock from `pyproject.toml`. `uv lock --upgrade` refreshes all
  pins, `uv lock --upgrade-package <name>` one.

## Contributing

1. Work on a branch and open a pull request to `main`.
2. `make check` is green.
3. A change to observable behaviour ships its manual test procedure (next section).
4. A design change starts from the decision log in
   [`design/architecture-v1.md`](design/architecture-v1.md): read the entries it touches.
5. Docs never use the em dash character and are written in a plain technical register.

## Testing

Three layers:

- **Functional tests**: `tests/test_*.py`, run by `make check`, against a dedicated
  `courtyard_test` database. Development data is never touched.
- **End to end**: `tests/communications/`, run by `make test-comms` on demand.
- **Manual verification**: a script in `scripts/runbook/` plus its entry in
  [`testing.md`](testing.md). Automated tests assert; these scripts show.

### Every feature ships a manual test procedure

It is part of done, together with a green `make check`. The entry in `testing.md`:

```
## <section name>

**Feature under test:** one or two sentences, with the design reference (section or D-number).

**Run:**
    <copy-paste command>            # omit if no single command applies

**Expected:** the specific values that confirm it works.
```

The script behind `Run:`:

- One file per procedure, in `scripts/runbook/`. `make check` lints it.
- Self-contained and self-cleaning: throwaway agents with unique names, removed at the
  end, no dependence on earlier runs, exit 0 on success.
- Prints its checkpoints, so the operator reads the real output: the envelope text, the
  peers listing.
- Uses the real client library (`courtyard.common.client`) and the real endpoints.
- Is run against a live hub before it is handed over. Never present a command unrun.

## Texts a model reads

Every text a model reads is a named template in `src/courtyard/texts/*.yml`, rendered with
`texts.render(key, **variables)`. Code decides which text applies and holds no wording of
its own. Design:
[`design/communication-protocols.md`](design/communication-protocols.md), section 8.

- **Change a wording:** edit the YAML, run
  `COURTYARD_UPDATE_GOLDEN=1 uv run pytest tests/texts -q`, review the diff of
  `tests/texts/golden/`. That diff is what a reviewer reads.
- **Add a text:** add the key to the YAML of its family and render it from the code. The
  catalog test fails on a key that does not exist and on a text nothing renders; `render`
  fails on a missing or unused variable.
- **A golden file differs without a YAML edit:** the code changed what it renders. Find
  out why before regenerating.
- **When a new wording reaches a running team:** envelopes, notices, refusals and tool
  results at the hub's restart. Tool definitions, instructions and the adapters' own texts
  at each agent's next session start. The pi skill when the agent's files are written
  again (Agents page, sync dir).

## WebUI

`webui/` is plain ES modules, no build step. The hub serves everything outside `/api/`
with `Cache-Control: no-cache`, so a normal reload is enough after any edit and the page
never runs a mix of old and new modules.

## Releasing

A release is a git tag `v<version>` on `main`. The workflow
`.github/workflows/release.yml` builds the install zip and publishes a GitHub Release with
it, as `courtyard.zip` and under the versioned name. `install.sh` downloads the newest
release.

The version is in `pyproject.toml` and in `uv.lock`, and the tag must match both. Let uv
move them; a hand edit of `pyproject.toml` leaves `uv.lock` behind.

1. On the branch, when it is ready to merge:

   ```sh
   uv version --bump patch        # or: uv version 0.2.0
   uv lock --check                # non-zero if the lock is behind pyproject.toml
   git add pyproject.toml uv.lock
   git commit -m "- bump version to 0.2.0"
   ```

2. Merge the branch into `main`.
3. Tag the merge and push the tag:

   ```sh
   git checkout main && git pull
   git tag v0.2.0 && git push --tags
   ```

4. Check the release page: both zips attached. `curl -fsSL .../install.sh | sh` in an
   empty directory is the end-to-end check.
