from fastapi import APIRouter, HTTPException, Query

from app.api.schemas import RouteOption, RouteRequest, RouteResponse
from app.routing.service import (BETA_SAFEST, NoRouteError, OutOfAreaError,
                                 find_routes, risk_geojson)

router = APIRouter(prefix="/api", tags=["routing"])


def _level(p: float) -> str:
    return "thấp" if p < 0.3 else "vừa" if p < 0.6 else "cao"


def _explain(fastest: dict, safest: dict) -> tuple[str, str, bool]:
    """Câu giải thích tạm thời."""
    if fastest["edge_ids"] == safest["edge_ids"]:
        msg = "Hai phương án trùng nhau: không có đoạn nào đủ rủi ro để phải đi vòng."
        return msg, msg, False
    dt = safest["duration_min"] - fastest["duration_min"]
    dd = safest["distance_km"] - fastest["distance_km"]
    s = (f"Mất thêm {dt} phút ({dd:+.1f} km) nhưng tránh đoạn có rủi ro "
         f"{_level(fastest['max_risk'])}; rủi ro lớn nhất còn {_level(safest['max_risk'])}.")
    f = f"Nhanh hơn {dt} phút nhưng đi qua đoạn có rủi ro {_level(fastest['max_risk'])}."
    return f, s, safest["max_risk"] < fastest["max_risk"]


@router.post("/route", response_model=RouteResponse)
def post_route(req: RouteRequest):
    try:
        fastest, safest, as_of = find_routes(req.origin, req.destination, req.beta or BETA_SAFEST)
    except OutOfAreaError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except NoRouteError as e:
        raise HTTPException(status_code=404, detail=str(e))
    f_text, s_text, safest_better = _explain(fastest, safest)
    return RouteResponse(
        fastest=RouteOption(**fastest, explanation=f_text, recommended=not safest_better),
        safest=RouteOption(**safest, explanation=s_text, recommended=safest_better),
        as_of=as_of,
    )


@router.get("/risk")
def get_risk(bbox: str = Query(..., description="west,south,east,north"),
             min_risk: float = Query(0.05, ge=0, le=1)):
    try:
        w, s, e, n = (float(x) for x in bbox.split(","))
    except ValueError:
        raise HTTPException(status_code=422, detail="bbox phải có dạng west,south,east,north")
    return risk_geojson((w, s, e, n), min_risk)