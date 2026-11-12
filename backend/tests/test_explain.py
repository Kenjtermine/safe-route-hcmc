import logging

import pytest

from app.explain.engine import classify, explain, explain_pair


def r(time, length, risky, maxr):
    return {"time_min": time, "length_km": length, "risky_km": risky, "max_risk": maxr}


FAST_RISKY = r(10, 3, 1.2, 0.9)

# (mã mong đợi, fastest, safest): mỗi dòng của bảng tình huống ít nhất một ca
CASES = [
    ("A", r(10, 3, 0, 0.1), r(10, 3, 0, 0.1)),
    ("I", r(10, 3, 0, 0.6), r(13, 3.5, 0, 0.3)),
    ("I", r(10, 3, 0, 0.6), r(10.5, 3.2, 0, 0.3)),
    ("B", FAST_RISKY, r(16, 5, 0, 0.1)),
    ("C", FAST_RISKY, r(10.5, 3.2, 0, 0.1)),
    ("D", FAST_RISKY, r(16, 5, 0.4, 0.8)),
    ("E", FAST_RISKY, r(10.5, 3.2, 0.4, 0.8)),
    ("F", FAST_RISKY, r(13, 3.4, 1.2, 0.75)),
    ("G", FAST_RISKY, r(10, 3, 1.2, 0.9)),
    ("J", r(10, 3, 1.2, 0.75), r(16, 5, 0.4, 0.95)),   # r giảm, max_risk tăng
    ("J", r(10, 3, 0.3, 0.95), r(14, 4, 1.0, 0.75)),   # r tăng, max_risk giảm
    ("H", FAST_RISKY, r(8, 3, 1.2, 0.9)),               # Safest nhanh hơn rõ rệt
    ("H", r(10, 3, 0, 0.3), r(15, 4, 0, 0.3)),          # chậm hơn mà không được gì
    ("H", r(10, 3, 0.2, 0.75), r(12, 3, 1.0, 0.9)),     # tệ hơn mà không có gì tốt hơn
    ("X", r(10, 3, 4, 0.9), r(10, 3, 0, 0.1)),          # risky_km > length_km
    ("X", r(0, 3, 0, 0.1), r(10, 3, 0, 0.1)),           # time_min = 0
    ("X", r(10, 3, 0, 1.5), r(10, 3, 0, 0.1)),          # max_risk ngoài [0, 1]
    ("X", r(10, 3, 1.2, 0.5), r(10, 3, 0, 0.1)),        # có risky_km nhưng max_risk <= RISKY_PROB
]


@pytest.mark.parametrize("expected,fast,safe", CASES)
def test_classify(expected, fast, safe):
    assert classify(fast, safe) == expected


def test_a_requires_both_routes_clean():
    # đoạn rủi ro ngắn (dưới EPS_KM) nhưng max_risk cao: KHÔNG được nói "an toàn"
    assert classify(r(10, 3, 0.05, 0.9), r(10, 3, 0.05, 0.9)) == "G"


def test_a_not_returned_when_only_safest_has_small_risky():
    # Fastest 0,10 km, Safest 0,15 km: chênh trong dung sai nhưng Safest vượt ngưỡng
    assert classify(r(10, 3, 0.10, 0.8), r(10, 3, 0.15, 0.8)) == "G"


def test_time_exactly_eps_is_not_slower():
    # chênh đúng EPS_TIME (1 phút) coi là bằng nhau -> C, không phải B
    assert classify(FAST_RISKY, r(11, 3, 0, 0.1)) == "C"


def test_missing_key_is_x():
    bad = {"time_min": 10, "length_km": 3, "risky_km": 0}
    assert classify(bad, r(10, 3, 0, 0.1)) == "X"


def test_branch_b_sentence():
    s = explain(FAST_RISKY, r(16, 5, 0, 0.1))
    assert "2,0 km" in s and "6 phút" in s and "1,2 km" in s


def test_branch_i_sentence_mentions_max_risk_only():
    s = explain(r(10, 3, 0, 0.6), r(13, 3.5, 0, 0.3))
    assert "60%" in s and "30%" in s and "tránh hoàn toàn" not in s


def test_branch_i_equal_time_omits_time_phrase():
    s = explain(r(10, 3, 0, 0.6), r(10.5, 3.2, 0, 0.3))
    assert "chậm hơn" not in s


def test_branch_j_sentence_states_both_sides():
    s = explain(r(10, 3, 1.2, 0.75), r(16, 5, 0.4, 0.95))
    assert "1,2 km xuống 0,4 km" in s and "75% lên 95%" in s


def test_explain_pair_has_both_sentences():
    out = explain_pair(FAST_RISKY, r(16, 5, 0, 0.1))
    assert out["case"] == "B"
    assert "Nhanh hơn 6 phút" in out["fastest"]
    assert out["safest"] == explain(FAST_RISKY, r(16, 5, 0, 0.1))


def test_abnormal_case_neutral_and_logs(caplog):
    with caplog.at_level(logging.WARNING):
        s = explain(FAST_RISKY, r(8, 3, 1.2, 0.9))
    assert "tránh" not in s
    assert any("bất thường" in m for m in caplog.messages)


def test_invalid_input_returns_empty_and_logs(caplog):
    with caplog.at_level(logging.ERROR):
        out = explain_pair(r(10, 3, 4, 0.9), r(10, 3, 0, 0.1))
    assert out == {"case": "X", "fastest": "", "safest": ""}
    assert caplog.messages