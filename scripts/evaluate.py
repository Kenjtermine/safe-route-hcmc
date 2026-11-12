"""scripts/evaluate.py: đánh giá theo kịch bản (chỉ mục 12).

Ba kịch bản:  1 = thời tiết bình thường · 2 = mưa lớn cục bộ · 3 = mưa lớn + triều cường.
Tiêu chí thành công của thầy (kịch bản 3): giảm ít nhất 80% quãng đường đi qua đoạn có
flood_probability > 0,7, với thời gian tăng thêm không quá 15% so với tuyến Fastest.

Cấu trúc:
  * Hàm THUẦN (test không cần DB): route_metrics, summarize, criterion_scenario3,
    classify_conditions, pick_times, render_markdown, ...
  * Phần cần hệ thống thật: fetch_candidates (SQL), replay_risks (gọi risk.compute.run),
    và get_routes do người C cắm vào:
        get_routes(od, thoi_diem) -> (fastest_segments, safest_segments)
    mỗi tuyến là list[RouteSegment].

Lưu ý: tiêu chí 80% được đo bằng CHÍNH mô hình rủi ro của nhóm, nên không chứng minh mô hình
đúng; nó chỉ cho biết bộ định tuyến phản ứng đúng với rủi ro mà mô hình sinh ra.
"""
from __future__ import annotations

import argparse
import csv
import importlib
import logging
import os
import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable

from backend.app.explain.engine import RISKY_PROB, explain_pair   # RISKY_PROB: một nguồn duy nhất

logger = logging.getLogger(__name__)

HEAVY_RAIN_MM = 50.0     # mưa lớn: tổng 1 giờ ở ít nhất một trạm
DRY_RAIN_MM = 1.0        # coi là không mưa
MAX_TIME_INCREASE_PCT = 15.0
MIN_RISKY_REDUCTION_PCT = 80.0
SCENARIO_NAMES = {1: "Thời tiết bình thường", 2: "Mưa lớn cục bộ", 3: "Mưa lớn + triều cường"}


# ---------------------------------------------------------------- kiểu dữ liệu
@dataclass(frozen=True)
class RouteSegment:
    segment_id: int
    length_m: float
    time_s: float


@dataclass(frozen=True)
class OD:
    od_id: str
    o_lon: float
    o_lat: float
    d_lon: float
    d_lat: float


GetRoutes = Callable[[OD, datetime], "tuple[list[RouteSegment], list[RouteSegment]]"]


# ---------------------------------------------------------------- đo một tuyến
def route_metrics(route, risk_by_segment: dict, risky_prob: float = RISKY_PROB) -> dict:
    """Trả đúng bốn khóa mà explain() cần. Đoạn không có trong bản đồ rủi ro tính là 0."""
    risks = [risk_by_segment.get(s.segment_id, 0.0) for s in route]
    return {
        "time_min": sum(s.time_s for s in route) / 60.0,
        "length_km": sum(s.length_m for s in route) / 1000.0,
        "risky_km": sum(s.length_m for s, p in zip(route, risks) if p > risky_prob) / 1000.0,
        "max_risk": max(risks, default=0.0),
    }


def evaluate_pair(od, thoi_diem, scenario, get_routes, risk_by_segment) -> dict:
    fast_route, safe_route = get_routes(od, thoi_diem)
    fm = route_metrics(fast_route, risk_by_segment)
    sm = route_metrics(safe_route, risk_by_segment)
    ex = explain_pair(fm, sm)
    row = {"scenario": scenario, "od_id": od.od_id, "thoi_diem": thoi_diem,
           "same_route": [s.segment_id for s in fast_route] == [s.segment_id for s in safe_route],
           "explain_case": ex["case"], "explain_safest": ex["safest"]}
    row.update({f"fastest_{k}": v for k, v in fm.items()})
    row.update({f"safest_{k}": v for k, v in sm.items()})
    return row


