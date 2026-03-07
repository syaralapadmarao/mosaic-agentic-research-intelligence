const NS_LABELS = {
  disclosure: 'Disclosure',
  opinion: 'Opinion',
  field_data: 'Field Data',
};

const NS_COLORS = {
  disclosure: { active: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30', inactive: 'bg-slate-800 text-slate-500 border-slate-700' },
  opinion: { active: 'bg-blue-500/20 text-blue-400 border-blue-500/30', inactive: 'bg-slate-800 text-slate-500 border-slate-700' },
  field_data: { active: 'bg-purple-500/20 text-purple-400 border-purple-500/30', inactive: 'bg-slate-800 text-slate-500 border-slate-700' },
};

export default function MosaicBanner({ mosaic, responseState }) {
  if (!mosaic) return null;

  const score = Math.round((mosaic.completeness_score || 0) * 100);

  return (
    <div className="mx-4 mt-3 p-3 rounded-xl bg-slate-800/50 border border-slate-700/50 flex items-center gap-4">
      <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
        Mosaic
      </div>

      <div className="flex gap-2">
        {['disclosure', 'opinion', 'field_data'].map(ns => {
          const present = ns === 'disclosure' ? mosaic.disclosure_present :
                          ns === 'opinion' ? mosaic.opinion_present :
                          mosaic.field_data_present;
          const colors = present ? NS_COLORS[ns].active : NS_COLORS[ns].inactive;
          return (
            <span key={ns} className={`text-xs px-2.5 py-1 rounded-full border ${colors}`}>
              {present ? '\u2713' : '\u2717'} {NS_LABELS[ns]}
            </span>
          );
        })}
      </div>

      <div className="ml-auto flex items-center gap-2">
        <div className="w-16 h-1.5 bg-slate-700 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all ${
              score >= 100 ? 'bg-emerald-500' : score >= 66 ? 'bg-blue-500' : 'bg-amber-500'
            }`}
            style={{ width: `${score}%` }}
          />
        </div>
        <span className="text-xs font-mono text-slate-400">{score}%</span>
      </div>
    </div>
  );
}
