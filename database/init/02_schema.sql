-- Tram do (mua + trieu). "Nha Be" co ca tram mua va tram trieu -> khoa chinh (tram, loai)
CREATE TABLE stations (
    tram  text,
    lon   double precision,
    lat   double precision,
    loai  text,               -- 'mua' | 'trieu'
    geog  geography(Point, 4326),
    PRIMARY KEY (tram, loai)
);

CREATE TABLE rain_10min (
    tram           text,
    ts             timestamp,  -- moc ket thuc khoang 10 phut
    mua_10phut_mm  real
);
CREATE INDEX ON rain_10min (tram, ts);

CREATE TABLE rain_daily (
    tram         text,
    ngay         date,
    mua_ngay_mm  real
);

CREATE TABLE tide_daily (
    tram          text,
    ngay          date,
    dinh_trieu_m  real,
    chan_trieu_m  real,
    muc_bao_dong  smallint,   -- 0..3
    nghi_van      boolean
);
CREATE INDEX ON tide_daily (tram, ngay);

-- HOP DONG GIUA CAC SERVICE: prediction-service ghi, routing-service doc
CREATE TABLE road_segment_risk (
    segment_id  bigint,       -- = ways.gid (bang do osm2pgrouting tao)
    thoi_diem   timestamp,
    risk        real,         -- 0..1
    PRIMARY KEY (segment_id, thoi_diem)
);
CREATE INDEX ON road_segment_risk (thoi_diem);
