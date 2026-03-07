import { useState, useEffect } from 'react';
import { fetchConsensus, fetchDivergences } from '../api';
import DivergenceAlert from './DivergenceAlert';

export default function ConsensusView({ company }) {
  const [consensus, setConsensus] = useState(null);
  const [divergences, setDivergences] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!company) return;
    setLoading(true);
    Promise.all([
      fetchConsensus(company),
      fetchDivergences(company),
    ]).then(([c, d]) => {
      setConsensus(c.consensus || {});
      setDivergences(d.divergences || []);
    }).catch(() => {
      setConsensus({});
      setDivergences([]);
    }).finally(() => setLoading(false));
  }, [company]);

  if (loading) return <div className="text-slate-500 text-sm p-4">Loading consensus data...</div>;

  const metrics = Object.keys(consensus || {});

  return (
    <div className="space-y-6">
      {/* Divergence alerts */}
      {divergences.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-slate-300 mb-3">Active Divergences</h3>
          {divergences.map((d, i) => (
            <DivergenceAlert key={i} divergence={d} />
          ))}
        </div>
      )}

      {/* Consensus estimates table */}
      {metrics.length > 0 ? (
        <div>
          <h3 className="text-sm font-semibold text-slate-300 mb-3">Consensus Estimates</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-700">
                  <th className="text-left py-2 px-3 text-slate-400 font-medium">Metric</th>
                  <th className="text-left py-2 px-3 text-slate-400 font-medium">Period</th>
                  <th className="text-right py-2 px-3 text-slate-400 font-medium">Mean</th>
                  <th className="text-right py-2 px-3 text-slate-400 font-medium">High</th>
                  <th className="text-right py-2 px-3 text-slate-400 font-medium">Low</th>
                  <th className="text-right py-2 px-3 text-slate-400 font-medium"># Analysts</th>
                </tr>
              </thead>
              <tbody>
                {metrics.map(metric =>
                  Object.entries(consensus[metric]).map(([period, data], j) => (
                    <tr key={`${metric}-${period}`} className="border-b border-slate-800 hover:bg-slate-800/30">
                      {j === 0 && (
                        <td className="py-2 px-3 text-slate-200 font-medium" rowSpan={Object.keys(consensus[metric]).length}>
                          {metric}
                        </td>
                      )}
                      <td className="py-2 px-3 text-slate-300">{period}</td>
                      <td className="py-2 px-3 text-right font-mono text-slate-200">
                        {data.mean != null ? data.mean.toLocaleString(undefined, { maximumFractionDigits: 1 }) : '-'}
                      </td>
                      <td className="py-2 px-3 text-right font-mono text-green-400">
                        {data.high != null ? data.high.toLocaleString(undefined, { maximumFractionDigits: 1 }) : '-'}
                      </td>
                      <td className="py-2 px-3 text-right font-mono text-red-400">
                        {data.low != null ? data.low.toLocaleString(undefined, { maximumFractionDigits: 1 }) : '-'}
                      </td>
                      <td className="py-2 px-3 text-right text-slate-400">{data.n_analysts || 0}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <div className="text-slate-500 text-sm text-center py-8">
          No consensus data available. Ingest sell-side reports first.
        </div>
      )}
    </div>
  );
}
