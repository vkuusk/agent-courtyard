"""`courtyard-invite`, the command-line register/connect/unregister: `--unregister` is
the full undo (files out, agent off the hub, like the WebUI's remove, unregister);
`--disconnect` takes the files out and leaves the agent registered."""

from __future__ import annotations

import httpx

from courtyard.adapters.claude_code import invite


def _run(capsys, *argv) -> str:
    invite.cli(list(argv))
    return capsys.readouterr().out


def test_unregister_is_a_full_undo_and_disconnect_is_not(live_hub, tmp_path, capsys):
    url = live_hub()
    workdir = tmp_path / "proj"
    workdir.mkdir()
    (workdir / ".git").mkdir()
    out = _run(
        capsys,
        "--hub",
        url,
        "--register",
        "--name",
        "cli-agent",
        "--type",
        "dummy",
        "--workdir",
        str(workdir),
    )
    assert "registered cli-agent" in out and (workdir / ".mcp.json").exists()
    assert (workdir / ".gitignore").exists() and ".gitignore updated" in out

    out = _run(capsys, "--hub", url, "--name", "cli-agent", "--disconnect")
    assert "stays registered" in out and not (workdir / ".mcp.json").exists()
    assert not (workdir / ".gitignore").exists()  # held only our lines
    assert httpx.get(f"{url}/api/agents/cli-agent").json()["removed_at"] is None

    # nothing left to take out of the directory: the registration still goes
    out = _run(capsys, "--hub", url, "--name", "cli-agent", "--unregister")
    assert "nothing to take out" in out and "removed cli-agent from the hub" in out
    assert httpx.get(f"{url}/api/agents/cli-agent").json()["removed_at"] is not None

    # the full undo in one go
    _run(
        capsys,
        "--hub",
        url,
        "--register",
        "--name",
        "cli-agent",
        "--type",
        "dummy",
        "--workdir",
        str(workdir),
    )  # D36: the name is free again
    out = _run(capsys, "--hub", url, "--name", "cli-agent", "--unregister")
    assert "removed the courtyard entry" in out and "removed cli-agent from the hub" in out
    assert not (workdir / ".mcp.json").exists()
