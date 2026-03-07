export default function DivergenceAlert({ divergence }) {
  return (
    <div className="rounded-xl bg-amber-500/10 border border-amber-500/30 p-3 mb-2">
      <div className="flex items-center gap-2 mb-2">
        <span className="text-amber-400 text-sm font-bold">Consensus Divergence</span>
        <span className="text-xs px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-300">
          {divergence.metric_or_topic}
        </span>
      </div>
      <div className="grid grid-cols-2 gap-3 text-xs">
        <div className="p-2 rounded-lg bg-slate-800/50 border border-slate-700/50">
          <div className="text-slate-400 mb-1">View A</div>
          <div className="text-slate-200">{divergence.view_a}</div>
        </div>
        <div className="p-2 rounded-lg bg-slate-800/50 border border-slate-700/50">
          <div className="text-slate-400 mb-1">View B</div>
          <div className="text-slate-200">{divergence.view_b}</div>
        </div>
      </div>
      {divergence.divergence_summary && (
        <div className="mt-2 text-xs text-amber-300/70">
          {divergence.divergence_summary}
        </div>
      )}
    </div>
  );
}
