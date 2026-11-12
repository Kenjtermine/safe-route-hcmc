import type { FeatureCollection } from 'geojson';

const BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

export async function fetchRisk(
    bbox: [number, number, number, number], minRisk = 0.05,
): Promise<FeatureCollection> {
    const res = await fetch(`${BASE}/api/risk?bbox=${bbox.join(',')}&min_risk=${minRisk}`);
    if (!res.ok) throw new Error('Không tải được lớp rủi ro.');
    return res.json();
}