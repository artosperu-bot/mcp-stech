from __future__ import annotations

from pathlib import Path

import pytest

from stech_mcp.chatgpt_bridge.git_transport import GitTransport, GitTransportError


class Result:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_pull_verifies_branch_and_uses_argument_arrays(tmp_path):
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        if args[1:] == ["branch", "--show-current"]:
            return Result(stdout="feat/chatgpt-research-bridge-v1\n")
        return Result()

    transport = GitTransport(tmp_path, "feat/chatgpt-research-bridge-v1", run_command=run)
    transport.pull()

    assert calls[0][0] == ["git", "branch", "--show-current"]
    assert calls[1][0] == ["git", "pull", "--ff-only", "origin", "feat/chatgpt-research-bridge-v1"]
    assert all(call[1]["cwd"] == Path(tmp_path) for call in calls)
    assert all("shell" not in call[1] for call in calls)


def test_pull_rejects_wrong_checked_out_branch(tmp_path):
    def run(args, **kwargs):
        return Result(stdout="main\n")

    transport = GitTransport(tmp_path, "feat/chatgpt-research-bridge-v1", run_command=run)
    with pytest.raises(GitTransportError, match="branch"):
        transport.pull()


def test_commit_and_push_skips_commit_when_mailbox_has_no_changes(tmp_path):
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        if args[1:] == ["diff", "--cached", "--quiet"]:
            return Result(returncode=0)
        return Result()

    transport = GitTransport(tmp_path, "feat/chatgpt-research-bridge-v1", run_command=run)
    assert transport.commit_and_push() is False
    assert not any("commit" in call for call in calls)
    assert not any("push" in call for call in calls)


def test_commit_and_push_only_stages_mailbox_and_pushes_configured_branch(tmp_path):
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        if args[1:] == ["diff", "--cached", "--quiet"]:
            return Result(returncode=1)
        return Result()

    transport = GitTransport(tmp_path, "feat/chatgpt-research-bridge-v1", run_command=run)
    assert transport.commit_and_push() is True
    assert ["git", "add", "--", "research_bridge"] in calls
    assert ["git", "push", "origin", "feat/chatgpt-research-bridge-v1"] in calls


def test_git_failure_is_explicit_and_never_becomes_no_data(tmp_path):
    def run(args, **kwargs):
        if args[1:] == ["branch", "--show-current"]:
            return Result(stdout="feat/chatgpt-research-bridge-v1\n")
        return Result(returncode=1, stderr="network unavailable")

    transport = GitTransport(tmp_path, "feat/chatgpt-research-bridge-v1", run_command=run)
    with pytest.raises(GitTransportError, match="network unavailable"):
        transport.pull()
