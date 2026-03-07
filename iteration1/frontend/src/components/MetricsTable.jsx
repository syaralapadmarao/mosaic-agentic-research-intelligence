import { useEffect, useState } from 'react';
import { getMetrics, getCitations } from '../api';

function fmt(v) {
  if (v == null) return null;
  if (Math.abs(v) >= 1_00_000) return v.toLocaleString('en-IN', { maximumFractionDigits: 0 });
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
    <div className="cite-row">
      {unique.map((c, i) => (
        <a
          key={i}
          href={pdfUrl(company, c.file_path, c.page_number)}
          target="_blank"
          rel="noopener noreferrer"
          title={c.passage || `Page ${c.page_number}`}
          className="cite-link"
        >
          [p.{c.page_number}]
        </a>
      ))}
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
  if (loading) return <Empty msg="Loading..." />;
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
      <div className="flex items-center justify-between px-5 py-2.5 border-b"
        style={{ borderColor: 'var(--border)' }}>
        <div className="flex gap-1">
          {['all', 'direct', 'derived'].map(f => (
            <button key={f} onClick={() => setFilter(f)}
              className={`filter-btn ${filter === f ? 'active' : 'inactive'}`}>
              {f === 'derived' ? 'Derived (code)' : f === 'direct' ? 'Direct' : 'All'}
            </button>
          ))}
        </div>
        <div className="legend">
          <span><span className="legend-dot" style={{ background: 'var(--green)' }} />QoQ increase</span>
          <span><span className="legend-dot" style={{ background: 'var(--red)' }} />QoQ decrease</span>
          <span><span className="cite-link" style={{ opacity: 1 }}>[p.N]</span> = click to open PDF</span>
        </div>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full border-collapse" style={{ tableLayout: 'fixed' }}>
          <colgroup>
            <col style={{ width: 240 }} />
            {quarters.map(q => (
              <col key={q} style={{ width: 130 }} />
            ))}
          </colgroup>
          <thead>
            <tr>
              <th className="text-left px-4 py-2 text-sm font-bold uppercase tracking-wider sticky left-0 z-10"
                style={{ background: 'var(--bg-secondary)', color: 'var(--text-secondary)' }}>
                Metric
              </th>
              {quarters.map(q => (
                <th key={q} className="px-2 py-2 text-center text-sm font-bold uppercase tracking-wider whitespace-nowrap"
                  style={{ background: 'var(--bg-secondary)', color: 'var(--text-secondary)' }}>
                  {q}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {entries.map(([name, m], idx) => {
              const bg = idx % 2 === 0 ? 'var(--bg-row-even)' : 'var(--bg-row-odd)';
              const derived = isDerived(name);
              return (
                <tr key={name} style={{ background: bg }}>
                  <td className="px-4 py-1.5 sticky left-0 z-10" style={{ background: bg }}>
                    <span className="metric-name">{name}</span>
                    {m.unit && <span className="metric-unit">({m.unit})</span>}
                    {derived && <span className="badge-derived">CODE</span>}
                  </td>
                  {quarters.map(q => {
                    const val = m.values[q];
                    const formatted = fmt(val);
                    const change = m.changes?.[q];
                    const qCites = cites[q]?.[name] || [];

                    const qoqClass = change != null
                      ? change > 0 ? 'up' : change < 0 ? 'down' : 'flat'
                      : null;

                    return (
                      <td key={q} className="px-2 py-1.5 text-center">
                        <div className="metric-cell">
                          <span className={`metric-value${formatted == null ? ' empty' : ''}`}>
                            {formatted ?? '—'}
                          </span>
                          {qoqClass && (
                            <span className={`metric-qoq ${qoqClass}`}>
                              {change > 0 ? '+' : ''}{change.toFixed(1)}%
                            </span>
                          )}
                          <Cites cites={qCites} company={company} />
                        </div>
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
      <p className="text-sm">{msg}</p>
    </div>
  );
}
