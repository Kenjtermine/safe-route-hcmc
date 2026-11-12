from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router as routing_router
from app.core.config import settings
from app.core.db import get_connection

app = FastAPI(title="SAFE-ROUTE HCMC API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routing_router)

@app.get("/health")
def health() -> dict:
    return {"status": "ok", "env": settings.app_env}


@app.get("/health/db")
def health_db() -> dict:
    """Kiểm tra kết nối DB và các extension PostGIS / pgRouting đã sẵn sàng."""
    with get_connection() as conn:
        postgis = conn.execute("SELECT postgis_version()").fetchone()[0]
        pgrouting = conn.execute("SELECT pgr_version()").fetchone()[0]
    return {"postgis": postgis, "pgrouting": pgrouting}
