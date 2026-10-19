"""
Routes/mapa.py
===============
Controladores para el módulo de mapa y zonas.

Rutas definidas:
┌──────────────────────────────────────────────────┬──────────────────────────────┐
│ Ruta                                             │ Qué hace                     │
├──────────────────────────────────────────────────┼──────────────────────────────┤
│ GET  /mapa/capas                                 │ Capas base (tiles externos)  │
│ GET  /lotes/{id}/ndvi                            │ Proxy NDVI (opcional)        │
│ GET  /lotes/{id}/zonas-mapa                      │ GeoJSON de zonas del lote    │
│ POST /lotes/{id}/zonas-mapa                      │ Crear zona                   │
│ PATCH  /zonas-mapa/{id}                          │ Actualizar zona              │
│ DELETE /zonas-mapa/{id}                          │ Eliminar zona                │
│ POST /lotes/{id}/zonas-mapa/generar-franja       │ Auto-generar franja riparia  │
└──────────────────────────────────────────────────┴──────────────────────────────┘
"""
import json
from fastapi import APIRouter, HTTPException, Query
from Config.database import get_connection, serialize_row, serialize_rows
from Models.schemas import ZonaMapaCreate, ZonaMapaUpdate

router = APIRouter(tags=["Mapa"])


# ══════════════════════════════════════════════
# GET /mapa/capas
# ══════════════════════════════════════════════
@router.get("/mapa/capas")
def obtener_capas():
    """
    Retorna la configuración de capas base para el mapa.

    Estas son URLs de proveedores EXTERNOS (no están en la BD).
    El frontend las usa para cargar tiles (imágenes del mapa).

    Nota: Algunas requieren API keys que se configuran en el frontend.
    """
    return {
        "capas": [
            {
                "id": "topografica",
                "nombre": "Topográfica",
                "tipo": "xyz",
                "url": "https://tile.opentopomap.org/{z}/{x}/{y}.png",
                "atribucion": "© OpenTopoMap"
            },
            {
                "id": "satelital",
                "nombre": "Satelital",
                "tipo": "xyz",
                "url": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
                "atribucion": "© Esri"
            },
            {
                "id": "osm",
                "nombre": "OpenStreetMap",
                "tipo": "xyz",
                "url": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
                "atribucion": "© OpenStreetMap contributors"
            },
            {
                "id": "ndvi",
                "nombre": "NDVI (Vegetación)",
                "tipo": "wms",
                "url": "https://services.sentinel-hub.com/ogc/wms/{INSTANCE_ID}",
                "nota": "Requiere cuenta en Sentinel Hub. Reemplazar {INSTANCE_ID}."
            },
        ]
    }


# ══════════════════════════════════════════════
# GET /lotes/{lote_id}/ndvi
# ══════════════════════════════════════════════
@router.get("/lotes/{lote_id}/ndvi")
def obtener_ndvi(
    lote_id: str,
    fecha: str = Query(default=None, description="Fecha ISO (YYYY-MM-DD)")
):
    """
    Endpoint opcional: proxy al proveedor de NDVI.

    En producción, esto consultaría Sentinel Hub o Google Earth Engine,
    cachearía el resultado y devolvería el valor promedio.

    Por ahora retorna un placeholder.
    """
    return {
        "lote_id": lote_id,
        "fecha": fecha,
        "ndvi_promedio": None,
        "mensaje": "Endpoint opcional. Configurar proveedor NDVI (Sentinel Hub / GEE)."
    }


# ══════════════════════════════════════════════
# GET /lotes/{lote_id}/zonas-mapa
# ══════════════════════════════════════════════
@router.get("/lotes/{lote_id}/zonas-mapa")
def obtener_zonas_mapa(
    lote_id: str,
    tipo: str = Query(default=None, description="Filtrar por tipo de zona")
):
    """
    Retorna las zonas del lote en formato GeoJSON.

    Tipos posibles:
    - siembra_prioritaria
    - franja_riparia
    - corredor_biologico
    """
    conn = get_connection()
    try:
        cur = conn.cursor()

        query = """
            SELECT id, tipo, etiqueta,
                   ST_AsGeoJSON(geom)::json AS geometria
            FROM zonas_mapa
            WHERE lote_id = %s
        """
        params = [str(lote_id)]

        if tipo:
            query += " AND tipo = %s"
            params.append(tipo)

        cur.execute(query, params)
        zonas = cur.fetchall()
        features = []
        for zona in zonas:
            features.append({
                "type": "Feature",
                "id": str(zona["id"]),
                "properties": {
                    "tipo": zona["tipo"],
                    "etiqueta": zona["etiqueta"],
                },
                "geometry": zona["geometria"]
            })

        return {
            "type": "FeatureCollection",
            "features": features
        }
    finally:
        conn.close()


