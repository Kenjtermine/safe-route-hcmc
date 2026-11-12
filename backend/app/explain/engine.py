"""Explainability Engine (rule-based) cho SAFE-ROUTE HCMC.

Đầu vào: hai dict mô tả tuyến Fastest và Safest, mỗi dict có các khóa
    time_min   (float, phút)
    length_km  (float, km)
    risky_km   (float, km đi qua đoạn có flood_probability > RISKY_PROB)
    max_risk   (float, 0..1, xác suất ngập cao nhất trên tuyến)

Mọi delta tính theo hướng "Safest so với Fastest" và CÓ DẤU (không dùng abs).

Các ca:
    A  cả hai tuyến sạch, không khác biệt
    I  cả hai chưa có đoạn nguy cơ cao, Safest vẫn giảm mức ngập cao nhất
    B  tránh hoàn toàn đoạn rủi ro, tốn thêm thời gian
    C  như B nhưng không tốn thêm thời gian
    D  giảm một phần đoạn rủi ro, tốn thêm thời gian
    E  như D nhưng không tốn thêm thời gian
    F  còn đoạn rủi ro, nhưng mức ngập cao nhất giảm
    G  không có tuyến thay thế tốt hơn (hai tuyến tương đương)
    J  đánh đổi: tốt hơn ở một chỉ số, kém hơn ở chỉ số kia
    H  bất thường (log cảnh báo, câu trung tính)
    X  dữ liệu vào sai ràng buộc (log lỗi, KHÔNG sinh câu: trả chuỗi rỗng)
"""
import logging
import math

logger = logging.getLogger(__name__)

# Ngưỡng "xấp xỉ bằng nhau": tham số cấu hình, hiệu chỉnh khi có dữ liệu thật.
EPS_TIME = 1.0    # phút
EPS_KM = 0.1      # km
EPS_RISK = 0.05   # xác suất

# Ngưỡng xác suất để một đoạn được tính vào risky_km.
# PHẢI trùng với ngưỡng mà phía routing dùng khi tính risky_km.
RISKY_PROB = 0.7

REQUIRED_KEYS = ("time_min", "length_km", "risky_km", "max_risk")


# ---------- Định dạng số liệu ----------
def _km(x: float) -> str:
    return f"{abs(x):.1f}".replace(".", ",")


def _min(x: float) -> str:
    return f"{abs(x):.0f}"


def _pct(p: float) -> str:
    return f"{p * 100:.0f}%"


# ---------- Kiểm tra ràng buộc đầu vào (ca X) ----------
def _problems(name: str, route: dict) -> list:
    out = []
    for k in REQUIRED_KEYS:
        v = route.get(k) if isinstance(route, dict) else None
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            out.append(f"{name}: thiếu hoặc sai kiểu khóa {k}")
    if out:
        return out
    for k in REQUIRED_KEYS:
        if not math.isfinite(route[k]):
            out.append(f"{name}: {k} phải là số hữu hạn")
    if out:
        return out
    if route["time_min"] <= 0:
        out.append(f"{name}: time_min phải > 0")
    if route["length_km"] <= 0:
        out.append(f"{name}: length_km phải > 0")
    if route["risky_km"] < 0 or route["risky_km"] > route["length_km"] + EPS_KM:
        out.append(f"{name}: risky_km phải nằm trong [0, length_km]")
    if not 0 <= route["max_risk"] <= 1:
        out.append(f"{name}: max_risk phải nằm trong [0, 1]")
    if route["risky_km"] > EPS_KM and route["max_risk"] <= RISKY_PROB:
        out.append(f"{name}: có risky_km nhưng max_risk không vượt RISKY_PROB")
    return out


# ---------- Tính delta ----------
def compute_deltas(fastest: dict, safest: dict) -> dict:
    return {
        "time": safest["time_min"] - fastest["time_min"],
        "length": safest["length_km"] - fastest["length_km"],
        "risky": fastest["risky_km"] - safest["risky_km"],
        "max_risk": fastest["max_risk"] - safest["max_risk"],
    }


