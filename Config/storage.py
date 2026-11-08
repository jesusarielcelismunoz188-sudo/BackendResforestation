"""Configuración no secreta del bucket privado de archivos."""
import os

STORAGE_BUCKET = os.getenv("SUPABASE_STORAGE_BUCKET", "reforestacion-archivos").strip()
MAX_UPLOAD_BYTES = int(os.getenv("STORAGE_MAX_FILE_SIZE_BYTES", str(10 * 1024 * 1024)))
SIGNED_URL_TTL_SECONDS = int(os.getenv("STORAGE_SIGNED_URL_TTL_SECONDS", "3600"))

if not STORAGE_BUCKET or MAX_UPLOAD_BYTES <= 0 or SIGNED_URL_TTL_SECONDS <= 0:
    raise RuntimeError("La configuración de Supabase Storage no es válida.")
