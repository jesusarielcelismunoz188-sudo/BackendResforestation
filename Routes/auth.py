"""Rutas de autenticación delegadas a Supabase Auth."""
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from Models.schemas import (
    GoogleCodeExchangeRequest,
    LoginRequest,
    RegisterRequest,
)
from Services import supabase_auth_service

router = APIRouter(prefix="/auth", tags=["Autenticación"])
bearer_scheme = HTTPBearer(auto_error=False)


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest):
    """Crea una cuenta en Supabase Auth; no guarda usuarios en la base de la API."""
    return await supabase_auth_service.register(
        body.email,
        body.password,
        body.full_name,
    )


@router.post("/login")
async def login(body: LoginRequest):
    """Inicia sesión con correo y contraseña mediante Supabase Auth."""
    return await supabase_auth_service.login(body.email, body.password)


@router.get("/google")
async def google_login(
    code_challenge: str = Query(..., min_length=43, max_length=43),
):
    """Devuelve la URL de Supabase Auth para iniciar el flujo OAuth PKCE con Google."""
    return {
        "authorization_url": supabase_auth_service.google_authorization_url(
            code_challenge
        )
    }


@router.post("/google/callback")
async def google_callback(body: GoogleCodeExchangeRequest):
    """Canjea el código PKCE de Supabase por la sesión de la aplicación."""
    return await supabase_auth_service.exchange_google_code(
        body.code,
        body.code_verifier,
    )


async def require_authenticated_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> Any:
    """Requiere y valida un access token de Supabase."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Se requiere un token Bearer válido.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return await supabase_auth_service.get_user(credentials.credentials)
    except HTTPException as exc:
        if exc.status_code in {
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        }:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="El token de acceso no es válido o ha expirado.",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc
        raise


@router.get("/me")
async def get_current_user(
    user: Any = Depends(require_authenticated_user),
) -> Any:
    """Devuelve el usuario asociado al access token de Supabase."""
    return user
