"""Cliente mínimo para delegar autenticación de usuarios a Supabase Auth."""
import os
from typing import Any, Optional
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv
from fastapi import HTTPException, status

load_dotenv()


def _settings() -> tuple[str, str]:
    url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    api_key = (
        os.getenv("SUPABASE_PUBLISHABLE_KEY")
        or os.getenv("SUPABASE_ANON_KEY")
        or ""
    ).strip()

    if not url or not api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="La autenticación no está configurada en el servidor.",
        )
    parsed_url = urlparse(url)
    if (
        parsed_url.scheme not in ("http", "https")
        or not parsed_url.hostname
        or parsed_url.username
        or parsed_url.password
    ):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="La URL de autenticación configurada no es válida.",
        )
    if parsed_url.scheme == "http" and parsed_url.hostname not in {
        "localhost",
        "127.0.0.1",
        "::1",
    }:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="La autenticación remota requiere una URL HTTPS.",
        )
    return url, api_key


async def _request(
    method: str,
    path: str,
    *,
    payload: Optional[dict[str, Any]] = None,
    access_token: Optional[str] = None,
    invalid_credentials: bool = False,
) -> Any:
    url, api_key = _settings()
    headers = {"apikey": api_key, "Content-Type": "application/json"}
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.request(
                method,
                f"{url}/auth/v1{path}",
                headers=headers,
                json=payload,
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="El servicio de autenticación no respondió a tiempo.",
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="No fue posible comunicarse con el servicio de autenticación.",
        ) from exc

    try:
        data = response.json()
    except ValueError:
        data = {}

    if response.is_error:
        if invalid_credentials and response.status_code in (400, 401):
            error_status = status.HTTP_401_UNAUTHORIZED
            message = "Correo o contraseña incorrectos."
        else:
            error_status = response.status_code
            message = "El servicio de autenticación rechazó la solicitud."
            if isinstance(data, dict):
                message = data.get("msg") or data.get("message") or message
        raise HTTPException(status_code=error_status, detail=message)

    return data


async def register(email: str, password: str, full_name: Optional[str]) -> Any:
    metadata = {"full_name": full_name} if full_name else {}
    return await _request(
        "POST",
        "/signup",
        payload={
            "email": email,
            "password": password,
            "data": metadata,
        },
    )


async def login(email: str, password: str) -> Any:
    return await _request(
        "POST",
        "/token?grant_type=password",
        payload={"email": email, "password": password},
        invalid_credentials=True,
    )


async def get_user(access_token: str) -> Any:
    return await _request("GET", "/user", access_token=access_token)
