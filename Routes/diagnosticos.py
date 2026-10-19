"""
Routes/diagnosticos.py
=======================
Controladores (rutas) para el módulo de diagnósticos.

En el patrón MVC, este archivo es el CONTROLADOR:
- Recibe las peticiones HTTP (request).
- Valida los datos con los Modelos (Pydantic).
- Llama a los Servicios para la lógica de negocio.
- Retorna la respuesta (view = JSON).

Las rutas aquí definidas:
┌──────────────────────────────────────────┬────────────────────────────────┐
│ Ruta                                     │ Qué hace                       │
├──────────────────────────────────────────┼────────────────────────────────┤
│ POST /lotes/{id}/diagnosticos            │ Crear diagnóstico completo     │
│ GET  /lotes/{id}/diagnostico             │ Diagnóstico vigente            │
│ GET  /lotes/{id}/diagnosticos            │ Historial de diagnósticos      │
│ GET  /diagnosticos/{id}/especies-sugeridas│ Especies compatibles          │
│ POST /diagnosticos/{id}/recalcular       │ Recalcular compatibilidad      │
└──────────────────────────────────────────┴────────────────────────────────┘
"""
from fastapi import APIRouter, HTTPException, Query
from Models.schemas import DiagnosticoCreate
from Services import diagnostico_service

router = APIRouter(tags=["Diagnósticos"])

# ══════════════════════════════════════════════
# POST /lotes/{lote_id}/diagnosticos
# ══════════════════════════════════════════════
@router.post("/lotes/{lote_id}/diagnosticos")
def crear_diagnostico(lote_id: str, body: DiagnosticoCreate):
    """
    Crea un diagnóstico completo para un lote.

    Todo ocurre en una transacción:
    1. Valida los 12 meses de precipitación.
    2. Inserta el diagnóstico con precipitación anual calculada.
    3. Inserta los 12 registros mensuales.
    4. Infiere el régimen si no viene.
    5. Resuelve la zona de vida Holdridge.
    6. Detecta ventanas de siembra.
    7. Calcula compatibilidad de especies.
    8. Responde con el diagnóstico completo.
    """
    try:
        resultado = diagnostico_service.crear_diagnostico(lote_id, body)
        return resultado
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")


# ══════════════════════════════════════════════
# GET /lotes/{lote_id}/diagnostico
# ══════════════════════════════════════════════
@router.get("/lotes/{lote_id}/diagnostico")
def obtener_diagnostico_vigente(lote_id: str):
    """
    Retorna el diagnóstico más reciente (vigente) de un lote.

    Incluye:
    - Datos del diagnóstico
    - Precipitación mensual (para gráficos)
    - Ventanas de siembra
    - Zona de vida (nombre, microclima, recomendación)
    - Resumen (cobertura remanente, especies sugeridas, compatibilidad promedio)
    - Restricciones (riesgo de acarreo, franja legal, conectividad)
    """
    resultado = diagnostico_service.obtener_diagnostico_vigente(lote_id)
    if not resultado:
        raise HTTPException(
            status_code=404,
            detail="No hay diagnósticos para este lote"
        )
    return resultado


# ══════════════════════════════════════════════
# GET /lotes/{lote_id}/diagnosticos
# ══════════════════════════════════════════════
@router.get("/lotes/{lote_id}/diagnosticos")
def obtener_historial(lote_id: str):
    """
    Retorna el historial de todos los diagnósticos de un lote,
    ordenados del más reciente al más antiguo.
    """
    historial = diagnostico_service.obtener_historial(lote_id)
    return {"lote_id": lote_id, "diagnosticos": historial}


# ══════════════════════════════════════════════
# GET /diagnosticos/{diagnostico_id}/especies-sugeridas
# ══════════════════════════════════════════════
@router.get("/diagnosticos/{diagnostico_id}/especies-sugeridas")
def obtener_especies_sugeridas(
    diagnostico_id: str,
    min: float = Query(default=50, description="Compatibilidad mínima (0-100)"),
    limit: int = Query(default=None, description="Máximo de resultados")
):
    """
    Retorna las especies compatibles con el diagnóstico,
    ordenadas por compatibilidad descendente.

    Parámetros de query:
    - min: puntaje mínimo de compatibilidad (default: 50)
    - limit: cantidad máxima de resultados (default: sin límite)
    """
    especies = diagnostico_service.obtener_especies_sugeridas(
        diagnostico_id, min_compat=min, limit=limit
    )
    return {
        "diagnostico_id": diagnostico_id,
        "total": len(especies),
        "especies": especies
    }


# ══════════════════════════════════════════════
# POST /diagnosticos/{diagnostico_id}/recalcular
# ══════════════════════════════════════════════
@router.post("/diagnosticos/{diagnostico_id}/recalcular")
def recalcular(diagnostico_id: str):
    """
    Vuelve a ejecutar el algoritmo de compatibilidad de especies.

    Útil cuando:
    - Cambian los objetivos del lote.
    - Se agregan nuevas especies al catálogo.
    - Se ajustan los pesos del algoritmo.
    """
    resultado = diagnostico_service.recalcular_compatibilidad(diagnostico_id)
    if not resultado:
        raise HTTPException(
            status_code=404,
            detail="Diagnóstico no encontrado"
        )
    return resultado
