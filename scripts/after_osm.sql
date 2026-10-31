-- Moi doan duong (ways.gid) -> tram mua gan nhat CO SO LIEU 10 PHUT + tram trieu gan nhat
DROP TABLE IF EXISTS segment_station;
CREATE TABLE segment_station AS
SELECT
    w.gid                        AS segment_id,
    m.tram                       AS tram_mua,
    ST_Distance(m.geog, c.g)     AS d_mua_m,
    t.tram                       AS tram_trieu,
    ST_Distance(t.geog, c.g)     AS d_trieu_m,
    1.5::double precision        AS elevation_m   -- TODO (Nguoi A): thay bang SRTM, hien la placeholder
FROM ways w
CROSS JOIN LATERAL (SELECT ST_Centroid(w.the_geom)::geography AS g) c
CROSS JOIN LATERAL (
    SELECT s.tram, s.geog FROM stations s
    WHERE s.loai = 'mua' AND s.tram IN (SELECT DISTINCT tram FROM rain_10min)
    ORDER BY s.geog <-> c.g LIMIT 1
) m
CROSS JOIN LATERAL (
    SELECT s.tram, s.geog FROM stations s
    WHERE s.loai = 'trieu'
    ORDER BY s.geog <-> c.g LIMIT 1
) t;
ALTER TABLE segment_station ADD PRIMARY KEY (segment_id);

SELECT tram_mua, tram_trieu, count(*) AS so_doan,
       round(avg(d_mua_m)) AS tb_cach_tram_mua_m
FROM segment_station GROUP BY 1, 2 ORDER BY 3 DESC;
