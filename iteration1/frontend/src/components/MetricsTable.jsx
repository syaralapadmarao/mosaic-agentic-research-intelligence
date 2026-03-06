import { useEffect, useState } from 'react';
import { getMetrics, getCitations } from '../api';

function fmt(v) {
  if (v == null) return '—';
  if (Math.abs(v) >= 10000) return v.toLocaleString('en-IN', { maximumFractionDigits: 0 });
  if (Math.abs(v) >= 100) return v.toLocaleString('en-IN', { maximumFractionDigits: 1 });
  return v.toFixed(1);
}

const DERIVED_KEYWORDS = ['per Bed', 'per bed', 'Occupied Bed Days', 'Growth'];

function isDerived(name) {
  return DERIVED_KEYWORDS.some(k => name.includes(k));
}

function pdfUrl(company, filePath, page) {
  if (!filePath) return null;
  const marker = '/sample_docs/';
  const idx = filePath.indexOf(marker);
  let rel;
  if (idx !== -1) {
    const afterMarker = filePath.slice(idx + marker.length);
    const slashIdx = afterMarker.indexOf('/');
    rel = slashIdx !== -1 ? afterMarker.slice(slashIdx + 1) : afterMarker;
  } else {
    rel = filePath.split('/').slice(-2).join('/');
  }
  return `/api/pdf/${encodeURIComponent(company)}/${rel}#page=${page}`;
}

function QoQ({ val }) {
  if (val == null) return null;
  const color = val > 0 ? 'var(--green)' : val < 0 ? 'var(--red)' : 'var(--text-muted)';
  return (
    <div className="text-[10px] mt-0.5" style={{ color }}>
      {val > 0 ? '+' : ''}{val.toFixed(1)}%
    </div>
  );
}

function Cites({ cites, company }) {
  if (!cites?.length) return null;
  const seen = new Set();
  const unique = cites.filter(c => {
    const key = `${c.page_number}:${c.file_path}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });

  return (
    <div className="flex flex-wrap gap-1 mt-1">
      {unique.map((c, i) => {
        const url = pdfUrl(company, c.file_path, c.page_number);
        return (
          <a
            key={i}
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            title={c.passage || `Page ${c.page_number}`}
            className="inline-block text-[10px] px-1.5 py-0.5 rounded transition-colors hover:opacity-80"
            style={{
              background: 'rgba(59,130,246,0.12)',
              color: 'var(--accent)',
              textDecoration: 'none',
              cursor: 'pointer',
            }}
          >
            p.{c.page_number}
          </a>
        );
      })}
    </div>
  );
}

export default function MetricsTable({ company }) {
  const [data, setData] = useState(null);
  const [cites, setCites] = useState({});
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState('all');

  useEffect(() => {
    if (!company) return;
    setLoading(true);
    Promise.all([getMetrics(company), getCitations(company)])
      .then(([m, c]) => { setData(m); setCites(c.citations || {}); })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [company]);

  if (!company) return <Empty msg="Select a company to view metrics" />;
  if (loading) return <Empty msg="Loading…" />;
  if (!data?.quarters?.length) return <Empty msg="No metrics data yet. Run the pipeline first." />;

  const { quarters, metrics } = data;
  const entries = Object.entries(metrics).filter(([name]) => {
    if (filter === 'direct') return !isDerived(name);
    if (filter === 'derived') return isDerived(name);
    return true;
  });

  return (
    <div>
      {/* Toolbar */}
      <div className="flex items-center justify-between px-4 py-2 border-b"
        style={{ borderColor: 'var(--border)' }}>
        <div className="flex gap-1">
          {['all', 'direct', 'derived'].map(f => (
            <button key={f} onClick={() => setFilter(f)}
              className="px-3 py-1 rounded text-[11px] font-medium uppercase tracking-wide transition-colors"
              style={{
                background: filter === f ? 'var(--bg-primary)' : 'transparent',
                color: filter === f ? 'var(--text-primary)' : 'var(--text-muted)',
              }}>
              {f === 'derived' ? '⚙ Derived' : f === 'direct' ? 'Direct' : 'All'}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-3 text-[10px]" style={{ color: 'var(--text-muted)' }}>
          <span><span style={{ color: 'var(--green)' }}>■</span> QoQ increase</span>
          <span><span style={{ color: 'var(--red)' }}>■</span> QoQ decrease</span>
          <span><span style={{ color: 'var(--accent)' }}>p.N</span> = open PDF page</span>
        </div>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr>
              <th className="text-left px-4 py-2.5 text-[11px] font-semibold uppercase tracking-wider sticky left-0 z-10"
                style={{ background: 'var(--bg-secondary)', color: 'var(--text-muted)', minWidth: 210 }}>
                Metric
              </th>
              {quarters.map(q => (
                <th key={q} className="px-3 py-2.5 text-center text-[11px] font-semibold uppercase tracking-wider whitespace-nowrap"
                  style={{ background: 'var(--bg-secondary)', color: 'var(--text-muted)', minWidth: 120 }}>
                  {q}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {entries.map(([name, m], idx) => {
              const bg = idx % 2 === 0 ? 'var(--bg-primary)' : 'rgba(26,29,39,0.5)';
              const derived = isDerived(name);
              return (
                <tr key={name} className="transition-colors" style={{ background: bg }}>
                  <td className="px-4 py-2.5 sticky left-0 z-10" style={{ background: bg }}>
                    <span className="font-medium text-sm" style={{ color: 'var(--text-primary)' }}>
                      {name}
                    </span>
                    {m.unit && (
                      <span className="text-[11px] ml-1.5" style={{ color: 'var(--text-muted)' }}>
                        ({m.unit})
                      </span>
                    )}
                    {derived && (
                      <span className="text-[9px] ml-2 px-1.5 py-0.5 rounded font-semibold"
                        style={{ background: 'rgba(59,130,246,0.15)', color: 'var(--accent)' }}>
                        CODE
                      </span>
                    )}
                  </td>
                  {quarters.map(q => {
                    const val = m.values[q];
                    const change = m.changes?.[q];
                    const qCites = cites[q]?.[name] || [];
                    const cellBorder = change != null
                      ? change > 0 ? '2px solid rgba(34,197,94,0.3)' : change < 0 ? '2px solid rgba(239,68,68,0.3)' : 'none'
                      : 'none';
                    return (
                      <td key={q} className="px-3 py-2.5 text-center" style={{ borderBottom: cellBorder }}>
                        <div className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                          {fmt(val)}
                        </div>
                        <QoQ val={change} />
                        <Cites cites={qCites} company={company} />
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Empty({ msg }) {
  return (
    <div className="flex items-center justify-center h-64" style={{ color: 'var(--text-muted)' }}>
      <p className="text-sm italic">{msg}</p>
    </div>
  );
}
