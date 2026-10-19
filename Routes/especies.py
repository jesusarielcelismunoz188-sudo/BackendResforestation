"""
Routes/especies.py
==================
Controladores (rutas) para el módulo de Especies, Protocolos y Viveros.

Cumple con HU-13, HU-14 y HU-15:
┌───────────────────────────────────────────────┬──────────────────────────────────────────────────────┐
│ Ruta                                          │ Qué hace                                             │
├───────────────────────────────────────────────┼──────────────────────────────────────────────────────┤
│ GET  /especies/{id}?lote_id=                  │ Ficha técnica completa (+ medidores de ajuste)      │
│ GET  /especies/{id}/protocolo                 │ Protocolo de siembra ordenado por fases              │
│ GET  /especies/{id}/stock?lote_id=            │ Stock por vivero (ordenado por ST_Distance con lote) │
│ GET  /viveros                                 │ Catálogo de viveros registrados                      │
│ POST /especies/{id}/ficha-tecnica             │ Exporta y registra PDF en documentos_exportados      │
└───────────────────────────────────────────────┴──────────────────────────────────────────────────────┘
"""
from fastapi import APIRouter, HTTPException, Query, status
from typing import Optional
from Models.schemas import FichaExportCreate
from Services import especie_service

router = APIRouter(tags=["Especies y Viveros"])


# ══════════════════════════════════════════════
# HU-13: FICHA TÉCNICA
# ══════════════════════════════════════════════

@router.get("/especies/{especie_id}")
def obtener_ficha_tecnica(
    especie_id: str,
    lote_id: Optional[str] = Query(None, description="UUID del lote para calcular los medidores de ajuste agronómico")
):
    """
    Retorna la ficha técnica integral de la especie botánica:
    - Datos taxonómicos, morfología, familia, estrato, grupo funcional, tasa de crecimiento y tipo de raíz.
    - Catálogos asociados: texturas de suelo compatibles, regímenes hídricos, etiquetas y servicios ecosistémicos.
    
    Si se incluye `lote_id`:
    - Añade `medidores_ajuste`: compara altitud, pH, humedad radicular y sol del lote frente a los rangos de la especie,
      calculando el porcentaje de ajuste individual con la misma lógica matemática del algoritmo de compatibilidad.
    """
    try:
        return especie_service.obtener_ficha_tecnica(especie_id, lote_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error interno: {str(e)}")


# ══════════════════════════════════════════════
# HU-14: PROTOCOLO DE SIEMBRA
# ══════════════════════════════════════════════

@router.get("/especies/{especie_id}/protocolo")
def obtener_protocolo(especie_id: str):
    """
    Retorna los pasos del protocolo técnico de siembra para la especie,
    ordenados cronológicamente por `orden` (excavación, desembuchado, fijación, riego, mulch, etc.).
    """
    try:
        return especie_service.obtener_protocolo_siembra(especie_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error interno: {str(e)}")


# ══════════════════════════════════════════════
# HU-15: STOCK POR VIVERO Y CERCANÍA
# ══════════════════════════════════════════════

@router.get("/especies/{especie_id}/stock")
def obtener_stock(
    especie_id: str,
    lote_id: Optional[str] = Query(None, description="UUID del lote para ordenar los viveros por cercanía geográfica (ST_Distance)")
):
    """
    Consulta la disponibilidad de plántulas de la especie en cada vivero:
    - Cantidad en stock, disponibilidad (`disponible: stock > 0`), certificado de origen y fecha de actualización.
    - Si se envía `lote_id`, ordena los viveros de menor a mayor distancia geográfica en kilómetros usando PostGIS.
    """
    try:
        return especie_service.obtener_stock_especie(especie_id, lote_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error interno: {str(e)}")


@router.get("/viveros")
def listar_viveros():
    """
    Retorna la lista de todos los viveros aliados registrados, su ubicación geográfica
    y el resumen de plántulas disponibles.
    """
    try:
        return especie_service.listar_viveros()
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error interno: {str(e)}")


# ══════════════════════════════════════════════
# EXPORTACIÓN DE FICHA TÉCNICA
# ══════════════════════════════════════════════

@router.post("/especies/{especie_id}/ficha-tecnica", status_code=status.HTTP_201_CREATED)
def exportar_ficha_tecnica(
    especie_id: str,
    body: Optional[FichaExportCreate] = None
):
    """
    Genera el registro del documento exportado de la ficha técnica (tipo `ficha_tecnica_especie`)
    y lo almacena en la tabla `documentos_exportados`.
    """
    try:
        url = body.url if body else None
        generado_por = str(body.generado_por) if (body and body.generado_por) else None
        return especie_service.registrar_exportacion_ficha(especie_id, url, generado_por)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error interno: {str(e)}")
