"""Rutas de autenticación delegadas a Supabase Auth."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from Models.schemas import LoginRequest, RegisterRequest
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


@router.get("/me")
async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
):
    """Valida el access token con Supabase y devuelve el usuario autenticado."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Se requiere un token Bearer válido.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return await supabase_auth_service.get_user(credentials.credentials)