# ---------- Phân loại: nhánh nào khớp trước thì dừng, nên không chồng nhau ----------
def classify(fastest: dict, safest: dict) -> str:
    # 1. Ràng buộc đầu vào
    problems = _problems("fastest", fastest) + _problems("safest", safest)
    if problems:
        logger.error("Explain: dữ liệu vào không hợp lệ: %s", "; ".join(problems))
        return "X"

    d = compute_deltas(fastest, safest)
    slower = d["time"] > EPS_TIME # Safest chậm hơn Fastest
    faster = d["time"] < -EPS_TIME # Safest nhanh hơn Fastest
    r_down, r_up = d["risky"] > EPS_KM, d["risky"] < -EPS_KM # Safest giảm hoặc tăng risky_km so với Fastest
    m_down, m_up = d["max_risk"] > EPS_RISK, d["max_risk"] < -EPS_RISK  # Safest giảm hoặc tăng max_risk so với Fastest
    gain_any, worse_any = r_down or m_down, r_up or m_up # Safest tốt hơn / tệ hơn Fastest ở ít nhất một chỉ số rủi ro
    rf = fastest["risky_km"] > EPS_KM # Fastest có risky_km ở mức đáng kể
    rs = safest["risky_km"] > EPS_KM # Safest có risky_km ở mức đáng kể

    # 2. Safest nhanh hơn rõ rệt: Fastest dùng β=0 nên không thể xảy ra
    if faster:
        return "H"

    # 3-4. Có chỉ số tăng
    if worse_any:
        return "J" if gain_any else "H"

    # 5. Không chỉ số nào đổi
    if not gain_any:
        if slower:
            return "H"  # đi vòng mà không được gì
        clean = (not rf and not rs
                 and fastest["max_risk"] <= RISKY_PROB
                 and safest["max_risk"] <= RISKY_PROB)
        return "A" if clean else "G"

    # 6. Có cải thiện, không có gì tệ hơn
    if r_down:
        if not rs:
            return "B" if slower else "C"   # tránh hoàn toàn
        return "D" if slower else "E"       # giảm một phần
    # r bằng, max_risk giảm
    return "F" if rs else "I"


# ---------- Mẫu câu ----------
def _length_part(d: dict) -> str:
    if d["length"] > EPS_KM:
        return f", đi xa hơn {_km(d['length'])} km"
    if d["length"] < -EPS_KM:
        return f", ngắn hơn {_km(d['length'])} km"
    return ""


def _time_part(d: dict) -> str:
    return f", chậm hơn {_min(d['time'])} phút" if d["time"] > EPS_TIME else ""


