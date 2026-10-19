"""
Services/compatibilidad_service.py
===================================
Algoritmo de compatibilidad de especies.

¿Qué hace?
Calcula un puntaje de 0 a 100 para CADA especie del catálogo,
evaluando qué tan compatible es con las condiciones del lote.

Los criterios y sus pesos:
┌─────────────┬──────┬──────────────────────────────────┐
│ Criterio    │ Peso │ Regla                            │
├─────────────┼──────┼──────────────────────────────────┤
│ Altitud     │  25  │ Dentro del rango = 100%          │
│ pH          │  15  │ Dentro del rango = 100%          │
│ Textura     │  15  │ Compatible = 100%, sino 0%       │
│ Régimen     │  15  │ Coincide = 100%, sino 0%         │
│ Humedad     │  10  │ Dentro del rango = 100%          │
│ Objetivos   │  10  │ Mapeo objetivo → especie         │
│ Pendiente   │  10  │ Pendiente alta → raíz profunda   │
└─────────────┴──────┴──────────────────────────────────┘

Si un criterio no tiene datos (null), se ignora y se reparte
su peso entre los demás (renormalización).
Solo se guardan las especies con puntaje >= UMBRAL_MINIMO.
"""

# ══════════════════════════════════════════════
# CONFIGURACIÓN (ajustar con el equipo técnico)
# ══════════════════════════════════════════════

PESOS = {
    "altitud":   25,
    "ph":        15,
    "textura":   15,
    "regimen":   15,
    "humedad":   10,
    "objetivos": 10,
    "pendiente": 10,
}

UMBRAL_MINIMO = 40

# ══════════════════════════════════════════════
# FUNCIONES AUXILIARES
# ══════════════════════════════════════════════

def _score_rango(valor, min_val, max_val, margen):
    if valor is None:
        return None
    if min_val is None and max_val is None:
        return None

    low = min_val if min_val is not None else float('-inf')
    high = max_val if max_val is not None else float('inf')
    if low <= valor <= high:
        return 100.0
    if valor < low:
        distancia = low - valor
    else:
        distancia = valor - high
    return max(0.0, 100.0 - (distancia / margen) * 100.0)


def _derivar_regimen_hidrico(precipitacion_anual):
    """
    Clasifica el régimen hídrico según la precipitación anual.

    - < 1000 mm/año → seco
    - 1000 a 2000 mm/año → moderado
    - > 2000 mm/año → húmedo
    """
    if precipitacion_anual < 1000:
        return "seco"
    elif precipitacion_anual <= 2000:
        return "moderado"
    else:
        return "humedo"


# ══════════════════════════════════════════════
# FUNCIÓN PRINCIPAL
# ══════════════════════════════════════════════

