-- Rui ro GIA de Nguoi C code routing/frontend truoc khi prediction-service xong
-- Chay: docker compose exec db psql -U <DB_USER> -d <DB_NAME> -f /seed/seed_fake_risk.sql
DELETE FROM road_segment_risk WHERE thoi_diem = '2022-10-24 22:00';
INSERT INTO road_segment_risk (segment_id, thoi_diem, risk)
SELECT gid, '2022-10-24 22:00', round(power(random(), 4)::numeric, 2)
FROM ways;
