import type { LngLat, RouteResponse } from '../types/api';

const BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

export async function fetchRoutes(a: LngLat, b: LngLat): Promise<RouteResponse> {
    const res = await fetch(`${BASE}/api/route`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ origin: a, destination: b }),
    });
    if (!res.ok) {
        const err = await res.json().catch(() => null);
        throw new Error(err?.detail ?? 'Không tìm được tuyến.');
    }
    return res.json();
}