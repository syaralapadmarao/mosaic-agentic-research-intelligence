import { useState, useEffect } from 'react';
import { fetchSources, fetchMnpiAudit } from '../api';

const TYPE_BADGES = {
  disclosure: 'bg-emerald-500/15 text-emerald-400',
  opinion: 'bg-blue-500/15 text-blue-400',
  field_data: 'bg-purple-500/15 text-purple-400',
};

export default function SourcesPanel({ company }) {
  const [sources, setSources] = useState([]);
  const [audit, setAudit] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showAudit, setShowAudit] = useState(false);

  useEffect(() => {
    if (!company) return;
    setLoading(true);
    Promise.all([
      fetchSources(company),
      fetchMnpiAudit(company),
    ]).then(([s, a]) => {
      setSources(s.sources || []);
      setAudit(a.audit || []);
    }).catch(() => {
      setSources([]);
      setAudit([]);
    }).finally(() => setLoading(false));
  }, [company]);

  if (loading) return <div className="text-slate-500 text-sm p-4">Loading sources...</div>;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-300">
          Ingested Sources ({sources.length})
        </h3>
        <button
          onClick={() => setShowAudit(!showAudit)}
          className="text-xs text-slate-500 hover:text-slate-300 transition-colors"
        >
          {showAudit ? 'Hide' : 'Show'} MNPI Audit ({audit.length})
        </button>
      </div>

      {/* Sources list */}
      <div className="grid gap-2">
        {sources.map((s, i) => (
          <div key={i} className="p-3 rounded-xl bg-slate-800/50 border border-slate-700/50 flex items-center gap-3">
            <span className={`text-xs px-2 py-0.5 rounded-full ${TYPE_BADGES[s.source_type] || TYPE_BADGES.disclosure}`}>
              {s.source_type}
            </span>
            <div className="flex-1 min-w-0">
              <div className="text-sm text-slate-200 truncate">{s.file_name}</div>
              <div className="text-xs text-slate-500">
                {s.doc_type} {s.firm && `| ${s.firm}`} {s.rating && `| ${s.rating}`} {s.date && `| ${s.date}`}
              </div>
            </div>
            {s.target_price && (
              <div className="text-xs font-mono text-slate-300">
                TP: {'\u20B9'}{s.target_price.toLocaleString()}
              </div>
            )}
          </div>
        ))}
        {sources.length === 0 && (
          <div className="text-slate-500 text-sm text-center py-8">
            No sources ingested yet. Use the Ingest tab to add documents.
          </div>
        )}
      </div>

      {/* MNPI Audit Log */}
      {showAudit && audit.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-slate-300 mb-2">MNPI Audit Log</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-slate-700">
                  <th className="text-left py-1.5 px-2 text-slate-400">File</th>
                  <th className="text-left py-1.5 px-2 text-slate-400">Classification</th>
                  <th className="text-left py-1.5 px-2 text-slate-400">Action</th>
                  <th className="text-left py-1.5 px-2 text-slate-400">Confidence</th>
                  <th className="text-left py-1.5 px-2 text-slate-400">Time</th>
                </tr>
              </thead>
              <tbody>
                {audit.map((a, i) => (
                  <tr key={i} className="border-b border-slate-800">
                    <td className="py-1.5 px-2 text-slate-300 truncate max-w-[200px]">{a.file_name}</td>
                    <td className="py-1.5 px-2 text-slate-400">{a.classification}</td>
                    <td className={`py-1.5 px-2 ${a.action === 'BLOCKED' ? 'text-red-400' : 'text-green-400'}`}>
                      {a.action}
                    </td>
                    <td className="py-1.5 px-2 text-slate-400 font-mono">{(a.confidence || 0).toFixed(2)}</td>
                    <td className="py-1.5 px-2 text-slate-500">{a.timestamp}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
