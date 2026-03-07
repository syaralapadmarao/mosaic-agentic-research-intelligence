import { useState, useEffect, useRef } from 'react';
import { getPipelineTrace } from '../api';

const STATUS_ICON = {
  ok: { symbol: '\u2713', color: 'var(--green)', bg: 'var(--green-dim)' },
  flag: { symbol: '!', color: 'var(--amber)', bg: 'var(--amber-dim)' },
  warn: { symbol: '~', color: 'var(--amber)', bg: 'var(--amber-dim)' },
  error: { symbol: '\u2717', color: 'var(--red)', bg: 'var(--red-dim)' },
  skip: { symbol: '\u2014', color: 'var(--text-muted)', bg: 'var(--bg-tertiary)' },
};

function StepIcon({ status }) {
  const cfg = STATUS_ICON[status] || STATUS_ICON.ok;
  return (
    <span
      className="inline-flex items-center justify-center rounded-full text-xs font-bold shrink-0"
      style={{
        width: 22, height: 22,
        background: cfg.bg, color: cfg.color,
        border: `1px solid ${cfg.color}33`,
        fontSize: 11, lineHeight: 1,
      }}
    >
      {cfg.symbol}
    </span>
  );
}

function MetricDetailTable({ detail }) {
  if (!detail || !Array.isArray(detail) || detail.length === 0) return null;
  return (
    <table className="w-full text-xs mt-2" style={{ borderSpacing: 0 }}>
      <thead>
        <tr style={{ borderBottom: '1px solid var(--border)' }}>
          <th className="text-left py-1 px-2 font-semibold" style={{ color: 'var(--text-secondary)' }}>Metric</th>
          <th className="text-center py-1 px-2 font-semibold" style={{ color: 'var(--text-secondary)' }}>Found</th>
          <th className="text-right py-1 px-2 font-semibold" style={{ color: 'var(--text-secondary)' }}>Value</th>
          <th className="text-left py-1 px-2 font-semibold" style={{ color: 'var(--text-secondary)' }}>Raw</th>
          <th className="text-center py-1 px-2 font-semibold" style={{ color: 'var(--text-secondary)' }}>Page</th>
          <th className="text-left py-1 px-2 font-semibold" style={{ color: 'var(--text-secondary)' }}>Note</th>
        </tr>
      </thead>
      <tbody>
        {detail.map((m, i) => (
          <tr key={i} style={{
            background: i % 2 === 0 ? 'var(--bg-row-even)' : 'var(--bg-row-odd)',
            borderBottom: '1px solid var(--border-subtle)',
          }}>
            <td className="py-1 px-2 font-medium" style={{ color: 'var(--text-primary)' }}>{m.metric}</td>
            <td className="py-1 px-2 text-center">
              <span style={{ color: m.found ? 'var(--green)' : 'var(--red)' }}>
                {m.found ? '\u2713' : '\u2717'}
              </span>
            </td>
            <td className="py-1 px-2 text-right" style={{
              fontVariantNumeric: 'tabular-nums',
              color: m.value != null ? 'var(--text-primary)' : 'var(--text-muted)',
            }}>
              {m.value != null ? m.value.toLocaleString() : '\u2014'}
            </td>
            <td className="py-1 px-2" style={{ color: 'var(--text-secondary)' }}>
              {m.raw_value || '\u2014'}
            </td>
            <td className="py-1 px-2 text-center" style={{ color: 'var(--text-muted)' }}>
              {m.page ?? '\u2014'}
            </td>
            <td className="py-1 px-2" style={{ color: 'var(--text-muted)', maxWidth: 200 }}>
              <span className="truncate block">{m.note || ''}</span>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function ValidationDetailTable({ detail }) {
  if (!detail || !Array.isArray(detail) || detail.length === 0) return null;
  return (
    <table className="w-full text-xs mt-2" style={{ borderSpacing: 0 }}>
      <thead>
        <tr style={{ borderBottom: '1px solid var(--border)' }}>
          <th className="text-left py-1 px-2 font-semibold" style={{ color: 'var(--text-secondary)' }}>Metric</th>
          <th className="text-center py-1 px-2 font-semibold" style={{ color: 'var(--text-secondary)' }}>Status</th>
          <th className="text-left py-1 px-2 font-semibold" style={{ color: 'var(--text-secondary)' }}>Issue</th>
        </tr>
      </thead>
      <tbody>
        {detail.map((r, i) => (
          <tr key={i} style={{
            background: i % 2 === 0 ? 'var(--bg-row-even)' : 'var(--bg-row-odd)',
            borderBottom: '1px solid var(--border-subtle)',
          }}>
            <td className="py-1 px-2 font-medium" style={{ color: 'var(--text-primary)' }}>{r.metric}</td>
            <td className="py-1 px-2 text-center">
              <span className="inline-block px-1.5 py-0.5 rounded text-[10px] font-semibold" style={{
                background: r.status === 'pass' ? 'var(--green-dim)' : 'var(--amber-dim)',
                color: r.status === 'pass' ? 'var(--green)' : 'var(--amber)',
              }}>
                {r.status}
              </span>
            </td>
            <td className="py-1 px-2" style={{ color: r.issue ? 'var(--amber)' : 'var(--text-muted)' }}>
              {r.issue || '\u2014'}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function GuidanceDetailTable({ detail }) {
  if (!detail || !Array.isArray(detail) || detail.length === 0) return null;
  return (
    <table className="w-full text-xs mt-2" style={{ borderSpacing: 0 }}>
      <thead>
        <tr style={{ borderBottom: '1px solid var(--border)' }}>
          <th className="text-left py-1 px-2 font-semibold" style={{ color: 'var(--text-secondary)' }}>Topic</th>
          <th className="text-left py-1 px-2 font-semibold" style={{ color: 'var(--text-secondary)' }}>Statement</th>
          <th className="text-center py-1 px-2 font-semibold" style={{ color: 'var(--text-secondary)' }}>Sentiment</th>
          <th className="text-left py-1 px-2 font-semibold" style={{ color: 'var(--text-secondary)' }}>Speaker</th>
          <th className="text-center py-1 px-2 font-semibold" style={{ color: 'var(--text-secondary)' }}>Page</th>
        </tr>
      </thead>
      <tbody>
        {detail.map((item, i) => (
          <tr key={i} style={{
            background: i % 2 === 0 ? 'var(--bg-row-even)' : 'var(--bg-row-odd)',
            borderBottom: '1px solid var(--border-subtle)',
          }}>
            <td className="py-1 px-2 font-medium" style={{ color: 'var(--accent)' }}>{item.topic}</td>
            <td className="py-1.5 px-2" style={{ color: 'var(--text-primary)', maxWidth: 340 }}>
              <span className="line-clamp-2">{item.statement}</span>
            </td>
            <td className="py-1 px-2 text-center">
              <span className="inline-block px-1.5 py-0.5 rounded text-[10px] font-semibold" style={{
                background: item.sentiment?.includes('bullish') ? 'var(--green-dim)' :
                  item.sentiment?.includes('cautious') ? 'var(--amber-dim)' : 'var(--bg-tertiary)',
                color: item.sentiment?.includes('bullish') ? 'var(--green)' :
                  item.sentiment?.includes('cautious') ? 'var(--amber)' : 'var(--text-muted)',
              }}>
                {item.sentiment}
              </span>
            </td>
            <td className="py-1 px-2" style={{ color: 'var(--text-secondary)' }}>{item.speaker || '\u2014'}</td>
            <td className="py-1 px-2 text-center" style={{ color: 'var(--text-muted)' }}>{item.page ?? '\u2014'}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function DeltaDetailTable({ detail }) {
  if (!detail || !Array.isArray(detail) || detail.length === 0) return null;
  const TYPE_COLORS = {
    new: { bg: 'var(--accent-dim)', color: 'var(--accent)' },
    upgraded: { bg: 'var(--green-dim)', color: 'var(--green)' },
    downgraded: { bg: 'var(--red-dim)', color: 'var(--red)' },
    reiterated: { bg: 'var(--bg-tertiary)', color: 'var(--text-muted)' },
    removed: { bg: 'var(--red-dim)', color: 'var(--red)' },
  };
  return (
    <table className="w-full text-xs mt-2" style={{ borderSpacing: 0 }}>
      <thead>
        <tr style={{ borderBottom: '1px solid var(--border)' }}>
          <th className="text-left py-1 px-2 font-semibold" style={{ color: 'var(--text-secondary)' }}>Topic</th>
          <th className="text-center py-1 px-2 font-semibold" style={{ color: 'var(--text-secondary)' }}>Change</th>
          <th className="text-left py-1 px-2 font-semibold" style={{ color: 'var(--text-secondary)' }}>Summary</th>
        </tr>
      </thead>
      <tbody>
        {detail.map((d, i) => {
          const tc = TYPE_COLORS[d.change_type] || TYPE_COLORS.reiterated;
          return (
            <tr key={i} style={{
              background: i % 2 === 0 ? 'var(--bg-row-even)' : 'var(--bg-row-odd)',
              borderBottom: '1px solid var(--border-subtle)',
            }}>
              <td className="py-1 px-2 font-medium" style={{ color: 'var(--accent)' }}>{d.topic}</td>
              <td className="py-1 px-2 text-center">
                <span className="inline-block px-1.5 py-0.5 rounded text-[10px] font-semibold"
                  style={{ background: tc.bg, color: tc.color }}>
                  {d.change_type}
                </span>
              </td>
              <td className="py-1.5 px-2" style={{ color: 'var(--text-primary)', maxWidth: 400 }}>
                <span className="line-clamp-2">{d.summary}</span>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function StepDetail({ step }) {
  const node = step.node;
  if (node === 'extract_metrics' || node === 'calculate_metrics') {
    return <MetricDetailTable detail={step.detail} />;
  }
  if (node === 'validate_metrics') {
    return <ValidationDetailTable detail={step.detail} />;
  }
  if (node === 'extract_guidance') {
    return <GuidanceDetailTable detail={step.detail} />;
  }
  if (node === 'detect_deltas') {
    return <DeltaDetailTable detail={step.detail} />;
  }
  if (node === 'classify' && step.detail) {
    const d = step.detail;
    return (
      <div className="mt-2 text-xs grid grid-cols-2 gap-x-6 gap-y-1 px-1" style={{ color: 'var(--text-secondary)' }}>
        <div><span style={{ color: 'var(--text-muted)' }}>Type:</span> {d.doc_type}</div>
        <div><span style={{ color: 'var(--text-muted)' }}>Company:</span> {d.company}</div>
        <div><span style={{ color: 'var(--text-muted)' }}>Ticker:</span> {d.ticker || '\u2014'}</div>
        <div><span style={{ color: 'var(--text-muted)' }}>Period:</span> {d.period}</div>
        <div><span style={{ color: 'var(--text-muted)' }}>Date:</span> {d.doc_date || '\u2014'}</div>
        <div><span style={{ color: 'var(--text-muted)' }}>Confidence:</span> {(d.confidence * 100).toFixed(0)}%</div>
        <div className="col-span-2"><span style={{ color: 'var(--text-muted)' }}>Summary:</span> {d.summary}</div>
      </div>
    );
  }
  return null;
}

function StepRow({ step }) {
  const [expanded, setExpanded] = useState(false);
  const hasDetail = step.detail && (Array.isArray(step.detail) ? step.detail.length > 0 : true);

  return (
    <div>
      <button
        onClick={() => hasDetail && setExpanded(!expanded)}
        className="w-full flex items-center gap-3 py-2 px-3 transition-colors"
        style={{
          cursor: hasDetail ? 'pointer' : 'default',
          background: 'transparent',
          border: 'none',
          textAlign: 'left',
        }}
      >
        <StepIcon status={step.status} />
        <span className="text-xs font-semibold shrink-0" style={{
          color: 'var(--text-secondary)', width: 180,
        }}>
          {step.label}
        </span>
        <span className="text-xs flex-1 truncate" style={{ color: 'var(--text-primary)' }}>
          {step.summary}
        </span>
        {hasDetail && (
          <span className="text-[10px] shrink-0" style={{ color: 'var(--text-muted)' }}>
            {expanded ? '\u25B2' : '\u25BC'}
          </span>
        )}
      </button>
      {expanded && hasDetail && (
        <div className="pb-2 px-3 ml-8" style={{
          borderLeft: '2px solid var(--border)',
          marginLeft: 11,
        }}>
          <StepDetail step={step} />
        </div>
      )}
    </div>
  );
}

function FileCard({ trace, index }) {
  const [open, setOpen] = useState(true);
  const routeLabel = trace.steps?.find(s => s.node === 'classify')?.detail?.route;
  const hasError = trace.steps?.some(s => s.status === 'error');
  const hasFlag = trace.steps?.some(s => s.status === 'flag');

  return (
    <div className="rounded-lg overflow-hidden" style={{
      background: 'var(--bg-secondary)',
      border: `1px solid ${hasError ? 'var(--red)' : hasFlag ? 'var(--amber)' : 'var(--border)'}`,
    }}>
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-3 px-4 py-3 transition-colors"
        style={{
          background: 'var(--bg-tertiary)',
          border: 'none',
          cursor: 'pointer',
          textAlign: 'left',
        }}
      >
        <span className="text-xs font-bold shrink-0" style={{ color: 'var(--text-muted)' }}>
          [{index + 1}]
        </span>
        <span className="text-sm font-semibold flex-1" style={{ color: 'var(--text-primary)' }}>
          {trace.file_name}
        </span>
        {trace.quarter && (
          <span className="text-[10px] px-2 py-0.5 rounded font-semibold" style={{
            background: 'var(--accent-dim)', color: 'var(--accent)',
          }}>
            {trace.quarter}
          </span>
        )}
        {routeLabel && (
          <span className="text-[10px] px-2 py-0.5 rounded font-semibold uppercase" style={{
            background: routeLabel === 'presentation' ? 'var(--green-dim)' : 'var(--amber-dim)',
            color: routeLabel === 'presentation' ? 'var(--green)' : 'var(--amber)',
          }}>
            {routeLabel === 'presentation' ? 'Metrics' : 'Guidance'}
          </span>
        )}
        <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
          {open ? '\u25B2' : '\u25BC'}
        </span>
      </button>
      {open && (
        <div className="divide-y" style={{ borderColor: 'var(--border-subtle)' }}>
          {trace.steps.map((step, j) => (
            <StepRow key={j} step={step} />
          ))}
        </div>
      )}
    </div>
  );
}

export default function PipelineTrace({ company }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const pollRef = useRef(null);

  const load = async () => {
    if (!company) return;
    try {
      setLoading(true);
      const resp = await getPipelineTrace(company);
      setData(resp);
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [company]);

  useEffect(() => {
    if (!company) return;
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const resp = await getPipelineTrace(company);
        setData(resp);
        if (resp.status === 'complete' || resp.status === 'error' || resp.status === 'idle') {
          clearInterval(pollRef.current);
          pollRef.current = null;
        }
      } catch { /* ignore */ }
    }, 3000);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [company]);

  if (!company) {
    return (
      <div className="flex items-center justify-center h-64">
        <p className="text-sm" style={{ color: 'var(--text-muted)' }}>Select a company to view pipeline traces</p>
      </div>
    );
  }

  if (loading && !data) {
    return (
      <div className="flex items-center justify-center h-64">
        <span className="animate-spin w-5 h-5 border-2 border-t-transparent rounded-full"
          style={{ borderColor: 'var(--accent)', borderTopColor: 'transparent' }} />
      </div>
    );
  }

  const traces = data?.traces || [];

  if (traces.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-3">
        <p className="text-sm" style={{ color: 'var(--text-muted)' }}>
          No pipeline traces yet for <span className="capitalize font-medium" style={{ color: 'var(--text-secondary)' }}>{company}</span>
        </p>
        <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
          Run the pipeline to see step-by-step processing details
        </p>
      </div>
    );
  }

  const presCount = traces.filter(t => t.steps?.some(s => s.detail?.route === 'presentation')).length;
  const transCount = traces.filter(t => t.steps?.some(s => s.detail?.route === 'transcript')).length;
  const errorCount = traces.filter(t => t.steps?.some(s => s.status === 'error')).length;

  return (
    <div className="p-4 space-y-3">
      <div className="flex items-center gap-4 pb-3 mb-1" style={{ borderBottom: '1px solid var(--border)' }}>
        <h3 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
          Pipeline Trace
        </h3>
        <div className="flex items-center gap-3 text-xs" style={{ color: 'var(--text-muted)' }}>
          <span>{traces.length} files</span>
          <span style={{ color: 'var(--green)' }}>{presCount} presentations</span>
          <span style={{ color: 'var(--amber)' }}>{transCount} transcripts</span>
          {errorCount > 0 && <span style={{ color: 'var(--red)' }}>{errorCount} errors</span>}
        </div>
        {data?.status === 'running' && (
          <span className="flex items-center gap-1.5 text-[10px] font-semibold ml-auto" style={{ color: 'var(--accent)' }}>
            <span className="animate-spin w-3 h-3 border-2 border-t-transparent rounded-full"
              style={{ borderColor: 'var(--accent)', borderTopColor: 'transparent' }} />
            Processing...
          </span>
        )}
      </div>
      {traces.map((trace, i) => (
        <FileCard key={i} trace={trace} index={i} />
      ))}
    </div>
  );
}
