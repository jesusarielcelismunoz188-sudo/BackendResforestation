"""Subida y consulta de archivos privados en Supabase Storage."""
import logging
import os
from pathlib import PurePosixPath, PureWindowsPath
import re
from typing import Any
from urllib.parse import quote, urlparse
from uuid import UUID, uuid4

import httpx
from dotenv import load_dotenv
from fastapi import HTTPException

from Config.database import get_connection, serialize_row, serialize_rows
from Config.storage import MAX_UPLOAD_BYTES, SIGNED_URL_TTL_SECONDS, STORAGE_BUCKET

load_dotenv()
logger = logging.getLogger(__name__)

ALLOWED_TYPES = {
    "application/pdf": {".pdf"},
    "image/jpeg": {".jpg", ".jpeg"},
    "image/png": {".png"},
    "image/webp": {".webp"},
}
CATEGORY_ENTITY_TYPES = {
    "project_document": {"proyecto"},
    "field_photo": {"predio", "lote"},
    "soil_report": {"lote"},
}
CATEGORY_MIME_TYPES = {
    "project_document": {"application/pdf"},
    "field_photo": {"image/jpeg", "image/png", "image/webp"},
    "soil_report": set(ALLOWED_TYPES),
}
ENTITY_QUERIES = {
    "proyecto": "SELECT id FROM proyectos WHERE id = %s",
    "predio": "SELECT id FROM predios WHERE id = %s",
    "lote": "SELECT id FROM lotes WHERE id = %s",
}


def _storage_settings() -> tuple[str, str]:
    url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    api_key = (
        os.getenv("SUPABASE_PUBLISHABLE_KEY")
        or os.getenv("SUPABASE_ANON_KEY")
        or ""
    ).strip()
    if not url or not api_key:
        raise HTTPException(
            status_code=503,
            detail="Supabase Storage no está configurado.",
        )
    parsed_url = urlparse(url)
    if (
        parsed_url.scheme not in ("http", "https")
        or not parsed_url.hostname
        or parsed_url.username
        or parsed_url.password
        or (
            parsed_url.scheme == "http"
            and parsed_url.hostname not in {"localhost", "127.0.0.1", "::1"}
        )
    ):
        raise HTTPException(
            status_code=503,
            detail="La URL remota de Supabase Storage debe usar HTTPS.",
        )
    return url, api_key


def _safe_filename(filename: str) -> str:
    basename = PureWindowsPath(PurePosixPath(filename).name).name
    extension = PurePosixPath(basename).suffix.lower()
    stem = PurePosixPath(basename).stem
    stem = re.sub(r"[^A-Za-z0-9_-]+", "-", stem).strip("-_")[:80] or "archivo"
    return f"{stem}{extension}"


def _validate_file(file_name: str, content_type: str, data: bytes) -> str:
    content_type = content_type.lower().split(";", 1)[0].strip()
    extension = PurePosixPath(file_name).suffix.lower()
    if content_type not in ALLOWED_TYPES or extension not in ALLOWED_TYPES[content_type]:
        raise HTTPException(
            status_code=415,
            detail="Tipo de archivo no permitido. Usa PDF, JPG, PNG o WebP.",
        )
    signatures = {
        "application/pdf": data.startswith(b"%PDF-"),
        "image/jpeg": data.startswith(b"\xff\xd8\xff"),
        "image/png": data.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/webp": (
            len(data) >= 12
            and data.startswith(b"RIFF")
            and data[8:12] == b"WEBP"
        ),
    }
    if not signatures[content_type]:
        raise HTTPException(
            status_code=415,
            detail="El contenido del archivo no coincide con su tipo declarado.",
        )
    return content_type


async def _storage_request(
    method: str,
    path: str,
    access_token: str,
    *,
    payload: Any = None,
    content: bytes | None = None,
    content_type: str | None = None,
):
    base_url, api_key = _storage_settings()
    headers = {
        "apikey": api_key,
        "Authorization": f"Bearer {access_token}",
    }
    if content_type:
        headers["Content-Type"] = content_type
    if method == "POST" and content is not None:
        headers["x-upsert"] = "false"
    request_body = {}
    if payload is not None:
        request_body["json"] = payload
    elif content is not None:
        request_body["content"] = content
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(
                method,
                f"{base_url}/storage/v1{path}",
                headers=headers,
                **request_body,
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=504,
            detail="Supabase Storage tardó demasiado en responder.",
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail="No fue posible comunicarse con Supabase Storage.",
        ) from exc
    if response.is_error:
        try:
            error_body = response.json()
            detail = error_body.get("message") or error_body.get("error")
        except (ValueError, AttributeError):
            detail = None
        if response.status_code in (401, 403):
            raise HTTPException(
                status_code=403,
                detail="Supabase Storage no autorizó el acceso. Verifica las políticas del bucket.",
            )
        raise HTTPException(
            status_code=502,
            detail=detail or "Supabase Storage rechazó la operación.",
        )
    if not response.content:
        return {}
    try:
        return response.json()
    except ValueError:
        return {}


def _validate_entity(entity_type: str, entity_id: UUID):
    query = ENTITY_QUERIES.get(entity_type)
    if query is None:
        raise HTTPException(status_code=422, detail="Tipo de entidad no permitido.")
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(query, (str(entity_id),))
        if cur.fetchone() is None:
            raise HTTPException(status_code=404, detail="No se encontró la entidad asociada.")
    finally:
        conn.close()