def calcular_compatibilidad(conn, diagnostico_id, lote_id,
                            muestra_suelo_id, precipitacion_anual):
    """
    Calcula la compatibilidad de TODAS las especies contra el lote.

    Pasos:
    1. Obtener datos del lote (altitud, pendiente)
    2. Obtener datos de la muestra de suelo (pH, textura, humedad)
    3. Obtener objetivos del lote
    4. Para cada especie → calcular puntaje ponderado
    5. Guardar las que superen el umbral en diagnostico_especies
    """
    cur = conn.cursor()
    cur.execute(
        "SELECT altitud_msnm, pendiente_grados FROM lotes WHERE id = %s",
        (str(lote_id),)
    )
    lote = cur.fetchone()
    altitud = lote["altitud_msnm"] if lote else None
    pendiente = (float(lote["pendiente_grados"])
                 if lote and lote["pendiente_grados"] else None)
    ph = None
    textura_id = None
    humedad = None
    if muestra_suelo_id:
        cur.execute(
            """SELECT ph, textura_id, humedad_retencion_pct
               FROM muestras_suelo WHERE id = %s""",
            (str(muestra_suelo_id),)
        )
        muestra = cur.fetchone()
        if muestra:
            ph = float(muestra["ph"]) if muestra["ph"] else None
            textura_id = muestra["textura_id"]
            humedad = (float(muestra["humedad_retencion_pct"])
                       if muestra["humedad_retencion_pct"] else None)
    cur.execute(
        """SELECT o.codigo
           FROM lote_objetivos lo
           JOIN objetivos_reforestacion o ON o.id = lo.objetivo_id
           WHERE lo.lote_id = %s""",
        (str(lote_id),)
    )
    objetivos = {row["codigo"] for row in cur.fetchall()}
    regimen_derivado = _derivar_regimen_hidrico(precipitacion_anual)
    cur.execute("""
        SELECT e.id, e.nombre_comun,
               e.altitud_min_msnm, e.altitud_max_msnm,
               e.ph_min, e.ph_max,
               e.humedad_radicular_min_pct, e.humedad_radicular_max_pct,
               gf.codigo AS grupo_funcional_codigo,
               tr.codigo AS tipo_raiz_codigo
        FROM especies e
        LEFT JOIN grupos_funcionales gf ON gf.id = e.grupo_funcional_id
        LEFT JOIN tipos_raiz tr ON tr.id = e.tipo_raiz_id
    """)
    especies = cur.fetchall()
    cur.execute("SELECT especie_id, textura_id FROM especie_texturas")
    texturas_por_especie = {}
    for row in cur.fetchall():
        eid = str(row["especie_id"])
        texturas_por_especie.setdefault(eid, set()).add(row["textura_id"])
    cur.execute("""
        SELECT erh.especie_id, rh.codigo
        FROM especie_regimenes_hidricos erh
        JOIN regimenes_hidricos rh ON rh.id = erh.regimen_hidrico_id
    """)
    regimenes_por_especie = {}
    for row in cur.fetchall():
        eid = str(row["especie_id"])
        regimenes_por_especie.setdefault(eid, set()).add(row["codigo"])
    cur.execute("""
        SELECT es.especie_id, se.codigo
        FROM especie_servicios es
        JOIN servicios_ecosistemicos se ON se.id = es.servicio_id
    """)
    servicios_por_especie = {}
    for row in cur.fetchall():
        eid = str(row["especie_id"])
        servicios_por_especie.setdefault(eid, set()).add(row["codigo"])
    resultados = []

    for esp in especies:
        esp_id = str(esp["id"])
        scores = {}
        if altitud is not None:
            s = _score_rango(
                altitud,
                esp["altitud_min_msnm"],
                esp["altitud_max_msnm"],
                margen=500 
            )
            if s is not None:
                scores["altitud"] = s
        if ph is not None:
            s = _score_rango(
                ph,
                float(esp["ph_min"]) if esp["ph_min"] else None,
                float(esp["ph_max"]) if esp["ph_max"] else None,
                margen=2.0
            )
            if s is not None:
                scores["ph"] = s
        if textura_id is not None:
            texturas_esp = texturas_por_especie.get(esp_id, set())
            if texturas_esp:
                scores["textura"] = 100.0 if textura_id in texturas_esp else 0.0
        regimenes_esp = regimenes_por_especie.get(esp_id, set())
        if regimenes_esp:
            scores["regimen"] = 100.0 if regimen_derivado in regimenes_esp else 0.0
        if humedad is not None:
            s = _score_rango(
                humedad,
                float(esp["humedad_radicular_min_pct"]) if esp["humedad_radicular_min_pct"] else None,
                float(esp["humedad_radicular_max_pct"]) if esp["humedad_radicular_max_pct"] else None,
                margen=20.0 
            )
            if s is not None:
                scores["humedad"] = s
        if objetivos:
            matches = 0
            total_objetivos = len(objetivos)

            if "control_erosion" in objetivos:
                if esp["tipo_raiz_codigo"] in ("fasciculada", "radicular_extendida"):
                    matches += 1

            if "proteccion_hidrica" in objetivos:
                servicios = servicios_por_especie.get(esp_id, set())
                if "cosecha_agua" in servicios or esp["tipo_raiz_codigo"] == "pivotante":
                    matches += 1

            if "corredores_biologicos" in objetivos:
                servicios = servicios_por_especie.get(esp_id, set())
                if "aves_fauna" in servicios:
                    matches += 1

            if "madera_sombra" in objetivos:
                if esp["grupo_funcional_codigo"] == "dosel":
                    matches += 1

            scores["objetivos"] = (matches / total_objetivos) * 100.0 if total_objetivos > 0 else 0.0

        if pendiente is not None:
            if pendiente > 30:
                scores["pendiente"] = (100.0
                    if esp["tipo_raiz_codigo"] in ("pivotante", "fasciculada")
                    else 40.0)
            elif pendiente > 15:
                scores["pendiente"] = (100.0
                    if esp["tipo_raiz_codigo"] in ("pivotante", "fasciculada")
                    else 70.0)
            else:
                scores["pendiente"] = 100.0

        if not scores:
            continue  # Sin datos → no se puede evaluar
        peso_total = sum(PESOS[k] for k in scores)
        puntaje = sum(scores[k] * PESOS[k] for k in scores) / peso_total

        if puntaje >= UMBRAL_MINIMO:
            resultados.append((esp_id, round(puntaje, 1)))
    cur.execute(
        "DELETE FROM diagnostico_especies WHERE diagnostico_id = %s",
        (str(diagnostico_id),)
    )
    for esp_id, puntaje in resultados:
        cur.execute(
            """INSERT INTO diagnostico_especies
                   (diagnostico_id, especie_id, compatibilidad_pct)
               VALUES (%s, %s, %s)
               ON CONFLICT (diagnostico_id, especie_id)
               DO UPDATE SET compatibilidad_pct = EXCLUDED.compatibilidad_pct,
                             calculado_en = now()""",
            (str(diagnostico_id), esp_id, puntaje)
        )

    return resultados
