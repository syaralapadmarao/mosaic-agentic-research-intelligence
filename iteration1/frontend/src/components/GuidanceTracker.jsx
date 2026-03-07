import { useEffect, useState } from 'react';
import { getGuidance, getDeltas, getSentimentConfig } from '../api';

function dominant(items) {
  if (!items?.length) return 'neutral';
  const c = {};
  items.forEach(i => { const s = i.sentiment || 'neutral'; c[s] = (c[s] || 0) + 1; });
  return Object.entries(c).sort((a, b) => b[1] - a[1])[0][0];
}

function topicTag(qData, quarters) {
  const present = quarters.filter(q => qData[q]?.length > 0);
  if (!present.length) return null;
  const lastIdx = Math.max(...present.map(q => quarters.indexOf(q)));
  const firstIdx = Math.min(...present.map(q => quarters.indexOf(q)));
  const latestIdx = quarters.length - 1;

  if (firstIdx === latestIdx && present.length === 1) return { label: 'NEW TOPIC', color: 'var(--green)' };
  if (lastIdx < latestIdx - 2) return { label: 'STALE', color: 'var(--red)' };
  if (present.length >= 2) {
    const r = [...present].sort((a, b) => quarters.indexOf(a) - quarters.indexOf(b)).slice(-2);
    const s0 = dominant(qData[r[0]]), s1 = dominant(qData[r[1]]);
    const bull = new Set(['very_bullish', 'bullish']), bear = new Set(['cautious', 'very_cautious']);
    if ((bull.has(s0) && bear.has(s1)) || (bear.has(s0) && bull.has(s1)))
      return { label: 'DRIFT', color: 'var(--amber)' };
  }
  return null;
}

const CHANGE_ICONS = { new: '🆕', upgraded: '⬆', downgraded: '⬇', reiterated: '↔', removed: '🚫' };

