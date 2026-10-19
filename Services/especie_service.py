"""
Services/especie_service.py
===========================
Lógica de negocio para Especies, Protocolos de Siembra y Stock en Viveros.

Cumple con HU-13, HU-14 y HU-15:
- HU-13: Ficha técnica detallada con desglose de medidores de ajuste si se especifica lote_id.
- HU-14: Protocolo de siembra ordenado por fases (excavación, desembuchado, fijación, riego, mulch).
- HU-15: Stock por vivero con disponibilidad y ordenamiento por cercanía geográfica (PostGIS ST_Distance).
- Exportación y registro de ficha técnica en documentos_exportados.
"""
from Config.database import get_connection, serialize_row, serialize_rows
from Services.compatibilidad_service import _score_rango
from typing import Optional, Dict, Any, List


def _clasificar_estado_ajuste(ajuste_pct: Optional[float]) -> str:
    if ajuste_pct is None:
        return "sin_datos"
    if ajuste_pct >= 85:
        return "optimo"
    if ajuste_pct >= 50:
        return "tolerable"
    return "no_apto"


# ══════════════════════════════════════════════
# HU-13: FICHA TÉCNICA DETALLADA
# ══════════════════════════════════════════════

def obtener_ficha_tecnica(especie_id: str, lote_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Obtiene la ficha técnica de una especie con sus relaciones:
    - Familia botánica, estrato forestal, grupo funcional, tasa de crecimiento, tipo de raíz.
    - Listas de texturas compatibles, regímenes hídricos, etiquetas ecológicas y servicios ecosistémicos con métricas.

    Si se proporciona `lote_id`, calcula los `medidores_ajuste` para altitud, pH, humedad y sol,
    desglosando la misma lógica matemática del algoritmo de compatibilidad.
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT e.*,
                   f.nombre AS familia_nombre,
                   ef.codigo AS estrato_codigo, ef.nombre AS estrato_nombre,
                   gf.codigo AS grupo_codigo, gf.nombre AS grupo_nombre,
                   tc.codigo AS tasa_codigo, tc.nombre AS tasa_nombre,
                   tc.incremento_min_m_anio, tc.incremento_max_m_anio,
                   tr.codigo AS raiz_codigo, tr.nombre AS raiz_nombre, tr.funcion AS raiz_funcion
            FROM especies e
            LEFT JOIN familias_botanicas f ON f.id = e.familia_id
            LEFT JOIN estratos_forestales ef ON ef.id = e.estrato_id
            LEFT JOIN grupos_funcionales gf ON gf.id = e.grupo_funcional_id
            LEFT JOIN tasas_crecimiento tc ON tc.id = e.tasa_crecimiento_id
            LEFT JOIN tipos_raiz tr ON tr.id = e.tipo_raiz_id
            WHERE e.id = %s
        """, (str(especie_id),))
        esp = cur.fetchone()

        if not esp:
            raise ValueError(f"Especie con id '{especie_id}' no encontrada")

        esp_data = serialize_row(esp)
        cur.execute("""
            SELECT ts.id, ts.codigo, ts.nombre
            FROM especie_texturas et
            JOIN texturas_suelo ts ON ts.id = et.textura_id
            WHERE et.especie_id = %s
            ORDER BY ts.id
        """, (str(especie_id),))
        texturas = serialize_rows(cur.fetchall())
        cur.execute("""
            SELECT rh.id, rh.codigo, rh.nombre
            FROM especie_regimenes_hidricos erh
            JOIN regimenes_hidricos rh ON rh.id = erh.regimen_hidrico_id
            WHERE erh.especie_id = %s
            ORDER BY rh.id
        """, (str(especie_id),))
        regimenes = serialize_rows(cur.fetchall())
        cur.execute("""
            SELECT ee.id, ee.codigo, ee.nombre
            FROM especie_etiquetas eet
            JOIN etiquetas_especie ee ON ee.id = eet.etiqueta_id
            WHERE eet.especie_id = %s
            ORDER BY ee.id
        """, (str(especie_id),))
        etiquetas = serialize_rows(cur.fetchall())
        cur.execute("""
            SELECT se.id, se.codigo, se.nombre,
                   es.descripcion, es.metrica_valor, es.metrica_unidad
            FROM especie_servicios es
            JOIN servicios_ecosistemicos se ON se.id = es.servicio_id
            WHERE es.especie_id = %s
            ORDER BY se.id
        """, (str(especie_id),))
        servicios = serialize_rows(cur.fetchall())
        ficha = {
            **esp_data,
            "familia": esp_data.get("familia_nombre"),
            "estrato": {
                "codigo": esp_data.get("estrato_codigo"),
                "nombre": esp_data.get("estrato_nombre")
            },
            "grupo_funcional": {
                "codigo": esp_data.get("grupo_codigo"),
                "nombre": esp_data.get("grupo_nombre")
            },
            "tasa_crecimiento": {
                "codigo": esp_data.get("tasa_codigo"),
                "nombre": esp_data.get("tasa_nombre"),
                "incremento_min_m_anio": esp_data.get("incremento_min_m_anio"),
                "incremento_max_m_anio": esp_data.get("incremento_max_m_anio")
            },
            "tipo_raiz": {
                "codigo": esp_data.get("raiz_codigo"),
                "nombre": esp_data.get("raiz_nombre"),
                "funcion": esp_data.get("raiz_funcion")
            },
            "texturas": texturas,
            "regimenes_hidricos": regimenes,
            "etiquetas": etiquetas,
            "servicios_ecosistemicos": servicios
        }
        if lote_id:
            cur.execute("""
                SELECT id, codigo, nombre, altitud_msnm, pendiente_grados
                FROM lotes
                WHERE id = %s
            """, (str(lote_id),))
            lote = cur.fetchone()
            if not lote:
                raise ValueError(f"Lote con id '{lote_id}' no encontrado")
            cur.execute("""
                SELECT ph, humedad_retencion_pct
                FROM muestras_suelo
                WHERE lote_id = %s
                ORDER BY fecha_muestra DESC
                LIMIT 1
            """, (str(lote_id),))
            muestra = cur.fetchone()
            if not muestra:
                cur.execute("""
                    SELECT ms.ph, ms.humedad_retencion_pct
                    FROM diagnosticos_lote d
                    JOIN muestras_suelo ms ON ms.id = d.muestra_suelo_id
                    WHERE d.lote_id = %s
                    ORDER BY d.fecha DESC
                    LIMIT 1
                """, (str(lote_id),))
                muestra = cur.fetchone()

            altitud_lote = lote["altitud_msnm"]
            ph_lote = float(muestra["ph"]) if (muestra and muestra["ph"] is not None) else None
            humedad_lote = float(muestra["humedad_retencion_pct"]) if (muestra and muestra["humedad_retencion_pct"] is not None) else None
            alt_score = _score_rango(
                altitud_lote,
                esp["altitud_min_msnm"],
                esp["altitud_max_msnm"],
                margen=500
            )
            ph_min = float(esp["ph_min"]) if esp["ph_min"] is not None else None
            ph_max = float(esp["ph_max"]) if esp["ph_max"] is not None else None
            ph_score = _score_rango(
                ph_lote,
                ph_min,
                ph_max,
                margen=2.0
            )
            hum_min = float(esp["humedad_radicular_min_pct"]) if esp["humedad_radicular_min_pct"] is not None else None
            hum_max = float(esp["humedad_radicular_max_pct"]) if esp["humedad_radicular_max_pct"] is not None else None
            hum_score = _score_rango(
                humedad_lote,
                hum_min,
                hum_max,
                margen=20.0
            )
            sol_min = float(esp["horas_sol_min"]) if esp["horas_sol_min"] is not None else None
            sol_lote_estimado = 5.5
            sol_score = None
            if sol_min is not None:
                if sol_lote_estimado >= sol_min:
                    sol_score = 100.0
                else:
                    dif = sol_min - sol_lote_estimado
                    sol_score = max(0.0, round(100.0 - (dif / 3.0) * 100.0, 1))

            medidores_ajuste = {
                "altitud": {
                    "variable": "Altitud",
                    "unidad": "msnm",
                    "valor_lote": altitud_lote,
                    "rango_especie": {
                        "min": esp["altitud_min_msnm"],
                        "max": esp["altitud_max_msnm"]
                    },
                    "ajuste_pct": round(alt_score, 1) if alt_score is not None else None,
                    "estado": _clasificar_estado_ajuste(alt_score)
                },
                "ph": {
                    "variable": "pH del Suelo",
                    "unidad": "pH",
                    "valor_lote": ph_lote,
                    "rango_especie": {
                        "min": ph_min,
                        "max": ph_max
                    },
                    "ajuste_pct": round(ph_score, 1) if ph_score is not None else None,
                    "estado": _clasificar_estado_ajuste(ph_score)
                },
                "humedad": {
                    "variable": "Humedad Radicular",
                    "unidad": "%",
                    "valor_lote": humedad_lote,
                    "rango_especie": {
                        "min": hum_min,
                        "max": hum_max
                    },
                    "ajuste_pct": round(hum_score, 1) if hum_score is not None else None,
                    "estado": _clasificar_estado_ajuste(hum_score)
                },
                "sol": {
                    "variable": "Horas de Sol Diarias",
                    "unidad": "horas/día",
                    "valor_lote": sol_lote_estimado,
                    "rango_especie": {
                        "min": sol_min,
                        "max": None
                    },
                    "ajuste_pct": sol_score,
                    "estado": _clasificar_estado_ajuste(sol_score)
                }
            }

            ficha["lote_evaluado"] = {
                "lote_id": str(lote["id"]),
                "codigo": lote["codigo"],
                "nombre": lote["nombre"]
            }
            ficha["medidores_ajuste"] = medidores_ajuste

        return ficha
    finally:
        conn.close()


# ══════════════════════════════════════════════
# HU-14: PROTOCOLO DE SIEMBRA
# ══════════════════════════════════════════════

def obtener_protocolo_siembra(especie_id: str) -> List[Dict[str, Any]]:
    """
    Retorna los pasos del protocolo de siembra para una especie,
    ordenados estrictamente por el campo `orden`.
    Fases: excavación, desembuchado, fijación, riego, mulch, etc.
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, nombre_comun FROM especies WHERE id = %s", (str(especie_id),))
        esp = cur.fetchone()
        if not esp:
            raise ValueError(f"Especie con id '{especie_id}' no encontrada")

        cur.execute("""
            SELECT id, especie_id, orden, titulo, descripcion,
                   parametro_etiqueta, parametro_valor, advertencia
            FROM protocolo_fases
            WHERE especie_id = %s
            ORDER BY orden ASC
        """, (str(especie_id),))
        fases = cur.fetchall()
        return serialize_rows(fases)
    finally:
        conn.close()


# ══════════════════════════════════════════════
# HU-15: STOCK POR VIVERO Y LISTADO
# ══════════════════════════════════════════════

def obtener_stock_especie(especie_id: str, lote_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Obtiene el stock de una especie por vivero:
    - stock actual
    - disponible (stock > 0)
    - certificado_origen_url
    - fecha de actualización
    - ubicación geográfica
    
    Si se proporciona `lote_id`, ordena los viveros por cercanía geográfica
    usando la función `ST_Distance` de PostGIS.
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, nombre_comun FROM especies WHERE id = %s", (str(especie_id),))
        esp = cur.fetchone()
        if not esp:
            raise ValueError(f"Especie con id '{especie_id}' no encontrada")

        if lote_id:
            cur.execute("SELECT id FROM lotes WHERE id = %s", (str(lote_id),))
            if not cur.fetchone():
                raise ValueError(f"Lote con id '{lote_id}' no encontrado")
            cur.execute("""
                SELECT vs.vivero_id,
                       v.nombre AS vivero_nombre,
                       v.municipio,
                       vs.stock,
                       (vs.stock > 0) AS disponible,
                       vs.certificado_origen_url,
                       vs.actualizado_en,
                       extensions.ST_AsGeoJSON(v.ubicacion)::json AS ubicacion,
                       ROUND(
                           (extensions.ST_Distance(
                               v.ubicacion::extensions.geography,
                               COALESCE(l.ubicacion, extensions.ST_Centroid(l.geom))::extensions.geography
                           ) / 1000.0)::numeric, 2
                       ) AS distancia_km
                FROM vivero_stock vs
                JOIN viveros v ON v.id = vs.vivero_id
                CROSS JOIN (
                    SELECT ubicacion, geom
                    FROM lotes
                    WHERE id = %s
                ) l
                WHERE vs.especie_id = %s
                ORDER BY distancia_km ASC NULLS LAST, vs.stock DESC
            """, (str(lote_id), str(especie_id)))
        else:
            cur.execute("""
                SELECT vs.vivero_id,
                       v.nombre AS vivero_nombre,
                       v.municipio,
                       vs.stock,
                       (vs.stock > 0) AS disponible,
                       vs.certificado_origen_url,
                       vs.actualizado_en,
                       extensions.ST_AsGeoJSON(v.ubicacion)::json AS ubicacion,
                       NULL AS distancia_km
                FROM vivero_stock vs
                JOIN viveros v ON v.id = vs.vivero_id
                WHERE vs.especie_id = %s
                ORDER BY vs.stock DESC, v.nombre ASC
            """, (str(especie_id),))

        return serialize_rows(cur.fetchall())
    finally:
        conn.close()


def listar_viveros() -> List[Dict[str, Any]]:
    """
    Retorna la lista de viveros registrados con su información geográfica
    y resumen de inventario disponible.
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT v.id,
                   v.nombre,
                   v.municipio,
                   extensions.ST_AsGeoJSON(v.ubicacion)::json AS ubicacion,
                   COUNT(vs.especie_id) FILTER (WHERE vs.stock > 0) AS especies_con_stock,
                   COALESCE(SUM(vs.stock), 0) AS total_plantulas
            FROM viveros v
            LEFT JOIN vivero_stock vs ON vs.vivero_id = v.id
            GROUP BY v.id, v.nombre, v.municipio, v.ubicacion
            ORDER BY v.nombre ASC
        """)
        return serialize_rows(cur.fetchall())
    finally:
        conn.close()


# ══════════════════════════════════════════════
# EXPORTACIÓN DE FICHA TÉCNICA
# ══════════════════════════════════════════════

def registrar_exportacion_ficha(especie_id: str, url: Optional[str] = None, generado_por: Optional[str] = None) -> Dict[str, Any]:
    """
    Registra la generación/exportación de un PDF de ficha técnica
    en la tabla `documentos_exportados`.
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, codigo_taxon, nombre_comun FROM especies WHERE id = %s", (str(especie_id),))
        esp = cur.fetchone()
        if not esp:
            raise ValueError(f"Especie con id '{especie_id}' no encontrada")

        pdf_url = url or f"/documentos/fichas/ficha_tecnica_{esp['codigo_taxon']}.pdf"

        cur.execute("""
            INSERT INTO documentos_exportados (especie_id, tipo, url, generado_por)
            VALUES (%s, 'ficha_tecnica_especie', %s, %s)
            RETURNING id, especie_id, tipo, url, generado_por, created_at
        """, (str(especie_id), pdf_url, str(generado_por) if generado_por else None))

        doc = cur.fetchone()
        conn.commit()

        res = serialize_row(doc)
        res["mensaje"] = "Ficha técnica exportada y registrada con éxito"
        return res
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
