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

def create_cuenca(cuenca: registroCuenca, user_id: Optional[str] = None) -> Dict[str, Any]:
    conn = get_connection()
    try:
        cur = conn.cursor()

        geom_val = json.dumps(cuenca.geom) if cuenca.geom else None

        cur.execute("""
            INSERT INTO cuencas (
                nombre,
                descripcion,
                elevacion_msnm,
                altitud_min_msnm,
                altitud_max_msnm,
                geom
            )
            VALUES (
                %s, %s, %s, %s, %s,
                CASE WHEN %s::text IS NOT NULL THEN ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326) ELSE NULL END
            )
            RETURNING id, nombre, descripcion, elevacion_msnm, altitud_min_msnm, altitud_max_msnm,
                    ST_AsGeoJSON(geom)::json AS geom, created_at
        """, (
            cuenca.nombre,
            cuenca.descripcion,
            cuenca.elevacion_msnm,
            cuenca.altitud_min_msnm,
            cuenca.altitud_max_msnm,
            geom_val,
            geom_val
        ))
        nueva_cuenca = cur.fetchone()
        cuenca_id = nueva_cuenca["id"]

        # Si se envió el user_id del creador, lo registramos como admin en cuenca_miembros
        if user_id:
            cur.execute("""
                INSERT INTO cuenca_miembros (cuenca_id, perfil_id, rol)
                VALUES (%s, %s, 'admin')
                ON CONFLICT (cuenca_id, perfil_id) DO UPDATE SET rol = 'admin'
            """, (str(cuenca_id), str(user_id)))

        conn.commit()
        return serialize_row(nueva_cuenca)
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()
