from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
RUNTIME_SETTINGS_FILE = DATA_DIR / "runtime_settings.json"


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    return int(value)


@dataclass(slots=True)
class Settings:
    app_name: str = os.environ.get("POOL_APP_NAME", "CLIProxyAPI-B Pool Maintainer")
    host: str = os.environ.get("POOL_HOST", "127.0.0.1")
    port: int = _env_int("POOL_PORT", 8420)
    debug: bool = _env_bool("POOL_DEBUG", True)

    cliproxy_base_url: str = os.environ.get(
        "CLIPROXY_BASE_URL", "http://127.0.0.1:8317"
    )
    cliproxy_management_key: str = os.environ.get("CLIPROXY_MANAGEMENT_KEY", "")
    cliproxy_timeout_seconds: int = _env_int("CLIPROXY_TIMEOUT_SECONDS", 20)

    auth_files_endpoint: str = os.environ.get(
        "CLIPROXY_AUTH_FILES_ENDPOINT", "/v0/management/auth-files"
    )
    auth_status_endpoint: str = os.environ.get(
        "CLIPROXY_AUTH_STATUS_ENDPOINT", "/v0/management/get-auth-status"
    )
    usage_endpoint: str = os.environ.get(
        "CLIPROXY_USAGE_ENDPOINT", "/v0/management/usage"
    )
    models_endpoint: str = os.environ.get("CLIPROXY_MODELS_ENDPOINT", "/v1/models")

    auth_dir: Path = Path(
        os.environ.get("CLIPROXY_AUTH_DIR", "/home/claw/projects/cli-proxy-api/auths")
    )
    state_file: Path = Path(
        os.environ.get("POOL_STATE_FILE", str(DATA_DIR / "pool_state.json"))
    )
    history_file: Path = Path(
        os.environ.get("POOL_HISTORY_FILE", str(DATA_DIR / "pool_history.jsonl"))
    )

    scan_interval_seconds: int = _env_int("POOL_SCAN_INTERVAL_SECONDS", 300)
    min_healthy_count: int = _env_int("POOL_MIN_HEALTHY_COUNT", 20)
    target_healthy_count: int = _env_int("POOL_TARGET_HEALTHY_COUNT", 30)
    unhealthy_grace_scans: int = _env_int("POOL_UNHEALTHY_GRACE_SCANS", 2)
    probe_timeout_seconds: int = _env_int("POOL_PROBE_TIMEOUT_SECONDS", 12)
    usage_exhaust_threshold: float = float(
        os.environ.get("POOL_USAGE_EXHAUST_THRESHOLD", "95")
    )
    auto_replenish_enabled: bool = _env_bool("POOL_AUTO_REPLENISH_ENABLED", False)
    auto_scan_enabled: bool = _env_bool("POOL_AUTO_SCAN_ENABLED", True)

    replenish_command: str = os.environ.get("POOL_REPLENISH_COMMAND", "")
    replenish_count_placeholder: str = os.environ.get(
        "POOL_REPLENISH_COUNT_PLACEHOLDER", "{count}"
    )


settings = Settings()
settings.state_file.parent.mkdir(parents=True, exist_ok=True)


@dataclass(slots=True)
class RuntimeSettings:
    cliproxy_base_url: str = settings.cliproxy_base_url
    cliproxy_management_key: str = settings.cliproxy_management_key
    cliproxy_timeout_seconds: int = settings.cliproxy_timeout_seconds
    auth_dir: str = str(settings.auth_dir)
    min_healthy_count: int = settings.min_healthy_count
    target_healthy_count: int = settings.target_healthy_count
    usage_exhaust_threshold: float = settings.usage_exhaust_threshold
    auto_scan_enabled: bool = settings.auto_scan_enabled
    auto_replenish_enabled: bool = settings.auto_replenish_enabled
    replenish_command: str = settings.replenish_command
    registration_key: str = os.environ.get("REGISTRATION_KEY", "")
    registration_base_url: str = os.environ.get("REGISTRATION_BASE_URL", "")

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def load_runtime_settings() -> RuntimeSettings:
    if not RUNTIME_SETTINGS_FILE.exists():
        runtime = RuntimeSettings()
        save_runtime_settings(runtime)
        return runtime
    try:
        raw = json.loads(RUNTIME_SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        raw = {}
    if not isinstance(raw, dict):
        raw = {}
    payload = {
        key: value
        for key, value in raw.items()
        if key in RuntimeSettings.__dataclass_fields__
    }
    runtime = RuntimeSettings(**payload)
    save_runtime_settings(runtime)
    return runtime


def save_runtime_settings(runtime: RuntimeSettings) -> None:
    RUNTIME_SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    RUNTIME_SETTINGS_FILE.write_text(
        json.dumps(runtime.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
