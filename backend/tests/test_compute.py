from datetime import datetime, timedelta

import pytest

from app.risk.compute import (ComputeConfig, RainReading, SegmentInfo, TideReading,
                          compute_segment_risks, effective_rain, latest_asof, latest_tide,
                          write_risks)

T = datetime(2023, 10, 15, 12, 0)


def seg(sid=1, elev=1.3, rd=1000.0, td=1000.0, rs="R1", ts="T1"):
    return SegmentInfo(sid, elev, rs, rd, ts, td)


def tide(peak=1.6, alert=0, day=None, suspect=False):
    return {"T1": [TideReading(day or T.date(), peak, 0.2, alert, suspect)]}


def rain(mm=60.0):
    """Sáu số đo 10 phút trong giờ gần nhất, tổng bằng mm."""
    return {"R1": [RainReading(T - timedelta(minutes=10 * i), mm / 6) for i in range(6)]}


def risk_of(segments, rain_s, tide_s, cfg=None):
    return compute_segment_risks(segments, rain_s, tide_s, T, cfg)


def test_basic_deep_flood_heavy_rain():
    rows, st = risk_of([seg(elev=1.3)], rain(60), tide(1.6))   # ΔH=0.3, mưa to
    assert rows == [(1, T, 1.0)] and st.computed == 1


def test_rain_2h_is_scaled_to_1h_threshold():
    hour1 = [RainReading(T - timedelta(minutes=10 * i), 5.0) for i in range(6)]          # 30 mm
    hour2 = [RainReading(T - timedelta(minutes=70), 20.0),
             RainReading(T - timedelta(minutes=80), 20.0)]                                # 40 mm
    mm, stale = effective_rain(hour1 + hour2, T, ComputeConfig())
    assert mm == pytest.approx(50.0) and not stale   # 70 mm/2h tương đương 50 mm/1h


def test_decay_mean_vs_min():
    segs = [seg(rd=1000.0, td=10000.0)]               # hệ số 1.0 và 0.5
    mean_rows, _ = risk_of(segs, rain(60), tide(1.6), ComputeConfig(decay_mode="mean"))
    min_rows, _ = risk_of(segs, rain(60), tide(1.6), ComputeConfig(decay_mode="min"))
    assert mean_rows[0][2] == pytest.approx(0.75)
    assert min_rows[0][2] == pytest.approx(0.5)


def test_no_decay_within_5km():
    rows, _ = risk_of([seg(rd=5000.0, td=5000.0)], rain(60), tide(1.6))
    assert rows[0][2] == 1.0


def test_alert_floor_uses_muc_bao_dong_and_is_off_by_default():
    segs = [seg(elev=5.0)]                             # đường rất cao, mưa 0
    off, _ = risk_of(segs, rain(0), tide(1.55, alert=2))
    on, _ = risk_of(segs, rain(0), tide(1.55, alert=2), ComputeConfig(use_alert_floor=True))
    assert off[0][2] == 0.0 and on[0][2] == pytest.approx(0.4)


def test_datum_offset_shifts_delta_h():
    segs = [seg(elev=1.0)]
    no_off, _ = risk_of(segs, rain(60), tide(1.6))                                   # ΔH=0.6 -> 1.0
    off, _ = risk_of(segs, rain(60), tide(1.6), ComputeConfig(datum_offset_m=-0.5))  # ΔH=0.1 -> 0.8
    assert no_off[0][2] == 1.0 and off[0][2] == pytest.approx(0.8)


def test_rain_station_outage_uses_window_ending_at_latest_reading():
    old = T - timedelta(hours=4)
    r = {"R1": [RainReading(old - timedelta(minutes=10 * i), 10.0) for i in range(6)]}   # 60 mm
    rows, st = risk_of([seg()], r, tide(1.6))
    assert rows[0][2] == 1.0 and st.stale_segments == 1


def test_stale_tide_counted():
    rows, st = risk_of([seg()], rain(60), tide(1.6, day=T.date() - timedelta(days=3)))
    assert rows[0][2] == 1.0 and st.stale_segments == 1


def test_suspect_tide_skipped_falls_back_to_previous_day():
    t = {"T1": [TideReading(T.date(), 1.6, 0.2, 3, True),
                TideReading(T.date() - timedelta(days=1), 1.0, 0.2, 0, False)]}
    skip, _ = risk_of([seg(elev=1.3)], rain(60), t)                                     # ΔH=-0.3 -> 0.6
    keep, _ = risk_of([seg(elev=1.3)], rain(60), t, ComputeConfig(skip_suspect_tide=False))  # ΔH=0.3 -> 1.0
    assert skip[0][2] == pytest.approx(0.6) and keep[0][2] == 1.0


def test_latest_tide_ignores_future_days_and_all_suspect_means_missing():
    future = [TideReading(T.date() + timedelta(days=1), 2.0, 0.2, 3, False)]
    assert latest_tide(future, T, ComputeConfig()) is None
    only_suspect = [TideReading(T.date(), 1.6, 0.2, 3, True)]
    assert latest_tide(only_suspect, T, ComputeConfig()) is None


def test_latest_asof_ignores_future_readings():
    s = [RainReading(T + timedelta(hours=1), 99.0), RainReading(T - timedelta(hours=1), 5.0)]
    assert latest_asof(s, T).mm == 5.0


def test_skips_are_counted_not_written():
    segs = [seg(1, elev=None), seg(2, rs=None), seg(3, rs="R_NODATA"), seg(4)]
    rows, st = risk_of(segs, rain(60), tide(1.6))
    assert [r[0] for r in rows] == [4]
    assert (st.skipped_no_elevation, st.skipped_no_station, st.skipped_no_data) == (1, 1, 1)


def test_invalid_decay_mode_rejected():
    with pytest.raises(ValueError):
        ComputeConfig(decay_mode="max")


class FakeCursor:
    def __init__(self, log): self.log = log
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def executemany(self, sql, rows): self.log.append((sql, list(rows)))


class FakeConn:
    def __init__(self): self.log, self.commits = [], 0
    def cursor(self): return FakeCursor(self.log)
    def commit(self): self.commits += 1


def test_write_risks_is_upsert_in_one_transaction():
    conn = FakeConn()
    write_risks(conn, [(1, T, 0.5)])
    sql, rows = conn.log[0]
    assert "ON CONFLICT (segment_id, thoi_diem) DO UPDATE" in sql
    assert rows == [(1, T, 0.5)] and conn.commits == 1


def test_write_risks_empty_does_nothing():
    conn = FakeConn()
    write_risks(conn, [])
    assert conn.log == [] and conn.commits == 0
