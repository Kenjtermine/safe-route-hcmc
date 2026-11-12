import { useCallback, useEffect, useState } from 'react';
import { fetchRoutes } from './api/routes';
import MapView from './components/map/MapView';
import Panel from './components/panel/Panel';
import type { LngLat, Place, RouteKind, RouteResponse } from './types/api';

export default function App() {
  const [origin, setOrigin] = useState<Place | null>(null);
  const [destination, setDestination] = useState<Place | null>(null);
  const [routes, setRoutes] = useState<RouteResponse | null>(null);
  const [selected, setSelected] = useState<RouteKind>('safest');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setError(null);
    if (!origin || !destination) { setRoutes(null); setLoading(false); return; }
    let cancelled = false;
    setLoading(true);
    fetchRoutes(origin.lngLat, destination.lngLat)
      .then((r) => { if (!cancelled) { setRoutes(r); setSelected('safest'); setLoading(false); } })
      // .catch(() => { if (!cancelled) { setError('Không tìm được tuyến. Hãy thử lại.'); setLoading(false); } });
      .catch((e) => { if (!cancelled) { setError(e.message); setLoading(false); } });
    return () => { cancelled = true; };
  }, [origin, destination]);

  // Click bản đồ: điền ô xuất phát trước, sau đó đặt/đổi điểm đến
  const onMapClick = useCallback((lngLat: LngLat) => {
    const p = { label: `Điểm đã chọn (${lngLat[1].toFixed(4)}, ${lngLat[0].toFixed(4)})`, lngLat };
    if (!origin) setOrigin(p); else setDestination(p);
  }, [origin]);

  return (
    <div className="app">
      <MapView origin={origin} destination={destination} routes={routes} selected={selected} onMapClick={onMapClick} />
      <Panel origin={origin} destination={destination} onOrigin={setOrigin} onDestination={setDestination}
        onSwap={() => { setOrigin(destination); setDestination(origin); }}
        routes={routes} loading={loading} error={error} selected={selected} onSelect={setSelected} />
      <div className="topbar">
        <button className="pill">ADMIN</button>
        <button className="avatar" aria-label="Tài khoản">
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor"
            strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <circle cx="12" cy="8" r="4" />
            <path d="M4 20c0-3.5 3.6-6 8-6s8 2.5 8 6" />
          </svg>
        </button>
      </div>
    </div>
  );
}