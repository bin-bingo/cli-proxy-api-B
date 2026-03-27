from __future__ import annotations

import asyncio
import contextlib
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .cliproxy import CLIProxyClient
from .config import (
    RuntimeSettings,
    load_runtime_settings,
    save_runtime_settings,
    settings,
)
from .health import apply_probe_result, evaluate_auth_file
from datetime import datetime, timedelta, timezone
from .models import AuthRecord, PoolState, PoolSummary, utc_now
from .replenisher import run_replenish
from .storage import append_jsonl, read_json, read_jsonl_tail, write_json


class PoolMaintainerService:
    def __init__(self) -> None:
        self.runtime_settings = load_runtime_settings()
        self.client = CLIProxyClient(self.runtime_settings)
        self._lock = asyncio.Lock()
        self._background_task: asyncio.Task | None = None
        self.state = self._load_state()

    def _refresh_client(self) -> None:
        self.client = CLIProxyClient(self.runtime_settings)

    def _load_state(self) -> PoolState:
        raw = read_json(settings.state_file, {})
        summary_raw = raw.get("summary", {}) if isinstance(raw, dict) else {}
        records_raw = raw.get("auth_records", []) if isinstance(raw, dict) else []
        history = read_jsonl_tail(settings.history_file, limit=100)

        summary = PoolSummary(
            **{
                k: v
                for k, v in summary_raw.items()
                if k in PoolSummary.__dataclass_fields__
            }
        )
        records: list[AuthRecord] = []
        for item in records_raw:
            if isinstance(item, dict):
                payload = {
                    k: v
                    for k, v in item.items()
                    if k in AuthRecord.__dataclass_fields__
                }
                records.append(AuthRecord(**payload))
        return PoolState(
            summary=summary,
            auth_records=records,
            history_tail=history,
            settings_snapshot=self.settings_snapshot(),
        )

    def settings_snapshot(self) -> dict[str, Any]:
        return {
            "cliproxy_base_url": self.runtime_settings.cliproxy_base_url,
            "auth_dir": self.runtime_settings.auth_dir,
            "scan_interval_seconds": settings.scan_interval_seconds,
            "min_healthy_count": self.runtime_settings.min_healthy_count,
            "target_healthy_count": self.runtime_settings.target_healthy_count,
            "usage_exhaust_threshold": self.runtime_settings.usage_exhaust_threshold,
            "auto_scan_enabled": self.runtime_settings.auto_scan_enabled,
            "auto_replenish_enabled": self.runtime_settings.auto_replenish_enabled,
            "replenish_command_configured": bool(
                self.runtime_settings.replenish_command.strip()
            ),
            "cliproxy_management_key_configured": bool(
                self.runtime_settings.cliproxy_management_key.strip()
            ),
            "registration_key_configured": bool(
                self.runtime_settings.registration_key.strip()
            ),
            "registration_base_url": self.runtime_settings.registration_base_url,
            "replenish_mode": self.runtime_settings.replenish_mode,
            "replenish_concurrency": self.runtime_settings.replenish_concurrency,
            "replenish_email_type": self.runtime_settings.replenish_email_type,
            "replenish_auto_cpa": self.runtime_settings.replenish_auto_cpa,
        }

    async def startup(self) -> None:
        if self.runtime_settings.auto_scan_enabled:
            self._background_task = asyncio.create_task(self._scan_loop())

    async def shutdown(self) -> None:
        if self._background_task:
            self._background_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._background_task

    async def _scan_loop(self) -> None:
        while True:
            try:
                await asyncio.to_thread(self.scan_once_sync, "auto")
            except Exception:
                pass
            await asyncio.sleep(settings.scan_interval_seconds)

    @staticmethod
    def _as_str(value: Any, default: str) -> str:
        if value is None:
            return default
        return str(value)

    @staticmethod
    def _as_int(value: Any, default: int) -> int:
        if value is None:
            return default
        return int(value)

    @staticmethod
    def _as_float(value: Any, default: float) -> float:
        if value is None:
            return default
        return float(value)

    async def update_runtime_settings(self, updates: dict[str, Any]) -> RuntimeSettings:
        async with self._lock:
            merged = self.runtime_settings.to_dict()
            for key, value in updates.items():
                if key not in RuntimeSettings.__dataclass_fields__:
                    continue
                merged[key] = value

            runtime = RuntimeSettings(
                cliproxy_base_url=self._as_str(
                    merged.get("cliproxy_base_url"),
                    self.runtime_settings.cliproxy_base_url,
                ),
                cliproxy_management_key=self._as_str(
                    merged.get("cliproxy_management_key"),
                    self.runtime_settings.cliproxy_management_key,
                ),
                cliproxy_timeout_seconds=self._as_int(
                    merged.get("cliproxy_timeout_seconds"),
                    self.runtime_settings.cliproxy_timeout_seconds,
                ),
                auth_dir=self._as_str(
                    merged.get("auth_dir"),
                    self.runtime_settings.auth_dir,
                ),
                min_healthy_count=self._as_int(
                    merged.get("min_healthy_count"),
                    self.runtime_settings.min_healthy_count,
                ),
                target_healthy_count=self._as_int(
                    merged.get("target_healthy_count"),
                    self.runtime_settings.target_healthy_count,
                ),
                usage_exhaust_threshold=self._as_float(
                    merged.get("usage_exhaust_threshold"),
                    self.runtime_settings.usage_exhaust_threshold,
                ),
                auto_scan_enabled=bool(
                    merged.get(
                        "auto_scan_enabled", self.runtime_settings.auto_scan_enabled
                    )
                ),
                auto_replenish_enabled=bool(
                    merged.get(
                        "auto_replenish_enabled",
                        self.runtime_settings.auto_replenish_enabled,
                    )
                ),
                replenish_command=self._as_str(
                    merged.get("replenish_command"),
                    self.runtime_settings.replenish_command,
                ),
                registration_key=self._as_str(
                    merged.get("registration_key"),
                    self.runtime_settings.registration_key,
                ),
                registration_base_url=self._as_str(
                    merged.get("registration_base_url"),
                    self.runtime_settings.registration_base_url,
                ),
            )
            self.runtime_settings = runtime
            save_runtime_settings(runtime)
            self._refresh_client()
            self.state.settings_snapshot = self.settings_snapshot()
            self._save_state()
            return runtime

    def _previous_failure_map(self) -> dict[str, int]:
        return {
            item.name: item.consecutive_failures for item in self.state.auth_records
        }

    def _record_history(self, event_type: str, payload: dict[str, Any]) -> None:
        event = {"timestamp": utc_now().isoformat(), "event": event_type, **payload}
        append_jsonl(settings.history_file, event)
        self.state.history_tail = read_jsonl_tail(settings.history_file, limit=100)

    def _save_state(self) -> None:
        self.state.settings_snapshot = self.settings_snapshot()
        write_json(settings.state_file, self.state.to_dict())

    def scan_once_sync(self, trigger: str = "manual", concurrency: int = 8) -> PoolState:
        auth_files_status, auth_files_remote = self.client.list_auth_files()
        auth_status_code, auth_status = self.client.get_auth_status()
        usage_code, usage = self.client.get_usage()
        models_code, _models = self.client.check_models()

        previous = self._previous_failure_map()
        global_signals = {
            "auth_status_ok": 200 <= auth_status_code < 300,
            "usage_ok": 200 <= usage_code < 300,
            "proxy_ok": 200 <= models_code < 300,
            "remote_auth_files_status": auth_files_status,
            "remote_auth_files_count": len(auth_files_remote),
            "auth_status": auth_status,
            "usage": usage,
        }

        auth_dir = Path(self.runtime_settings.auth_dir)
        files = sorted(auth_dir.glob("*.json"))
        previous_failures_map = self._previous_failure_map()
        base_records = [
            (path, evaluate_auth_file(path, global_signals, previous_failures=previous_failures_map.get(path.name, 0)))
            for path in files
        ]

        def probe_item(item: tuple[Path, AuthRecord]) -> AuthRecord:
            path, record = item
            if not self.runtime_settings.cliproxy_management_key:
                return record
            probe_payload = {
                "authIndex": path.name,
                "method": "GET",
                "url": "https://chatgpt.com/backend-api/wham/usage",
                "header": {
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "User-Agent": "Mozilla/5.0",
                },
            }
            probe_status, probe_result = self.client.post_api_call(probe_payload, timeout=4)
            if probe_status > 0:
                return apply_probe_result(record, probe_status, probe_result)
            record.metadata["probe_status_code"] = 0
            record.metadata["probe_error"] = str(probe_result.get("error") or "probe timeout")
            if record.status != "dead":
                record.status = "degraded"
                record.healthy = False
                record.reason = "probe timeout/failed"
            return record

        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, concurrency)) as executor:
            results = list(executor.map(probe_item, base_records))
        records = results

        healthy_count = sum(1 for item in records if item.status == "healthy")
        pending_count = sum(1 for item in records if item.status == "pending")
        degraded_count = sum(1 for item in records if item.status == "degraded")
        dead_count = sum(1 for item in records if item.status == "dead")
        unknown_count = sum(1 for item in records if item.status == "unknown")

        previous_total = self.state.summary.total_count if self.state.summary else 0
        current_total = len(records)
        added_count = max(0, current_total - previous_total)
        removed_count = max(0, previous_total - current_total)

        summary = PoolSummary(
            total_count=current_total,
            healthy_count=healthy_count,
            pending_count=pending_count,
            degraded_count=degraded_count,
            dead_count=dead_count,
            unknown_count=unknown_count,
            added_count=added_count,
            removed_count=removed_count,
            cleanup_mode="未启用自动清除",
            last_scan_at=utc_now().isoformat(),
        )
        cooldown_until = None
        in_flight = self.state.summary.in_flight_replenish_count if self.state.summary else 0
        raw_cooldown = self.state.summary.replenish_cooldown_until if self.state.summary else None
        if raw_cooldown:
            try:
                cooldown_until = datetime.fromisoformat(raw_cooldown)
            except Exception:
                cooldown_until = None
        if cooldown_until and datetime.now(timezone.utc) >= cooldown_until:
            cooldown_until = None
            in_flight = 0

        available_count = summary.total_count - summary.dead_count + in_flight
        summary.in_flight_replenish_count = in_flight
        summary.replenish_cooldown_until = cooldown_until.isoformat() if cooldown_until else None
        summary.needs_replenish = (
            available_count < self.runtime_settings.min_healthy_count
        )
        summary.replenish_count = (
            max(0, self.runtime_settings.target_healthy_count - available_count)
            if summary.needs_replenish
            else 0
        )
        summary.last_scan_result = (
            f"健康 {healthy_count} / 待确认 {pending_count} / 差 {degraded_count} / 失效 {dead_count}"
        )

        self.state.auth_records = records
        self.state.summary = summary
        self._record_history(
            "scan",
            {
                "trigger": trigger,
                "summary": summary.to_dict(),
                "global_signals": {
                    "auth_status_code": auth_status_code,
                    "usage_code": usage_code,
                    "models_code": models_code,
                    "remote_auth_files_status": auth_files_status,
                    "remote_auth_files_count": len(auth_files_remote),
                },
            },
        )

        if self.runtime_settings.auto_replenish_enabled and summary.replenish_count > 0 and not summary.replenish_cooldown_until:
            replenish = run_replenish(summary.replenish_count, self.runtime_settings)
            self.state.summary.last_replenish_at = replenish.executed_at
            self.state.summary.last_replenish_result = replenish.message
            if replenish.success:
                cooldown_until = datetime.now(timezone.utc) + timedelta(minutes=10)
                self.state.summary.in_flight_replenish_count = summary.replenish_count
                self.state.summary.replenish_cooldown_until = cooldown_until.isoformat()
            self._record_history("replenish", replenish.to_dict())

        self._save_state()
        return self.state

    async def run_scan(self, trigger: str = "manual") -> PoolState:
        async with self._lock:
            return await asyncio.to_thread(self.scan_once_sync, trigger)

    async def run_manual_replenish(self, count: int | None = None) -> dict[str, Any]:
        async with self._lock:
            desired = (
                count
                if count is not None
                else max(
                    0,
                    self.runtime_settings.target_healthy_count
                    - self.state.summary.healthy_count,
                )
            )
            result = run_replenish(desired, self.runtime_settings)
            self.state.summary.last_replenish_at = result.executed_at
            self.state.summary.last_replenish_result = result.message
            if result.success and desired > 0:
                cooldown_until = datetime.now(timezone.utc) + timedelta(minutes=10)
                self.state.summary.in_flight_replenish_count = desired
                self.state.summary.replenish_cooldown_until = cooldown_until.isoformat()
            self._record_history("replenish", result.to_dict())
            self._save_state()
            return result.to_dict()

    def get_status(self) -> dict[str, Any]:
        return self.state.to_dict()

    def get_history(self, limit: int = 50) -> list[dict[str, Any]]:
        return read_jsonl_tail(settings.history_file, limit=limit)

    def test_cpa_connection(self) -> dict[str, Any]:
        status_code, payload = self.client.list_auth_files()
        ok = 200 <= status_code < 300
        result = {
            "target": "cpa",
            "ok": ok,
            "status_code": status_code,
            "message": "CPA connection ok" if ok else "CPA connection failed",
            "details": {
                "base_url": self.runtime_settings.cliproxy_base_url,
                "auth_files_count": len(payload),
            },
            "checked_at": utc_now().isoformat(),
        }
        self._record_history("connection_test", result)
        self._save_state()
        return result

    def test_registration_connection(self) -> dict[str, Any]:
        base_url = self.runtime_settings.registration_base_url.strip().rstrip("/")
        if not base_url:
            result = {
                "target": "registration",
                "ok": False,
                "status_code": 0,
                "message": "Registration base URL is not configured",
                "details": {},
                "checked_at": utc_now().isoformat(),
            }
            self._record_history("connection_test", result)
            self._save_state()
            return result

        url = f"{base_url}/login"
        request = urllib.request.Request(url=url, headers={"Accept": "text/html"})
        try:
            with urllib.request.urlopen(request, timeout=self.runtime_settings.cliproxy_timeout_seconds) as response:
                result = {
                    "target": "registration",
                    "ok": 200 <= response.status < 300,
                    "status_code": response.status,
                    "message": "Registration connection ok" if 200 <= response.status < 300 else "Registration connection returned non-OK status",
                    "details": {"url": url},
                    "checked_at": utc_now().isoformat(),
                }
        except urllib.error.HTTPError as exc:
            result = {
                "target": "registration",
                "ok": False,
                "status_code": exc.code,
                "message": f"Registration connection failed with HTTP {exc.code}",
                "details": {"url": url},
                "checked_at": utc_now().isoformat(),
            }
        except Exception as exc:
            result = {
                "target": "registration",
                "ok": False,
                "status_code": 0,
                "message": f"Registration connection error: {exc}",
                "details": {"url": url},
                "checked_at": utc_now().isoformat(),
            }

        self._record_history("connection_test", result)
        self._save_state()
        return result


service = PoolMaintainerService()
