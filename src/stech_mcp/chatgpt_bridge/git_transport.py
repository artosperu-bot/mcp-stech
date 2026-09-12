from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Callable


class GitTransportError(RuntimeError):
    pass


class GitTransport:
    def __init__(
        self,
        repo_path: str | Path,
        branch: str,
        *,
        timeout_seconds: int = 60,
        run_command: Callable[..., Any] = subprocess.run,
    ) -> None:
        self.repo_path = Path(repo_path)
        self.branch = str(branch or "").strip()
        self.timeout_seconds = max(int(timeout_seconds), 1)
        self.run_command = run_command
        if not self.branch:
            raise ValueError("git branch is required")

    def _run(self, args: list[str], *, allowed: set[int] | None = None) -> Any:
        result = self.run_command(
            args,
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds,
        )
        accepted = allowed or {0}
        if int(getattr(result, "returncode", 1)) not in accepted:
            detail = str(getattr(result, "stderr", "") or getattr(result, "stdout", "") or "git command failed").strip()
            raise GitTransportError(detail)
        return result

    def pull(self) -> None:
        current = self._run(["git", "branch", "--show-current"]).stdout.strip()
        if current != self.branch:
            raise GitTransportError(
                f"wrong git branch: expected {self.branch}, found {current or '<detached>'}"
            )
        self._run(["git", "pull", "--ff-only", "origin", self.branch])

    def commit_and_push(self) -> bool:
        self._run(["git", "add", "--", "research_bridge"])
        diff = self._run(["git", "diff", "--cached", "--quiet"], allowed={0, 1})
        if int(diff.returncode) == 0:
            return False
        self._run(["git", "commit", "-m", "chore: sync research bridge mailbox"])
        self._run(["git", "push", "origin", self.branch])
        return True
