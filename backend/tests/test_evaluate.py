from datetime import datetime, timedelta

import pytest

import app.explain.engine as engine
import scripts.evaluate as ev
from scripts.evaluate import (OD, RouteSegment as S, classify_conditions, criterion_scenario3,
                              evaluate_scenarios, load_reference_csv, pick_times,
                              reference_comparison, render_markdown, route_metrics, summarize,
                              write_rows_csv)

T0 = datetime(2023, 10, 15, 12, 0)

# fastest: s1 (1 km, 2 phút, p 0,9) + s2 (1 km, 2 phút, p 0,1); safest: s3 + s4 (1,5 km, 3 phút, p thấp)
FAST = [S(1, 1000, 120), S(2, 1000, 120)]
SAFE = [S(3, 1500, 180), S(4, 1500, 180)]
RISK = {1: 0.9, 2: 0.1, 3: 0.2, 4: 0.1}
ODS = [OD("a", 106.7, 10.8, 106.8, 10.9), OD("b", 106.7, 10.8, 106.8, 10.9)]


def test_route_metrics_and_missing_risk_is_zero():
    m = route_metrics(FAST, RISK)
    assert m == {"time_min": 4.0, "length_km": 2.0, "risky_km": 1.0, "max_risk": 0.9}
    assert route_metrics([S(99, 500, 60)], {})["max_risk"] == 0.0
    assert route_metrics([], RISK)["time_min"] == 0.0


def test_risky_threshold_is_strictly_greater_and_shared_with_explain():
    assert route_metrics([S(1, 1000, 60)], {1: engine.RISKY_PROB})["risky_km"] == 0.0
    assert ev.RISKY_PROB == engine.RISKY_PROB


def fake_routes(od, t):
    return (FAST, SAFE) if od.od_id == "a" else (FAST, FAST)   # cặp b: hai tuyến trùng nhau


def test_summarize_and_criterion():
    rows = evaluate_scenarios({3: [T0]}, ODS, fake_routes, lambda t: RISK)
    s = summarize(rows)[3]
    assert s["n"] == 2
    assert s["fastest_risky_km"] == 2.0 and s["safest_risky_km"] == 1.0   # cặp b vẫn đi qua s1
    assert s["risky_reduction_pct"] == pytest.approx(50.0)
    assert s["time_increase_pct"] == pytest.approx(25.0)                 # (6+4)/(4+4) - 1
    assert s["share_over_time_limit"] == 0.5 and s["identical_route_share"] == 0.5
    c = criterion_scenario3(s)
    assert c == {"reduction_ok": False, "time_ok": False, "passed": False}


def test_criterion_pass_and_not_evaluable():
    ok = {"risky_reduction_pct": 85.0, "time_increase_pct": 10.0}
    assert criterion_scenario3(ok)["passed"] is True
    assert criterion_scenario3({"risky_reduction_pct": None, "time_increase_pct": 5.0})["passed"] is None
    assert criterion_scenario3({"risky_reduction_pct": 80.0, "time_increase_pct": 15.0})["passed"] is True


def test_pair_row_carries_explain_sentence():
    rows = evaluate_scenarios({3: [T0]}, [ODS[0]], fake_routes, lambda t: RISK)
    assert rows[0]["explain_case"] == "B" and "tránh hoàn toàn" in rows[0]["explain_safest"]


def test_risk_map_loaded_once_per_time():
    calls = []
    evaluate_scenarios({1: [T0], 2: [T0]}, ODS, fake_routes, lambda t: calls.append(t) or RISK)
    assert len(calls) == 1


def test_classify_conditions():
    assert classify_conditions(0.0, 0) == 1
    assert classify_conditions(60.0, 0) == 2
    assert classify_conditions(60.0, 2) == 3
    assert classify_conditions(60.0, 1) is None      # mưa lớn + báo động I: không thuộc kịch bản nào
    assert classify_conditions(10.0, 0) is None


def test_pick_times_gap_top_rain_and_even_spacing():
    base = datetime(2023, 1, 1)
    rows = [(base + timedelta(hours=i), 0.0, 0) for i in range(100)]                  # kịch bản 1
    rows += [(T0 + timedelta(minutes=10 * i), 80.0 - i, 2) for i in range(6)]         # một cơn mưa liên tục
    rows += [(T0 + timedelta(days=1), 70.0, 2), (T0 + timedelta(days=2), 60.0, 2)]
    picked = pick_times(rows, per_scenario=3, min_gap_hours=3)
    assert picked[3] == [T0, T0 + timedelta(days=1), T0 + timedelta(days=2)]           # không lấy mốc liền nhau
    assert len(picked[1]) == 3 and picked[1][0] == base and picked[1] == sorted(picked[1])
    assert picked[2] == []


def test_reference_csv_and_ratio(tmp_path):
    p = tmp_path / "ref.csv"
    p.write_text("od_id,gmaps_time_min,gmaps_length_km\na,4.0,2.0\nb,8.0,3.0\n", encoding="utf-8")
    refs = load_reference_csv(str(p))
    rows = evaluate_scenarios({1: [T0]}, ODS, fake_routes, lambda t: RISK)
    r = reference_comparison(rows, refs)
    assert r["n"] == 2 and r["median_time_ratio"] == pytest.approx(0.75)   # (4/4 và 4/8)
    assert reference_comparison(rows, {}) is None


def test_report_files(tmp_path):
    rows = evaluate_scenarios({1: [T0], 3: [T0]}, ODS, fake_routes, lambda t: RISK)
    write_rows_csv(rows, str(tmp_path / "pairs.csv"))
    assert (tmp_path / "pairs.csv").read_text(encoding="utf-8").startswith("scenario,od_id")
    md = render_markdown({"base": summarize(rows)})
    assert "Cấu hình: base" in md and "KHÔNG ĐẠT" in md and "3. Mưa lớn + triều cường" in md


def test_empty_scenario_times_do_not_crash():
    
    assert evaluate_scenarios({1: [], 2: []}, ODS, fake_routes, lambda t: RISK) == []
    assert summarize([]) == {}