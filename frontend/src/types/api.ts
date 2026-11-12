export type LngLat = [number, number]; // [kinh độ, vĩ độ]
export interface Place { label: string; lngLat: LngLat }
export type RouteKind = 'safest' | 'fastest';

export interface RouteOption {
    kind: RouteKind;
    duration_min: number;
    distance_km: number;
    via: string[];
    max_risk: number;      // p lớn nhất dọc tuyến, 0..1
    clearance_m: number | null;   // cao độ mặt đường so với mực triều
    explanation: string;
    recommended: boolean;
    geometry: { type: 'LineString'; coordinates: LngLat[] };
}
export interface RouteResponse { safest: RouteOption; fastest: RouteOption }