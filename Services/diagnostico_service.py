"""
Services/diagnostico_service.py
================================
Lógica de negocio para los diagnósticos de lote.

Este es el "cerebro" del módulo de diagnóstico. Aquí están
las reglas de negocio, NO en las rutas (controladores).

¿Por qué separar?
- Las rutas solo reciben datos y responden.
- Los servicios hacen el trabajo pesado.
- Si mañana cambias de FastAPI a otro framework, este archivo no cambia.
"""
from Config.database import get_connection, serialize_row, serialize_rows
from Services.compatibilidad_service import calcular_compatibilidad


# ══════════════════════════════════════════════
# FUNCIONES AUXILIARES (privadas, empiezan con _)
# ══════════════════════════════════════════════

def inferir_regimen(precipitacion_mensual):
    promedio = sum(precipitacion_mensual) / 12
    es_humedo = [p >= promedio for p in precipitacion_mensual]
    picos = 0
    en_pico = False

    for i in range(12):
        if es_humedo[i] and not en_pico:
            picos += 1
            en_pico = True
        elif not es_humedo[i]:
            en_pico = False
    if es_humedo[0] and es_humedo[11] and picos > 1:
        picos -= 1

    return "bimodal" if picos >= 2 else "monomodal"


def resolver_zona_vida(conn, altitud, precipitacion_anual):
    reglas = [
        {
            "codigo": "bmh-PM",
            "alt_min": 800, "alt_max": 2500,
            "precip_min": 1000, "precip_max": 4500
        },
    ]

    for regla in reglas:
        alt_ok = (altitud is None or
                  regla["alt_min"] <= altitud <= regla["alt_max"])
        precip_ok = (regla["precip_min"] <= precipitacion_anual <= regla["precip_max"])

        if alt_ok and precip_ok:
            cur = conn.cursor()
            cur.execute(
                "SELECT id FROM zonas_vida_holdridge WHERE codigo = %s",
                (regla["codigo"],)
            )
            row = cur.fetchone()
            return row["id"] if row else None

    return None


def detectar_ventanas_siembra(precipitacion_mensual, umbral=None):
    if umbral is None:
        promedio = sum(precipitacion_mensual) / 12
        umbral = max(100.0, promedio)
    sobre_umbral = [p >= umbral for p in precipitacion_mensual]
    if not any(sobre_umbral):
        return []
    if all(sobre_umbral):
        return [{"mes_inicio": 1, "mes_fin": 12, "nota": "Lluvia todo el año"}]
    ventanas = []
    inicio_escaneo = 0
    for i in range(12):
        if not sobre_umbral[i]:
            inicio_escaneo = i
            break

    inicio_ventana = None
    for offset in range(12):
        i = (inicio_escaneo + offset) % 12

        if sobre_umbral[i]:
            if inicio_ventana is None:
                inicio_ventana = i
        else:
            if inicio_ventana is not None:
                fin = (inicio_escaneo + offset - 1) % 12
                ventanas.append({
                    "mes_inicio": inicio_ventana + 1,  
                    "mes_fin": fin + 1,            
                    "nota": None
                })
                inicio_ventana = None
    if inicio_ventana is not None:
        fin = (inicio_escaneo - 1) % 12
        ventanas.append({
            "mes_inicio": inicio_ventana + 1,
            "mes_fin": fin + 1,
            "nota": "Cruza diciembre-enero"
        })

    return ventanas


# ══════════════════════════════════════════════
# OPERACIONES PRINCIPALES (usadas por las rutas)
# ══════════════════════════════════════════════

