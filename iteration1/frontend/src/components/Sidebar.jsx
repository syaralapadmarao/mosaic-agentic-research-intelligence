import { useEffect, useState } from 'react';
import { getCompanies, getSchemas } from '../api';

export default function Sidebar({ selected, onSelect, schemaKey, onSchemaChange }) {
  const [companies, setCompanies] = useState([]);
  const [schemas, setSchemas] = useState([]);

  useEffect(() => {
    getCompanies().then(setCompanies).catch(console.error);
    getSchemas().then(setSchemas).catch(console.error);
  }, []);

  const loaded = companies.filter(c => c.quarters_loaded > 0).length;

  return (
    <aside className="w-60 min-h-screen flex flex-col border-r shrink-0"
      style={{ background: 'var(--bg-secondary)', borderColor: 'var(--border)' }}>

      {/* Brand */}
      <div className="px-4 pt-5 pb-4 border-b" style={{ borderColor: 'var(--border)' }}>
        <h1 className="text-base font-bold tracking-widest" style={{ color: 'var(--accent)' }}>
          MOSAIC
        </h1>
        <p className="text-[10px] mt-0.5 uppercase tracking-wider"
          style={{ color: 'var(--text-muted)' }}>
          Iter 1 — Earnings Dashboard
        </p>
      </div>

      {/* Schema picker */}
      <div className="px-4 py-3 border-b" style={{ borderColor: 'var(--border)' }}>
        <label className="text-[10px] font-semibold uppercase tracking-wider"
          style={{ color: 'var(--text-muted)' }}>
          Industry Schema
        </label>
        <select
          value={schemaKey}
          onChange={e => onSchemaChange(e.target.value)}
          className="mt-1 w-full px-2 py-1.5 rounded text-xs outline-none cursor-pointer"
          style={{
            background: 'var(--bg-tertiary)', color: 'var(--text-primary)',
            border: '1px solid var(--border)',
          }}
        >
          <option value="">Select…</option>
          {schemas.map(s => (
            <option key={s.key} value={s.key}>
              {s.key} · {s.sector} · {s.metric_count} metrics
            </option>
          ))}
        </select>
      </div>

      {/* Company list header */}
      <div className="px-4 pt-3 pb-1">
        <p className="text-[10px] font-semibold uppercase tracking-wider"
          style={{ color: 'var(--text-muted)' }}>
          Companies&nbsp;&nbsp;
          <span style={{ color: 'var(--text-primary)' }}>
            {loaded} loaded
          </span>
          &nbsp;·&nbsp;{companies.length} tracked
        </p>
      </div>

      {/* Company list */}
      <nav className="flex-1 overflow-y-auto px-2 py-1">
        {companies.map(c => {
          const isSelected = selected === c.name;
          const hasData = c.quarters_loaded > 0;
          return (
            <button
              key={c.name}
              onClick={() => onSelect(c.name)}
              className="w-full text-left px-3 py-2 rounded-md mb-0.5 transition-all"
              style={{
                background: isSelected ? 'var(--bg-tertiary)' : 'transparent',
                borderLeft: isSelected ? '2px solid var(--accent)' : '2px solid transparent',
              }}
            >
              <div className="flex items-center justify-between">
                <span className="font-medium text-xs capitalize"
                  style={{ color: isSelected ? 'var(--text-primary)' : 'var(--text-secondary)' }}>
                  {c.name}
                </span>
                {hasData && (
                  <span className="text-[9px] px-1.5 py-0.5 rounded"
                    style={{ background: 'rgba(34,197,94,0.15)', color: 'var(--green)' }}>
                    {c.quarters_loaded}Q
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2 mt-0.5">
                {c.last_quarter && (
                  <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
                    Last: {c.last_quarter}
                  </span>
                )}
                {c.topic_count > 0 && (
                  <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
                    · {c.topic_count} topics
                  </span>
                )}
                {!hasData && (
                  <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
                    {c.pdf_count} PDFs
                  </span>
                )}
              </div>
            </button>
          );
        })}
      </nav>
    </aside>
  );
}
