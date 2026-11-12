import { useEffect, useRef, useState } from 'react';
import * as maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import workerURL from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';
import { MAP_BOUNDS, MAP_CENTER, MAP_STYLE, MAP_ZOOM } from '../../config/map';
import type { LngLat, Place, RouteKind, RouteResponse } from '../../types/api';

maplibregl.setWorkerUrl(workerURL)

type GeoData = Parameters<maplibregl.GeoJSONSource['setData']>[0];
const KINDS: RouteKind[] = ['fastest', 'safest'];
const COLOR: Record<RouteKind, string> = { fastest: '#2563eb', safest: '#0d9488' };
const emptyFC = () => ({ type: 'FeatureCollection' as const, features: [] });

const riskOpacity = (k: number): maplibregl.ExpressionSpecification =>
    ['interpolate', ['linear'], ['get', 'p'], 0.05, 0.25 * k, 0.5, 0.8 * k, 1, 0.95 * k];

function addLayers(map: maplibregl.Map) {
    // Chèn dưới lớp chữ để tên đường vẫn đọc được
    const firstSymbol = map.getStyle().layers.find((l) => l.type === 'symbol')?.id;

    map.addSource('risk', { type: 'geojson', data: emptyFC() });
    map.addLayer({
        id: 'risk-lines', type: 'line', source: 'risk',
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: {
            'line-width': ['interpolate', ['linear'], ['zoom'], 12, 1.5, 15, 3, 17, 6],
            'line-color': ['interpolate', ['linear'], ['get', 'p'],
                0.05, '#fde68a', 0.3, '#fbbf24', 0.5, '#f97316', 0.75, '#dc2626', 1, '#7f1d1d'],
            'line-opacity': riskOpacity(1),
        },
    }, firstSymbol);

    for (const k of KINDS) {
        map.addSource(`route-${k}`, { type: 'geojson', data: emptyFC() });
        const layout = { 'line-cap': 'round', 'line-join': 'round' } as const;
        map.addLayer({
            id: `route-${k}-casing`, type: 'line', source: `route-${k}`, layout,
            paint: { 'line-width': 11, 'line-color': '#ffffff' },
        });
        map.addLayer({
            id: `route-${k}-line`, type: 'line', source: `route-${k}`, layout,
            paint: { 'line-width': 6, 'line-color': COLOR[k] },
        });
    }
}

interface Props {
    origin: Place | null;
    destination: Place | null;
    routes: RouteResponse | null;
    selected: RouteKind;
    riskData?: GeoData; // GeoJSON từ GET /risk-map; truyền vào khi có dữ liệu
    onMapClick: (p: LngLat) => void;
}

export default function MapView({ origin, destination, routes, selected, riskData, onMapClick }: Props) {
    const box = useRef<HTMLDivElement>(null);
    const mapRef = useRef<maplibregl.Map | null>(null);
    const pins = useRef<maplibregl.Marker[]>([]);
    const clickRef = useRef(onMapClick);
    clickRef.current = onMapClick;
    const [ready, setReady] = useState(false);
    const [showRisk, setShowRisk] = useState(true);

    useEffect(() => {
        if (!box.current) return;
        const map = new maplibregl.Map({
            container: box.current, style: MAP_STYLE, center: MAP_CENTER, zoom: MAP_ZOOM,
            maxBounds: MAP_BOUNDS, attributionControl: { compact: true },
        });
        map.on('load', () => { addLayers(map); setReady(true); });
        map.on('error', (e) => console.error('MapLibre:', e.error));
        map.on('click', (e) => clickRef.current([e.lngLat.lng, e.lngLat.lat]));
        mapRef.current = map;
        return () => { map.remove(); mapRef.current = null; setReady(false); }; // cần cho StrictMode
    }, []);

    useEffect(() => {
        const map = mapRef.current;
        if (!map) return;
        pins.current.forEach((m) => m.remove());
        pins.current = [];
        ([[origin, 'origin'], [destination, 'destination']] as const).forEach(([p, cls]) => {
            if (!p) return;
            const el = document.createElement('div');
            el.className = `pin pin--${cls}`;
            pins.current.push(new maplibregl.Marker({ element: el }).setLngLat(p.lngLat).addTo(map));
        });
        return () => { pins.current.forEach((m) => m.remove()); pins.current = []; };
    }, [origin, destination]);

    useEffect(() => {
        const map = mapRef.current;
        if (!map || !ready) return;
        const bounds = new maplibregl.LngLatBounds();
        for (const k of KINDS) {
            const g = routes?.[k].geometry;
            (map.getSource(`route-${k}`) as maplibregl.GeoJSONSource).setData(
                g ? { type: 'Feature', properties: {}, geometry: g } : emptyFC());
            g?.coordinates.forEach((c) => bounds.extend(c));
        }
        if (routes) {
            const left = window.innerWidth > 700 ? 420 : 60;
            map.fitBounds(bounds, { padding: { top: 80, bottom: 80, left, right: 80 }, maxZoom: 16 });
        }
    }, [routes, ready]);

    useEffect(() => {
        const map = mapRef.current;
        if (!map || !ready) return;
        map.setPaintProperty('risk-lines', 'line-opacity', riskOpacity(routes ? 0.55 : 1));
    }, [routes, ready]);

    useEffect(() => {
        const map = mapRef.current;
        if (!map || !ready) return;
        for (const k of KINDS) {
            const on = k === selected;
            map.setPaintProperty(`route-${k}-line`, 'line-opacity', on ? 1 : 0.55);
            map.setPaintProperty(`route-${k}-line`, 'line-width', on ? 7 : 4);
            map.setPaintProperty(`route-${k}-casing`, 'line-opacity', on ? 1 : 0.5);
            map.setPaintProperty(`route-${k}-casing`, 'line-width', on ? 12 : 7);
        }
        map.moveLayer(`route-${selected}-casing`);
        map.moveLayer(`route-${selected}-line`);
    }, [selected, routes, ready]);

    useEffect(() => {
        const map = mapRef.current;
        if (!map || !ready) return;
        (map.getSource('risk') as maplibregl.GeoJSONSource).setData(riskData ?? emptyFC());
    }, [riskData, ready]);

    useEffect(() => {
        const map = mapRef.current;
        if (!map || !ready) return;
        map.setLayoutProperty('risk-lines', 'visibility', showRisk ? 'visible' : 'none');
    }, [showRisk, ready]);

    const locate = () =>
        navigator.geolocation?.getCurrentPosition((pos) =>
            mapRef.current?.flyTo({ center: [pos.coords.longitude, pos.coords.latitude], zoom: 15 }));

    return (
        <div className="map-wrap">
            <div ref={box} className="map" />
            <div className="map-controls">
                <button aria-label="Phóng to" onClick={() => mapRef.current?.zoomIn()}>+</button>
                <button aria-label="Thu nhỏ" onClick={() => mapRef.current?.zoomOut()}>−</button>
                <button aria-label="Vị trí của tôi" onClick={locate}>◎</button>
                <button aria-label="Bật/tắt lớp rủi ro ngập" aria-pressed={showRisk}
                    className={showRisk ? 'is-on' : ''} onClick={() => setShowRisk((v) => !v)}>☰</button>
            </div>
            <div className="legend">
                <span>Mức rủi ro ngập</span>
                <i className="legend__bar" />
                <div><span>Thấp</span><span>0,25</span><span>0,5</span><span>0,75</span><span>Cao</span></div>
            </div>
        </div>
    );
}