def crear_diagnostico(lote_id, body):
    """
    Crea un diagnóstico completo para un lote.

    Todo ocurre en UNA TRANSACCIÓN: si algo falla, no se guarda nada.

    Pasos:
    1. Validar datos (Pydantic ya validó los 12 meses)
    2. Inferir régimen si no viene
    3. Resolver zona de vida Holdridge
    4. Insertar diagnóstico principal
    5. Insertar 12 registros de precipitación mensual
    6. Detectar e insertar ventanas de siembra
    7. Calcular compatibilidad de especies
    8. Retornar diagnóstico completo
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        precipitacion = body.precipitacion_mensual
        precipitacion_anual = int(sum(precipitacion))
        codigo_regimen = body.regimen_precipitacion
        if not codigo_regimen:
            codigo_regimen = inferir_regimen(precipitacion)

        cur.execute(
            "SELECT id FROM regimenes_precipitacion WHERE codigo = %s",
            (codigo_regimen,)
        )
        row = cur.fetchone()
        if not row:
            raise ValueError(
                f"Régimen '{codigo_regimen}' no encontrado. "
                f"Usa 'monomodal' o 'bimodal'."
            )
        regimen_id = row["id"]
        cur.execute(
            "SELECT altitud_msnm FROM lotes WHERE id = %s",
            (str(lote_id),)
        )
        lote = cur.fetchone()
        if not lote:
            raise ValueError("Lote no encontrado")
        altitud = lote["altitud_msnm"]
        zona_vida_id = resolver_zona_vida(conn, altitud, precipitacion_anual)
        cur.execute("""
            INSERT INTO diagnosticos_lote
                (lote_id, muestra_suelo_id, zona_vida_id,
                 regimen_precipitacion_id, precipitacion_anual_mm,
                 perdida_cobertura_pct, franja_riparia_legal_m,
                 riesgo_acarreo, conectividad_fauna, observaciones)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            str(lote_id),
            str(body.muestra_suelo_id) if body.muestra_suelo_id else None,
            zona_vida_id,
            regimen_id,
            precipitacion_anual,
            body.perdida_cobertura_pct,
            body.franja_riparia_legal_m,
            body.riesgo_acarreo,
            body.conectividad_fauna,
            body.observaciones,
        ))
        diagnostico_id = str(cur.fetchone()["id"])
        for mes, valor in enumerate(precipitacion, start=1):
            cur.execute("""
                INSERT INTO diagnostico_precipitacion_mensual
                    (diagnostico_id, mes, precipitacion_mm)
                VALUES (%s, %s, %s)
            """, (diagnostico_id, mes, valor))
        ventanas = detectar_ventanas_siembra(precipitacion)
        for v in ventanas:
            cur.execute("""
                INSERT INTO ventanas_siembra
                    (diagnostico_id, mes_inicio, mes_fin, nota)
                VALUES (%s, %s, %s, %s)
            """, (diagnostico_id, v["mes_inicio"], v["mes_fin"], v["nota"]))
        calcular_compatibilidad(
            conn, diagnostico_id, lote_id,
            body.muestra_suelo_id, precipitacion_anual
        )
        conn.commit()
        return obtener_diagnostico_completo(diagnostico_id, conn)

    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def obtener_diagnostico_vigente(lote_id):
    """
    Obtiene el diagnóstico más reciente de un lote.
    Usa la vista v_diagnostico_vigente de la BD.

    Incluye: datos base, precipitación mensual (para gráficos),
    ventanas de siembra, zona de vida, resumen y restricciones.
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT id FROM v_diagnostico_vigente WHERE lote_id = %s
        """, (str(lote_id),))
        row = cur.fetchone()
        if not row:
            return None
        return obtener_diagnostico_completo(str(row["id"]), conn)
    finally:
        conn.close()


def obtener_historial(lote_id):
    """Lista todos los diagnósticos de un lote, del más reciente al más antiguo."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, fecha, precipitacion_anual_mm, perdida_cobertura_pct,
                   riesgo_acarreo, conectividad_fauna
            FROM diagnosticos_lote
            WHERE lote_id = %s
            ORDER BY fecha DESC
        """, (str(lote_id),))
        return serialize_rows(cur.fetchall())
    finally:
        conn.close()


def obtener_especies_sugeridas(diagnostico_id, min_compat=50, limit=None):
    """
    Obtiene las especies sugeridas para un diagnóstico,
    ordenadas por compatibilidad descendente.
    """
    conn = get_connection()
    try:
        cur = conn.cursor()

        query = """
            SELECT de.especie_id, e.codigo_taxon,
                   e.nombre_comun, e.nombre_cientifico,
                   gf.nombre AS grupo_funcional,
                   de.compatibilidad_pct, de.calculado_en
            FROM diagnostico_especies de
            JOIN especies e ON e.id = de.especie_id
            LEFT JOIN grupos_funcionales gf ON gf.id = e.grupo_funcional_id
            WHERE de.diagnostico_id = %s
              AND de.compatibilidad_pct >= %s
            ORDER BY de.compatibilidad_pct DESC
        """
        params = [str(diagnostico_id), min_compat]

        if limit:
            query += " LIMIT %s"
            params.append(limit)

        cur.execute(query, params)
        return serialize_rows(cur.fetchall())
    finally:
        conn.close()


