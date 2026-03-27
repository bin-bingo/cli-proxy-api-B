from __future__ import annotations

import asyncio
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .cliproxy import CLIProxyClient
from .config import settings
from .health import evaluate_auth_file
from .models import AuthRecord, PoolState, PoolSummary, utc_now
from .replenisher import run_replenish
from .storage import append_jsonl, read_json, read_jsonl_tail, write_json


class PoolMaintainerService:
    def __init__(self) -> None:
        self.client = CLIProxyClient()
        self._lock = asyncio.Lock()
        self._background_task: asyncio.Task | None = None
        self.state = self._load_state()

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
            "cliproxy_base_url": settings.cliproxy_base_url,
            "auth_dir": str(settings.auth_dir),
            "scan_interval_seconds": settings.scan_interval_seconds,
            "min_healthy_count": settings.min_healthy_count,
            "target_healthy_count": settings.target_healthy_count,
            "usage_exhaust_threshold": settings.usage_exhaust_threshold,
            "auto_scan_enabled": settings.auto_scan_enabled,
            "auto_replenish_enabled": settings.auto_replenish_enabled,
            "replenish_command_configured": bool(settings.replenish_command.strip()),
        }

    async def startup(self) -> None:
        if settings.auto_scan_enabled:
            self._background_task = asyncio.create_task(self._scan_loop())

    async def shutdown(self) -> None:
        if self._background_task:
            self._background_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._background_task

    async def _scan_loop(self) -> None:
        while True:
            try:
                await self.run_scan(trigger="auto")
            except Exception:
                pass
            await asyncio.sleep(settings.scan_interval_seconds)

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

    async def run_scan(self, trigger: str = "manual") -> PoolState:
        async with self._lock:
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

            records: list[AuthRecord] = []
            for path in sorted(settings.auth_dir.glob("*.json")):
                record = evaluate_auth_file(
                    path, global_signals, previous_failures=previous.get(path.name, 0)
                )
                records.append(record)

            summary = PoolSummary(
                total_count=len(records),
                healthy_count=sum(1 for item in records if item.status == "healthy"),
                degraded_count=sum(1 for item in records if item.status == "degraded"),
                dead_count=sum(1 for item in records if item.status == "dead"),
                unknown_count=sum(1 for item in records if item.status == "unknown"),
                last_scan_at=utc_now().isoformat(),
            )
            summary.needs_replenish = summary.healthy_count < settings.min_healthy_count
            summary.replenish_count = (
                max(0, settings.target_healthy_count - summary.healthy_count)
                if summary.needs_replenish
                else 0
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

            if settings.auto_replenish_enabled and summary.replenish_count > 0:
                replenish = run_replenish(summary.replenish_count)
                self.state.summary.last_replenish_at = replenish.executed_at
                self.state.summary.last_replenish_result = replenish.message
                self._record_history("replenish", replenish.to_dict())

            self._save_state()
            return self.state

    async def run_manual_replenish(self, count: int | None = None) -> dict[str, Any]:
        async with self._lock:
            desired = (
                count
                if count is not None
                else max(
                    0, settings.target_healthy_count - self.state.summary.healthy_count
                )
            )
            result = run_replenish(desired)
            self.state.summary.last_replenish_at = result.executed_at
            self.state.summary.last_replenish_result = result.message
            self._record_history("replenish", result.to_dict())
            self._save_state()
            return result.to_dict()

    def get_status(self) -> dict[str, Any]:
        return self.state.to_dict()

    def get_history(self, limit: int = 50) -> list[dict[str, Any]]:
        return read_jsonl_tail(settings.history_file, limit=limit)


import contextlib


service = PoolMaintainerService()
