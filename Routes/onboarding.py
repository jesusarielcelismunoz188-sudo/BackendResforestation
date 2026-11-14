"""Endpoints aislados para la creación y consulta del espacio personal."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from psycopg2.errors import UniqueViolation

from Models.schemas import LoteOnboardingCreate, PredioOnboardingCreate
from Routes.auth import require_authenticated_user
from Services import onboarding_service

router = APIRouter(tags=["Onboarding"])


@router.get("/lotes")
def listar_lotes(user=Depends(require_authenticated_user)):
    return onboarding_service.list_lotes(user)


@router.post("/predios", status_code=status.HTTP_201_CREATED)
def crear_predio(
    body: PredioOnboardingCreate,
    user=Depends(require_authenticated_user),
):
    try:
        return onboarding_service.create_predio(body, user)
    except UniqueViolation as exc:
        if exc.diag.constraint_name != "predios_subcuenca_id_nombre_key":
            raise
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe un predio con ese nombre en esta ubicación.",
        ) from exc


@router.post("/predios/{predio_id}/lotes", status_code=status.HTTP_201_CREATED)
def crear_lote(
    predio_id: UUID,
    body: LoteOnboardingCreate,
    user=Depends(require_authenticated_user),
):
    try:
        lote = onboarding_service.create_lote(predio_id, body, user)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    if lote is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Predio no encontrado.")
    return lote


@router.get("/lotes/{lote_id}/proyectos")
def listar_proyectos(lote_id: UUID, user=Depends(require_authenticated_user)):
    proyectos = onboarding_service.list_proyectos(lote_id, user)
    if proyectos is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lote no encontrado.")
    return proyectos
