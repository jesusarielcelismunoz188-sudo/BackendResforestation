"""
Services/proyecto_service.py
============================
Lógica de negocio para Proyectos y Selección de Especies (HU-16).

En este sistema, la "selección" de especies corresponde al `proyecto`
en fase `borrador` o `planificacion_activa`. Las cantidades se almacenan
en la tabla `proyecto_especies` con su zona de plantación.

Incluye:
- Creación de proyectos en borrador asociados a lotes y diagnósticos vigentes.
- Reemplazo y adición/eliminación de especies con validación de fase y cantidades.
- Cálculo de insumos y requerimientos (plántulas, compost, agua, jornales).
- Corrección geométrica del área según el patrón de siembra:
  * Tresbolillo: espaciado² × 0.866
  * Cuadrado/Rectangular: espaciado²
- Alertas de stock insuficiente frente al vivero del proyecto.
"""
from Config.database import get_connection, serialize_row, serialize_rows
from Models.schemas import ProyectoCreate, EspecieSeleccionItem
from typing import Optional, Dict, Any, List, Union
import math

FASES_MODIFICABLES = {"borrador", "planificacion_activa"}
FACTORES_PATRON = {
    "tresbolillo": round(math.sqrt(3) / 2, 4),  # ~0.8660
    "cuadrado": 1.0,
    "rectangular": 1.0
}


def _resolver_zona_id(cur, zona: Union[str, int]) -> int:
    if isinstance(zona, int) or (isinstance(zona, str) and zona.isdigit()):
        cur.execute("SELECT id FROM zonas_plantacion WHERE id = %s", (int(zona),))
        row = cur.fetchone()
        if row:
            return row["id"]

    cur.execute(
        "SELECT id FROM zonas_plantacion WHERE codigo = %s OR LOWER(nombre) = LOWER(%s)",
        (str(zona), str(zona))
    )
    row = cur.fetchone()
    if not row:
        raise ValueError(
            f"Zona de plantación '{zona}' no válida. Opciones comunes: 'dosel_alto', 'ripario', 'borde'."
        )
    return row["id"]


def _validar_fase_proyecto(cur, proyecto_id: str) -> Dict[str, Any]:
    cur.execute("SELECT * FROM proyectos WHERE id = %s", (str(proyecto_id),))
    proyecto = cur.fetchone()
    if not proyecto:
        raise ValueError(f"Proyecto con id '{proyecto_id}' no encontrado")

    fase = proyecto["fase"]
    if fase not in FASES_MODIFICABLES:
        raise ValueError(
            f"No se puede modificar la selección de especies: el proyecto está en fase '{fase}'. "
            f"Solo se permite en: {', '.join(FASES_MODIFICABLES)}."
        )
    return proyecto


# ══════════════════════════════════════════════
# CREACIÓN DE PROYECTO (HU-16)
# ══════════════════════════════════════════════

def crear_proyecto_borrador(lote_id: str, body: ProyectoCreate) -> Dict[str, Any]:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, nombre, codigo FROM lotes WHERE id = %s", (str(lote_id),))
        lote = cur.fetchone()
        if not lote:
            raise ValueError(f"Lote con id '{lote_id}' no encontrado")
        diag_id = str(body.diagnostico_id) if body.diagnostico_id else None
        if not diag_id:
            cur.execute("""
                SELECT id FROM diagnosticos_lote
                WHERE lote_id = %s
                ORDER BY fecha DESC
                LIMIT 1
            """, (str(lote_id),))
            diag_row = cur.fetchone()
            if diag_row:
                diag_id = str(diag_row["id"])
        else:
            cur.execute("SELECT id FROM diagnosticos_lote WHERE id = %s", (diag_id,))
            if not cur.fetchone():
                raise ValueError(f"Diagnóstico con id '{diag_id}' no encontrado")
        if body.vivero_id:
            cur.execute("SELECT id FROM viveros WHERE id = %s", (str(body.vivero_id),))
            if not cur.fetchone():
                raise ValueError(f"Vivero con id '{body.vivero_id}' no encontrado")
        patron = (body.patron or "tresbolillo").lower()
        if patron not in FACTORES_PATRON:
            raise ValueError(f"Patrón de siembra '{patron}' inválido. Opciones: tresbolillo, cuadrado, rectangular.")
        cur.execute("""
            INSERT INTO proyectos (
                lote_id, diagnostico_id, vivero_id, responsable_id,
                nombre, fase, area_restaurada_m2, patron, espaciado_m,
                hoyo_lado_cm, hoyo_profundidad_cm, fecha_inicio
            )
            VALUES (%s, %s, %s, %s, %s, 'borrador', %s, %s, %s, %s, %s, %s)
            RETURNING *
        """, (
            str(lote_id),
            diag_id,
            str(body.vivero_id) if body.vivero_id else None,
            str(body.responsable_id) if body.responsable_id else None,
            body.nombre,
            body.area_restaurada_m2,
            patron,
            body.espaciado_m or 3.0,
            body.hoyo_lado_cm or 40,
            body.hoyo_profundidad_cm or 40,
            body.fecha_inicio
        ))
        nuevo_proyecto = cur.fetchone()
        conn.commit()

        res = serialize_row(nuevo_proyecto)
        res["lote"] = {"id": str(lote["id"]), "codigo": lote["codigo"], "nombre": lote["nombre"]}
        return res
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ══════════════════════════════════════════════
# GESTIÓN DE ESPECIES EN EL PROYECTO
# ══════════════════════════════════════════════

