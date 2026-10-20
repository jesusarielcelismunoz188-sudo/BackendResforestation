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
