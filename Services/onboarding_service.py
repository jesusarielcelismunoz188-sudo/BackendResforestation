"""Persistencia de los espacios personales creados durante el onboarding."""
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID, uuid4

from Config.database import get_connection, serialize_row, serialize_rows
from Models.schemas import LoteOnboardingCreate, PredioOnboardingCreate


def _user_id(user: dict[str, Any]) -> str:
    return str(UUID(str(user["id"])))


def _ensure_profile(cur, user: dict[str, Any], user_id: str) -> None:
    metadata = user.get("user_metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    name = (
        metadata.get("full_name")
        or metadata.get("name")
        or user.get("email")
        or user_id
    )
    if not isinstance(name, str) or not name.strip():
        name = user_id
    avatar_url = metadata.get("avatar_url")
    if not isinstance(avatar_url, str):
        avatar_url = None
    cur.execute(
        """
        INSERT INTO perfiles (id, nombre_completo, avatar_url)
        VALUES (%s, %s, %s)
        ON CONFLICT (id) DO UPDATE
        SET nombre_completo = EXCLUDED.nombre_completo,
            avatar_url = COALESCE(EXCLUDED.avatar_url, perfiles.avatar_url)
        """,
        (user_id, name.strip(), avatar_url),
    )


def _ensure_personal_subcuenca(
    cur,
    user_id: str,
    municipio: str,
    departamento: str,
) -> str:
    workspace_name = f"Espacio personal {user_id}"
    cur.execute(
        """
        INSERT INTO cuencas (nombre, descripcion, es_espacio_personal)
        VALUES (%s, 'Espacio personal creado durante el onboarding.', true)
        ON CONFLICT (nombre) DO UPDATE
        SET es_espacio_personal = true
        RETURNING id
        """,
        (workspace_name,),
    )
    cuenca_id = cur.fetchone()["id"]
    cur.execute(
        """
        INSERT INTO cuenca_miembros (cuenca_id, perfil_id, rol)
        VALUES (%s, %s, 'admin')
        ON CONFLICT (cuenca_id, perfil_id) DO UPDATE SET rol = 'admin'
        """,
        (str(cuenca_id), user_id),
    )

    subcuenca_name = f"{municipio}, {departamento}"
    cur.execute(
        """
        INSERT INTO subcuencas (cuenca_id, nombre)
        VALUES (%s, %s)
        ON CONFLICT (cuenca_id, nombre) DO UPDATE SET nombre = EXCLUDED.nombre
        RETURNING id
        """,
        (str(cuenca_id), subcuenca_name),
    )
    return str(cur.fetchone()["id"])


def _new_lote(
    cur,
    predio_id: str,
    nombre: str,
    area_ha: Decimal,
) -> dict[str, Any]:
    cur.execute(
        """
        INSERT INTO lotes (predio_id, codigo, nombre, area_ha)
        VALUES (%s, %s, %s, %s)
        RETURNING id, predio_id, nombre, area_ha
        """,
        (predio_id, f"ONB-{uuid4().hex}", nombre, area_ha),
    )
    return serialize_row(cur.fetchone())


def create_predio(body: PredioOnboardingCreate, user: dict[str, Any]) -> dict[str, Any]:
    user_id = _user_id(user)
    conn = get_connection()
    try:
        cur = conn.cursor()
        _ensure_profile(cur, user, user_id)
        subcuenca_id = _ensure_personal_subcuenca(
            cur,
            user_id,
            body.municipio,
            body.departamento,
        )
        cur.execute(
            """
            INSERT INTO predios (
                subcuenca_id, nombre, municipio, departamento, area_ha, created_by
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id, nombre, municipio, departamento, area_ha
            """,
            (
                subcuenca_id,
                body.nombre,
                body.municipio,
                body.departamento,
                body.area_ha,
                user_id,
            ),
        )
        predio = serialize_row(cur.fetchone())
        lote = _new_lote(
            cur,
            predio["id"],
            body.primer_lote.nombre,
            body.primer_lote.area_ha,
        )
        lote.update(
            {
                "predio_nombre": predio["nombre"],
                "municipio": predio["municipio"],
                "departamento": predio["departamento"],
            }
        )
        conn.commit()
        return {"predio": predio, "lote": lote}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def list_lotes(user: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    user_id = _user_id(user)
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT l.id, COALESCE(l.nombre, l.codigo) AS nombre, l.predio_id,
                   p.nombre AS predio_nombre, l.area_ha, p.municipio, p.departamento
            FROM lotes l
            JOIN predios p ON p.id = l.predio_id
            JOIN subcuencas s ON s.id = p.subcuenca_id
            JOIN cuenca_miembros cm ON cm.cuenca_id = s.cuenca_id
            WHERE cm.perfil_id = %s
            ORDER BY p.nombre, l.nombre, l.codigo
            """,
            (user_id,),
        )
        return {"lotes": serialize_rows(cur.fetchall())}
    finally:
        conn.close()


def create_lote(
    predio_id: UUID,
    body: LoteOnboardingCreate,
    user: dict[str, Any],
) -> Optional[dict[str, Any]]:
    user_id = _user_id(user)
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT p.id, p.nombre, p.municipio, p.departamento, p.area_ha
            FROM predios p
            JOIN subcuencas s ON s.id = p.subcuenca_id
            JOIN cuenca_miembros cm ON cm.cuenca_id = s.cuenca_id
            WHERE p.id = %s AND cm.perfil_id = %s
            FOR UPDATE OF p
            """,
            (str(predio_id), user_id),
        )
        predio = cur.fetchone()
        if predio is None:
            return None
        if predio["area_ha"] is not None and body.area_ha > predio["area_ha"]:
            raise ValueError("El área del lote no puede superar la del predio.")

        lote = _new_lote(cur, str(predio["id"]), body.nombre, body.area_ha)
        lote.update(
            {
                "predio_nombre": predio["nombre"],
                "municipio": predio["municipio"],
                "departamento": predio["departamento"],
            }
        )
        conn.commit()
        return lote
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def list_proyectos(
    lote_id: UUID,
    user: dict[str, Any],
) -> Optional[dict[str, list[dict[str, Any]]]]:
    user_id = _user_id(user)
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT 1
            FROM lotes l
            JOIN predios p ON p.id = l.predio_id
            JOIN subcuencas s ON s.id = p.subcuenca_id
            JOIN cuenca_miembros cm ON cm.cuenca_id = s.cuenca_id
            WHERE l.id = %s AND cm.perfil_id = %s
            """,
            (str(lote_id), user_id),
        )
        if cur.fetchone() is None:
            return None

        cur.execute(
            """
            SELECT pr.id, pr.lote_id, pr.nombre, pr.fase
            FROM proyectos pr
            WHERE pr.lote_id = %s
            ORDER BY pr.created_at DESC, pr.id
            """,
            (str(lote_id),),
        )
        return {"proyectos": serialize_rows(cur.fetchall())}
    finally:
        conn.close()