def reemplazar_especies_proyecto(proyecto_id: str, items: List[EspecieSeleccionItem]) -> Dict[str, Any]:
    """
    Reemplaza en su totalidad la selección de especies del proyecto.
    Valida fase 'borrador' o 'planificacion_activa', cantidades > 0 y existencia de especies.
    """
    if not items:
        raise ValueError("La lista de especies a seleccionar no puede estar vacía")

    conn = get_connection()
    try:
        cur = conn.cursor()
        _validar_fase_proyecto(cur, proyecto_id)
        nuevas_filas = []
        for it in items:
            if it.cantidad <= 0:
                raise ValueError(f"La cantidad para la especie {it.especie_id} debe ser mayor a 0")
            cur.execute("SELECT id FROM especies WHERE id = %s", (str(it.especie_id),))
            if not cur.fetchone():
                raise ValueError(f"Especie con id '{it.especie_id}' no existe en el catálogo")
            zona_id = _resolver_zona_id(cur, it.zona_plantacion)
            nuevas_filas.append((str(proyecto_id), str(it.especie_id), zona_id, it.cantidad))
        cur.execute("DELETE FROM proyecto_especies WHERE proyecto_id = %s", (str(proyecto_id),))
        for fila in nuevas_filas:
            cur.execute("""
                INSERT INTO proyecto_especies (proyecto_id, especie_id, zona_plantacion_id, cantidad)
                VALUES (%s, %s, %s, %s)
            """, fila)

        conn.commit()
        return listar_especies_proyecto(proyecto_id)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def agregar_o_actualizar_especie(proyecto_id: str, item: EspecieSeleccionItem) -> Dict[str, Any]:
    """
    Agrega una especie al proyecto en una zona específica,
    o actualiza la cantidad si ya existía.
    """
    if item.cantidad <= 0:
        raise ValueError("La cantidad debe ser mayor a 0")

    conn = get_connection()
    try:
        cur = conn.cursor()
        _validar_fase_proyecto(cur, proyecto_id)
        cur.execute("SELECT id, nombre_comun FROM especies WHERE id = %s", (str(item.especie_id),))
        esp = cur.fetchone()
        if not esp:
            raise ValueError(f"Especie con id '{item.especie_id}' no encontrada")

        zona_id = _resolver_zona_id(cur, item.zona_plantacion)
        cur.execute("""
            INSERT INTO proyecto_especies (proyecto_id, especie_id, zona_plantacion_id, cantidad)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (proyecto_id, especie_id, zona_plantacion_id)
            DO UPDATE SET cantidad = EXCLUDED.cantidad
            RETURNING *
        """, (str(proyecto_id), str(item.especie_id), zona_id, item.cantidad))
        guardado = cur.fetchone()
        conn.commit()
        res = serialize_row(guardado)
        res["nombre_comun"] = esp["nombre_comun"]
        return res
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def eliminar_especie_proyecto(proyecto_id: str, especie_id: str, zona: Optional[str] = None) -> Dict[str, Any]:
    """
    Elimina una especie del proyecto.
    Si se especifica `zona`, se elimina únicamente de esa zona de plantación.
    Si no se especifica, se elimina de todas las zonas del proyecto.
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        _validar_fase_proyecto(cur, proyecto_id)

        if zona:
            zona_id = _resolver_zona_id(cur, zona)
            cur.execute("""
                DELETE FROM proyecto_especies
                WHERE proyecto_id = %s AND especie_id = %s AND zona_plantacion_id = %s
            """, (str(proyecto_id), str(especie_id), zona_id))
        else:
            cur.execute("""
                DELETE FROM proyecto_especies
                WHERE proyecto_id = %s AND especie_id = %s
            """, (str(proyecto_id), str(especie_id)))

        filas_eliminadas = cur.rowcount
        conn.commit()

        if filas_eliminadas == 0:
            return {
                "mensaje": "No se encontraron registros de la especie para eliminar en este proyecto",
                "eliminadas": 0
            }

        return {
            "mensaje": f"Especie eliminada con éxito ({filas_eliminadas} registro(s) eliminado(s))",
            "eliminadas": filas_eliminadas
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def listar_especies_proyecto(proyecto_id: str) -> Dict[str, Any]:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT pe.especie_id,
                   e.codigo_taxon,
                   e.nombre_comun,
                   e.nombre_cientifico,
                   zp.id AS zona_id,
                   zp.codigo AS zona_codigo,
                   zp.nombre AS zona_nombre,
                   pe.cantidad
            FROM proyecto_especies pe
            JOIN especies e ON e.id = pe.especie_id
            JOIN zonas_plantacion zp ON zp.id = pe.zona_plantacion_id
            WHERE pe.proyecto_id = %s
            ORDER BY zp.id, e.nombre_comun
        """, (str(proyecto_id),))
        filas = serialize_rows(cur.fetchall())
        total_arboles = sum(f["cantidad"] for f in filas)
        return {
            "proyecto_id": str(proyecto_id),
            "total_arboles": total_arboles,
            "especies": filas
        }
    finally:
        conn.close()


