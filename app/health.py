from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import settings
from .models import AuthRecord, utc_now


def _safe_load_auth(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        return {"_parse_error": str(exc)}


def _pick_email(name: str, payload: dict[str, Any]) -> str:
    for key in ("email", "username", "account", "name"):
        value = payload.get(key)
        if isinstance(value, str) and "@" in value:
            return value
    return name.removesuffix(".json")


def _pick_type(payload: dict[str, Any]) -> str:
    for key in ("type", "provider", "kind"):
        value = payload.get(key)
        if isinstance(value, str):
            return value
    return "codex"


def _pick_quota_percent(payload: dict[str, Any]) -> float | None:
    candidates = [
        payload.get("usage_percent"),
        payload.get("used_percent"),
        payload.get("quota_used_percent"),
    ]
    usage = payload.get("usage")
    if isinstance(usage, dict):
        candidates.extend(
            [usage.get("used_percent"), usage.get("percentage"), usage.get("percent")]
        )
    for item in candidates:
        if isinstance(item, (int, float)):
            return float(item)
        if isinstance(item, str):
            raw = item.strip().rstrip("%")
            try:
                return float(raw)
            except ValueError:
                continue
    return None


def evaluate_auth_file(
    path: Path, global_signals: dict[str, Any], previous_failures: int = 0
) -> AuthRecord:
    payload = _safe_load_auth(path)
    parse_error = payload.get("_parse_error")
    quota_percent = _pick_quota_percent(payload)
    auth_status_ok = bool(global_signals.get("auth_status_ok"))
    usage_ok = bool(global_signals.get("usage_ok"))
    proxy_ok = bool(global_signals.get("proxy_ok"))

    reason = ""
    status = "healthy"
    healthy = True
    failures = previous_failures

    if parse_error:
        status = "dead"
        healthy = False
        reason = f"parse_error: {parse_error}"
    elif not payload.get("access_token") and not payload.get("id_token"):
        status = "dead"
        healthy = False
        reason = "missing access_token/id_token"
    elif (
        quota_percent is not None and quota_percent >= settings.usage_exhaust_threshold
    ):
        status = "degraded"
        healthy = False
        reason = f"quota threshold reached ({quota_percent:.1f}%)"
    elif not auth_status_ok or not usage_ok or not proxy_ok:
        status = "degraded"
        healthy = False
        reason = "global cliproxy signals unhealthy"

    if healthy:
        failures = 0
    else:
        failures += 1
        if failures > settings.unhealthy_grace_scans:
            status = "dead"

    return AuthRecord(
        name=path.name,
        path=str(path),
        type=_pick_type(payload),
        email=_pick_email(path.name, payload),
        healthy=healthy,
        status=status,
        reason=reason,
        quota_used_percent=quota_percent,
        proxy_ok=proxy_ok,
        auth_status_ok=auth_status_ok,
        usage_ok=usage_ok,
        consecutive_failures=failures,
        last_checked_at=utc_now().isoformat(),
        metadata={
            "has_access_token": bool(payload.get("access_token")),
            "has_refresh_token": bool(payload.get("refresh_token")),
        },
    )
