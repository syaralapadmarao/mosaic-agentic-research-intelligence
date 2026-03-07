const TYPE_STYLES = {
  disclosure: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
  opinion: 'bg-blue-500/15 text-blue-400 border-blue-500/30',
  field_data: 'bg-purple-500/15 text-purple-400 border-purple-500/30',
};

export default function SourceBadges({ badges }) {
  if (!badges?.length) return null;

  const grouped = {};
  for (const b of badges) {
    const key = `${b.source_type}:${b.doc_ref}`;
    if (!grouped[key]) grouped[key] = b;
  }

  return (
    <div className="mt-3 pt-2 border-t border-slate-700/50">
      <div className="text-xs text-slate-500 mb-1.5">Sources:</div>
      <div className="flex flex-wrap gap-1.5">
        {Object.values(grouped).map((b, i) => (
          <span
            key={i}
            className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full border ${
              TYPE_STYLES[b.source_type] || TYPE_STYLES.disclosure
            }`}
            title={`${b.source_type} | ${b.doc_ref}${b.date ? ` | ${b.date}` : ''}${b.broker_name ? ` | ${b.broker_name}` : ''}`}
          >
            <span className="font-medium capitalize">{b.source_type.replace('_', ' ')}</span>
            <span className="text-slate-500">|</span>
            <span className="truncate max-w-[200px]">{b.doc_ref}</span>
            {b.broker_name && <span className="text-slate-500">{b.broker_name}</span>}
          </span>
        ))}
      </div>
    </div>
  );
}
