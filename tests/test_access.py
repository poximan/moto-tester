import sys
from pathlib import Path

import pytest
from fastapi import HTTPException
from starlette.requests import Request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "trasvase-tester"))

from app.access import EdgeAccessGuard


def request_with_headers(**headers: str) -> Request:
    raw_headers = [
        (name.replace("_", "-").encode("ascii"), value.encode("ascii"))
        for name, value in headers.items()
    ]
    return Request({"type": "http", "headers": raw_headers})


@pytest.mark.parametrize("mode", ["secure", "protected"])
def test_edge_access_does_not_require_a_protected_session(mode: str):
    guard = EdgeAccessGuard("emulator-secret")

    guard.require_edge(request_with_headers(x_edge_mode=mode))


def test_direct_access_without_edge_marker_is_rejected():
    guard = EdgeAccessGuard("emulator-secret")

    with pytest.raises(HTTPException) as exc_info:
        guard.require_edge(request_with_headers())

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Acceso requerido a traves de edge-platform"


def test_internal_emulator_keeps_its_private_access():
    guard = EdgeAccessGuard("emulator-secret")

    guard.require_edge_or_emulator(
        request_with_headers(x_internal_emulator_token="emulator-secret")
    )


def test_invalid_internal_token_does_not_bypass_edge_access():
    guard = EdgeAccessGuard("emulator-secret")

    with pytest.raises(HTTPException) as exc_info:
        guard.require_edge_or_emulator(
            request_with_headers(x_internal_emulator_token="wrong")
        )

    assert exc_info.value.status_code == 403
