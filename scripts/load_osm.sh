#!/bin/bash
# Chay: docker compose exec db bash /scripts/load_osm.sh
# Tai duong pho khu Thu Duc tu OpenStreetMap -> bang ways (pgRouting) -> gan tram gan nhat
set -e
BBOX="10.80,106.72,10.88,106.80"   # (nam, tay, bac, dong) quanh tram mua Thu Duc
OSM=/osm/thuduc.osm
QUERY="[out:xml][timeout:300];(way[\"highway\"]($BBOX);>;);out body;"
# Server chinh hay tra 406/429/504 -> thu lan luot, loi thi chuyen sang mirror
SERVERS="https://overpass-api.de/api/interpreter https://overpass.kumi.systems/api/interpreter"

if [ -s "$OSM" ] && ! head -c 500 "$OSM" | grep -q "<osm"; then
  echo ">> $OSM khong phai du lieu OSM, xoa de tai lai"
  rm -f "$OSM"
fi

if [ ! -s "$OSM" ]; then
  for URL in $SERVERS; do
    echo ">> Tai OSM tu $URL (1-3 phut)..."
    # Tai ra file tam, chi doi ten khi tai thanh cong va dung la XML OSM
    if curl -sS --fail --max-time 360 -A "safe-route-hcmc/1.0" \
         -o "$OSM.tmp" --data-urlencode "data=$QUERY" "$URL" \
       && head -c 500 "$OSM.tmp" | grep -q "<osm"; then
      mv "$OSM.tmp" "$OSM"
      break
    fi
    echo ">> Loi khi tai tu $URL, thu server khac"
    rm -f "$OSM.tmp"
  done
  [ -s "$OSM" ] || { echo ">> Khong tai duoc OSM tu server nao" >&2; exit 1; }
fi

CONF=$(ls /usr/share/osm2pgrouting/mapconfig_for_cars.xml 2>/dev/null \
       || find / -name 'mapconfig_for_cars.xml' 2>/dev/null | head -1)
echo ">> osm2pgrouting voi config: $CONF"
osm2pgrouting -f "$OSM" -c "$CONF" -d "$POSTGRES_DB" -U "$POSTGRES_USER" \
  -h localhost -W "$POSTGRES_PASSWORD" --clean

echo ">> Gan tram gan nhat (KNN) cho tung doan duong..."
psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -f /scripts/after_osm.sql
echo ">> Xong."