def evaluate_scenarios(scenario_times: dict, ods, get_routes: GetRoutes,
                       load_risk: Callable[[datetime], dict]) -> list:
    """Chạy mọi cặp OD tại mọi thời điểm của từng kịch bản. load_risk(thoi_diem) -> {segment_id: p}."""
    rows, cache = [], {}
    for scenario, times in sorted(scenario_times.items()):
        if not times:
            logger.warning("Kịch bản %s không có thời điểm nào để đánh giá", scenario)
        for t in times:
            if t not in cache:
                cache[t] = load_risk(t)
            for od in ods:
                rows.append(evaluate_pair(od, t, scenario, get_routes, cache[t]))
    return rows


# ---------------------------------------------------------------- tổng hợp
def _pct(num, den):
    return None if den <= 0 else num / den * 100.0


def summarize(rows) -> dict:
    """{scenario: tổng hợp}. Giảm rủi ro tính trên TỔNG km của mọi cặp (không lấy trung bình tỷ lệ)."""
    out = {}
    for sc in sorted({r["scenario"] for r in rows}):
        rs = [r for r in rows if r["scenario"] == sc]
        f_risky = sum(r["fastest_risky_km"] for r in rs)
        s_risky = sum(r["safest_risky_km"] for r in rs)
        f_time = sum(r["fastest_time_min"] for r in rs)
        s_time = sum(r["safest_time_min"] for r in rs)
        over = sum(1 for r in rs if r["safest_time_min"] > r["fastest_time_min"]
                   * (1 + MAX_TIME_INCREASE_PCT / 100.0))
        out[sc] = {
            "n": len(rs),
            "fastest_risky_km": f_risky,
            "safest_risky_km": s_risky,
            "risky_reduction_pct": None if f_risky <= 0 else (1 - s_risky / f_risky) * 100.0,
            "time_increase_pct": None if f_time <= 0 else (s_time / f_time - 1) * 100.0,
            "share_over_time_limit": over / len(rs),
            "identical_route_share": sum(1 for r in rs if r["same_route"]) / len(rs),
        }
    return out


def criterion_scenario3(summary: dict, min_reduction_pct: float = MIN_RISKY_REDUCTION_PCT,
                        max_time_pct: float = MAX_TIME_INCREASE_PCT) -> dict:
    """None nghĩa là không đánh giá được (ví dụ tuyến Fastest không đi qua đoạn nguy cơ nào)."""
    red, inc = summary.get("risky_reduction_pct"), summary.get("time_increase_pct")
    reduction_ok = None if red is None else red >= min_reduction_pct
    time_ok = None if inc is None else inc <= max_time_pct
    passed = None if reduction_ok is None or time_ok is None else (reduction_ok and time_ok)
    return {"reduction_ok": reduction_ok, "time_ok": time_ok, "passed": passed}


def load_reference_csv(path: str) -> dict:
    """CSV lấy tay từ Google Maps: od_id, gmaps_time_min, gmaps_length_km."""
    with open(path, newline="", encoding="utf-8") as f:
        return {r["od_id"]: {"time_min": float(r["gmaps_time_min"]),
                             "length_km": float(r["gmaps_length_km"])}
                for r in csv.DictReader(f)}


def reference_comparison(rows, refs: dict, scenario: int = 1):
    """Trung vị tỷ lệ thời gian Fastest / Google Maps ở kịch bản bình thường (≈ 1 là tương đương)."""
    ratios = [r["fastest_time_min"] / refs[r["od_id"]]["time_min"]
              for r in rows if r["scenario"] == scenario and r["od_id"] in refs
              and refs[r["od_id"]]["time_min"] > 0]
    return {"n": len(ratios), "median_time_ratio": statistics.median(ratios)} if ratios else None