export default function GuidanceTracker({ company }) {
  const [data, setData] = useState(null);
  const [deltasData, setDeltasData] = useState(null);
  const [config, setConfig] = useState(null);
  const [loading, setLoading] = useState(false);
  const [view, setView] = useState('tracker');

  useEffect(() => { getSentimentConfig().then(setConfig).catch(console.error); }, []);

  useEffect(() => {
    if (!company) return;
    setLoading(true);
    Promise.all([getGuidance(company), getDeltas(company)])
      .then(([g, d]) => { setData(g); setDeltasData(d); })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [company]);

  if (!company) return <Empty msg="Select a company to view guidance" />;
  if (loading) return <Empty msg="Loading…" />;
  if (!data?.quarters?.length || !Object.keys(data?.topics || {}).length)
    return <Empty msg="No guidance data yet. Run the pipeline with transcripts first." />;

  const { quarters, topics } = data;

  return (
    <div>
      {/* Toolbar */}
      <div className="flex items-center justify-between px-4 py-2 border-b"
        style={{ borderColor: 'var(--border)' }}>
        <div className="flex gap-1">
          <button onClick={() => setView('tracker')}
            className="px-3 py-1 rounded text-[11px] font-medium transition-colors"
            style={{
              background: view === 'tracker' ? 'var(--bg-primary)' : 'transparent',
              color: view === 'tracker' ? 'var(--text-primary)' : 'var(--text-muted)',
            }}>
            Topic × Quarter
          </button>
          <button onClick={() => setView('deltas')}
            className="px-3 py-1 rounded text-[11px] font-medium transition-colors"
            style={{
              background: view === 'deltas' ? 'var(--bg-primary)' : 'transparent',
              color: view === 'deltas' ? 'var(--text-primary)' : 'var(--text-muted)',
            }}>
            QoQ Changes
          </button>
        </div>
        {config && (
          <div className="flex gap-3 text-[10px]" style={{ color: 'var(--text-muted)' }}>
            {Object.entries(config.arrows).map(([level, arrow]) => (
              <span key={level} className="flex items-center gap-0.5">
                <span style={{ color: config.colors[level], fontWeight: 'bold', fontSize: 13 }}>{arrow}</span>
                {level.replace(/_/g, ' ')}
              </span>
            ))}
          </div>
        )}
      </div>

      {view === 'tracker' ? (
        <TrackerView quarters={quarters} topics={topics} config={config} company={company} />
      ) : (
        <DeltasView data={deltasData} />
      )}
    </div>
  );
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

function TrackerView({ quarters, topics, config, company }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr>
            <th className="text-left px-4 py-2 text-sm font-bold uppercase tracking-wider sticky left-0 z-10"
              style={{ background: 'var(--bg-secondary)', color: 'var(--text-secondary)', minWidth: 170 }}>
              Topic
            </th>
            {quarters.map(q => (
              <th key={q} className="px-3 py-2 text-center text-sm font-bold uppercase tracking-wider whitespace-nowrap"
                style={{ background: 'var(--bg-secondary)', color: 'var(--text-secondary)', minWidth: 200 }}>
                {q}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {Object.entries(topics).map(([topic, qData], idx) => {
            const tag = topicTag(qData, quarters);
            const bg = idx % 2 === 0 ? 'var(--bg-primary)' : 'rgba(26,29,39,0.5)';
            return (
              <tr key={topic} style={{ background: bg }}>
                <td className="px-4 py-1.5 align-top sticky left-0 z-10" style={{ background: bg }}>
                  <div className="flex items-center gap-1.5">
                    <span className="font-medium text-sm" style={{ color: 'var(--text-primary)' }}>{topic}</span>
                    {tag && (
                      <span className="text-[9px] font-bold px-1.5 py-0.5 rounded"
                        style={{ background: `${tag.color}20`, color: tag.color }}>
                        {tag.label}
                      </span>
                    )}
                  </div>
                </td>
                {quarters.map(q => {
                  const items = qData[q] || [];
                  if (!items.length) {
                    return (
                      <td key={q} className="px-3 py-1.5 text-center align-top italic text-xs"
                        style={{ color: 'var(--text-muted)' }}>
                        Not discussed
                      </td>
                    );
                  }
                  const sentiment = dominant(items);
                  const arrow = config?.arrows?.[sentiment] || '→';
                  const color = config?.colors?.[sentiment] || 'var(--text-muted)';
                  const text = items.map(i => i.statement).join(' ');
                  const summary = text.length > 160 ? text.slice(0, 157) + '…' : text;
                  const seen = new Set();
                  const pageLinks = items
                    .filter(i => i.page_number)
                    .filter(i => { const k = `${i.page_number}:${i.file_path}`; if (seen.has(k)) return false; seen.add(k); return true; });

                  return (
                    <td key={q} className="px-3 py-1.5 align-top" style={{ maxWidth: 260 }}>
                      <div className="flex gap-2">
                        <span className="text-base font-bold shrink-0 leading-5" style={{ color }}>{arrow}</span>
                        <div className="min-w-0">
                          <p className="text-[11px] leading-4" style={{ color: 'var(--text-secondary)' }}>
                            {summary}
                          </p>
                          {pageLinks.length > 0 && (
                            <div className="cite-row" style={{ justifyContent: 'flex-start', marginTop: 3 }}>
                              {pageLinks.map((pl, i) => (
                                <a key={i}
                                  href={pdfUrl(company, pl.file_path, pl.page_number)}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  title={pl.passage || `Page ${pl.page_number}`}
                                  className="cite-link"
                                >
                                  [p.{pl.page_number}]
                                </a>
                              ))}
                            </div>
                          )}
                        </div>
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
  );
}

function DeltasView({ data }) {
  if (!data?.deltas || Object.keys(data.deltas).length === 0) {
    return <Empty msg="No quarter-over-quarter changes detected yet." />;
  }

  return (
    <div className="p-4 space-y-5">
      {Object.entries(data.deltas).map(([quarter, deltas]) => {
        const prior = deltas[0]?.prior_quarter || '?';
        return (
          <div key={quarter}>
            <h3 className="text-xs font-semibold mb-2" style={{ color: 'var(--text-primary)' }}>
              {quarter} <span style={{ color: 'var(--text-muted)' }}>vs {prior}</span>
            </h3>
            <div className="space-y-1.5">
              {deltas.map((d, i) => (
                <div key={i} className="flex items-start gap-2 px-3 py-2 rounded"
                  style={{ background: 'var(--bg-tertiary)' }}>
                  <span className="text-sm shrink-0">{CHANGE_ICONS[d.change_type] || '•'}</span>
                  <div className="min-w-0">
                    <span className="text-[11px] font-semibold mr-2"
                      style={{ color: 'var(--accent)' }}>{d.topic}</span>
                    <span className="text-[11px]" style={{ color: 'var(--text-secondary)' }}>
                      {d.summary}
                    </span>
                    {d.current_statement && (
                      <p className="text-[10px] mt-0.5 italic" style={{ color: 'var(--text-muted)' }}>
                        Now: {d.current_statement}
                      </p>
                    )}
                  </div>
                  <span className="text-[9px] shrink-0 px-1.5 py-0.5 rounded font-semibold uppercase"
                    style={{
                      background: d.change_type === 'upgraded' ? 'rgba(34,197,94,0.15)' :
                        d.change_type === 'downgraded' ? 'rgba(239,68,68,0.15)' :
                        d.change_type === 'new' ? 'rgba(59,130,246,0.15)' :
                        d.change_type === 'removed' ? 'rgba(239,68,68,0.15)' : 'rgba(148,163,184,0.15)',
                      color: d.change_type === 'upgraded' ? 'var(--green)' :
                        d.change_type === 'downgraded' ? 'var(--red)' :
                        d.change_type === 'new' ? 'var(--accent)' :
                        d.change_type === 'removed' ? 'var(--red)' : 'var(--text-muted)',
                    }}>
                    {d.change_type}
                  </span>
                </div>
              ))}
            </div>
          </div>
        );
      })}
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
