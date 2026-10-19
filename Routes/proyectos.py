"""
Routes/proyectos.py
===================
Controladores (rutas) para Proyectos y Selección de Especies (HU-16).

En la arquitectura del sistema, la "selección técnica" equivale a un `proyecto`
en fase `borrador` o `planificacion_activa`.

┌───────────────────────────────────────────────────┬─────────────────────────────────────────────────┐
│ Ruta                                              │ Qué hace                                        │
├───────────────────────────────────────────────────┼─────────────────────────────────────────────────┤
│ POST   /lotes/{id}/proyectos                      │ Crea proyecto en 'borrador'                     │
│ PUT    /proyectos/{id}/especies                   │ Reemplaza el conjunto de especies del proyecto │
│ POST   /proyectos/{id}/especies                   │ Añade o actualiza una especie en el proyecto    │
│ DELETE /proyectos/{id}/especies/{especieId}?zona= │ Quita una especie (por zona o global)           │
│ GET    /proyectos/{id}/especies                   │ Lista las especies asignadas al proyecto        │
│ GET    /proyectos/{id}/seleccion/calculo          │ Cálculo de insumos, área corregida y stock      │
└───────────────────────────────────────────────────┴─────────────────────────────────────────────────┘
"""
from fastapi import APIRouter, HTTPException, Query, status
from typing import List, Optional
from Models.schemas import ProyectoCreate, EspecieSeleccionItem
from Services import proyecto_service

router = APIRouter(tags=["Proyectos y Selección"])


# ══════════════════════════════════════════════
# HU-16: CREAR PROYECTO (SELECCIÓN EN BORRADOR)
# ══════════════════════════════════════════════

@router.post("/lotes/{lote_id}/proyectos", status_code=status.HTTP_201_CREATED)
def crear_proyecto(lote_id: str, body: ProyectoCreate):
    """
    Crea un nuevo proyecto en fase `borrador` para el lote indicado:
    - Asocia el nombre, vivero proveedor, fecha de inicio, patrón de siembra (tresbolillo, cuadrado, rectangular),
      espaciado y área meta en m².
    - Si no se envía `diagnostico_id`, vincula de forma automática el diagnóstico más reciente del lote.
    """
    try:
        return proyecto_service.crear_proyecto_borrador(lote_id, body)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error interno: {str(e)}")


# ══════════════════════════════════════════════
# GESTIÓN BOTÁNICA DEL PROYECTO
# ══════════════════════════════════════════════

@router.put("/proyectos/{proyecto_id}/especies")
def reemplazar_especies(proyecto_id: str, body: List[EspecieSeleccionItem]):
    """
    Reemplaza en su totalidad la selección botánica del proyecto:
    - Valida que el proyecto esté en fase `borrador` o `planificacion_activa`.
    - Valida cantidades estrictamente mayores a 0.
    - Valida que las especies existan en el catálogo y resuelve las zonas de plantación.
    - Ejecuta el reemplazo atómico en una sola transacción.
    """
    try:
        return proyecto_service.reemplazar_especies_proyecto(proyecto_id, body)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error interno: {str(e)}")


@router.post("/proyectos/{proyecto_id}/especies", status_code=status.HTTP_201_CREATED)
def agregar_especie(proyecto_id: str, body: EspecieSeleccionItem):
    """
    Añade una especie a una zona del proyecto (o actualiza su cantidad si ya existía).
    Valida fase del proyecto, cantidad > 0 y existencia de la especie.
    """
    try:
        return proyecto_service.agregar_o_actualizar_especie(proyecto_id, body)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error interno: {str(e)}")


@router.delete("/proyectos/{proyecto_id}/especies/{especie_id}")
def eliminar_especie(
    proyecto_id: str,
    especie_id: str,
    zona: Optional[str] = Query(None, description="Código (ej: dosel_alto) o ID de la zona. Si se omite, se quita la especie de todas las zonas.")
):
    """
    Elimina una especie del proyecto:
    - Si se especifica `zona`, se quita solo de esa zona de plantación.
    - Si se omite `zona`, se quita de todas las zonas del proyecto.
    - Valida que el proyecto esté en fase `borrador` o `planificacion_activa`.
    """
    try:
        return proyecto_service.eliminar_especie_proyecto(proyecto_id, especie_id, zona)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error interno: {str(e)}")


@router.get("/proyectos/{proyecto_id}/especies")
def listar_especies(proyecto_id: str):
    """
    Retorna la lista de todas las especies seleccionadas para el proyecto,
    sus cantidades agrupadas por zona de plantación y el total general.
    """
    try:
        return proyecto_service.listar_especies_proyecto(proyecto_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error interno: {str(e)}")


# ══════════════════════════════════════════════
# HU-16: CÁLCULO DE PLAN DE SIEMBRA
# ══════════════════════════════════════════════

@router.get("/proyectos/{proyecto_id}/seleccion/calculo")
def obtener_calculo_plan(proyecto_id: str):
    """
    Calcula los requerimientos integrales del plan de siembra:
    - Por especie: plántulas requeridas, compost (kg), agua inicial (litros), jornales de trabajo
      y área estimada en m².
    - Corrección del patrón geométrico:
      * En tresbolillo aplica: espaciado² × 0.866
      * En cuadrado/rectangular aplica: espaciado²
    - Totales consolidados de insumos y cobertura meta porcentual.
    - Advertencia si `plantulas > stock` del vivero asignado al proyecto.
    """
    try:
        return proyecto_service.obtener_calculo_seleccion(proyecto_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error interno: {str(e)}")
