from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass

from .config import RuntimeSettings, settings
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


def _build_replenish_command(count: int, runtime: RuntimeSettings) -> str:
    base_url = runtime.registration_base_url.rstrip("/")
    if not base_url:
        return ""
    payload = {
        "count": count,
        "email_service_type": runtime.replenish_email_type,
        "auto_upload_cpa": runtime.replenish_auto_cpa,
        "mode": runtime.replenish_mode,
        "concurrency": runtime.replenish_concurrency,
    }
    import json as _json
    body = _json.dumps(payload, ensure_ascii=False)
    return f"curl -s -X POST {base_url}/api/registration/batch -H 'Content-Type: application/json' -d '{body}'"


def run_replenish(count: int, runtime: RuntimeSettings) -> ReplenishResult:
    if count <= 0:
        return ReplenishResult(
            False,
            True,
            "No replenish needed",
            count=0,
            executed_at=utc_now().isoformat(),
        )

    command = _build_replenish_command(count, runtime)

    if not command:
        return ReplenishResult(
            False,
            False,
            "Registration base URL is not configured",
            count=count,
            executed_at=utc_now().isoformat(),
        )
    env = os.environ.copy()
    env.setdefault("POOL_REQUESTED_COUNT", str(count))
    if runtime.registration_key:
        env["REGISTRATION_KEY"] = runtime.registration_key
    if runtime.cliproxy_management_key:
        env.setdefault("CLIPROXY_MANAGEMENT_KEY", runtime.cliproxy_management_key)
    if runtime.registration_base_url:
        env["REGISTRATION_BASE_URL"] = runtime.registration_base_url

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
