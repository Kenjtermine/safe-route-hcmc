"""risk/compute.py: tính flood_probability cho mọi đoạn đường tại một thời điểm.

Luồng:  số đo mưa/triều  +  segment_station  +  độ cao đoạn đường
          -> compute_segment_risks()   (hàm THUẦN, test được không cần DB)
          -> write_risks()             (upsert vào road_segment_risk)
`run()` nối các bước trên; Lambda (EventBridge) chỉ cần gọi run().

Khớp với 02_schema.sql:
  * mưa : rain_10min(tram, ts, mua_10phut_mm)  - số đo 10 phút, ts là mốc KẾT THÚC khoảng
  * triều: tide_daily(tram, ngay, dinh_trieu_m, chan_trieu_m, muc_bao_dong, nghi_van) - theo NGÀY
  * ghi : road_segment_risk(segment_id, thoi_diem, risk), segment_id = ways.gid

segment_station do A tạo trong after_osm.sql: MỘT dòng cho mỗi đoạn (khóa chính segment_id) gồm
  segment_id, tram_mua, d_mua_m, tram_trieu, d_trieu_m, elevation_m
  (elevation_m hiện là placeholder 1,5 m, A sẽ thay bằng SRTM; khoảng cách tính tại tâm đoạn)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from .logic import decay_factor, flood_probability

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------- kiểu dữ liệu
@dataclass(frozen=True)
class RainReading:
    ts: datetime                 # rain_10min.ts (mốc kết thúc khoảng 10 phút)
    mm: float                    # rain_10min.mua_10phut_mm


@dataclass(frozen=True)
class TideReading:
    ngay: date                   # tide_daily.ngay
    peak_m: float                # tide_daily.dinh_trieu_m, dùng làm mực nước tính ΔH
    trough_m: float | None       # tide_daily.chan_trieu_m (chưa dùng)
    alert: int                   # tide_daily.muc_bao_dong: 0..3, đã có sẵn, không tự tính lại
    suspect: bool                # tide_daily.nghi_van


@dataclass(frozen=True)
class SegmentInfo:
    segment_id: int              # ways.gid
    elevation_m: float | None
    rain_station: str | None
    rain_dist_m: float | None
    tide_station: str | None
    tide_dist_m: float | None


@dataclass
class ComputeConfig:
    rain_1h_ref_mm: float = 50.0       # ngưỡng vượt công suất thoát nước theo 1 giờ
    rain_2h_ref_mm: float = 70.0       # ngưỡng theo 2 giờ; mưa 2h được quy đổi về thang 1h
    use_alert_floor: bool = False      # trục báo động: mặc định TẮT
    decay_mode: str = "mean"           # "mean" (trung bình 2 hệ số) | "min"
    datum_offset_m: float = 0.0        # cộng vào mực nước để đưa về cùng mốc độ cao với DEM
    stale_after_h: float = 3.0         # mưa: số đo cũ hơn ngưỡng này thì chỉ ghi log
    tide_stale_after_days: int = 1     # triều: số đo cũ hơn số ngày này thì chỉ ghi log
    skip_suspect_tide: bool = True     # bỏ qua dòng tide_daily có nghi_van = true
    tide_lookback_days: int = 14       # chỉ nạp số đo triều trong ngần ấy ngày gần nhất

    def __post_init__(self):
        if self.decay_mode not in ("mean", "min"):
            raise ValueError("decay_mode phải là 'mean' hoặc 'min'")


@dataclass
class ComputeStats:
    computed: int = 0
    skipped_no_elevation: int = 0
    skipped_no_station: int = 0        # đoạn chưa được gán trạm trong segment_station
    skipped_no_data: int = 0           # trạm được gán nhưng chưa có số đo dùng được
    stale_segments: int = 0            # đoạn dùng số đo cũ hơn ngưỡng


# ---------------------------------------------------------------- hàm thuần
def _hours(a: datetime, b: datetime) -> float:
    return (a - b).total_seconds() / 3600


def latest_asof(series, thoi_diem: datetime):
    """Số đo mưa gần nhất có ts <= thoi_diem (không cần series đã sắp xếp)."""
    best = None
    for r in series:
        if r.ts <= thoi_diem and (best is None or r.ts > best.ts):
            best = r
    return best


def _window_sum(series, anchor: datetime, hours: float):
    """Tổng mưa các số đo 10 phút có ts trong (anchor - hours, anchor]."""
    vals = [r.mm for r in series if anchor - timedelta(hours=hours) < r.ts <= anchor]
    return sum(vals), len(vals)


def effective_rain(series, thoi_diem: datetime, cfg: ComputeConfig):
    """Trả (mưa quy đổi theo thang 1 giờ, stale) hoặc None nếu trạm chưa có số đo nào.

    Có số đo trong 2 giờ gần nhất: neo cửa sổ tại thoi_diem.
    Không có (trạm mất dữ liệu): quy tắc "dùng giá trị gần nhất có sẵn" nghĩa là neo cửa sổ
    tại số đo gần nhất, rồi mới cộng dồn.
    Kết quả = max(tổng 1h, tổng 2h quy đổi bằng 1h_ref/2h_ref).
    """
    latest = latest_asof(series, thoi_diem)
    if latest is None:
        return None
    _, n_recent = _window_sum(series, thoi_diem, 2)
    anchor = thoi_diem if n_recent else latest.ts
    s1, _ = _window_sum(series, anchor, 1)
    s2, _ = _window_sum(series, anchor, 2)
    stale = _hours(thoi_diem, latest.ts) > cfg.stale_after_h
    return max(s1, s2 * cfg.rain_1h_ref_mm / cfg.rain_2h_ref_mm), stale


def latest_tide(series, thoi_diem: datetime, cfg: ComputeConfig):
    """Dòng tide_daily mới nhất có ngay <= ngày của thoi_diem; trả (TideReading, stale) hoặc None."""
    today = thoi_diem.date()
    cands = [r for r in series
             if r.ngay <= today and not (cfg.skip_suspect_tide and r.suspect)]
    if not cands:
        return None
    best = max(cands, key=lambda r: r.ngay)
    return best, (today - best.ngay).days > cfg.tide_stale_after_days


def combined_decay(rain_dist_m: float, tide_dist_m: float, mode: str) -> float:
    """Kết hợp hệ số decay của hai trạm (trung bình HỆ SỐ, không trung bình khoảng cách)."""
    fr, ft = decay_factor(rain_dist_m), decay_factor(tide_dist_m)
    return min(fr, ft) if mode == "min" else (fr + ft) / 2


def compute_segment_risks(segments, rain_series, tide_series, thoi_diem, cfg=None):
    """Hàm thuần. rain_series: {tram: [RainReading]}, tide_series: {tram: [TideReading]}.

    Trả ([(segment_id, thoi_diem, risk)], ComputeStats).
    """
    cfg = cfg or ComputeConfig()
    stats = ComputeStats()

    # tính một lần cho mỗi trạm, không tính lại theo từng đoạn
    rain_by_station = {st: effective_rain(s, thoi_diem, cfg) for st, s in rain_series.items()}
    tide_by_station = {st: latest_tide(s, thoi_diem, cfg) for st, s in tide_series.items()}

    rows = []
    for seg in segments:
        if None in (seg.rain_station, seg.tide_station, seg.rain_dist_m, seg.tide_dist_m):
            stats.skipped_no_station += 1
            continue
        if seg.elevation_m is None:
            stats.skipped_no_elevation += 1
            continue
        rain = rain_by_station.get(seg.rain_station)
        tide = tide_by_station.get(seg.tide_station)
        if rain is None or tide is None:
            stats.skipped_no_data += 1
            continue

        rain_mm, rain_stale = rain
        tide_reading, tide_stale = tide
        if rain_stale or tide_stale:
            stats.stale_segments += 1

        delta_h = tide_reading.peak_m + cfg.datum_offset_m - seg.elevation_m
        alert = tide_reading.alert if cfg.use_alert_floor else 0
        p = flood_probability(delta_h, rain_mm, alert, use_alert_floor=cfg.use_alert_floor)
        p *= combined_decay(seg.rain_dist_m, seg.tide_dist_m, cfg.decay_mode)
        rows.append((seg.segment_id, thoi_diem, round(min(max(p, 0.0), 1.0), 4)))
        stats.computed += 1

    if stats.stale_segments:
        logger.warning("compute: %d đoạn dùng số đo cũ hơn ngưỡng (mưa %.1fh, triều %d ngày)",
                       stats.stale_segments, cfg.stale_after_h, cfg.tide_stale_after_days)
    return rows, stats


# ---------------------------------------------------------------- vào/ra DB (CHƯA chạy thử với DB thật)
SQL_SEGMENTS = """
SELECT segment_id, elevation_m, tram_mua, d_mua_m, tram_trieu, d_trieu_m
FROM segment_station
"""
# số đo mưa trong 2 giờ trước thoi_diem
SQL_RAIN_RECENT = """SELECT tram, ts, mua_10phut_mm FROM rain_10min
                     WHERE ts > %s AND ts <= %s"""
# 2 giờ trước số đo gần nhất của MỖI trạm (dùng khi trạm mất dữ liệu)
SQL_RAIN_AROUND_LATEST = """
WITH latest AS (
  SELECT tram, max(ts) AS ts FROM rain_10min WHERE ts <= %s GROUP BY tram
)
SELECT r.tram, r.ts, r.mua_10phut_mm
FROM rain_10min r JOIN latest l ON l.tram = r.tram
WHERE r.ts > l.ts - interval '2 hours' AND r.ts <= l.ts
"""
SQL_TIDE = """SELECT tram, ngay, dinh_trieu_m, chan_trieu_m, muc_bao_dong, nghi_van
              FROM tide_daily
              WHERE ngay <= %s AND ngay > %s AND dinh_trieu_m IS NOT NULL"""
SQL_UPSERT = """INSERT INTO road_segment_risk (segment_id, thoi_diem, risk)
                VALUES (%s, %s, %s)
                ON CONFLICT (segment_id, thoi_diem) DO UPDATE SET risk = EXCLUDED.risk"""


def _fetch(conn, sql, params=()):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def load_inputs(conn, thoi_diem: datetime, cfg: ComputeConfig):
    segments = [SegmentInfo(*row) for row in _fetch(conn, SQL_SEGMENTS)]

    rain: dict[str, dict[datetime, RainReading]] = {}
    rows = (_fetch(conn, SQL_RAIN_RECENT, (thoi_diem - timedelta(hours=2), thoi_diem))
            + _fetch(conn, SQL_RAIN_AROUND_LATEST, (thoi_diem,)))
    for tram, ts, mm in rows:
        if mm is not None:
            rain.setdefault(tram, {})[ts] = RainReading(ts, float(mm))
    rain_series = {tram: list(d.values()) for tram, d in rain.items()}

    tide_series: dict[str, list[TideReading]] = {}
    since = thoi_diem.date() - timedelta(days=cfg.tide_lookback_days)
    for tram, ngay, peak, trough, muc, nghi in _fetch(conn, SQL_TIDE, (thoi_diem.date(), since)):
        tide_series.setdefault(tram, []).append(TideReading(
            ngay, float(peak), None if trough is None else float(trough),
            int(muc or 0), bool(nghi)))
    return segments, rain_series, tide_series


def write_risks(conn, rows) -> None:
    """Upsert trong một giao dịch: chạy lại cùng thoi_diem không tạo dòng trùng."""
    if not rows:
        return
    with conn.cursor() as cur:
        cur.executemany(SQL_UPSERT, rows)
    conn.commit()


def floor_to_10min(dt: datetime) -> datetime:
    """Làm tròn xuống mốc 10 phút (khớp rain_10min.ts); chạy lại trong cùng mốc thì upsert đè lên nhau."""
    return dt.replace(minute=dt.minute - dt.minute % 10, second=0, microsecond=0)


def run(conn, thoi_diem: datetime, cfg: ComputeConfig | None = None) -> ComputeStats:
    cfg = cfg or ComputeConfig()
    thoi_diem = floor_to_10min(thoi_diem)
    segments, rain_series, tide_series = load_inputs(conn, thoi_diem, cfg)
    rows, stats = compute_segment_risks(segments, rain_series, tide_series, thoi_diem, cfg)
    write_risks(conn, rows)
    logger.info("compute %s: %s", thoi_diem.isoformat(), stats)
    return stats
