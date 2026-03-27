from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"


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
