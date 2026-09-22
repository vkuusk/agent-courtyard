"""courtyard-invite — put a Claude Code agent's launch config into its project (step 6d).

A thin operator convenience over the hub's install API: it writes `<workdir>/.mcp.json`
(merging with anything already there, keeping a backup) so the agent starts with the
courtyard MCP server — the operator never hand-edits the file.

    # existing agent (the hub keeps its token, D19):
    courtyard-invite --name coding --workdir ~/proj/payments

    # register and install in one step:
    courtyard-invite --register --name coding --type claude-code \\
        --sme-domain "the payments service" --workdir ~/proj/payments

    # fresh hub: a current team is required before the first agent (D33) — choose
    # the team's charter directory in the same command (empty dir = initialized):
    courtyard-invite --team-dir ~/teams/devops --team-name devops \\
        --register --name coding --type claude-code --workdir ~/proj/payments

    # unregister: the files come out of the directory AND the agent leaves the hub and
    # the team charter (the WebUI's remove, unregister; the name can be registered again):
    courtyard-invite --name coding --unregister

    # disconnect: the files come out of the directory only, the agent stays registered
    # (the WebUI's remove, disconnect; save or a charter load connects it again):
    courtyard-invite --name coding --disconnect

Dev-mode only: the hub writes the file, so it must share this machine's filesystem (the
normal local setup). In live/container mode use the WebUI's copy-paste config instead.
The written file carries the token and is chmod 600 — do not commit it; under git the
hub adds it to .gitignore and says so.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from courtyard.common.client import DEFAULT_HUB_URL, HubClient, HubError


def _ensure_team(client: HubClient, team_dir: str, name: str | None) -> None:
    """Register the charter directory if the hub does not know it, then make it
    current (D33: a current team is required before agents can register)."""
    path = str(Path(team_dir).expanduser().resolve())
    team = next((t for t in client.teams() if t.charter_dir == path), None)
    if team is None:
        team = client.add_team(path, name)
        print(f"registered team {team.name!r} from {path}")
    if not team.is_current:
        client.set_current_team(team.id)
        print(f"made {team.name!r} the current team")


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="courtyard-invite", description=__doc__)
    p.add_argument("--hub", default=DEFAULT_HUB_URL, help=f"hub URL (default {DEFAULT_HUB_URL})")
    p.add_argument("--name", required=True, help="the agent's courtyard name")
    p.add_argument("--token", help="the agent's token (optional — the hub keeps it)")
    p.add_argument("--workdir", help="the agent's project dir (default: its registered workdir)")
    undo = p.add_mutually_exclusive_group()
    undo.add_argument(
        "--unregister",
        action="store_true",
        help="take the files out of the workdir and remove the agent from the hub and the charter",
    )
    undo.add_argument(
        "--disconnect",
        action="store_true",
        help="take the files out of the workdir only; the agent stays registered",
    )
    p.add_argument(
        "--register", action="store_true", help="register the agent first, then connect its workdir"
    )
    p.add_argument(
        "--type", default="claude-code", help="agent type when --register (default claude-code)"
    )
    p.add_argument("--description", help="what the agent is for (when --register)")
    p.add_argument("--sme-domain", help="what the agent owns (when --register)")
    p.add_argument("--anti-scope", help="what NOT to ask this agent (when --register)")
    p.add_argument("--color", help="board colour: red orange yellow green teal blue purple pink")
    p.add_argument("--model", help="model for the agent's runtime, e.g. sonnet (when --register)")
    p.add_argument(
        "--team-dir",
        help="the team's charter directory: registered with the hub and made current if "
        "needed (a current team is required before the first --register on a fresh hub)",
    )
    p.add_argument(
        "--team-name",
        help="team name when --team-dir points at a directory without a charter yet "
        "(the directory is then initialized)",
    )
    return p


def cli(argv: list[str] | None = None) -> None:
    args = _parser().parse_args(argv)
    client = HubClient(args.hub)
    try:
        if args.unregister or args.disconnect:
            try:
                result = client.disconnect(args.name, args.workdir)
            except HubError as exc:
                # no files to take out (never connected, or already disconnected) is not
                # a reason to keep the registration: same as the WebUI's unregister
                if exc.code != "nothing_to_disconnect" or args.disconnect:
                    raise
                print(f"courtyard-invite: nothing to take out of the directory ({exc})")
            else:
                how = (
                    "restored the pre-install file"
                    if result["restored_from_backup"]
                    else "removed the courtyard entry"
                )
                print(f"courtyard-invite: {how} at {result['path']}")
                if result.get("gitignore_cleaned"):
                    print("  took the courtyard lines out of .gitignore")
            if args.disconnect:
                print(f"  {args.name} stays registered on the hub")
            else:
                client.remove_agent(args.name)
                print(f"  removed {args.name} from the hub (its lines are archived)")
            return

        if args.team_dir:
            _ensure_team(client, args.team_dir, args.team_name)
        token = args.token
        if args.register:
            _agent, token = client.register_agent(
                args.name,
                args.type,
                args.description,
                args.sme_domain,
                args.workdir,
                args.color,
                model=args.model,
                anti_scope=args.anti_scope,
            )
            print(f"registered {args.name}; token: {token}")

        result = client.connect(args.name, token, args.workdir)
        print(f"courtyard-invite: wrote {result['path']}")
        if result["backed_up"]:
            print(f"  (backed up the previous file to {result['backed_up']})")
        if result.get("script_path"):
            print(f"  also wrote {result['script_path']}")
            print("  To start this agent by hand, run ./start-with-courtyard.sh in its directory.")
            if args.type == "claude-code":
                print("  If a Claude Code session is already running there, close it first;")
                print("  a session started plainly (bare `claude`) cannot hear the hub.")
        print(f"  {result['warning']}")
        if result.get("gitignore"):
            print(f"  (.gitignore updated: {result['gitignore']})")
    except HubError as exc:
        print(f"courtyard-invite: hub refused: {exc}", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    cli()
