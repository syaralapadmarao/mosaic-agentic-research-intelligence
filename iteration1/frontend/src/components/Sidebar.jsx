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
    <aside className="w-72 min-h-screen flex flex-col border-r shrink-0"
      style={{ background: 'var(--bg-secondary)', borderColor: 'var(--border)' }}>

      {/* Brand */}
      <div className="px-5 pt-6 pb-5 border-b" style={{ borderColor: 'var(--border)' }}>
        <h1 className="text-xl font-extrabold tracking-[0.3em]" style={{ color: 'var(--accent)' }}>
          MOSAIC
        </h1>
        <p className="text-xs mt-1.5 tracking-wider font-medium"
          style={{ color: 'var(--text-muted)' }}>
          Earnings Intelligence
        </p>
      </div>

      {/* Schema picker */}
      <div className="px-5 py-4 border-b" style={{ borderColor: 'var(--border)' }}>
        <label className="text-[11px] font-bold uppercase tracking-wider block mb-2"
          style={{ color: 'var(--text-secondary)' }}>
          Industry Schema
        </label>
        <select
          value={schemaKey}
          onChange={e => onSchemaChange(e.target.value)}
          className="w-full px-3 py-2 rounded-lg text-sm outline-none cursor-pointer"
          style={{
            background: 'var(--bg-tertiary)', color: 'var(--text-primary)',
            border: '1px solid var(--border)',
          }}
        >
          <option value="">Select schema...</option>
          {schemas.map(s => (
            <option key={s.key} value={s.key}>
              {s.key} — {s.sector} — {s.metric_count} metrics
            </option>
          ))}
        </select>
      </div>

      {/* Company list header */}
      <div className="px-5 pt-4 pb-2 flex items-baseline justify-between">
        <span className="text-[11px] font-bold uppercase tracking-wider"
          style={{ color: 'var(--text-secondary)' }}>
          Companies
        </span>
        <span className="text-xs font-semibold" style={{ color: 'var(--text-muted)' }}>
          <span style={{ color: 'var(--accent)' }}>{loaded}</span> / {companies.length} loaded
        </span>
      </div>

      {/* Company list */}
      <nav className="flex-1 overflow-y-auto px-3 py-1">
        {companies.map(c => {
          const isSelected = selected === c.name;
          const hasData = c.quarters_loaded > 0;
          return (
            <button
              key={c.name}
              onClick={() => onSelect(c.name)}
              className="w-full text-left px-4 py-3 rounded-lg mb-1 transition-all"
              style={{
                background: isSelected ? 'var(--bg-tertiary)' : 'transparent',
                borderLeft: isSelected ? '3px solid var(--accent)' : '3px solid transparent',
                boxShadow: isSelected ? '0 1px 6px rgba(0,0,0,0.25)' : 'none',
              }}
            >
              <div className="flex items-center justify-between">
                <span className="font-semibold text-sm capitalize"
                  style={{ color: isSelected ? 'var(--text-primary)' : 'var(--text-secondary)' }}>
                  {c.name}
                </span>
                {hasData && (
                  <span className="text-[10px] px-2 py-0.5 rounded-md font-bold"
                    style={{ background: 'var(--green-dim)', color: 'var(--green)' }}>
                    {c.quarters_loaded}Q
                  </span>
                )}
              </div>
              {(c.last_quarter || c.topic_count > 0 || !hasData) && (
                <div className="text-[11px] mt-1" style={{ color: 'var(--text-muted)' }}>
                  {c.last_quarter && <span>Last: {c.last_quarter}</span>}
                  {c.topic_count > 0 && <span> &middot; {c.topic_count} topics</span>}
                  {!hasData && <span>{c.pdf_count} PDFs available</span>}
                </div>
              )}
            </button>
          );
        })}
      </nav>
    </aside>
  );
}
