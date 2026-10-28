CREATE TEMP TABLE st_raw (tram text, lon double precision, lat double precision, loai text);
COPY st_raw FROM '/data/clean/stations.csv' WITH (FORMAT csv, HEADER true);
INSERT INTO stations (tram, lon, lat, loai, geog)
SELECT tram, lon, lat, loai, ST_SetSRID(ST_MakePoint(lon, lat), 4326)::geography FROM st_raw;
CREATE INDEX ON stations USING gist (geog);

COPY rain_10min FROM '/data/clean/rain_10min_2022_2023.csv' WITH (FORMAT csv, HEADER true);
COPY rain_daily FROM '/data/clean/rain_daily_1995_2021.csv' WITH (FORMAT csv, HEADER true);
COPY tide_daily FROM '/data/clean/tide_daily_1995_2022.csv' WITH (FORMAT csv, HEADER true);
