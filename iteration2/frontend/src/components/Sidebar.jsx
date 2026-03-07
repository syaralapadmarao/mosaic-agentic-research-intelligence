export default function Sidebar({ companies, selected, onSelect, stats }) {
  return (
    <aside className="w-56 border-r border-slate-800 min-h-[calc(100vh-60px)] bg-slate-900/30 p-3">
      <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">
        Companies
      </h3>
      <ul className="space-y-1">
        {companies.map(c => (
          <li key={c.name}>
            <button
              onClick={() => onSelect(c.name)}
              className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-all ${
                selected === c.name
                  ? 'bg-blue-500/20 text-blue-400 border border-blue-500/30'
                  : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'
              }`}
            >
              <div className="font-medium capitalize">{c.name}</div>
              <div className="text-xs text-slate-500 mt-0.5">
                {c.pdf_count} docs &middot; {c.quarters_loaded} Q loaded
              </div>
            </button>
          </li>
        ))}
      </ul>

      {stats && (
        <div className="mt-6 pt-4 border-t border-slate-800">
          <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">
            Vector Store
          </h3>
          <div className="space-y-1.5 text-xs">
            {Object.entries(stats.namespaces || {}).map(([ns, count]) => (
              <div key={ns} className="flex justify-between text-slate-400">
                <span className="capitalize">{ns}</span>
                <span className="font-mono text-slate-300">{count}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </aside>
  );
}