# ══════════════════════════════════════════════
# HU-16: CÁLCULO DE SELECCIÓN Y ESTIMACIÓN
# ══════════════════════════════════════════════

def obtener_calculo_seleccion(proyecto_id: str) -> Dict[str, Any]:
    """
    Calcula los requerimientos técnicos y de insumos para la selección actual:
    - plántulas
    - compost_kg
    - agua_inicial_l
    - jornales de siembra
    - area_aprox_m2 CORREGIDA según el patrón geométrico (tresbolillo: espaciado² × 0.866)
    - advertencias de disponibilidad de stock en el vivero asignado.
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT p.*,
                   v.nombre AS vivero_nombre,
                   l.nombre AS lote_nombre,
                   l.codigo AS lote_codigo
            FROM proyectos p
            LEFT JOIN viveros v ON v.id = p.vivero_id
            LEFT JOIN lotes l ON l.id = p.lote_id
            WHERE p.id = %s
        """, (str(proyecto_id),))
        proy = cur.fetchone()
        if not proy:
            raise ValueError(f"Proyecto con id '{proyecto_id}' no encontrado")

        patron = proy["patron"] or "tresbolillo"
        factor_area = FACTORES_PATRON.get(patron, 0.866)
        espaciado_proyecto = float(proy["espaciado_m"]) if proy["espaciado_m"] else None
        vivero_id = str(proy["vivero_id"]) if proy["vivero_id"] else None
        cur.execute("""
            SELECT pe.especie_id,
                   e.codigo_taxon,
                   e.nombre_comun,
                   e.nombre_cientifico,
                   e.compost_kg_hoyo,
                   e.agua_inicial_l_planta,
                   e.plantulas_por_jornal,
                   e.espaciado_m AS espaciado_especie_m,
                   SUM(pe.cantidad) AS plantulas
            FROM proyecto_especies pe
            JOIN especies e ON e.id = pe.especie_id
            WHERE pe.proyecto_id = %s
            GROUP BY pe.especie_id, e.codigo_taxon, e.nombre_comun, e.nombre_cientifico,
                     e.compost_kg_hoyo, e.agua_inicial_l_planta, e.plantulas_por_jornal, e.espaciado_m
            ORDER BY e.nombre_comun
        """, (str(proyecto_id),))
        especies_calculo = cur.fetchall()
        stock_map = {}
        if vivero_id:
            cur.execute("""
                SELECT especie_id, stock
                FROM vivero_stock
                WHERE vivero_id = %s
            """, (vivero_id,))
            for s in cur.fetchall():
                stock_map[str(s["especie_id"])] = s["stock"]
        resumen_especies = []
        advertencias_stock = []

        total_plantulas = 0
        total_compost_kg = 0.0
        total_agua_l = 0.0
        total_jornales = 0.0
        total_area_aprox_m2 = 0.0

        for row in especies_calculo:
            eid = str(row["especie_id"])
            cant = int(row["plantulas"])
            compost_unit = float(row["compost_kg_hoyo"]) if row["compost_kg_hoyo"] is not None else 3.0
            agua_unit = float(row["agua_inicial_l_planta"]) if row["agua_inicial_l_planta"] is not None else 12.0
            rend_jornal = int(row["plantulas_por_jornal"]) if row["plantulas_por_jornal"] else 20
            espaciado = espaciado_proyecto or (float(row["espaciado_especie_m"]) if row["espaciado_especie_m"] else 3.0)
            area_especie = round(cant * (espaciado ** 2) * factor_area, 1)
            compost_kg = round(cant * compost_unit, 1)
            agua_l = round(cant * agua_unit, 1)
            jornales = round(cant / rend_jornal, 1)
            stock_disponible = stock_map.get(eid, 0) if vivero_id else None
            if vivero_id is not None:
                if stock_disponible < cant:
                    advertencias_stock.append({
                        "especie_id": eid,
                        "codigo_taxon": row["codigo_taxon"],
                        "nombre_comun": row["nombre_comun"],
                        "requeridas": cant,
                        "stock_disponible": stock_disponible,
                        "deficit": cant - stock_disponible,
                        "mensaje": f"Stock insuficiente en vivero: faltan {cant - stock_disponible} plántulas para '{row['nombre_comun']}'."
                    })

            resumen_especies.append({
                "especie_id": eid,
                "codigo_taxon": row["codigo_taxon"],
                "nombre_comun": row["nombre_comun"],
                "nombre_cientifico": row["nombre_cientifico"],
                "plantulas": cant,
                "espaciado_m": espaciado,
                "compost_kg": compost_kg,
                "agua_inicial_l": agua_l,
                "jornales": jornales,
                "area_aprox_m2": area_especie,
                "stock_vivero": stock_disponible
            })

            total_plantulas += cant
            total_compost_kg += compost_kg
            total_agua_l += agua_l
            total_jornales += jornales
            total_area_aprox_m2 += area_especie

        if not vivero_id and total_plantulas > 0:
            advertencias_stock.append({
                "tipo": "sin_vivero",
                "mensaje": "El proyecto no tiene un vivero asignado. Asigne un vivero para verificar la disponibilidad de plántulas."
            })

        area_meta = float(proy["area_restaurada_m2"]) if proy["area_restaurada_m2"] else None
        cobertura_meta_pct = None
        if area_meta and area_meta > 0:
            cobertura_meta_pct = round((total_area_aprox_m2 / area_meta) * 100, 1)

        return {
            "proyecto": {
                "id": str(proy["id"]),
                "nombre": proy["nombre"],
                "fase": proy["fase"],
                "patron": patron,
                "factor_patron": factor_area,
                "espaciado_base_m": espaciado_proyecto,
                "area_restaurada_m2": area_meta,
                "vivero_id": vivero_id,
                "vivero_nombre": proy.get("vivero_nombre")
            },
            "especies": resumen_especies,
            "totales": {
                "plantulas": total_plantulas,
                "compost_kg": round(total_compost_kg, 1),
                "compost_bultos_25kg": math.ceil(total_compost_kg / 25.0) if total_compost_kg > 0 else 0,
                "agua_inicial_l": round(total_agua_l, 1),
                "jornales_estimados": round(total_jornales, 1),
                "area_calculada_m2": round(total_area_aprox_m2, 1),
                "area_calculada_ha": round(total_area_aprox_m2 / 10000.0, 3),
                "cobertura_meta_pct": cobertura_meta_pct
            },
            "advertencias_stock": advertencias_stock,
            "formula_area": f"cant × espaciado² × {factor_area} ({patron})"
        }
    finally:
        conn.close()
