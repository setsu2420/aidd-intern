"""Read-only update checks for local AIDD-Intern installations."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DISABLE_UPDATE_CHECK_ENV = "AIDD_INTERN_DISABLE_UPDATE_CHECK"
UPDATE_CHECK_TIMEOUT_ENV = "AIDD_INTERN_UPDATE_CHECK_TIMEOUT"
DEFAULT_TIMEOUT_SECONDS = 3.0

VersionStatus = Literal["current", "outdated", "unknown", "disabled"]


@dataclass(frozen=True)
class VersionCheckResult:
    status: VersionStatus
    source: str
    detail: str
    current: str | None = None
    latest: str | None = None
    update_command: str | None = None


def check_for_update(
    project_root: Path = PROJECT_ROOT,
    *,
    timeout: float | None = None,
) -> VersionCheckResult:
    """Compare this checkout with its configured GitHub branch.

    The check is intentionally read-only: it uses ``git ls-remote`` instead of
    ``git fetch`` so existing user checkouts, ``.env`` files, and local config
    files are never changed by the version check itself.
    """
    if _env_bool(DISABLE_UPDATE_CHECK_ENV):
        return VersionCheckResult(
            status="disabled",
            source="local",
            detail=f"update checks disabled by {DISABLE_UPDATE_CHECK_ENV}",
        )

    timeout = timeout if timeout is not None else _timeout_from_env()
    root = Path(project_root).resolve()
    if not _git_success(["rev-parse", "--is-inside-work-tree"], root, timeout):
        return VersionCheckResult(
            status="unknown",
            source="local",
            detail="not running from a Git checkout",
        )

    current = _git_output(["rev-parse", "HEAD"], root, timeout)
    if not current:
        return VersionCheckResult(
            status="unknown",
            source="local",
            detail="could not read the current Git revision",
        )

    remote, branch = _resolve_remote_branch(root, timeout)
    if not branch:
        return VersionCheckResult(
            status="unknown",
            source=remote or "origin",
            current=current,
            detail=(
                "could not determine the update branch; set AIDD_INTERN_UPDATE_BRANCH"
            ),
        )

    source = f"{remote}/{branch}"
    latest = _remote_head(remote, branch, root, timeout)
    if not latest:
        return VersionCheckResult(
            status="unknown",
            source=source,
            current=current,
            detail="could not read the remote Git revision",
        )

    if current == latest or _local_contains_remote(root, latest, timeout):
        return VersionCheckResult(
            status="current",
            source=source,
            current=current,
            latest=latest,
            detail=f"local checkout matches {source}",
        )

    return VersionCheckResult(
        status="outdated",
        source=source,
        current=current,
        latest=latest,
        detail=f"local checkout is behind {source}",
        update_command="scripts/update-local.sh",
    )


def format_update_notice(result: VersionCheckResult) -> str | None:
    if result.status != "outdated":
        return None
    current = _short_sha(result.current)
    latest = _short_sha(result.latest)
    command = result.update_command or "scripts/update-local.sh"
    return (
        f"AIDD-Intern update available: local {current} is behind "
        f"{result.source} {latest}.\n"
        f"Run `{command}` from the checkout root to update. Existing `.env`, "
        "user config, and local secrets are preserved."
    )


def _resolve_remote_branch(root: Path, timeout: float) -> tuple[str, str | None]:
    explicit_remote = os.environ.get("AIDD_INTERN_UPDATE_REMOTE")
    explicit_branch = os.environ.get("AIDD_INTERN_UPDATE_BRANCH")
    upstream = _git_output(
        ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
        root,
        timeout,
    )

    upstream_remote = None
    upstream_branch = None
    if upstream and "/" in upstream:
        upstream_remote, upstream_branch = upstream.split("/", 1)

    remote = explicit_remote or upstream_remote or "origin"
    branch = (
        explicit_branch
        or upstream_branch
        or _git_output(["branch", "--show-current"], root, timeout)
    )
    return remote, branch or None


def _remote_head(remote: str, branch: str, root: Path, timeout: float) -> str | None:
    output = _git_output(["ls-remote", remote, f"refs/heads/{branch}"], root, timeout)
    if not output:
        return None
    return output.split()[0] if output.split() else None


def _local_contains_remote(root: Path, latest: str, timeout: float) -> bool:
    return _git_success(["merge-base", "--is-ancestor", latest, "HEAD"], root, timeout)


def _git_success(args: list[str], root: Path, timeout: float) -> bool:
    result = _run_git_command(args, root, timeout)
    return result.returncode == 0


def _git_output(args: list[str], root: Path, timeout: float) -> str | None:
    result = _run_git_command(args, root, timeout)
    if result.returncode != 0:
        return None
    output = result.stdout.strip()
    return output or None


def _run_git_command(
    args: list[str], root: Path, timeout: float
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", "-C", str(root), *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(
            ["git", "-C", str(root), *args],
            returncode=1,
            stdout="",
            stderr=str(exc),
        )


def _timeout_from_env() -> float:
    raw = os.environ.get(UPDATE_CHECK_TIMEOUT_ENV)
    if not raw:
        return DEFAULT_TIMEOUT_SECONDS
    try:
        parsed = float(raw)
    except ValueError:
        return DEFAULT_TIMEOUT_SECONDS
    return parsed if parsed > 0 else DEFAULT_TIMEOUT_SECONDS


def _env_bool(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _short_sha(value: str | None) -> str:
    return value[:7] if value else "unknown"
