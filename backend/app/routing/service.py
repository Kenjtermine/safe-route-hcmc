"""Routing service: pgRouting (pgr_aStar), cost = time × (1 + β × p)  (tài liệu v0, mục 6.1)."""
from datetime import datetime

from psycopg import sql
from psycopg.rows import dict_row

from app.core.db import get_connection

BETA_SAFEST = 20.0
SNAP_MAX_M = 500
LOW_CONF_M = 5000

LngLat = tuple[float, float]


class OutOfAreaError(Exception):
    pass


class NoRouteError(Exception):
    pass


SNAP_SQL = """
WITH p AS (SELECT ST_SetSRID(ST_MakePoint(%s, %s), 4326) AS g)
SELECT v.id, ST_Distance(v.the_geom::geography, p.g::geography) AS d
FROM ways_vertices_pgr v, p
ORDER BY v.the_geom <-> p.g
LIMIT 1
"""

PATH_SQL = """
SELECT p.path_seq, w.gid, w.name, w.length_m,
       CASE WHEN p.node = w.source THEN w.cost_s ELSE w.reverse_cost_s END AS time_s,
       COALESCE(r.risk, 0) AS risk,
       ST_AsGeoJSON(CASE WHEN p.node = w.source THEN w.the_geom
                         ELSE ST_Reverse(w.the_geom) END)::json AS geom
FROM pgr_aStar(%s::text, %s::bigint, %s::bigint, directed => true) p
JOIN ways w ON w.gid = p.edge
LEFT JOIN road_segment_risk r ON r.segment_id = w.gid AND r.thoi_diem = %s
ORDER BY p.path_seq
"""

RISK_SQL = """
SELECT r.risk, COALESCE(s.d_mua_m, 0) > %s AS low_confidence,
       ST_AsGeoJSON(ST_SimplifyPreserveTopology(w.the_geom, 0.00003))::json AS geom
FROM ways w
JOIN road_segment_risk r ON r.segment_id = w.gid AND r.thoi_diem = %s
LEFT JOIN segment_station s ON s.segment_id = w.gid
WHERE w.the_geom && ST_MakeEnvelope(%s, %s, %s, %s, 4326) AND r.risk >= %s
"""


def latest_time(cur) -> datetime | None:
    cur.execute("SELECT max(thoi_diem) AS t FROM road_segment_risk")
    return cur.fetchone()["t"]


def _snap(cur, point: LngLat, label: str) -> int:
    cur.execute(SNAP_SQL, point)
    row = cur.fetchone()
    if row is None or row["d"] > SNAP_MAX_M:
        raise OutOfAreaError(f"{label} nằm ngoài vùng hỗ trợ.")
    return row["id"]


def _edges_sql(conn, beta: float, t: datetime | None) -> str:
    q = sql.SQL("""
        SELECT w.gid AS id, w.source, w.target,
               w.cost_s         * (1 + {b} * COALESCE(r.risk, 0)) AS cost,
               w.reverse_cost_s * (1 + {b} * COALESCE(r.risk, 0)) AS reverse_cost,
               w.x1, w.y1, w.x2, w.y2
        FROM ways w
        LEFT JOIN road_segment_risk r ON r.segment_id = w.gid AND r.thoi_diem = {t}
    """).format(b=sql.Literal(float(beta)), t=sql.Literal(t))
    return q.as_string(conn)


def _summarize(kind: str, rows: list[dict]) -> dict:
    if not rows:
        raise NoRouteError("Không tìm được đường nối hai điểm này.")
    coords: list = []
    for r in rows:
        c = r["geom"]["coordinates"]
        coords.extend(c[1:] if coords else c)
    by_name: dict[str, float] = {}
    for r in rows:
        if r["name"]:
            by_name[r["name"]] = by_name.get(r["name"], 0) + (r["length_m"] or 0)
    secs = sum(r["time_s"] or 0 for r in rows)
    return {
        "kind": kind,
        "duration_min": max(1, round(secs / 60)),
        "distance_km": round(sum(r["length_m"] or 0 for r in rows) / 1000, 1),
        "via": sorted(by_name, key=by_name.get, reverse=True)[:2],
        "max_risk": float(max(r["risk"] for r in rows)),
        "clearance_m": None,
        "geometry": {"type": "LineString", "coordinates": coords},
        "edge_ids": [r["gid"] for r in rows],
    }


def find_routes(origin: LngLat, destination: LngLat, beta: float = BETA_SAFEST,
                at: datetime | None = None):
    """Trả (fastest, safest, as_of). at=None: dùng thời điểm rủi ro mới nhất."""
    with get_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        t = at or latest_time(cur)
        src = _snap(cur, origin, "Điểm xuất phát")
        dst = _snap(cur, destination, "Điểm đến")
        if src == dst:
            raise NoRouteError("Điểm đi và điểm đến trùng nhau.")
        out = {}
        for kind, b in (("fastest", 0.0), ("safest", beta)):
            cur.execute(PATH_SQL, (_edges_sql(conn, b, t), src, dst, t))
            out[kind] = _summarize(kind, cur.fetchall())
    return out["fastest"], out["safest"], t


def risk_geojson(bbox: tuple[float, float, float, float], min_risk: float = 0.05) -> dict:
    """Lớp rủi ro cho bản đồ: chỉ các đoạn trong khung nhìn và có p >= min_risk."""
    with get_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        t = latest_time(cur)
        cur.execute(RISK_SQL, (LOW_CONF_M, t, *bbox, min_risk))
        feats = [
            {"type": "Feature", "geometry": r["geom"],
             "properties": {"p": float(r["risk"]), "low_confidence": r["low_confidence"]}}
            for r in cur.fetchall() if r["geom"]
        ]
    return {"type": "FeatureCollection", "features": feats, "as_of": t.isoformat() if t else None}