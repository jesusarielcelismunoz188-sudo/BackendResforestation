from Config.database import get_connection, serialize_row, serialize_rows
from typing import Optional, Dict, Any, List
from Models.schemas import registroCuenca
import json

def get_cuencas() -> List[Dict[str, Any]]:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""SELECT id, nombre, descripcion, elevacion_msnm, altitud_min_msnm, altitud_max_msnm,
                   ST_AsGeoJSON(geom)::json AS geom, created_at
            FROM cuencas
            ORDER BY nombre ASC""")
        filas = cur.fetchall()
        return serialize_rows(filas)
    except Exception as e:
        raise e
    finally:
        conn.close()

def create_cuenca(cuenca: registroCuenca) -> None:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO cuencas (nombre, descripcion, elevacion_msnm, altitud_min_msnm, altitud_max_msnm, geom)
            VALUES (%s, %s, %s, %s, %s, ST_GeomFromGeoJSON(%s))
        """, (
            cuenca.nombre,
            cuenca.descripcion,
            cuenca.elevacion_msnm,
            cuenca.altitud_min_msnm,
            cuenca.altitud_max_msnm,
            json.dumps(cuenca.geom)  # Convertir el dict a JSON string
        ))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()