# ══════════════════════════════════════════════
# POST /lotes/{lote_id}/zonas-mapa
# ══════════════════════════════════════════════
@router.post("/lotes/{lote_id}/zonas-mapa")
def crear_zona_mapa(lote_id: str, body: ZonaMapaCreate):
    """Crea una nueva zona en el mapa del lote."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        geom_json = json.dumps(body.geom)

        cur.execute("""
            INSERT INTO zonas_mapa (lote_id, tipo, etiqueta, geom)
            VALUES (%s, %s, %s, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326))
            RETURNING id, tipo, etiqueta, ST_AsGeoJSON(geom)::json AS geometria
        """, (str(lote_id), body.tipo, body.etiqueta, geom_json))

        zona = cur.fetchone()
        conn.commit()

        return {
            "type": "Feature",
            "id": str(zona["id"]),
            "properties": {
                "tipo": zona["tipo"],
                "etiqueta": zona["etiqueta"],
            },
            "geometry": zona["geometria"]
        }
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=f"Error al crear zona: {str(e)}")
    finally:
        conn.close()


# ══════════════════════════════════════════════
# PATCH /zonas-mapa/{zona_id}
# ══════════════════════════════════════════════
@router.patch("/zonas-mapa/{zona_id}")
def actualizar_zona_mapa(zona_id: str, body: ZonaMapaUpdate):
    """Actualiza parcialmente una zona del mapa."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        campos = []
        valores = []

        if body.tipo is not None:
            campos.append("tipo = %s")
            valores.append(body.tipo)

        if body.etiqueta is not None:
            campos.append("etiqueta = %s")
            valores.append(body.etiqueta)

        if body.geom is not None:
            campos.append("geom = ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)")
            valores.append(json.dumps(body.geom))

        if not campos:
            raise HTTPException(status_code=400, detail="No se enviaron campos para actualizar")

        valores.append(str(zona_id))

        cur.execute(f"""
            UPDATE zonas_mapa
            SET {', '.join(campos)}
            WHERE id = %s
            RETURNING id, tipo, etiqueta, ST_AsGeoJSON(geom)::json AS geometria
        """, valores)

        zona = cur.fetchone()
        if not zona:
            raise HTTPException(status_code=404, detail="Zona no encontrada")

        conn.commit()

        return {
            "type": "Feature",
            "id": str(zona["id"]),
            "properties": {
                "tipo": zona["tipo"],
                "etiqueta": zona["etiqueta"],
            },
            "geometry": zona["geometria"]
        }
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=f"Error: {str(e)}")
    finally:
        conn.close()


# ══════════════════════════════════════════════
# DELETE /zonas-mapa/{zona_id}
# ══════════════════════════════════════════════
@router.delete("/zonas-mapa/{zona_id}")
def eliminar_zona_mapa(zona_id: str):
    """Elimina una zona del mapa."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM zonas_mapa WHERE id = %s RETURNING id",
            (str(zona_id),)
        )
        deleted = cur.fetchone()
        if not deleted:
            raise HTTPException(status_code=404, detail="Zona no encontrada")

        conn.commit()
        return {"mensaje": "Zona eliminada", "id": str(deleted["id"])}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


# ══════════════════════════════════════════════
# POST /lotes/{lote_id}/zonas-mapa/generar-franja
# ══════════════════════════════════════════════
@router.post("/lotes/{lote_id}/zonas-mapa/generar-franja")
def generar_franja_riparia(lote_id: str):
    """
    Genera automáticamente la franja riparia usando ST_Buffer
    sobre el drenaje del lote.

    Usa franja_riparia_legal_m del diagnóstico vigente como ancho
    del buffer. Si no hay diagnóstico, usa 30 metros por defecto.

    Nota: Requiere que el lote tenga una geometría (geom) definida.
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT franja_riparia_legal_m
            FROM diagnosticos_lote
            WHERE lote_id = %s
            ORDER BY fecha DESC
            LIMIT 1
        """, (str(lote_id),))
        diag = cur.fetchone()
        ancho_m = diag["franja_riparia_legal_m"] if diag and diag["franja_riparia_legal_m"] else 30
        ancho_grados = ancho_m / 111320.0

        cur.execute("""
            INSERT INTO zonas_mapa (lote_id, tipo, etiqueta, geom)
            SELECT %s, 'franja_riparia', %s,
                   ST_Buffer(geom, %s)
            FROM lotes
            WHERE id = %s AND geom IS NOT NULL
            RETURNING id, tipo, etiqueta, ST_AsGeoJSON(geom)::json AS geometria
        """, (
            str(lote_id),
            f"Franja riparia ({ancho_m}m)",
            ancho_grados,
            str(lote_id)
        ))

        zona = cur.fetchone()
        if not zona:
            raise HTTPException(
                status_code=400,
                detail="El lote no tiene geometría definida (geom)"
            )

        conn.commit()

        return {
            "type": "Feature",
            "id": str(zona["id"]),
            "properties": {
                "tipo": zona["tipo"],
                "etiqueta": zona["etiqueta"],
                "ancho_m": ancho_m,
            },
            "geometry": zona["geometria"]
        }
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()
