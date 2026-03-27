from __future__ import annotations

import os
import shlex
import subprocess
from dataclasses import dataclass

from .config import settings
from .models import utc_now


@dataclass(slots=True)
class ReplenishResult:
    attempted: bool
    success: bool
    message: str
    command: str | None = None
    count: int = 0
    executed_at: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "attempted": self.attempted,
            "success": self.success,
            "message": self.message,
            "command": self.command,
            "count": self.count,
            "executed_at": self.executed_at,
        }


def run_replenish(count: int) -> ReplenishResult:
    command_template = settings.replenish_command.strip()
    if count <= 0:
        return ReplenishResult(
            False,
            True,
            "No replenish needed",
            count=0,
            executed_at=utc_now().isoformat(),
        )
    if not command_template:
        return ReplenishResult(
            False,
            False,
            "POOL_REPLENISH_COMMAND is not configured",
            count=count,
            executed_at=utc_now().isoformat(),
        )

    command = command_template.replace(settings.replenish_count_placeholder, str(count))
    env = os.environ.copy()
    env.setdefault("POOL_REQUESTED_COUNT", str(count))

    try:
        completed = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            env=env,
            cwd=str(settings.auth_dir.parent),
            timeout=max(300, count * 60),
        )
        output = (completed.stdout or completed.stderr or "").strip()
        success = completed.returncode == 0
        message = (
            output[:1200]
            if output
            else ("Command completed" if success else "Command failed")
        )
        return ReplenishResult(
            True,
            success,
            message,
            command=command,
            count=count,
            executed_at=utc_now().isoformat(),
        )
    except Exception as exc:
        return ReplenishResult(
            True,
            False,
            f"replenish exception: {exc}",
            command=command,
            count=count,
            executed_at=utc_now().isoformat(),
        )
