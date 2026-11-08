"""API de adjuntos privados para proyectos, predios y lotes."""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.security import HTTPAuthorizationCredentials

from Config.storage import MAX_UPLOAD_BYTES
from Routes.auth import bearer_scheme, require_authenticated_user
from Services import storage_service

router = APIRouter(tags=["Archivos"])


async def require_authenticated_context(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    user=Depends(require_authenticated_user),
):
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail="Se requiere un token Bearer válido.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return {"user": user, "access_token": credentials.credentials}


@router.post("/archivos", status_code=201)
async def subir_archivo(
    tipo_entidad: str = Query(..., description="proyecto | predio | lote"),
    id_entidad: UUID = Query(...),
    categoria: str = Query(
        ...,
        description="project_document | field_photo | soil_report",
    ),
    file: UploadFile = File(...),
    context=Depends(require_authenticated_context),
):
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"El archivo supera el límite de {MAX_UPLOAD_BYTES} bytes.",
        )
    return await storage_service.upload_file(
        entity_type=tipo_entidad,
        entity_id=id_entidad,
        category=categoria,
        original_name=file.filename or "archivo",
        content_type=file.content_type or "",
        data=data,
        user=context["user"],
        access_token=context["access_token"],
    )


@router.get("/archivos")
def listar_archivos(
    tipo_entidad: str = Query(..., description="proyecto | predio | lote"),
    id_entidad: UUID = Query(...),
    categoria: Optional[str] = Query(None),
    context=Depends(require_authenticated_context),
):
    return storage_service.list_files(
        entity_type=tipo_entidad,
        entity_id=id_entidad,
        user_id=UUID(str(context["user"]["id"])),
        category=categoria,
    )


@router.get("/archivos/{archivo_id}/url")
async def obtener_url_firmada(
    archivo_id: UUID,
    context=Depends(require_authenticated_context),
):
    return await storage_service.create_signed_url(
        archivo_id,
        UUID(str(context["user"]["id"])),
        context["access_token"],
    )


@router.delete("/archivos/{archivo_id}")
async def eliminar_archivo(
    archivo_id: UUID,
    context=Depends(require_authenticated_context),
):
    deleted_id = await storage_service.delete_file(
        archivo_id,
        UUID(str(context["user"]["id"])),
        context["access_token"],
    )
    if deleted_id is None:
        raise HTTPException(status_code=404, detail="Archivo no encontrado.")
    return {"id": deleted_id, "mensaje": "Archivo eliminado del bucket."}
