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
    Body del POST /lotes/:id/diagnosticos

    Ejemplo:
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
    Body del POST /lotes/:id/zonas-mapa

    Ejemplo:
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