# ---------------------------------------------------------------- chọn thời điểm cho từng kịch bản
def classify_conditions(max_mm_1h: float, max_alert: int):
    """Kịch bản (1, 2, 3) hoặc None nếu không thuộc kịch bản nào."""
    if max_mm_1h >= HEAVY_RAIN_MM and max_alert >= 2:
        return 3
    if max_mm_1h >= HEAVY_RAIN_MM and max_alert == 0:
        return 2
    if max_mm_1h < DRY_RAIN_MM and max_alert == 0:
        return 1
    return None


def pick_times(rows, per_scenario: int = 3, min_gap_hours: float = 3.0) -> dict:
    """rows: (ts, max_mm_1h, max_alert). Kịch bản 1: rải đều; 2 và 3: mưa lớn nhất, cách nhau
    ít nhất min_gap_hours để không lấy các mốc liền nhau của cùng một cơn mưa."""
    buckets = {1: [], 2: [], 3: []}
    for ts, mm, alert in rows:
        sc = classify_conditions(mm, alert)
        if sc is not None:
            buckets[sc].append((ts, mm))

    picked = {}
    s1 = sorted(buckets[1])
    step = max(1, len(s1) // per_scenario)
    picked[1] = [s1[i * step][0] for i in range(per_scenario) if i * step < len(s1)]
    for sc in (2, 3):
        chosen = []
        for ts, _ in sorted(buckets[sc], key=lambda x: (-x[1], x[0])):
            if all(abs(ts - c) >= timedelta(hours=min_gap_hours) for c in chosen):
                chosen.append(ts)
            if len(chosen) == per_scenario:
                break
        picked[sc] = sorted(chosen)
    return picked


SQL_CANDIDATES = """
WITH r AS (
  SELECT tram, ts, sum(mua_10phut_mm) OVER (
           PARTITION BY tram ORDER BY ts
           RANGE BETWEEN INTERVAL '50 minutes' PRECEDING AND CURRENT ROW) AS mm_1h
  FROM rain_10min
), rain_ts AS (
  SELECT ts, max(mm_1h) AS max_mm_1h FROM r GROUP BY ts
), tide AS (
  SELECT ngay, max(muc_bao_dong) AS max_alert FROM tide_daily
  WHERE COALESCE(nghi_van, false) = false GROUP BY ngay
)
SELECT rt.ts, rt.max_mm_1h, td.max_alert
FROM rain_ts rt JOIN tide td ON td.ngay = rt.ts::date
ORDER BY rt.ts
"""
SQL_RISK_MAP = "SELECT segment_id, risk FROM road_segment_risk WHERE thoi_diem = %s"


def fetch_candidates(conn):
    with conn.cursor() as cur:
        cur.execute(SQL_CANDIDATES)
        return [(ts, float(mm), int(al)) for ts, mm, al in cur.fetchall()]


def load_risk_map(conn, thoi_diem: datetime) -> dict:
    with conn.cursor() as cur:
        cur.execute(SQL_RISK_MAP, (thoi_diem,))
        return {int(sid): float(risk) for sid, risk in cur.fetchall()}


def ablation_configs() -> dict:
    """Các biến thể để so sánh: có/không sàn báo động, decay mean/min."""
    from backend.app.risk.compute import ComputeConfig
    return {"base": ComputeConfig(),
            "alert_floor_on": ComputeConfig(use_alert_floor=True),
            "decay_min": ComputeConfig(decay_mode="min")}


def replay_risks(conn, times, cfg) -> None:
    """Chạy compute cho từng mốc thời gian lịch sử (event stream giả lập), ghi vào road_segment_risk."""
    from backend.app.risk.compute import run
    for t in times:
        run(conn, t, cfg)


# ---------------------------------------------------------------- báo cáo
def write_rows_csv(rows, path: str) -> None:
    if not rows:
        return
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def _fmt(v, suffix=""):
    return "n/a" if v is None else f"{v:.1f}{suffix}"


def render_markdown(summaries: dict) -> str:
    """summaries: {tên cấu hình: {scenario: tổng hợp}}."""
    lines = ["# Kết quả đánh giá theo kịch bản", ""]
    for name, summ in summaries.items():
        lines += [f"## Cấu hình: {name}", "",
                  "| Kịch bản | Số lượt | Km nguy cơ Fastest | Km nguy cơ Safest | Giảm rủi ro | Tăng thời gian | Lượt vượt 15% | Trùng tuyến |",
                  "|---|---|---|---|---|---|---|---|"]
        for sc, s in sorted(summ.items()):
            lines.append(
                f"| {sc}. {SCENARIO_NAMES.get(sc, '')} | {s['n']} | {s['fastest_risky_km']:.2f} | "
                f"{s['safest_risky_km']:.2f} | {_fmt(s['risky_reduction_pct'], '%')} | "
                f"{_fmt(s['time_increase_pct'], '%')} | {s['share_over_time_limit'] * 100:.0f}% | "
                f"{s['identical_route_share'] * 100:.0f}% |")
        if 3 in summ:
            c = criterion_scenario3(summ[3])
            verdict = {True: "ĐẠT", False: "KHÔNG ĐẠT", None: "không đánh giá được"}[c["passed"]]
            lines += ["", f"Tiêu chí kịch bản 3 (giảm ≥ {MIN_RISKY_REDUCTION_PCT:.0f}% km nguy cơ, "
                          f"tăng thời gian ≤ {MAX_TIME_INCREASE_PCT:.0f}%): **{verdict}** "
                          f"(giảm rủi ro: {c['reduction_ok']}, thời gian: {c['time_ok']})"]
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------- CLI (cần DB thật và bộ định tuyến của C)
def _load_ods(path: str) -> list:
    with open(path, newline="", encoding="utf-8") as f:
        return [OD(r["od_id"], float(r["o_lon"]), float(r["o_lat"]),
                   float(r["d_lon"]), float(r["d_lat"])) for r in csv.DictReader(f)]


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dsn", required=True)
    ap.add_argument("--od-csv", required=True, help="od_id,o_lon,o_lat,d_lon,d_lat")
    ap.add_argument("--routes", required=True, help="module:function, là get_routes của người C")
    ap.add_argument("--ref-csv", help="od_id,gmaps_time_min,gmaps_length_km (lấy tay từ Google Maps)")
    ap.add_argument("--out", default="eval_out")
    ap.add_argument("--per-scenario", type=int, default=3)
    ap.add_argument("--ablation", action="store_true", help="chạy thêm các biến thể cấu hình")
    args = ap.parse_args(argv)

    try:
        import psycopg
        conn = psycopg.connect(args.dsn)
    except ImportError:
        import psycopg2
        conn = psycopg2.connect(args.dsn)

    mod, fn = args.routes.split(":")
    get_routes = getattr(importlib.import_module(mod), fn)
    ods = _load_ods(args.od_csv)
    refs = load_reference_csv(args.ref_csv) if args.ref_csv else {}
    os.makedirs(args.out, exist_ok=True)

    times = pick_times(fetch_candidates(conn), per_scenario=args.per_scenario)
    all_times = sorted({t for ts in times.values() for t in ts})
    configs = ablation_configs() if args.ablation else {"base": ablation_configs()["base"]}

    summaries = {}
    for name, cfg in configs.items():
        replay_risks(conn, all_times, cfg)   # LƯU Ý: ghi đè road_segment_risk; bộ định tuyến phải đọc bản mới
        rows = evaluate_scenarios(times, ods, get_routes, lambda t: load_risk_map(conn, t))
        write_rows_csv(rows, os.path.join(args.out, f"pairs_{name}.csv"))
        summaries[name] = summarize(rows)
        if refs:
            logger.info("%s: so với Google Maps: %s", name, reference_comparison(rows, refs))
    with open(os.path.join(args.out, "summary.md"), "w", encoding="utf-8") as f:
        f.write(render_markdown(summaries))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()