"""
Models/schemas.py
=================
Modelos Pydantic para validar los datos de entrada (request bodies).

En el patrón MVC, estos son los "Modelos":
- Definen la FORMA de los datos que recibe la API.
- Validan automáticamente (ej: que precipitación tenga 12 valores).
- Si los datos no cumplen las reglas, FastAPI responde 422 automáticamente.
"""
from pydantic import BaseModel, Field
from typing import List, Optional
from uuid import UUID


# ══════════════════════════════════════════════
# DIAGNÓSTICO
# ══════════════════════════════════════════════

class DiagnosticoCreate(BaseModel):
    """
    {
        "muestra_suelo_id": "uuid-de-la-muestra",
        "perdida_cobertura_pct": 35,
        "precipitacion_mensual": [120, 95, 150, 180, 200, 80, 60, 70, 140, 190, 160, 100],
        "regimen_precipitacion": "bimodal",
        "franja_riparia_legal_m": 30,
        "riesgo_acarreo": "medio_alto",
        "conectividad_fauna": "parcial",
        "observaciones": "Zona con erosión visible"
    }
    """
    muestra_suelo_id: Optional[UUID] = None
    perdida_cobertura_pct: float = Field(..., ge=0, le=100)
    precipitacion_mensual: List[float] = Field(
        ...,
        min_length=12,
        max_length=12,
        description="12 valores de precipitación mensual en mm (enero a diciembre)"
    )
    regimen_precipitacion: Optional[str] = Field(
        None,
        description="'bimodal' o 'monomodal'. Si no se envía, se infiere."
    )
    franja_riparia_legal_m: Optional[int] = Field(None, ge=0)
    riesgo_acarreo: Optional[str] = Field(
        None,
        description="bajo | medio | medio_alto | alto"
    )
    conectividad_fauna: Optional[str] = Field(
        None,
        description="continuo | parcial | interrumpido"
    )
    observaciones: Optional[str] = None


# ══════════════════════════════════════════════
# ZONAS DE MAPA
# ══════════════════════════════════════════════

class ZonaMapaCreate(BaseModel):
    """
    {
        "tipo": "franja_riparia",
        "etiqueta": "Franja río principal",
        "geom": { "type": "Polygon", "coordinates": [[[...], ...]] }
    }
    """
    tipo: str = Field(
        ...,
        description="siembra_prioritaria | franja_riparia | corredor_biologico"
    )
    etiqueta: Optional[str] = None
    geom: dict = Field(..., description="Geometría en formato GeoJSON")


class ZonaMapaUpdate(BaseModel):
    """Body del PATCH /zonas-mapa/:id — todos los campos son opcionales."""
    tipo: Optional[str] = None
    etiqueta: Optional[str] = None
    geom: Optional[dict] = None


# ══════════════════════════════════════════════
# HU-16: PROYECTOS Y SELECCIÓN DE ESPECIES
# ══════════════════════════════════════════════

class ProyectoCreate(BaseModel):
    """
    Body del POST /lotes/:id/proyectos
    """
    nombre: str = Field(..., min_length=2, description="Nombre descriptivo del proyecto")
    diagnostico_id: Optional[UUID] = Field(None, description="Diagnóstico vigente asociado (si es null se busca el último)")
    vivero_id: Optional[UUID] = Field(None, description="Vivero seleccionado para suministro de plántulas")
    responsable_id: Optional[UUID] = None
    fecha_inicio: Optional[str] = Field(None, description="Fecha tentativa de inicio (YYYY-MM-DD)")
    patron: Optional[str] = Field("tresbolillo", description="tresbolillo | cuadrado | rectangular")
    espaciado_m: Optional[float] = Field(3.0, gt=0, description="Distancia entre plántulas en metros")
    area_restaurada_m2: Optional[float] = Field(None, gt=0, description="Área meta a restaurar en m²")
    hoyo_lado_cm: Optional[int] = Field(40, gt=0, description="Ancho del hoyo de siembra en cm")
    hoyo_profundidad_cm: Optional[int] = Field(40, gt=0, description="Profundidad del hoyo de siembra en cm")


class EspecieSeleccionItem(BaseModel):
    """
    Elemento individual de selección de especie para el proyecto.
    """
    especie_id: UUID = Field(..., description="UUID de la especie seleccionada")
    zona_plantacion: str = Field(..., description="Código (ej: dosel_alto, ripario, borde) o ID de la zona")
    cantidad: int = Field(..., gt=0, description="Número de plántulas a sembrar (> 0)")


class FichaExportCreate(BaseModel):
    """
    Body opcional del POST /especies/:id/ficha-tecnica
    """
    url: Optional[str] = Field(None, description="URL pública del documento si ya fue generado")
    generado_por: Optional[UUID] = None

class registroCuenca(BaseModel):

    nombre: str = Field(..., min_length=2, description="Nombre de su cuenca")
    descripcion: Optional[str] = Field(None, description="Descripción de la cuenca")
    elevacion_msnm: Optional[int] = Field(None, description="Elevación media de la cuenca en metros sobre el nivel del mar")
    altitud_min_msnm: Optional[int] = Field(None, description="Altitud minima de la cuenca en metros sobre el nivel del mar")
    altitud_max_msnm: Optional[int] = Field(None, description="Altitud máxima de la cuenca en metros sobre el nivel del mar")
    geom: dict = Field(..., description="Geometría en formato GeoJSON")
