from __future__ import annotations

import subprocess
from pathlib import Path

from agent.core import version_check


def _completed(args: list[str], stdout: str = "", returncode: int = 0):
    return subprocess.CompletedProcess(args, returncode, stdout, "")


def test_version_check_detects_outdated_source_checkout(monkeypatch):
    old_sha = "1" * 40
    new_sha = "2" * 40

    def fake_git(args, _root, _timeout):
        if args == ["rev-parse", "--is-inside-work-tree"]:
            return _completed(args, "true\n")
        if args == ["rev-parse", "HEAD"]:
            return _completed(args, f"{old_sha}\n")
        if args == ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"]:
            return _completed(args, "origin/main\n")
        if args == ["ls-remote", "origin", "refs/heads/main"]:
            return _completed(args, f"{new_sha}\trefs/heads/main\n")
        if args == ["rev-parse", "--verify", "--quiet", "origin/main"]:
            return _completed(args, "", 1)
        return _completed(args, "", 1)

    monkeypatch.setattr(version_check, "_run_git_command", fake_git)

    result = version_check.check_for_update(Path("/repo"))

    assert result.status == "outdated"
    assert result.current == old_sha
    assert result.latest == new_sha
    assert result.source == "origin/main"
    notice = version_check.format_update_notice(result)
    assert notice is not None
    assert "scripts/update-local.sh" in notice
    assert "Existing `.env`, user config, and local secrets are preserved" in notice


def test_version_check_accepts_a_local_checkout_that_already_contains_latest_commit(
    monkeypatch,
):
    current_sha = "3" * 40
    latest_sha = "4" * 40

    def fake_git(args, _root, _timeout):
        if args == ["rev-parse", "--is-inside-work-tree"]:
            return _completed(args, "true\n")
        if args == ["rev-parse", "HEAD"]:
            return _completed(args, f"{current_sha}\n")
        if args == ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"]:
            return _completed(args, "origin/main\n")
        if args == ["ls-remote", "origin", "refs/heads/main"]:
            return _completed(args, f"{latest_sha}\trefs/heads/main\n")
        if args == ["merge-base", "--is-ancestor", latest_sha, "HEAD"]:
            return _completed(args, "")
        return _completed(args, "", 1)

    monkeypatch.setattr(version_check, "_run_git_command", fake_git)

    result = version_check.check_for_update(Path("/repo"))

    assert result.status == "current"
    assert result.current == current_sha
    assert result.latest == latest_sha


def test_version_check_can_be_disabled(monkeypatch):
    monkeypatch.setenv(version_check.DISABLE_UPDATE_CHECK_ENV, "1")

    result = version_check.check_for_update(Path("/repo"))

    assert result.status == "disabled"
    assert version_check.format_update_notice(result) is None
