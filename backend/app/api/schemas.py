"""Hợp đồng API với frontend (khớp frontend/src/types/api.ts)."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

LngLat = tuple[float, float]  # (kinh độ, vĩ độ)


class RouteRequest(BaseModel):
    origin: LngLat
    destination: LngLat
    beta: float | None = Field(default=None, ge=0, le=100)  # trống = β mặc định của Safest


class LineString(BaseModel):
    type: Literal["LineString"] = "LineString"
    coordinates: list[LngLat]


class RouteOption(BaseModel):
    kind: Literal["safest", "fastest"]
    duration_min: int
    distance_km: float
    via: list[str]
    max_risk: float                  # p lớn nhất dọc tuyến, 0..1
    clearance_m: float | None = None  # chưa có dữ liệu cao độ thật
    explanation: str = ""
    recommended: bool = False
    geometry: LineString


class RouteResponse(BaseModel):
    safest: RouteOption
    fastest: RouteOption
    as_of: datetime | None = None    # thời điểm của dữ liệu