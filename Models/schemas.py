"""
Models/schemas.py
=================
Modelos Pydantic para validar los datos de entrada (request bodies).

En el patrón MVC, estos son los "Modelos":
- Definen la FORMA de los datos que recibe la API.
- Validan automáticamente (ej: que precipitación tenga 12 valores).
- Si los datos no cumplen las reglas, FastAPI responde 422 automáticamente.
"""
from decimal import Decimal
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator
from uuid import UUID
from datetime import date


# ══════════════════════════════════════════════
# AUTENTICACIÓN (Supabase Auth)
# ══════════════════════════════════════════════

class RegisterRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)
    password: str = Field(..., min_length=6, max_length=128)
    full_name: Optional[str] = Field(None, max_length=120)


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)
    password: str = Field(..., min_length=1, max_length=128)


class GoogleCodeExchangeRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=4096)
    code_verifier: str = Field(
        ...,
        min_length=43,
        max_length=128,
        pattern=r"^[A-Za-z0-9._~-]+$",
    )


# ══════════════════════════════════════════════
# ONBOARDING
# ══════════════════════════════════════════════

class CoordenadaGPS(BaseModel):
    lat: float = Field(..., ge=-90, le=90, allow_inf_nan=False)
    lng: float = Field(..., ge=-180, le=180, allow_inf_nan=False)


class GeoJSONPolygon(BaseModel):
    type: Literal["Polygon"]
    coordinates: list[list[tuple[float, float]]]

    @model_validator(mode="after")
    def validate_rings(self):
        if not self.coordinates:
            raise ValueError("El polígono debe incluir al menos un anillo.")
        for ring in self.coordinates:
            if len(ring) < 4:
                raise ValueError("Cada anillo debe tener al menos cuatro coordenadas.")
            if ring[0] != ring[-1]:
                raise ValueError("El anillo del polígono debe estar cerrado.")
            for longitude, latitude in ring:
                if not -180 <= longitude <= 180 or not -90 <= latitude <= 90:
                    raise ValueError(
                        "Las coordenadas GeoJSON deben usar [longitud, latitud] "
                        "dentro del rango geográfico válido."
                    )
        return self


class FirstLoteCreate(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=200)
    area_ha: Decimal = Field(..., gt=0, max_digits=10, decimal_places=2)
    ubicacion: Optional[CoordenadaGPS] = None
    geom: Optional[GeoJSONPolygon] = None

    @field_validator("nombre")
    @classmethod
    def nombre_no_vacio(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("El nombre no puede estar vacío.")
        return value


class PredioOnboardingCreate(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=200)
    municipio: str = Field(..., min_length=1, max_length=120)
    departamento: str = Field(..., min_length=1, max_length=120)
    area_ha: Decimal = Field(..., gt=0, max_digits=10, decimal_places=2)
    ubicacion: Optional[CoordenadaGPS] = None
    primer_lote: FirstLoteCreate

    @field_validator("nombre", "municipio", "departamento")
    @classmethod
    def campos_texto_no_vacios(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("El valor no puede estar vacío.")
        return value

    @model_validator(mode="after")
    def area_del_primer_lote_valida(self):
        if self.primer_lote.area_ha > self.area_ha:
            raise ValueError("El área del primer lote no puede superar la del predio.")
        return self


class LoteOnboardingCreate(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=200)
    area_ha: Decimal = Field(..., gt=0, max_digits=10, decimal_places=2)
    ubicacion: Optional[CoordenadaGPS] = None
    geom: Optional[GeoJSONPolygon] = None

    @field_validator("nombre")
    @classmethod
    def nombre_no_vacio(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("El nombre no puede estar vacío.")
        return value


# ══════════════════════════════════════════════
# HU-02: PREDIOS Y LOTES
# ══════════════════════════════════════════════

class PredioCreate(BaseModel):
    nombre: str = Field(..., min_length=2, max_length=200)
    altitud_msnm: Optional[int] = None
    ubicacion: CoordenadaGPS
    descripcion: Optional[str] = None


class PredioUpdate(BaseModel):
    nombre: Optional[str] = Field(None, min_length=2, max_length=200)
    altitud_msnm: Optional[int] = None
    ubicacion: Optional[CoordenadaGPS] = None
    descripcion: Optional[str] = None


class LoteCreate(BaseModel):
    codigo: str = Field(..., min_length=1, max_length=80)
    nombre: Optional[str] = Field(None, max_length=200)
    area_ha: Optional[float] = Field(None, gt=0)
    prioridad: str = Field("media", pattern="^(alta|media|baja)$")
    altitud_msnm: Optional[int] = None
    pendiente_grados: Optional[float] = Field(None, ge=0, le=90)
    ubicacion: Optional[CoordenadaGPS] = None
    geom: Optional[dict] = None
    objetivos: List[int] = Field(default_factory=list)


class LoteUpdate(BaseModel):
    codigo: Optional[str] = Field(None, min_length=1, max_length=80)
    nombre: Optional[str] = Field(None, max_length=200)
    area_ha: Optional[float] = Field(None, gt=0)
    prioridad: Optional[str] = Field(None, pattern="^(alta|media|baja)$")
    altitud_msnm: Optional[int] = None
    pendiente_grados: Optional[float] = Field(None, ge=0, le=90)
    ubicacion: Optional[CoordenadaGPS] = None
    geom: Optional[dict] = None


# ══════════════════════════════════════════════
# HU-03: OBJETIVOS
# ══════════════════════════════════════════════

class ObjetivosReplace(BaseModel):
    objetivo_ids: List[int]


# ══════════════════════════════════════════════
# HU-04: MUESTRAS DE SUELO
# ══════════════════════════════════════════════

class MuestraSueloCreate(BaseModel):
    ph: float = Field(..., ge=0, le=14)
    textura_id: Optional[int] = None
    materia_organica_pct: Optional[float] = Field(None, ge=0, le=100)
    humedad_retencion_pct: Optional[float] = Field(None, ge=0, le=100)


# ══════════════════════════════════════════════
# HU-19: INSUMOS DE PROYECTO
# ══════════════════════════════════════════════

class ProyectoInsumoCreate(BaseModel):
    insumo_id: int = Field(..., gt=0)
    cantidad: float = Field(..., gt=0)
    estado: str = Field("pendiente", pattern="^(pendiente|en_transito|en_bodega)$")
    ubicacion: Optional[str] = None
    fecha_estimada_llegada: Optional[date] = None


class ProyectoInsumoUpdate(BaseModel):
    cantidad: Optional[float] = Field(None, gt=0)
    estado: Optional[str] = Field(None, pattern="^(pendiente|en_transito|en_bodega)$")
    ubicacion: Optional[str] = None
    fecha_estimada_llegada: Optional[date] = None


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
