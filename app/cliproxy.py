from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .config import RuntimeSettings, settings


class CLIProxyClient:
    def __init__(self, runtime: RuntimeSettings) -> None:
        self.base_url = runtime.cliproxy_base_url.rstrip("/")
        self.management_key = runtime.cliproxy_management_key
        self.timeout = runtime.cliproxy_timeout_seconds

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.management_key:
            headers["Authorization"] = f"Bearer {self.management_key}"
            headers["X-Management-Key"] = self.management_key
        return headers

    def _request_json(self, path: str, managed: bool = True) -> tuple[int, Any]:
        url = f"{self.base_url}{path}"
        request = urllib.request.Request(
            url=url,
            headers=self._headers() if managed else {"Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read().decode("utf-8", errors="replace")
                return response.status, json.loads(body) if body else {}
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            try:
                data = json.loads(body) if body else {}
            except Exception:
                data = {"raw": body}
            return exc.code, data
        except Exception as exc:
            return 0, {"error": str(exc)}

    def list_auth_files(self) -> tuple[int, list[dict[str, Any]]]:
        status, data = self._request_json(settings.auth_files_endpoint)
        if isinstance(data, dict):
            files = data.get("files") or data.get("authFiles") or data.get("data") or []
        elif isinstance(data, list):
            files = data
        else:
            files = []
        normalized = [item for item in files if isinstance(item, dict)]
        return status, normalized

    def get_auth_status(self) -> tuple[int, dict[str, Any]]:
        status, data = self._request_json(settings.auth_status_endpoint)
        return status, data if isinstance(data, dict) else {"raw": data}

    def get_usage(self) -> tuple[int, dict[str, Any]]:
        status, data = self._request_json(settings.usage_endpoint)
        return status, data if isinstance(data, dict) else {"raw": data}

    def check_models(self) -> tuple[int, dict[str, Any]]:
        status, data = self._request_json(settings.models_endpoint, managed=False)
        return status, data if isinstance(data, dict) else {"raw": data}

    def delete_auth_file(self, name: str) -> tuple[int, dict[str, Any]]:
        encoded = urllib.parse.quote(name, safe="")
        url = f"{self.base_url}/v0/management/auth-files?name={encoded}"
        request = urllib.request.Request(url=url, headers=self._headers(), method="DELETE")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                text = response.read().decode("utf-8", errors="replace")
                parsed = json.loads(text) if text else {}
                return response.status, parsed if isinstance(parsed, dict) else {"raw": parsed}
        except urllib.error.HTTPError as exc:
            text = exc.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(text) if text else {}
            except Exception:
                parsed = {"raw": text}
            return exc.code, parsed if isinstance(parsed, dict) else {"raw": parsed}
        except Exception as exc:
            return 0, {"error": str(exc)}

    def post_api_call(
        self, payload: dict[str, Any], timeout: int | None = None
    ) -> tuple[int, dict[str, Any]]:
        url = f"{self.base_url}/v0/management/api-call"
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url=url,
            data=body,
            headers={**self._headers(), "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout or self.timeout) as response:
                text = response.read().decode("utf-8", errors="replace")
                parsed = json.loads(text) if text else {}
                return (
                    response.status,
                    parsed if isinstance(parsed, dict) else {"raw": parsed},
                )
        except urllib.error.HTTPError as exc:
            text = exc.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(text) if text else {}
            except Exception:
                parsed = {"raw": text}
            return exc.code, parsed if isinstance(parsed, dict) else {"raw": parsed}
        except Exception as exc:
            return 0, {"error": str(exc)}
