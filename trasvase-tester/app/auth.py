from __future__ import annotations

import hmac
import urllib.error
import urllib.request

from fastapi import HTTPException, Request


class RequestAuthenticator:
    def __init__(self, verify_url: str, internal_emulator_token: str):
        self.verify_url = verify_url
        self.internal_emulator_token = internal_emulator_token

    def require_operator(self, request: Request) -> None:
        cookie = request.headers.get("cookie")
        if not cookie:
            raise HTTPException(status_code=401, detail="Sesion protegida requerida")

        verification = urllib.request.Request(
            self.verify_url,
            method="GET",
            headers={"Cookie": cookie},
        )
        try:
            with urllib.request.urlopen(verification, timeout=2) as response:  # noqa: S310
                if response.status != 204:
                    raise HTTPException(status_code=401, detail="Sesion protegida invalida")
        except urllib.error.HTTPError as exc:
            if exc.code in {401, 403}:
                raise HTTPException(status_code=401, detail="Sesion protegida invalida") from exc
            raise HTTPException(status_code=503, detail="Validador de sesion no disponible") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise HTTPException(status_code=503, detail="Validador de sesion no disponible") from exc

    def require_operator_or_emulator(self, request: Request) -> None:
        supplied_token = request.headers.get("x-internal-emulator-token", "")
        if supplied_token and hmac.compare_digest(supplied_token, self.internal_emulator_token):
            return
        self.require_operator(request)