def recalcular_compatibilidad(diagnostico_id):
    """
    Vuelve a ejecutar el algoritmo de compatibilidad.
    Útil si cambian los objetivos del lote o el catálogo de especies.
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT lote_id, muestra_suelo_id, precipitacion_anual_mm
            FROM diagnosticos_lote WHERE id = %s
        """, (str(diagnostico_id),))
        diag = cur.fetchone()
        if not diag:
            return None
        resultados = calcular_compatibilidad(
            conn,
            str(diagnostico_id),
            str(diag["lote_id"]),
            str(diag["muestra_suelo_id"]) if diag["muestra_suelo_id"] else None,
            diag["precipitacion_anual_mm"]
        )
        conn.commit()
        return {
            "diagnostico_id": str(diagnostico_id),
            "especies_recalculadas": len(resultados),
            "especies": obtener_especies_sugeridas(diagnostico_id, min_compat=0)
        }
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


# ══════════════════════════════════════════════
# FUNCIÓN AUXILIAR: Armar respuesta completa
# ══════════════════════════════════════════════

def obtener_diagnostico_completo(diagnostico_id, conn=None):
    """
    Arma la respuesta completa de un diagnóstico con TODOS sus datos
    relacionados. Es la función que usan tanto el POST como el GET.
    """
    cerrar = conn is None
    if cerrar:
        conn = get_connection()

    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM diagnosticos_lote WHERE id = %s",
            (str(diagnostico_id),)
        )
        diagnostico = serialize_row(cur.fetchone())
        if not diagnostico:
            return None
        cur.execute("""
            SELECT mes, precipitacion_mm
            FROM diagnostico_precipitacion_mensual
            WHERE diagnostico_id = %s
            ORDER BY mes
        """, (str(diagnostico_id),))
        diagnostico["precipitacion_mensual"] = serialize_rows(cur.fetchall())
        cur.execute("""
            SELECT id, mes_inicio, mes_fin, nota
            FROM ventanas_siembra
            WHERE diagnostico_id = %s
        """, (str(diagnostico_id),))
        diagnostico["ventanas_siembra"] = serialize_rows(cur.fetchall())
        if diagnostico.get("zona_vida_id"):
            cur.execute("""
                SELECT codigo, nombre, descripcion_microclima,
                       recomendacion_siembra
                FROM zonas_vida_holdridge WHERE id = %s
            """, (diagnostico["zona_vida_id"],))
            diagnostico["zona_vida"] = serialize_row(cur.fetchone())
        else:
            diagnostico["zona_vida"] = None
        if diagnostico.get("regimen_precipitacion_id"):
            cur.execute("""
                SELECT codigo, nombre
                FROM regimenes_precipitacion WHERE id = %s
            """, (diagnostico["regimen_precipitacion_id"],))
            diagnostico["regimen"] = serialize_row(cur.fetchone())
        else:
            diagnostico["regimen"] = None
        cur.execute("""
            SELECT cobertura_remanente_pct,
                   total_especies_sugeridas,
                   compatibilidad_promedio_pct
            FROM v_diagnostico_resumen
            WHERE diagnostico_id = %s
        """, (str(diagnostico_id),))
        diagnostico["resumen"] = serialize_row(cur.fetchone())
        diagnostico["restricciones"] = {
            "riesgo_acarreo": diagnostico.get("riesgo_acarreo"),
            "franja_riparia_legal_m": diagnostico.get("franja_riparia_legal_m"),
            "conectividad_fauna": diagnostico.get("conectividad_fauna"),
        }
        cur.execute("""
            SELECT de.especie_id, e.codigo_taxon,
                   e.nombre_comun, e.nombre_cientifico,
                   gf.nombre AS grupo_funcional,
                   de.compatibilidad_pct
            FROM diagnostico_especies de
            JOIN especies e ON e.id = de.especie_id
            LEFT JOIN grupos_funcionales gf ON gf.id = e.grupo_funcional_id
            WHERE de.diagnostico_id = %s
            ORDER BY de.compatibilidad_pct DESC
        """, (str(diagnostico_id),))
        diagnostico["especies_sugeridas"] = serialize_rows(cur.fetchall())
        return diagnostico
    finally:
        if cerrar:
            conn.close()
