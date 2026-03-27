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


def _safe_json_value(value: Any) -> Any:
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        return value
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        return None


def _extract_used_percent_from_probe(probe_payload: dict[str, Any]) -> float | None:
    body = _safe_json_value(probe_payload.get("body"))
    if not isinstance(body, dict):
        return None
    rate_limit = body.get("rate_limit")
    if isinstance(rate_limit, dict):
        primary = rate_limit.get("primary_window")
        if isinstance(primary, dict):
            value = primary.get("used_percent")
            if isinstance(value, (int, float)):
                return float(value)
    return None


def _is_invalid_probe(probe_payload: dict[str, Any], status_code: int | None) -> bool:
    haystacks = [
        str(probe_payload.get("error") or "").lower(),
        str(probe_payload.get("message") or "").lower(),
        str(probe_payload.get("body") or "").lower(),
        str(probe_payload.get("raw") or "").lower(),
    ]
    if isinstance(status_code, int) and status_code == 401:
        return True
    return any(
        token in text
        for text in haystacks
        for token in (
            "token_revoked",
            "refresh_token_reused",
            "unauthorized",
            "invalidated oauth token",
        )
    )


def apply_probe_matrix(
    record: AuthRecord, probe_results: dict[str, tuple[int, dict[str, Any]]]
) -> AuthRecord:
    serializable: dict[str, Any] = {}
    for name, (probe_status, payload) in probe_results.items():
        status_code = payload.get("status_code", probe_status)
        serializable[name] = {
            "probe_status": probe_status,
            "status_code": status_code,
            "error": payload.get("error") or payload.get("message"),
        }
        if _is_invalid_probe(
            payload, status_code if isinstance(status_code, int) else None
        ):
            record.healthy = False
            record.status = "dead"
            record.reason = f"probe invalid ({name})"
            record.metadata["probe_results"] = serializable
            return record

    used_percent = None
    for name in ("wham_usage", "codex_usage"):
        result = probe_results.get(name)
        if not result:
            continue
        _, payload = result
        used_percent = _extract_used_percent_from_probe(payload)
        if used_percent is not None:
            break
    if used_percent is not None:
        record.quota_used_percent = used_percent
        if used_percent >= settings.usage_exhaust_threshold:
            record.healthy = False
            record.status = "degraded"
            record.reason = f"used_percent high ({used_percent:.1f}%)"

    required_ok = False
    required_failed = []
    for name in ("me", "wham_usage"):
        if name not in probe_results:
            required_failed.append(name)
            continue
        probe_status, payload = probe_results[name]
        status_code = payload.get("status_code", probe_status)
        if isinstance(status_code, int) and 200 <= status_code < 300:
            required_ok = True
        else:
            required_failed.append(name)

    if record.status == "dead":
        record.metadata["probe_results"] = serializable
        return record

    if required_ok and record.status != "degraded":
        record.healthy = True
        record.status = "healthy"
        record.reason = "live probe ok"
    elif required_failed:
        record.healthy = False
        record.status = "pending"
        record.reason = f"probe pending ({', '.join(required_failed)})"

    record.metadata["probe_results"] = serializable
    return record


def evaluate_auth_file(
    path: Path,
    global_signals: dict[str, Any],
    previous_failures: int = 0,
    remote_meta: dict[str, Any] | None = None,
) -> AuthRecord:
    payload = _safe_load_auth(path)
    remote = remote_meta or {}
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
    else:
        remote_status = str(remote.get("status") or "").strip().lower()
        remote_unavailable = bool(remote.get("unavailable"))
        remote_message = str(remote.get("status_message") or "").lower()
        if remote_status == "error" or remote_unavailable:
            if any(
                key in remote_message
                for key in (
                    "401",
                    "token_revoked",
                    "unauthorized",
                    "refresh_token_reused",
                )
            ):
                status = "dead"
                healthy = False
                reason = "cpa marked invalid"
        if (
            healthy
            and quota_percent is not None
            and quota_percent >= settings.usage_exhaust_threshold
        ):
            status = "degraded"
            healthy = False
            reason = f"quota threshold reached ({quota_percent:.1f}%)"

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
            "remote_status": remote.get("status"),
            "remote_unavailable": remote.get("unavailable"),
            "remote_status_message": remote.get("status_message"),
            "remote_auth_index": remote.get("auth_index"),
            "remote_account_id": (remote.get("id_token") or {}).get(
                "chatgpt_account_id"
            )
            if isinstance(remote.get("id_token"), dict)
            else None,
        },
    )


def apply_probe_result(
    record: AuthRecord, probe_status: int, probe_payload: dict[str, Any]
) -> AuthRecord:
    status_code = probe_payload.get("status_code", probe_status)
    body_text = str(probe_payload.get("body") or probe_payload.get("raw") or "")
    error_text = str(probe_payload.get("error") or probe_payload.get("message") or "")

    record.metadata["probe_status_code"] = status_code
    record.metadata["probe_error"] = error_text

    if (
        probe_status == 200
        and isinstance(status_code, int)
        and 200 <= status_code < 300
    ):
        if record.status != "dead":
            record.healthy = True
            record.status = "healthy"
            record.reason = "live probe ok"
        lowered = body_text.lower()
        if "limit_reached" in lowered and "true" in lowered:
            record.healthy = False
            record.status = "degraded"
            record.reason = "rate limit reached"
        elif "refresh_token_reused" in lowered:
            record.healthy = False
            record.status = "dead"
            record.reason = "refresh token reused"
        elif "unauthorized" in lowered:
            record.healthy = False
            record.status = "dead"
            record.reason = "probe unauthorized"
        return record

    if record.status == "dead":
        return record

    if isinstance(status_code, int) and status_code == 401:
        record.healthy = False
        record.status = "dead"
        record.reason = "probe unauthorized"
        record.consecutive_failures += 1
    elif isinstance(status_code, int) and status_code in {403, 429}:
        record.healthy = False
        record.status = "degraded"
        record.reason = f"probe limited ({status_code})"
    elif probe_status == 0:
        record.healthy = False
        record.status = "pending"
        record.reason = "probe timeout/failed"
    elif error_text:
        record.healthy = False
        record.status = "pending"
        record.reason = f"probe failed: {error_text[:120]}"
    else:
        record.healthy = False
        record.status = "degraded"
        record.reason = f"probe failed ({status_code})"
    return record
