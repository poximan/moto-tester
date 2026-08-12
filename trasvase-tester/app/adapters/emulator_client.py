from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


class EmulatorClientError(RuntimeError):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class EmulatorClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"} if payload is not None else {}
        request = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=3) as response:  # noqa: S310
                result = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise EmulatorClientError(exc.code, detail) from exc
        except Exception as exc:  # noqa: BLE001
            raise EmulatorClientError(
                502,
                f"Servicio experto no disponible: {exc}",
            ) from exc
        if not isinstance(result, dict):
            raise EmulatorClientError(502, "Servicio experto devolvio un contrato invalido")
        return result

    def safe_state(self) -> dict[str, Any]:
        try:
            return self.request("GET", "/state")
        except EmulatorClientError as exc:
            return {"last_error": exc.detail}