def _metadata_row(file_id: UUID, user_id: UUID):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, entity_type, entity_id, category, original_name,
                   content_type, size_bytes, object_path, created_at
            FROM archivos_adjuntos
            WHERE id = %s AND uploaded_by = %s
            """,
            (str(file_id), str(user_id)),
        )
        row = cur.fetchone()
        return serialize_row(row) if row else None
    finally:
        conn.close()


async def upload_file(
    *,
    entity_type: str,
    entity_id: UUID,
    category: str,
    original_name: str,
    content_type: str,
    data: bytes,
    user: dict[str, Any],
    access_token: str,
):
    allowed_entities = CATEGORY_ENTITY_TYPES.get(category)
    if allowed_entities is None or entity_type not in allowed_entities:
        raise HTTPException(
            status_code=422,
            detail="La categoría no corresponde al tipo de entidad.",
        )
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"El archivo supera el límite de {MAX_UPLOAD_BYTES} bytes.",
        )
    if not data:
        raise HTTPException(status_code=400, detail="El archivo está vacío.")

    user_id = UUID(str(user["id"]))
    clean_name = _safe_filename(original_name)
    content_type = _validate_file(clean_name, content_type, data)
    if content_type not in CATEGORY_MIME_TYPES[category]:
        raise HTTPException(
            status_code=415,
            detail="El tipo de archivo no está permitido para esta categoría.",
        )
    _validate_entity(entity_type, entity_id)

    object_path = (
        f"{user_id}/{entity_type}/{entity_id}/{category}/"
        f"{uuid4().hex}_{clean_name}"
    )
    encoded_path = quote(object_path, safe="/")
    await _storage_request(
        "POST",
        f"/object/{quote(STORAGE_BUCKET, safe='')}/{encoded_path}",
        access_token,
        content=data,
        content_type=content_type,
    )

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO archivos_adjuntos (
                entity_type, entity_id, category, original_name,
                content_type, size_bytes, object_path, uploaded_by
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, entity_type, entity_id, category, original_name,
                      content_type, size_bytes, created_at
            """,
            (
                entity_type,
                str(entity_id),
                category,
                clean_name,
                content_type,
                len(data),
                object_path,
                str(user_id),
            ),
        )
        metadata = serialize_row(cur.fetchone())
        conn.commit()
        return metadata
    except Exception as exc:
        conn.rollback()
        try:
            await _storage_request(
                "DELETE",
                f"/object/{quote(STORAGE_BUCKET, safe='')}",
                access_token,
                payload={"prefixes": [object_path]},
            )
        except HTTPException:
            logger.exception(
                "No se pudo limpiar el objeto Storage %s luego de fallar el registro de metadatos",
                object_path,
            )
        raise HTTPException(
            status_code=500,
            detail="El archivo se subió, pero no se pudo registrar su metadata.",
        ) from exc
    finally:
        conn.close()


def list_files(
    *,
    entity_type: str,
    entity_id: UUID,
    user_id: UUID,
    category: str | None,
):
    if entity_type not in ENTITY_QUERIES:
        raise HTTPException(status_code=422, detail="Tipo de entidad no permitido.")
    _validate_entity(entity_type, entity_id)
    conn = get_connection()
    try:
        cur = conn.cursor()
        query = """
            SELECT id, entity_type, entity_id, category, original_name,
                   content_type, size_bytes, created_at
            FROM archivos_adjuntos
            WHERE entity_type = %s AND entity_id = %s AND uploaded_by = %s
        """
        params: list[Any] = [entity_type, str(entity_id), str(user_id)]
        if category:
            query += " AND category = %s"
            params.append(category)
        query += " ORDER BY created_at DESC"
        cur.execute(query, params)
        return serialize_rows(cur.fetchall())
    finally:
        conn.close()


async def create_signed_url(
    file_id: UUID,
    user_id: UUID,
    access_token: str,
):
    metadata = _metadata_row(file_id, user_id)
    if metadata is None:
        raise HTTPException(status_code=404, detail="Archivo no encontrado.")
    encoded_path = quote(metadata["object_path"], safe="/")
    response = await _storage_request(
        "POST",
        f"/object/sign/{quote(STORAGE_BUCKET, safe='')}/{encoded_path}",
        access_token,
        payload={"expiresIn": SIGNED_URL_TTL_SECONDS},
    )
    signed_path = response.get("signedURL") or response.get("signedUrl")
    if not signed_path:
        logger.error("Supabase Storage devolvió una URL firmada vacía para archivo %s", file_id)
        raise HTTPException(status_code=502, detail="Supabase Storage no devolvió un enlace firmado.")
    if signed_path.startswith("http://") or signed_path.startswith("https://"):
        signed_url = signed_path
    else:
        base_url, _ = _storage_settings()
        signed_url = f"{base_url}/storage/v1{signed_path if signed_path.startswith('/') else '/' + signed_path}"
    return {
        "id": str(file_id),
        "url": signed_url,
        "expires_in": SIGNED_URL_TTL_SECONDS,
    }


async def delete_file(file_id: UUID, user_id: UUID, access_token: str):
    metadata = _metadata_row(file_id, user_id)
    if metadata is None:
        return None
    await _storage_request(
        "DELETE",
        f"/object/{quote(STORAGE_BUCKET, safe='')}",
        access_token,
        payload={"prefixes": [metadata["object_path"]]},
    )
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM archivos_adjuntos WHERE id = %s AND uploaded_by = %s RETURNING id",
            (str(file_id), str(user_id)),
        )
        row = cur.fetchone()
        conn.commit()
        return str(row["id"]) if row else None
    except Exception:
        conn.rollback()
        logger.exception("El objeto Storage se eliminó pero falló el borrado de metadata para %s", file_id)
        raise HTTPException(
            status_code=500,
            detail="El archivo se eliminó del bucket, pero no se pudo actualizar su metadata.",
        )
    finally:
        conn.close()
