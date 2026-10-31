ARG BASE_IMAGE=nickblah/pgrouting:16-bookworm-postgis-3.6-pgrouting-4.0.1
FROM ${BASE_IMAGE}

# osm2pgrouting: nạp bản đồ OSM vào bảng ways; curl: tải file OSM
# --no-install-recommends để apt không kéo thêm PostgreSQL/pgRouting bản khác của Debian
RUN apt-get update \
    && apt-get install -y --no-install-recommends osm2pgrouting curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*
