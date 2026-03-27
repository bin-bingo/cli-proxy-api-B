from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat()


@dataclass(slots=True)
class AuthRecord:
    name: str
    path: str
    type: str = ""
    email: str = ""
    healthy: bool = False
    status: str = "unknown"
    reason: str = ""
    quota_used_percent: float | None = None
    proxy_ok: bool | None = None
    auth_status_ok: bool | None = None
    usage_ok: bool | None = None
    last_checked_at: str | None = None
    consecutive_failures: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PoolSummary:
    total_count: int = 0
    healthy_count: int = 0
    pending_count: int = 0
    degraded_count: int = 0
    dead_count: int = 0
    unknown_count: int = 0
    in_flight_replenish_count: int = 0
    replenish_cooldown_until: str | None = None
    needs_replenish: bool = False
    replenish_count: int = 0
    last_scan_at: str | None = None
    last_replenish_at: str | None = None
    last_replenish_result: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PoolState:
    summary: PoolSummary = field(default_factory=PoolSummary)
    auth_records: list[AuthRecord] = field(default_factory=list)
    history_tail: list[dict[str, Any]] = field(default_factory=list)
    settings_snapshot: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary.to_dict(),
            "auth_records": [item.to_dict() for item in self.auth_records],
            "history_tail": self.history_tail,
            "settings_snapshot": self.settings_snapshot,
        }
