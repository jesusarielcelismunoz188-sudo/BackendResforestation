"""
Para ejecutar en desarrollo:
    uvicorn main:app --reload
"""
import os

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from Config.rate_limiter import RateLimitMiddleware
from Routes.auth import require_authenticated_user, router as auth_router
from Routes.home import router as home_router
from Routes.diagnosticos import router as diagnosticos_router
from Routes.mapa import router as mapa_router
from Routes.especies import router as especies_router
from Routes.proyectos import router as proyectos_router
from Routes.cuencas import router as cuencas_router

app = FastAPI(
    title="Reforest API",
    description="API para el sistema de reforestación — Diagnóstico, especies y planificación de siembra",
    version="1.0.0",
)

# Diez solicitudes por segundo por IP; el estado es local a cada proceso.
app.add_middleware(RateLimitMiddleware, limit=10, window_seconds=1.0)

# ── CORS (para que el frontend pueda consumir la API) ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in os.getenv(
            "CORS_ORIGINS",
            "http://localhost:3000,http://127.0.0.1:3000",
        ).split(",")
        if origin.strip()
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(home_router)
protected_route_dependencies = [Depends(require_authenticated_user)]
app.include_router(diagnosticos_router, dependencies=protected_route_dependencies)
app.include_router(mapa_router, dependencies=protected_route_dependencies)
app.include_router(especies_router, dependencies=protected_route_dependencies)
app.include_router(proyectos_router, dependencies=protected_route_dependencies)
app.include_router(cuencas_router, dependencies=protected_route_dependencies)
