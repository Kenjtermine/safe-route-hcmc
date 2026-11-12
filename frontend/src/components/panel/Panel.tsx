import { useEffect, useState } from 'react';
import { PLACES } from '../../data/places';
import type { Place, RouteKind, RouteOption, RouteResponse } from '../../types/api';

const fold = (s: string) =>
    s.normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/đ/g, 'd').toLowerCase();

const riskLevel = (p: number) =>
    p < 0.3 ? { key: 'low', text: 'Thấp' } : p < 0.6 ? { key: 'mid', text: 'Vừa' } : { key: 'high', text: 'Cao' };

function PlaceField({ kind, label, place, onChange }: {
    kind: 'origin' | 'destination'; label: string; place: Place | null; onChange: (p: Place | null) => void;
}) {
    const [q, setQ] = useState(place?.label ?? '');
    const [open, setOpen] = useState(false);
    useEffect(() => setQ(place?.label ?? ''), [place]);
    const matches = PLACES.filter((p) => fold(p.label).includes(fold(q.trim()))).slice(0, 5);

    return (
        <div className="field">
            <span className={`dot dot--${kind}`} />
            <div className="field__body">
                <label className="label">{label}</label>
                <input value={q} placeholder="Gõ địa danh hoặc chọn trên bản đồ"
                    onChange={(e) => { setQ(e.target.value); setOpen(true); }}
                    onFocus={() => setOpen(true)} onBlur={() => setOpen(false)} />
                {open && matches.length > 0 && (
                    <ul className="suggest">
                        {matches.map((p) => (
                            <li key={p.label}>
                                <button type="button" onMouseDown={() => { onChange(p); setOpen(false); }}>{p.label}</button>
                            </li>
                        ))}
                    </ul>
                )}
            </div>
            {place && <button className="icon-btn" aria-label="Xóa" onClick={() => { onChange(null); setQ(''); }}>×</button>}
        </div>
    );
}

function RouteDetail({ route }: { route: RouteOption }) {
    const lv = riskLevel(route.max_risk);
    return (
        <section className="detail" data-kind={route.kind}>
            <div className="detail__top">
                <strong>Qua {route.via.join(' & ')}</strong>
                {route.recommended && <span className="badge">Khuyến nghị</span>}
            </div>
            <p className={`row risk--${lv.key}`}>Mức rủi ro ngập: <b>{lv.text}</b></p>
            {route.clearance_m != null && (
                <p className="row">Cao độ mặt đường cao nhất (+{route.clearance_m} m so với mực triều)</p>
            )}
            <p className="explain">{route.explanation}</p>
        </section>
    );
}

interface Props {
    origin: Place | null; destination: Place | null;
    onOrigin: (p: Place | null) => void; onDestination: (p: Place | null) => void; onSwap: () => void;
    routes: RouteResponse | null; loading: boolean; error: string | null;
    selected: RouteKind; onSelect: (k: RouteKind) => void;
}

export default function Panel(p: Props) {
    return (
        <aside className="panel">
            <header className="panel__head">
                <h1>SAFE ROUTE</h1>
            </header>

            <div className="places">
                <PlaceField kind="origin" label="Điểm xuất phát" place={p.origin} onChange={p.onOrigin} />
                <button className="swap" aria-label="Đổi chiều" onClick={p.onSwap}>⇅</button>
                <PlaceField kind="destination" label="Điểm đến" place={p.destination} onChange={p.onDestination} />
            </div>

            <h2 className="section">Phương án lưu thông</h2>
            {p.loading && <p className="hint">Đang tìm tuyến…</p>}
            {p.error && <p className="hint hint--error">{p.error}</p>}
            {!p.routes && !p.loading && !p.error && <p className="hint">Chọn điểm đi và điểm đến để xem hai tuyến.</p>}

            {p.routes && (
                <>
                    <div className="tabs" role="tablist">
                        {(['safest', 'fastest'] as const).map((k) => (
                            <button key={k} role="tab" aria-selected={p.selected === k}
                                className={`tab ${p.selected === k ? 'is-active' : ''}`} data-kind={k}
                                onClick={() => p.onSelect(k)}>
                                <span className="tab__row">
                                    <span className="label">{k === 'safest' ? 'Safest' : 'Fastest'}</span>
                                    <span className="label">{p.routes![k].distance_km} km</span>
                                </span>
                                <span><strong>{p.routes![k].duration_min}</strong> phút</span>
                            </button>
                        ))}
                    </div>
                    <RouteDetail route={p.routes[p.selected]} />
                </>
            )}
        </aside>
    );
}