"""
Config/database.py
==================
Conexión a la base de datos PostgreSQL (Supabase).

¿Qué hace este archivo?
- Crea conexiones a la base de datos usando psycopg2.
- Tiene helpers para convertir los datos de PostgreSQL a JSON.

Para que funcione, necesitas una variable de entorno DATABASE_URL
en tu archivo .env con la URL de tu base de datos Supabase.
"""
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from uuid import UUID
from datetime import datetime, date
from decimal import Decimal
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")


def get_connection():
    """
    Crea y retorna una nueva conexión a la base de datos.
    Usa RealDictCursor para que los resultados sean diccionarios
    en vez de tuplas (más fácil de usar).
    """
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)


def serialize_row(row):
    """
    Convierte UN registro de la BD a un diccionario que se puede
    convertir a JSON.

    ¿Por qué? PostgreSQL retorna tipos especiales:
    - UUID → no se puede poner en JSON directamente
    - Decimal → tampoco
    - datetime → tampoco

    Entonces los convertimos a string, float y string ISO.
    """
    if row is None:
        return None
    result = {}
    for key, value in row.items():
        if isinstance(value, UUID):
            result[key] = str(value)
        elif isinstance(value, (datetime, date)):
            result[key] = value.isoformat()
        elif isinstance(value, Decimal):
            result[key] = float(value)
        else:
            result[key] = value
    return result


def serialize_rows(rows):
    """Convierte una LISTA de registros a diccionarios serializables."""
    return [serialize_row(row) for row in rows]