def _safest_sentence(case: str, fastest: dict, safest: dict, d: dict) -> str:
    lp, tp = _length_part(d), _time_part(d)
    t = _min(d["time"])
    if case == "A":
        return ("Tuyến nhanh nhất cũng là tuyến an toàn: không có đoạn nào "
                "có nguy cơ ngập cao nên không cần đi vòng.")
    if case == "I":
        return (f"Cả hai tuyến đều không có đoạn nguy cơ ngập cao đáng kể. Tuyến an toàn{lp}{tp} "
                f"để giảm mức ngập cao nhất từ {_pct(fastest['max_risk'])} "
                f"xuống {_pct(safest['max_risk'])}.")
    if case == "B":
        return (f"Tuyến an toàn{lp}, chậm hơn {t} phút nhưng tránh hoàn toàn "
                f"{_km(d['risky'])} km đoạn có nguy cơ ngập cao.")
    if case == "C":
        return (f"Tuyến an toàn{lp} nhưng không mất thêm thời gian, "
                f"và tránh hoàn toàn {_km(d['risky'])} km đoạn có nguy cơ ngập cao.")
    if case == "D":
        return (f"Tuyến an toàn{lp}, chậm hơn {t} phút, giảm đoạn có nguy cơ "
                f"ngập cao từ {_km(fastest['risky_km'])} km xuống {_km(safest['risky_km'])} km.")
    if case == "E":
        return (f"Tuyến an toàn{lp} không mất thêm thời gian, giảm đoạn có nguy cơ "
                f"ngập cao từ {_km(fastest['risky_km'])} km xuống {_km(safest['risky_km'])} km.")
    if case == "F":
        return (f"Tuyến an toàn vẫn đi qua đoạn có nguy cơ ngập{tp} nhưng mức ngập cao nhất "
                f"giảm từ {_pct(fastest['max_risk'])} xuống {_pct(safest['max_risk'])}.")
    if case == "G":
        return ("Không có đường vòng nào giảm được nguy cơ ngập: "
                "hai tuyến có mức rủi ro tương đương.")
    if case == "J":
        if d["risky"] > EPS_KM:  # giảm số km nhưng đoạn tệ nhất nặng hơn
            return (f"Tuyến an toàn{tp}, giảm đoạn có nguy cơ ngập cao từ "
                    f"{_km(fastest['risky_km'])} km xuống {_km(safest['risky_km'])} km, "
                    f"nhưng đoạn ngập nặng nhất có mức cao hơn "
                    f"(từ {_pct(fastest['max_risk'])} lên {_pct(safest['max_risk'])}).")
        return (f"Tuyến an toàn{tp}, đi qua nhiều đoạn có nguy cơ ngập cao hơn "
                f"(từ {_km(fastest['risky_km'])} km lên {_km(safest['risky_km'])} km), "
                f"nhưng mức ngập cao nhất thấp hơn "
                f"(từ {_pct(fastest['max_risk'])} xuống {_pct(safest['max_risk'])}).")
    if case == "H":
        return ("Chưa thể so sánh rõ ràng hai tuyến trong điều kiện hiện tại, "
                "bạn nên tự cân nhắc trước khi đi.")
    return ""  # X


def _fastest_sentence(case: str, fastest: dict, safest: dict, d: dict) -> str:
    if case in ("A", "G", "H"):
        return _safest_sentence(case, fastest, safest, d)
    if case == "X":
        return ""
    if case in ("B", "D"):
        return (f"Nhanh hơn {_min(d['time'])} phút nhưng đi qua {_km(fastest['risky_km'])} km "
                f"đoạn có nguy cơ ngập cao (xác suất cao nhất {_pct(fastest['max_risk'])}).")
    if case in ("C", "E"):
        return (f"Cùng thời gian nhưng đi qua {_km(fastest['risky_km'])} km đoạn có "
                f"nguy cơ ngập cao (xác suất cao nhất {_pct(fastest['max_risk'])}).")
    if case in ("F", "I"):
        return f"Mức ngập cao nhất trên tuyến này là {_pct(fastest['max_risk'])}."
    # J
    head = f"Nhanh hơn {_min(d['time'])} phút, đi" if d["time"] > EPS_TIME else "Đi"
    return (f"{head} qua {_km(fastest['risky_km'])} km đoạn có nguy cơ ngập cao, "
            f"mức ngập cao nhất {_pct(fastest['max_risk'])}.")


# ---------- API ----------
def explain_pair(fastest: dict, safest: dict) -> dict:
    """Trả {"case", "fastest", "safest"}. Ca X: hai câu rỗng, phía UI nên ẩn phần giải thích."""
    case = classify(fastest, safest)
    if case == "X":
        return {"case": "X", "fastest": "", "safest": ""}
    d = compute_deltas(fastest, safest)
    if case == "H":
        logger.warning("Explain: ca bất thường, deltas=%s", d)
    return {
        "case": case,
        "fastest": _fastest_sentence(case, fastest, safest, d),
        "safest": _safest_sentence(case, fastest, safest, d),
    }


def explain(fastest: dict, safest: dict) -> str:
    """Giao diện đã chốt với C: một câu giải thích (góc nhìn Safest so với Fastest).
    Trả chuỗi rỗng khi dữ liệu vào không hợp lệ (ca X)."""
    return explain_pair(fastest, safest)["safest"]
