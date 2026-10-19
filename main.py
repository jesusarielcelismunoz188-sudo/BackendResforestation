"""
Para ejecutar en desarrollo:
    uvicorn main:app --reload
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from Routes.home import router as home_router
from Routes.diagnosticos import router as diagnosticos_router
from Routes.mapa import router as mapa_router

app = FastAPI(
    title="Reforest API",
    description="API para el sistema de reforestación — Diagnóstico y planificación de siembra",
    version="1.0.0",
)

# ── CORS (para que el frontend pueda consumir la API) ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],      # En producción, poner el dominio del frontend
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(home_router)
app.include_router(diagnosticos_router)
app.include_router(mapa_router)
