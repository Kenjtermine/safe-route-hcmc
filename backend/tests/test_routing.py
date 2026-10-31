"""Spike S1: đổi p của các đoạn thì tuyến Safest đổi, Fastest không đổi.
Cần DB đã nạp OSM (load_osm.sh). Dùng mốc thời gian riêng nên không đụng dữ liệu seed."""
from datetime import datetime

import pytest

from app.core.db import get_connection
from app.routing.service import find_routes

A = (106.7558, 10.8448)   # hai điểm mẫu trong README
B = (106.79, 10.81)
T = datetime(2099, 1, 1)


@pytest.fixture
def cleanup():
    yield
    with get_connection() as conn:
        conn.execute("DELETE FROM road_segment_risk WHERE thoi_diem = %s", (T,))


def test_safest_avoids_risky_segments(cleanup):
    fast0, safe0, _ = find_routes(A, B, at=T)
    assert fast0["edge_ids"] == safe0["edge_ids"]  # chưa có rủi ro -> hai tuyến trùng

    with get_connection() as conn:  # đặt p = 1 cho mọi đoạn của tuyến Fastest
        conn.execute(
            "INSERT INTO road_segment_risk (segment_id, thoi_diem, risk) "
            "SELECT unnest(%s::bigint[]), %s, 1", (fast0["edge_ids"], T))

    fast1, safe1, _ = find_routes(A, B, at=T)
    assert fast1["edge_ids"] == fast0["edge_ids"]   # Fastest bỏ qua rủi ro (β = 0)
    assert safe1["edge_ids"] != fast1["edge_ids"]   # Safest đi đường khác
    # Một vài đoạn sát A/B là không thể tránh, nên không so max_risk mà so số đoạn rủi ro còn phải đi qua
    shared = set(safe1["edge_ids"]) & set(fast1["edge_ids"])
    assert len(shared) < len(fast1["edge_ids"])