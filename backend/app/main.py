from fastapi import FastAPI

from app.core.config import settings
from app.core.db import get_connection

app = FastAPI(title="SAFE-ROUTE HCMC API")


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
